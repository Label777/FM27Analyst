"""Установка плагина FM27 Analyst Bridge в игру.

Ядро везёт с собой FM27AnalystBridge.dll и при запуске кладёт его в BepInEx/plugins найденной FM27,
если там нет файла или он старее. Игра, сейвы и другие моды не трогаются. Если игра запущена
(файл плагина занят), сообщаем: обновится при следующем запуске помощника с закрытой игрой.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path

PLUGIN_NAME = "FM27AnalystBridge.dll"
PLUGIN_DIR = Path("BepInEx") / "plugins" / "FM27AnalystBridge"


@dataclass
class GameInstall:
    path: str
    bepinex: bool
    plugin: str  # installed | current | updated | outdated_locked | no_bepinex | error
    message: str


@dataclass
class PluginStatus:
    bundled: bool
    games: list[GameInstall] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def bundled_plugin() -> Path | None:
    try:
        p = resources.files("fm27_analyst.data").joinpath("plugin", PLUGIN_NAME)
        path = Path(str(p))
        return path if path.exists() else None
    except (ModuleNotFoundError, FileNotFoundError):
        return None


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def steam_libraries(steam_path: str | None = None) -> list[Path]:
    """Папки библиотек Steam: из реестра (Windows) и libraryfolders.vdf."""
    roots: list[Path] = []
    if steam_path:
        roots.append(Path(steam_path))
    elif sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(Path(winreg.QueryValueEx(k, "SteamPath")[0]))
        except OSError:
            pass
    libs: list[Path] = []
    for r in roots:
        libs.append(r)
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")):
                libs.append(Path(m.group(1).replace("\\\\", "\\")))
    seen, out = set(), []
    for l in libs:
        key = str(l).lower()
        if key not in seen:
            seen.add(key)
            out.append(l)
    return out


def find_games(libraries: list[Path]) -> list[Path]:
    games = []
    for lib in libraries:
        common = lib / "steamapps" / "common"
        if common.is_dir():
            games += sorted(p for p in common.iterdir() if p.is_dir() and p.name.startswith("Football Manager 27"))
    return games


def ensure_plugin(games: list[Path] | None = None, plugin: Path | None = None) -> PluginStatus:
    plugin = plugin or bundled_plugin()
    if games is None:
        games = find_games(steam_libraries())
    status = PluginStatus(bundled=plugin is not None)
    if plugin is None:
        status.note = "В этой сборке нет файла плагина."
        return status
    if not games:
        status.note = "FM27 в библиотеках Steam не найдена."
        return status
    want = _sha(plugin)
    for g in games:
        if not (g / "BepInEx" / "plugins").is_dir():
            status.games.append(GameInstall(str(g), False, "no_bepinex",
                                            "Нет BepInEx — установите его (проще всего вместе с FM27 Exporter)."))
            continue
        dst = g / PLUGIN_DIR / PLUGIN_NAME
        if dst.exists() and _sha(dst) == want:
            status.games.append(GameInstall(str(g), True, "current", "Плагин актуален."))
            continue
        existed = dst.exists()
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_suffix(".new")
            shutil.copyfile(plugin, tmp)
            tmp.replace(dst)
            status.games.append(GameInstall(str(g), True, "updated" if existed else "installed",
                                            "Плагин обновлён." if existed else "Плагин установлен."))
        except PermissionError:
            try:
                dst.with_suffix(".new").unlink(missing_ok=True)
            except OSError:
                pass
            status.games.append(GameInstall(str(g), True, "outdated_locked",
                                            "Есть новая версия плагина, но игра запущена. Закройте FM27 и перезапустите помощника."))
        except OSError as e:
            status.games.append(GameInstall(str(g), True, "error", f"Не удалось установить плагин: {e}"))
    return status
