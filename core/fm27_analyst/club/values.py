"""Разбор значений из выгрузок FM: диапазоны атрибутов, деньги, звёзды, даты, позиции."""

from __future__ import annotations

import re
from datetime import date

# --- атрибуты ---
_RANGE = re.compile(r"^\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s*$")


def parse_attr(raw: str | None) -> tuple[int, int] | None:
    """'14' → (14, 14); '9-11' → (9, 11); '-' или пусто → None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in {"-", "—", "?"}:
        return None
    m = _RANGE.match(s)
    if m:
        lo, hi = sorted((int(m.group(1)), int(m.group(2))))
        if 1 <= lo <= 20 and 1 <= hi <= 20:
            return lo, hi
        return None
    if s.isdigit() and 1 <= int(s) <= 20:
        v = int(s)
        return v, v
    return None


def attr_mid(r: tuple[int, int]) -> float:
    return (r[0] + r[1]) / 2


def attr_certainty(r: tuple[int, int]) -> float:
    """1.0 — точное значение; диапазон шириной 4 — 0.6; шире — меньше."""
    return max(0.2, 1.0 - (r[1] - r[0]) * 0.1)


# --- звёзды (текущий/потенциальный уровень) ---
def parse_stars(raw: str | None) -> tuple[float, float] | None:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", ".").replace("★", "")
    if not s or s in {"-", "—"}:
        return None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    nums = [n for n in nums if 0 <= n <= 5]
    if not nums:
        return None
    return (min(nums[:2]), max(nums[:2]))


# --- деньги ---
_MULT = {
    "k": 1e3, "к": 1e3, "тыс": 1e3, "тыс.": 1e3,
    "m": 1e6, "м": 1e6, "млн": 1e6, "млн.": 1e6,
    "b": 1e9, "bn": 1e9, "млрд": 1e9,
}
_CURRENCY = {"€": "EUR", "£": "GBP", "$": "USD", "₴": "UAH", "₽": "RUB", "eur": "EUR", "gbp": "GBP", "usd": "USD"}
_MONEY = re.compile(r"(\d+(?:[.,]\d+)?)\s*(k|к|тыс\.?|m|м|млн\.?|bn|b|млрд)?", re.I)


def parse_money(raw: str | None) -> dict | None:
    """'€15M' → {low: 15e6, high: 15e6, currency: EUR}; '€10M - €14M' → диапазон;
    '€1.2K p/w' → {..., per: week}. 'Not for Sale', '-', пусто → None."""
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(" ", " ")
    if not s or s in {"-", "—", "n/a"} or "not for sale" in s or "не прода" in s:
        return None
    currency = next((v for k, v in _CURRENCY.items() if k in s), None)
    per = None
    if any(k in s for k in ("p/w", "pw", "/w", "в нед", "/нед", "нед.")):
        per = "week"
    elif any(k in s for k in ("p/m", "pm", "/m ", "в мес", "/мес")):
        per = "month"
    elif any(k in s for k in ("p/a", "pa", "в год", "/год")):
        per = "year"
    # убрать пробелы-разделители тысяч: "1 200 000"
    s2 = re.sub(r"(?<=\d) (?=\d{3}\b)", "", s)
    vals = []
    for num, suf in _MONEY.findall(s2):
        v = float(num.replace(",", "."))
        if suf:
            v *= _MULT.get(suf.lower().rstrip("."), _MULT.get(suf.lower(), 1))
        vals.append(v)
    if not vals:
        return None
    return {"low": min(vals), "high": max(vals), "currency": currency, "per": per}


def weekly_wage(m: dict | None) -> float | None:
    if not m:
        return None
    v = (m["low"] + m["high"]) / 2
    return {"week": v, "month": v * 12 / 52, "year": v / 52}.get(m.get("per") or "week", v)


# --- даты контракта ---
def parse_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(20\d{2})\b", s)
    if m:
        return date(int(m.group(1)), 6, 30)
    return None


def parse_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    m = re.search(r"\d+", str(raw))
    return int(m.group(0)) if m else None


# --- позиции ---
# Внутренние коды: GK, D_L, D_C, D_R, WB_L, WB_R, DM, M_L, M_C, M_R, AM_L, AM_C, AM_R, ST
_EN_LINES = {"GK": "GK", "D": "D", "WB": "WB", "DM": "DM", "M": "M", "AM": "AM", "ST": "ST", "F": "ST", "S": "ST"}
# Русская локализация (сверить по реальной выгрузке): ВР, З, КЗ, ОП, П, АП, Н/НАП/Ф
_RU_LINES = {"ВР": "GK", "ВРТ": "GK", "З": "D", "КЗ": "WB", "ОП": "DM", "П": "M", "ПЗ": "M", "АП": "AM", "АПЗ": "AM",
             "Н": "ST", "НАП": "ST", "Ф": "ST", "ЦФ": "ST"}
_SIDES_EN = {"L": "L", "C": "C", "R": "R"}
_SIDES_RU = {"Л": "L", "Ц": "C", "П": "R"}


def parse_positions(raw: str | None) -> set[str]:
    """'D (RC), DM' → {D_R, D_C, DM}; 'M/AM (L)' → {M_L, AM_L}; 'ST (C)' → {ST}."""
    out: set[str] = set()
    if not raw:
        return out
    s = str(raw).upper().replace("Ё", "Е")
    for part in re.split(r",\s*", s):
        m = re.match(r"^\s*([A-ZА-Я/]+)\s*(?:\(([A-ZА-Я]+)\))?\s*$", part)
        if not m:
            continue
        lines_raw, sides_raw = m.group(1), m.group(2) or ""
        for ln in lines_raw.split("/"):
            line = _EN_LINES.get(ln) or _RU_LINES.get(ln)
            if not line:
                continue
            if line in ("GK", "DM", "ST"):
                out.add(line)
                continue
            sides = [(_SIDES_EN.get(c) or _SIDES_RU.get(c)) for c in sides_raw] or ["C"]
            for side in sides:
                if side:
                    if line == "WB" and side == "C":
                        continue
                    out.add(f"{line}_{side}")
    return out


POSITION_RU = {
    "GK": "вратарь", "D_L": "левый защитник", "D_C": "центральный защитник", "D_R": "правый защитник",
    "WB_L": "левый латераль", "WB_R": "правый латераль", "DM": "опорный полузащитник",
    "M_L": "левый полузащитник", "M_C": "центральный полузащитник", "M_R": "правый полузащитник",
    "AM_L": "левый вингер", "AM_C": "атакующий полузащитник", "AM_R": "правый вингер", "ST": "нападающий",
}
