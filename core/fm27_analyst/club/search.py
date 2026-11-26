"""Поиск игроков по запросу на естественном языке (раздел 17.1).

Запрос превращается в фильтры. Помощник всегда показывает, как он понял
запрос, чтобы пользователь мог поправить трактовку.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

from pydantic import BaseModel, Field, ValidationError

from .. import reference as ref
from .db import ClubDNA
from .fit import FitResult, best_fit
from .importer import ScoutPlayer
from .values import POSITION_RU

log = logging.getLogger(__name__)


class Filters(BaseModel):
    positions: list[str] = Field(default_factory=list)
    age_min: int | None = None
    age_max: int | None = None
    max_value: float | None = None
    max_wage_week: float | None = None
    min_attrs: dict[str, float] = Field(default_factory=dict)
    free_agent: bool = False
    expiring_contract: bool = False
    loan_candidate: bool = False
    min_potential_stars: float | None = None
    undervalued: bool = False
    text_in_division: str | None = None
    limit: int = 20


POS_PATTERNS: list[tuple[str, list[str]]] = [
    (r"центральн\w*\s+защитник|центрбек|\bцз\b|центр\w* обороны", ["D_C"]),
    (r"лев\w*\s+(?:крайн\w*\s+)?защитник|лев\w*\s+бек|лев\w*\s+латерал", ["D_L", "WB_L"]),
    (r"прав\w*\s+(?:крайн\w*\s+)?защитник|прав\w*\s+бек|прав\w*\s+латерал", ["D_R", "WB_R"]),
    (r"крайн\w*\s+защитник|латерал|фулбек", ["D_L", "D_R", "WB_L", "WB_R"]),
    (r"лев\w*\s+(?:вингер|крайн\w*|флангов\w*)", ["AM_L", "M_L"]),
    (r"прав\w*\s+(?:вингер|крайн\w*|флангов\w*)", ["AM_R", "M_R"]),
    (r"вингер|флангов\w*\s+(?:полузащит|атакующ)|крайн\w*\s+полузащит", ["AM_L", "AM_R", "M_L", "M_R"]),
    (r"опорн\w*|\bоп\b|шестёрк|шестерк", ["DM"]),
    (r"центральн\w*\s+полузащит|\bцп\b|восьмёрк|восьмерк|бокс.ту.бокс", ["M_C"]),
    (r"атакующ\w*\s+полузащит|плеймейкер|десятк|\bап\b", ["AM_C"]),
    (r"нападающ|форвард|страйкер|девятк|бомбардир|центрфорвард", ["ST"]),
    (r"вратар|голкипер", ["GK"]),
]

ATTR_WORDS: list[tuple[str, str]] = [
    (r"дриблинг|обводк", "dribbling"), (r"ускорени|стартов", "acceleration"), (r"скорост|быстр", "pace"),
    (r"видени|видение поля", "vision"), (r"\bпас\w*|передач", "passing"), (r"отбор", "tackling"),
    (r"игр\w* головой|верхов|в воздухе", "heading"), (r"завершени|реализац|забива", "finishing"),
    (r"техник|техничн", "technique"), (r"выносливост", "stamina"), (r"работоспособн|трудолюб", "work_rate"),
    (r"\bсил\w*|мощн|физическ", "strength"), (r"навес", "crossing"), (r"опек", "marking"),
    (r"выбор\w* позиции|позиционн|позиционир", "positioning"), (r"предвиден|чтени\w* игры", "anticipation"),
    (r"хладнокров", "composure"), (r"реакци", "reflexes"), (r"лидер", "leadership"), (r"креатив|импровиз", "flair"),
    (r"решени", "decisions"), (r"первое касание|обработк", "first_touch"), (r"дальн\w* удар", "long_shots"),
]

_NUM = r"(\d+(?:[.,]\d+)?)"
_MULT = {"млрд": 1e9, "млн": 1e6, "миллион": 1e6, "м": 1e6, "m": 1e6, "тыс": 1e3, "k": 1e3, "к": 1e3}


def find_all_positions(text: str) -> list[list[str]]:
    """Все позиции, упомянутые в тексте, по порядку (для «усилить ЦЗ и опорную зону»)."""
    q = " " + text.lower().replace("ё", "е") + " "
    found: list[tuple[int, list[str]]] = []
    taken: list[tuple[int, int]] = []
    extra = [(r"центральн\w* защит\w*|центр\w* оборон\w*|центральн\w* зону обороны", ["D_C"]),
             (r"опорн\w* зон\w*|опорн\w* полузащит\w*|центр\w* поля", ["DM"]),
             (r"фланг\w* атак\w*|вингер\w*", ["AM_L", "AM_R", "M_L", "M_R"])]
    for pat, codes in POS_PATTERNS + extra:
        for m in re.finditer(pat, q):
            if any(not (m.end() <= a or m.start() >= b) for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), codes))
    out: list[list[str]] = []
    for _, codes in sorted(found, key=lambda x: x[0]):
        if codes not in out:
            out.append(codes)
    return out


def _money(num: str, unit: str | None) -> float:
    v = float(num.replace(",", "."))
    if unit:
        for k, m in _MULT.items():
            if unit.lower().startswith(k):
                return v * m
    return v * 1e6 if v < 1000 else v  # «бюджет 15» — миллионы


def parse_query(text: str) -> tuple[Filters, list[str]]:
    """Разбор запроса правилами. Возвращает фильтры и строки «как понял»."""
    q = " " + text.lower().replace("ё", "е") + " "
    f = Filters()
    understood: list[str] = []
    for pat, codes in POS_PATTERNS:
        if re.search(pat, q):
            f.positions = codes
            understood.append("Позиция: " + ", ".join(POSITION_RU[c] for c in codes))
            break
    m = re.search(r"(?:до|младше|моложе|не старше|не более)\s+(\d{2})\s*(?:лет|год)", q) or re.search(r"\bu-?(\d{2})\b", q)
    if m:
        f.age_max = int(m.group(1))
        understood.append(f"Возраст: до {f.age_max} включительно")
    m = re.search(r"(?:старше|от)\s+(\d{2})\s*(?:лет|год)", q)
    if m:
        f.age_min = int(m.group(1)) + (1 if "старше" in m.group(0) else 0)
        understood.append(f"Возраст: от {f.age_min}")
    if f.age_max is None and re.search(r"молод|юн\w|перспективн", q):
        f.age_max = 23
        understood.append("«Молодой» — трактую как до 23 лет")
    if f.age_min is None and re.search(r"опытн|ветеран", q):
        f.age_min = 28
        understood.append("«Опытный» — трактую как от 28 лет")
    m = re.search(rf"(?:бюджет\w*|стоимост\w*|цен\w*|за)\s*(?:до|не более|в пределах)?\s*€?\s*{_NUM}\s*(млрд|млн|миллион\w*|тыс\w*|m|k|м)?", q)
    if m:
        f.max_value = _money(m.group(1), m.group(2))
        understood.append(f"Стоимость: до {f.max_value / 1e6:g} млн")
    m = re.search(rf"зарплат\w*\s*(?:до|не более)?\s*€?\s*{_NUM}\s*(тыс\w*|k|к|млн)?", q)
    if m:
        v = float(m.group(1).replace(",", "."))
        unit = m.group(2) or ""
        v *= 1e3 if unit.startswith(("тыс", "k", "к")) else (1e6 if unit.startswith("млн") else 1)
        f.max_wage_week = v
        understood.append(f"Зарплата: до {v:,.0f} в неделю".replace(",", " "))
    level = 15 if re.search(r"отличн|элитн|высок\w* уровн|лучш", q) else 13
    for pat, attr in ATTR_WORDS:
        if re.search(pat, q):
            f.min_attrs[attr] = level
    if f.min_attrs:
        understood.append("Атрибуты от " + str(level) + ": " + ", ".join(ref.attr_ru(a) for a in f.min_attrs))
    if re.search(r"свободн\w*\s+агент|бесплатн|без клуба", q):
        f.free_agent = True
        understood.append("Только свободные агенты")
    if re.search(r"истека\w*|заканчива\w*\s+контракт|последн\w* год\w* контракт", q):
        f.expiring_contract = True
        understood.append("Контракт истекает в ближайшие 12 месяцев (по дате сейва)")
    if re.search(r"аренд", q):
        f.loan_candidate = True
        if f.age_max is None:
            f.age_max = 23
        understood.append("Аренда: показываю молодых игроков; доступность для аренды в выгрузке не видна")
    if "потенциал" in q:
        f.min_potential_stars = 4.0 if re.search(r"апл|топ|элит|высок|сборн|лиг\w* чемпион", q) else 3.5
        understood.append(f"Потенциал: от {f.min_potential_stars}★"
                          + (" — уровень «для АПЛ/топ-лиги» трактую так; поправьте при необходимости"
                             if f.min_potential_stars >= 4 else ""))
    if re.search(r"недооцен|дешев\w* для своего уровня|выгодн", q):
        f.undervalued = True
        understood.append("Недооценённые: сортировка по соответствию на единицу стоимости")
    m = re.search(r"\bиз\s+(?:чемпионата\s+|лиги\s+)?([a-zа-я\-]{3,})", q)
    if m and m.group(1) not in {"них", "клуба", "команды"}:
        f.text_in_division = m.group(1)
        understood.append(f"Лига/страна содержит «{m.group(1)}»")
    if not understood:
        understood.append("Фильтров не распознано — показываю лучших по соответствию тактике")
    return f, understood


LLM_SCHEMA = (
    "Преобразуй запрос тренера в JSON-фильтры поиска игроков FM27. Только поля: positions (коды из "
    + json.dumps(list(POSITION_RU), ensure_ascii=False)
    + "), age_min, age_max, max_value (в единицах валюты), max_wage_week, min_attrs (ключи: "
    + ", ".join(ref.load()["attribute_ru"])
    + "; значения 1–20), free_agent, expiring_contract, loan_candidate, min_potential_stars (0–5), undervalued, "
    "text_in_division. И поле understood — список строк по-русски, как ты понял запрос. Ответь одним JSON."
)


def parse_query_llm(text: str, provider) -> tuple[Filters, list[str]] | None:
    try:
        raw = provider.complete(LLM_SCHEMA, text, "claude-haiku-5-5", 600)
        d = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        understood = [str(x) for x in d.pop("understood", [])]
        f = Filters.model_validate(d)
        f.positions = [p for p in f.positions if p in POSITION_RU]
        f.min_attrs = {k: v for k, v in f.min_attrs.items() if k in ref.load()["attribute_ru"] and 1 <= v <= 20}
        return f, understood or ["Разобрано AI-аналитиком"]
    except (AttributeError, json.JSONDecodeError, ValidationError, Exception) as e:  # noqa: BLE001
        log.warning("LLM-разбор запроса не удался: %s", e)
        return None


class SearchHit(BaseModel):
    player: ScoutPlayer
    fit: FitResult | None
    reasons: list[str]


def _game_date(dna: ClubDNA) -> date:
    return dna.game_date or date.today()


def run_search(players: list[ScoutPlayer], f: Filters, dna: ClubDNA) -> list[SearchHit]:
    gd = _game_date(dna)
    hits: list[SearchHit] = []
    for p in players:
        if f.positions and not (set(p.positions) & set(f.positions)):
            continue
        if f.age_max is not None and (p.age is None or p.age > f.age_max):
            continue
        if f.age_min is not None and (p.age is None or p.age < f.age_min):
            continue
        if f.max_value is not None and p.value_low is not None and p.value_low > f.max_value:
            continue
        if f.max_wage_week is not None and p.wage_week is not None and p.wage_week > f.max_wage_week:
            continue
        if f.free_agent and not p.is_free_agent():
            continue
        if f.expiring_contract and not (p.contract_until and p.contract_until <= gd + timedelta(days=365)):
            continue
        if f.min_potential_stars is not None and not (p.potential_stars and p.potential_stars[1] >= f.min_potential_stars):
            continue
        if f.text_in_division:
            hay = f"{p.division or ''} {p.nationality or ''} {p.club or ''}".lower()
            if f.text_in_division not in hay:
                continue
        ok, reasons = True, []
        for a, need in f.min_attrs.items():
            v = p.attr(a)
            if v is None or v < need:
                ok = False
                break
            reasons.append(f"{ref.attr_ru(a)} {p.attributes[a][0]}" + ("" if p.attributes[a][0] == p.attributes[a][1] else f"–{p.attributes[a][1]}"))
        if not ok:
            continue
        pos = next((x for x in f.positions if x in p.positions), None)
        fit = best_fit(p, dna, pos)
        if p.value_low is not None and f.max_value is not None and p.value_high and p.value_high > f.max_value:
            reasons.append("Верхняя оценка стоимости выше бюджета — возможен торг")
        hits.append(SearchHit(player=p, fit=fit, reasons=reasons))

    def key(h: SearchHit):
        s = h.fit.score if h.fit and h.fit.score is not None else -1
        if f.undervalued and h.player.value_mid:
            return -(max(s, 0) / max(h.player.value_mid / 1e6, 0.1))
        return -s

    hits.sort(key=key)
    return hits[: f.limit]
