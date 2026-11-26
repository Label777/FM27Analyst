"""Игровая дата из текстов интерфейса FM27 (русский и английский интерфейс).

Дату не выдумываем: если в текстах её нет — возвращаем None, и приложение так и пишет.
"""

from __future__ import annotations

import re
from datetime import date

RU_MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7,
    "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}
EN_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# 26 ноября 2026 / 26 ноя 2026 / 26-ноя-2026
_WORD_RU = re.compile(r"(?<!\d)(\d{1,2})[\s\-.]+([а-яё]{3,9})\.?[\s\-.,]+(\d{4})(?!\d)", re.I)
# 26 November 2026 / 26 Nov 2026
_WORD_EN = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?[\s\-.]+([a-z]{3,9})\.?[\s\-.,]+(\d{4})(?!\d)", re.I)
# November 26, 2026
_EN_MDY = re.compile(r"\b([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})(?!\d)", re.I)
# 26.11.2026 / 26/11/2026
_NUM = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)")


def _mk(y: int, m: int, d: int) -> date | None:
    if not 1990 <= y <= 2200:
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(text: str) -> date | None:
    t = text.strip()
    for m in _WORD_RU.finditer(t):
        mon = RU_MONTHS.get(m.group(2).lower()[:3])
        if mon:
            d = _mk(int(m.group(3)), mon, int(m.group(1)))
            if d:
                return d
    for m in _WORD_EN.finditer(t):
        mon = EN_MONTHS.get(m.group(2).lower()[:3])
        if mon:
            d = _mk(int(m.group(3)), mon, int(m.group(1)))
            if d:
                return d
    for m in _EN_MDY.finditer(t):
        mon = EN_MONTHS.get(m.group(1).lower()[:3])
        if mon:
            d = _mk(int(m.group(3)), mon, int(m.group(2)))
            if d:
                return d
    for m in _NUM.finditer(t):
        d = _mk(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            return d
    return None


def find_game_date(texts: list[str]) -> tuple[date, str] | None:
    """Первая дата в порядке чтения (сверху вниз) — в FM это дата в шапке экрана."""
    for t in texts:
        d = parse_date(t)
        if d:
            return d, t
    return None
