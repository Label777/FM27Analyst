"""Импорт выгрузок списков игроков FM27 (CSV и HTML-таблица в формате FM24 Web Page)."""

from __future__ import annotations

import csv
import io
import json
import re
import time
from datetime import date
from functools import lru_cache
from html.parser import HTMLParser
from importlib import resources

from pydantic import BaseModel, Field

from .values import (
    attr_certainty,
    parse_attr,
    parse_date,
    parse_int,
    parse_money,
    parse_positions,
    parse_stars,
    weekly_wage,
)


class SourceInfo(BaseModel):
    file: str
    imported_at: float
    kind: str = "export"  # export | screenshot | manual | demo


class ScoutPlayer(BaseModel):
    """Игрок из выгрузки. Пустое поле = в выгрузке не было, не выдумываем."""

    id: int | None = None
    key: str
    uid: str | None = None
    name: str
    age: int | None = None
    positions: list[str] = Field(default_factory=list)
    position_raw: str | None = None
    club: str | None = None
    nationality: str | None = None
    division: str | None = None
    value_low: float | None = None
    value_high: float | None = None
    currency: str | None = None
    wage_week: float | None = None
    contract_until: date | None = None
    current_stars: tuple[float, float] | None = None
    potential_stars: tuple[float, float] | None = None
    foot_left: str | None = None
    foot_right: str | None = None
    personality: str | None = None
    on_loan_from: str | None = None
    attributes: dict[str, tuple[int, int]] = Field(default_factory=dict)
    status: dict[str, str] = Field(default_factory=dict)  # состояние: сост., готовность, настроение, форма, статистика — как в игре
    extra: dict[str, str] = Field(default_factory=dict)  # колонки, которые не распознаны
    scope: str = "market"  # own — наш состав, market — рынок/поиск
    source: SourceInfo

    def attr(self, key: str) -> float | None:
        r = self.attributes.get(key)
        return (r[0] + r[1]) / 2 if r else None

    @property
    def certainty(self) -> float:
        if not self.attributes:
            return 0.0
        return sum(attr_certainty(r) for r in self.attributes.values()) / len(self.attributes)

    @property
    def value_mid(self) -> float | None:
        if self.value_low is None:
            return None
        return (self.value_low + (self.value_high or self.value_low)) / 2

    def is_free_agent(self) -> bool:
        c = (self.club or "").strip().lower()
        return c in {"free agent", "unattached", "без клуба", "свободный агент", "-", ""} and self.club is not None


class ImportResult(BaseModel):
    players: list[ScoutPlayer]
    mapped: dict[str, str]  # заголовок -> поле
    unmapped: list[str]
    warnings: list[str]


def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", h.replace(" ", " ")).strip().lower()


@lru_cache(maxsize=1)
def column_map() -> tuple[dict[str, str], dict[str, dict]]:
    with resources.files("fm27_analyst.data").joinpath("export_columns.json").open(encoding="utf-8") as f:
        d = json.load(f)
    m: dict[str, str] = {}
    for field, names in d["fields"].items():
        for n in names:
            m[_norm(n)] = field
    for attr, names in d["attributes"].items():
        for n in names:
            m[_norm(n)] = f"attr:{attr}"
    for key, names in d.get("status", {}).items():
        if not key.startswith("_"):
            for n in names:
                m[_norm(n)] = f"stat:{key}"
    for n in d.get("ignore", []):
        m[_norm(n)] = "ignore"
    amb = {k: v for k, v in d["ambiguous"].items() if not k.startswith("_")}
    return m, amb


def attribute_groups() -> dict[str, list[str]]:
    with resources.files("fm27_analyst.data").joinpath("export_columns.json").open(encoding="utf-8") as f:
        return json.load(f)["attribute_groups"]


# --- чтение таблиц ---
class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(c for c in self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def read_table(text: str, filename: str = "") -> list[list[str]]:
    head = text.lstrip()[:500].lower()
    if filename.lower().endswith((".html", ".htm")) or head.startswith("<") or "<table" in head:
        p = _TableParser()
        p.feed(text)
        return p.rows
    sample = text[:4000]
    delim = ";" if sample.count(";") > sample.count(",") else ("\t" if sample.count("\t") > sample.count(",") else ",")
    return [row for row in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in row)]


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _looks_numeric(values: list[str]) -> bool:
    vals = [v for v in values if v.strip() and v.strip() not in {"-", "—"}]
    return bool(vals) and sum(parse_attr(v) is not None for v in vals) >= 0.8 * len(vals)


def import_table(text: str, filename: str, scope: str = "market", kind: str = "export") -> ImportResult:
    return import_rows(read_table(text, filename), filename, scope=scope, kind=kind)


def import_rows(rows: list[list[str]], filename: str, scope: str = "market", kind: str = "export") -> ImportResult:
    """Строки таблицы (первая — заголовки) → игроки. Общий путь для файлов и для моста из игры."""
    warnings: list[str] = []
    if len(rows) < 2:
        return ImportResult(players=[], mapped={}, unmapped=[], warnings=["В файле не найдена таблица с игроками"])
    # Строка заголовков — первая, где распознано хотя бы 2 известных поля
    cmap, amb = column_map()
    header_idx = 0
    for i, r in enumerate(rows[:5]):
        if sum(_norm(c) in cmap or _norm(c) in amb for c in r) >= 2:
            header_idx = i
            break
    header = rows[header_idx]
    body = [r for r in rows[header_idx + 1:] if len(r) >= len(header) // 2]
    mapping: dict[int, str] = {}
    for i, h in enumerate(header):
        key = _norm(h)
        if key in amb:
            col = [r[i] for r in body[:50] if i < len(r)]
            mapping[i] = f"attr:{amb[key]['numeric']}" if _looks_numeric(col) else amb[key]["text"]
        elif key in cmap:
            mapping[i] = cmap[key]
    if "name" not in mapping.values():
        warnings.append("Нет колонки с именем игрока — импорт невозможен. Проверьте вид (view) в игре.")
        return ImportResult(players=[], mapped={}, unmapped=header, warnings=warnings)
    now = time.time()
    src = SourceInfo(file=filename, imported_at=now, kind=kind)
    players: list[ScoutPlayer] = []
    bad_attr = 0
    for r in body:
        d: dict = {"attributes": {}, "extra": {}, "status": {}}
        for i, cell in enumerate(r):
            f = mapping.get(i)
            if f is None:
                if i < len(header) and header[i].strip() and cell.strip():
                    d["extra"][header[i].strip()] = cell.strip()
                continue
            if f == "ignore":
                continue
            if f.startswith("stat:"):
                if cell.strip() not in {"", "-", "—"}:
                    d["status"][f[5:]] = cell.strip()
                continue
            if f.startswith("attr:"):
                v = parse_attr(cell)
                if v:
                    d["attributes"][f[5:]] = v
                elif cell.strip() not in {"", "-", "—"}:
                    bad_attr += 1
            else:
                d[f] = cell.strip()
        name = d.get("name", "").strip()
        if not name:
            continue
        money = parse_money(d.get("value"))
        wage = parse_money(d.get("wage"))
        p = ScoutPlayer(
            key="",
            uid=d.get("uid") or None,
            name=name,
            age=parse_int(d.get("age")),
            positions=sorted(parse_positions(d.get("position"))),
            position_raw=d.get("position"),
            club=d.get("club"),
            nationality=d.get("nationality"),
            division=d.get("division"),
            value_low=money["low"] if money else None,
            value_high=money["high"] if money else None,
            currency=(money or wage or {}).get("currency"),
            wage_week=weekly_wage(wage),
            contract_until=parse_date(d.get("contract")),
            current_stars=parse_stars(d.get("current_stars")),
            potential_stars=parse_stars(d.get("potential_stars")),
            foot_left=d.get("foot_left"),
            foot_right=d.get("foot_right"),
            personality=d.get("personality"),
            on_loan_from=d.get("on_loan") or None,
            attributes=d["attributes"],
            extra=d["extra"],
            status=d["status"],
            scope=scope,
            source=src,
        )
        p.key = p.uid or f"{p.name}|{p.age or ''}|{p.nationality or ''}"
        players.append(p)
    unmapped = [h for i, h in enumerate(header) if i not in mapping and h.strip()]
    mapping = {i: f for i, f in mapping.items() if f != "ignore"}
    if unmapped:
        warnings.append(
            "Не распознаны колонки: " + ", ".join(unmapped[:12]) + (" …" if len(unmapped) > 12 else "")
            + ". Они сохранены как есть; пришлите выгрузку — добавлю их в сопоставление."
        )
    if bad_attr:
        warnings.append(f"{bad_attr} значений атрибутов не удалось разобрать — пропущены")
    if players and not any(p.attributes for p in players):
        warnings.append("В таблице нет атрибутов игроков — тактическое соответствие посчитать не получится. "
                        "В игре переключите вид таблицы на атрибуты (Ctrl+F8 из FM27 Exporter добавляет все 47 атрибутов "
                        "в свой вид) и заберите таблицу ещё раз.")
    return ImportResult(
        players=players,
        mapped={header[i]: f for i, f in mapping.items()},
        unmapped=unmapped,
        warnings=warnings,
    )


def today() -> date:
    return date.today()
