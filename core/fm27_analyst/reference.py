"""Доступ к справочнику настроек FM27."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def load() -> dict:
    with resources.files("fm27_analyst.data").joinpath("fm27_reference.json").open(encoding="utf-8") as f:
        return json.load(f)


def tweak_ids() -> set[str]:
    return {t["id"] for t in load()["tactical_tweaks"]}


def tweak(tid: str) -> dict:
    for t in load()["tactical_tweaks"]:
        if t["id"] == tid:
            return t
    raise KeyError(tid)


def position_group(position: str | None) -> str | None:
    if not position:
        return None
    pos = position.strip().upper()
    for group, labels in load()["position_groups"].items():
        if group.startswith("_"):
            continue
        if pos in (lbl.upper() for lbl in labels):
            return group
    return None


def attr_ru(key: str) -> str:
    return load()["attribute_ru"].get(key, key)


def sub_profile(group: str) -> list[str]:
    return load()["substitution_profiles"].get(group, [])
