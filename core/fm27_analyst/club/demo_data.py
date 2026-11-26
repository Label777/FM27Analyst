"""Демо-выгрузки (вымышленные игроки) в формате FM24 Web Page / FM27 Exporter.

Нужны для тестов и чтобы попробовать скаутинг без игры. Генерация
детерминирована (seed), имена и клубы вымышленные.
"""

from __future__ import annotations

import random

ABBR = {
    "corners": "Cor", "crossing": "Cro", "dribbling": "Dri", "finishing": "Fin", "first_touch": "Fir",
    "free_kicks": "Fre", "heading": "Hea", "long_shots": "Lon", "long_throws": "L Th", "marking": "Mar",
    "passing": "Pas", "penalty_taking": "Pen", "tackling": "Tck", "technique": "Tec", "aggression": "Agg",
    "anticipation": "Ant", "bravery": "Bra", "composure": "Cmp", "concentration": "Cnt", "decisions": "Dec",
    "determination": "Det", "flair": "Fla", "leadership": "Ldr", "off_the_ball": "OtB", "positioning": "Pos",
    "teamwork": "Tea", "vision": "Vis", "work_rate": "Wor", "acceleration": "Acc", "agility": "Agi",
    "balance": "Bal", "jumping_reach": "Jum", "natural_fitness": "Nat", "pace": "Pac", "stamina": "Sta",
    "strength": "Str", "aerial_reach": "Aer", "command_of_area": "Cmd", "communication": "Com",
    "eccentricity": "Ecc", "handling": "Han", "kicking": "Kic", "one_on_ones": "1v1", "punching": "Pun",
    "reflexes": "Ref", "rushing_out": "TRO", "throwing": "Thr",
}
GK_ATTRS = {"aerial_reach", "command_of_area", "communication", "eccentricity", "handling", "kicking",
            "one_on_ones", "punching", "reflexes", "rushing_out", "throwing"}
FIRST = ["Артём", "Богдан", "Влад", "Денис", "Егор", "Игорь", "Кирилл", "Лука", "Марк", "Назар", "Олег", "Павел",
         "Роман", "Савва", "Тарас", "Устим", "Филипп", "Юрий", "Ярослав", "Матео", "Лиам", "Ноа", "Эмиль", "Оскар"]
LAST = ["Береговой", "Вишняк", "Гордиенко", "Дубовик", "Жуковский", "Зорич", "Калина", "Лозовой", "Мартыненко",
        "Нечай", "Орлик", "Петрук", "Ромашко", "Сирко", "Тимошук", "Устенко", "Федорчук", "Хоменко", "Цыбуля",
        "Чайка", "Шуляк", "Яремчук", "Андерсен", "Берг", "Карвальо", "Дюваль", "Эрикссон", "Фалько"]
CLUBS = ["ФК Северный", "Днепровские Волки", "Атлетик Порту-Нова", "Рапид Карпаты", "Олимпик Лаго",
         "Спортинг Бриз", "Динамо Степь", "Юнайтед Харбор"]
DIVS = ["Премьер-лига (вымышл.)", "Первая лига (вымышл.)", "Лига Иберия (вымышл.)"]
NATS = ["UKR", "POL", "POR", "ESP", "DEN", "SWE", "FRA", "BRA"]

ARCH = {
    "GK": ("GK", {"reflexes": 3, "one_on_ones": 2, "handling": 2, "aerial_reach": 2, "positioning": 2, "command_of_area": 2}),
    "D_C": ("D (C)", {"marking": 3, "tackling": 3, "heading": 3, "positioning": 3, "strength": 2, "jumping_reach": 2, "anticipation": 2, "passing": 0, "pace": 0}),
    "D_L": ("D/WB (L)", {"stamina": 3, "work_rate": 3, "crossing": 2, "acceleration": 2, "pace": 2, "tackling": 2, "marking": 1}),
    "D_R": ("D/WB (R)", {"stamina": 3, "work_rate": 3, "crossing": 2, "acceleration": 2, "pace": 2, "tackling": 2, "marking": 1}),
    "DM": ("DM, M (C)", {"positioning": 3, "tackling": 3, "anticipation": 2, "passing": 2, "decisions": 2, "teamwork": 2, "stamina": 1}),
    "M_C": ("M (C)", {"passing": 3, "stamina": 2, "work_rate": 2, "vision": 2, "decisions": 2, "first_touch": 2, "technique": 1}),
    "AM_C": ("AM (C)", {"vision": 3, "passing": 3, "technique": 3, "first_touch": 2, "flair": 2, "decisions": 2}),
    "AM_L": ("AM (L), M (L)", {"dribbling": 3, "acceleration": 3, "pace": 3, "crossing": 2, "technique": 2, "flair": 2, "agility": 2}),
    "AM_R": ("AM (R), M (R)", {"dribbling": 3, "acceleration": 3, "pace": 3, "crossing": 2, "technique": 2, "flair": 2, "agility": 2}),
    "ST": ("ST (C)", {"finishing": 3, "off_the_ball": 3, "anticipation": 2, "composure": 2, "acceleration": 1, "strength": 1, "heading": 1}),
}


def _player(rng: random.Random, pos: str, quality: float, age: int, scouted: bool, club: str | None) -> list[str]:
    label, prof = ARCH[pos]
    attrs = {}
    for a in ABBR:
        if (a in GK_ATTRS) != (pos == "GK") and a not in ("positioning", "kicking", "passing", "first_touch"):
            base = rng.uniform(1, 5) if a in GK_ATTRS else quality - 4 + rng.gauss(0, 1.5)
            attrs[a] = max(1, min(20, round(base)))
            continue
        base = quality + rng.gauss(0, 1.6) + prof.get(a, -1.2) * 1.1
        if age <= 20:
            base -= 1.0
        attrs[a] = max(1, min(20, round(base)))
    cells = {}
    for a, v in attrs.items():
        if scouted:
            cells[ABBR[a]] = str(v)
        else:
            lo, hi = max(1, v - rng.randint(1, 2)), min(20, v + rng.randint(1, 2))
            cells[ABBR[a]] = f"{lo}-{hi}"
    cur = max(0.5, min(5.0, round((quality - 6) / 2.2 * 2) / 2))
    pot = max(cur, min(5.0, cur + (round(rng.uniform(0.5, 2.0) * 2) / 2 if age <= 21 else rng.choice([0, 0, 0.5]))))
    value = max(0.15, (quality - 7) ** 2.1 * 0.18 * (1.4 if age <= 23 else (0.6 if age >= 30 else 1)) * rng.uniform(0.6, 1.6))
    wage = max(1.0, value * rng.uniform(2.5, 5.0))
    side = "R" if pos.endswith("_L") and rng.random() < 0.6 else ("L" if pos.endswith("_R") and rng.random() < 0.6 else None)
    strong, weak = "Very Strong", rng.choice(["Weak", "Reasonable", "Fairly Strong"])
    lf, rf = (strong, weak) if (side == "L" or (side is None and rng.random() < 0.3)) else (weak, strong)
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    return [
        str(rng.randint(10_000_000, 99_999_999)), name, label, str(age), club or "Free Agent", rng.choice(NATS),
        rng.choice(DIVS) if club else "-", f"€{value:.1f}M" if value >= 1 else f"€{value * 1000:.0f}K",
        f"€{wage:.1f}K p/w", f"30/6/{2027 + rng.randint(0, 4)}" if club else "-",
        f"{cur:g}" if scouted else f"{max(0.5, cur - 0.5):g}-{min(5, cur + 0.5):g}",
        f"{pot:g}" if scouted else f"{max(cur, pot - 0.5):g}-{min(5, pot + 0.5):g}",
        lf, rf,
    ] + [cells[ABBR[a]] for a in ABBR]


HEADER = ["UID", "Name", "Position", "Age", "Club", "Nat", "Division", "Transfer Value", "Wage", "Expires",
          "CA", "PA", "Left Foot", "Right Foot"] + list(ABBR.values())


def _html(rows: list[list[str]], title: str) -> str:
    th = "".join(f"<th>{h}</th>" for h in HEADER)
    trs = "\n".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<html><head><meta charset='utf-8'><title>{title}</title></head><body><table>\n<tr>{th}</tr>\n{trs}\n</table></body></html>"


def market_export(seed: int = 27, n: int = 90) -> str:
    rng = random.Random(seed)
    rows = []
    positions = list(ARCH)
    for i in range(n):
        pos = positions[i % len(positions)]
        age = rng.choice([17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 33])
        q = rng.uniform(8.5, 15.5)
        free = rng.random() < 0.06
        rows.append(_player(rng, pos, q, age, scouted=rng.random() < 0.6, club=None if free else rng.choice(CLUBS)))
    return _html(rows, "Player Search")


def squad_export(seed: int = 7) -> str:
    """Наш состав: 4-2-3-1, есть слабые места (левый ЦЗ, глубина на опорной зоне)."""
    rng = random.Random(seed)
    plan = [("GK", 12.5, 29), ("GK", 10, 24), ("D_C", 13, 27), ("D_C", 10.0, 31), ("D_C", 9.5, 22), ("D_L", 12, 25),
            ("D_L", 10, 19), ("D_R", 12.5, 26), ("DM", 13, 28), ("DM", 9.0, 33), ("M_C", 12, 24), ("M_C", 11, 20),
            ("AM_C", 13, 25), ("AM_L", 12.5, 23), ("AM_L", 10.5, 18), ("AM_R", 13, 26), ("AM_R", 10, 30),
            ("ST", 13.5, 28), ("ST", 11, 21)]
    rows = [_player(rng, pos, q, age, scouted=True, club="Наш клуб") for pos, q, age in plan]
    return _html(rows, "Squad")


def opponent_export(seed: int = 33) -> str:
    """Соперник (вымышленный): 4-3-3, медленный левый ЦЗ, быстрый правый вингер, высокий нападающий."""
    rng = random.Random(seed)
    plan = [("GK", 12, 30), ("D_L", 12, 27), ("D_C", 13, 29), ("D_C", 12.5, 31), ("D_R", 12, 24), ("DM", 13, 27),
            ("M_C", 12.5, 25), ("M_C", 12, 28), ("AM_L", 12.5, 23), ("AM_R", 14.5, 22), ("ST", 13.5, 29),
            ("GK", 9, 21), ("D_C", 10, 20), ("M_C", 10.5, 19), ("AM_R", 10, 24), ("ST", 11, 26)]
    rows = [_player(rng, pos, q, age, scouted=True, club="ФК Соперник (демо)") for pos, q, age in plan]
    idx = {h: i for i, h in enumerate(HEADER)}
    rows[3][idx["Pac"]], rows[3][idx["Acc"]] = "8", "9"  # медленный центральный защитник
    rows[9][idx["Pac"]], rows[9][idx["Acc"]], rows[9][idx["Dri"]] = "18", "17", "16"  # быстрый правый вингер
    rows[10][idx["Hea"]], rows[10][idx["Jum"]] = "17", "16"  # сильный в воздухе нападающий
    return _html(rows, "Opponent Squad")


def squad_export_later(seed: int = 7, months: int = 6) -> str:
    """Тот же состав через `months` месяцев: молодые выросли, один молодой застрял в развитии."""
    rows = []
    for r in _rows_of(squad_export(seed)):
        rows.append(list(r))
    grow = random.Random(seed * 101)
    attr_start = len(HEADER) - len(ABBR)
    young = [r for r in rows if int(r[3]) <= 21]
    stuck = young[-1] if young else None  # последний молодой — «застрял»
    for r in rows:
        age = int(r[3])
        if age <= 21 and r is not stuck:
            for i in range(attr_start, len(HEADER)):
                v = int(r[i])
                if grow.random() < 0.45:
                    r[i] = str(min(20, v + grow.choice([1, 1, 2])))
        elif age >= 31:
            for i in range(attr_start, len(HEADER)):
                if HEADER[i] in ("Pac", "Acc", "Sta", "Agi") and grow.random() < 0.6:
                    r[i] = str(max(1, int(r[i]) - 1))
        if months >= 12:
            r[3] = str(age + 1)
    return _html(rows, "Squad")


def _rows_of(html: str) -> list[list[str]]:
    from .importer import read_table

    return read_table(html, "x.html")[1:]
