"""Обновление приложения из релизов GitHub (Label777/FM27Analyst).

Проверка: последний релиз → версия из тега vX.Y.Z → сравнение с текущей.
Установка: скачиваем установщик (*-setup.exe) во временную папку и запускаем его;
он закрывает FM27 Analyst, ставит новую версию и запускает её снова.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__

REPO = "Label777/FM27Analyst"
API = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v.split("-")[0].split("+")[0])
    return tuple(int(n) for n in nums[:3]) if nums else (0,)


@dataclass
class UpdateInfo:
    current: str
    latest: str | None
    available: bool
    url: str | None = None
    notes: str = ""
    page: str | None = None
    error: str | None = None


def _get(url: str, timeout: float = 10) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"FM27Analyst/{__version__}",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def pick_installer(assets: list[dict]) -> str | None:
    for a in assets:
        name = a.get("name", "").lower()
        if name.endswith("-setup.exe") or (name.endswith(".exe") and "setup" in name):
            return a.get("browser_download_url")
    return None


def check(fetch=_get, current: str = __version__) -> UpdateInfo:
    try:
        rel = json.loads(fetch(API))
    except Exception as e:  # сеть, лимит GitHub, нет релизов
        return UpdateInfo(current=current, latest=None, available=False, error=str(e))
    tag = rel.get("tag_name") or ""
    url = pick_installer(rel.get("assets") or [])
    newer = parse_version(tag) > parse_version(current)
    return UpdateInfo(current=current, latest=tag.lstrip("v") or None, available=bool(newer and url), url=url,
                      notes=(rel.get("body") or "")[:2000], page=rel.get("html_url"))


def download_and_run(url: str, fetch=_get) -> Path:
    if not url.startswith(f"https://github.com/{REPO}/releases/download/"):
        raise ValueError("Установщик можно скачивать только из релизов FM27Analyst на GitHub")
    data = fetch(url, timeout=300)
    path = Path(tempfile.gettempdir()) / Path(url).name
    path.write_bytes(data)
    if sys.platform == "win32":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        # /P — установка без лишних вопросов (только прогресс), /R — запустить приложение после установки
        subprocess.Popen([str(path), "/P", "/R"], creationflags=flags, close_fds=True, cwd=os.path.dirname(path))
    return path
