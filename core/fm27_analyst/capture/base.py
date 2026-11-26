from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Protocol

from PIL import Image

FM_WINDOW_TITLES = ("Football Manager 27", "Football Manager 2027", "FM27")


class CaptureError(RuntimeError):
    pass


class FrameSource(Protocol):
    name: str

    def grab(self, region: tuple[int, int, int, int] | None = None) -> Image.Image:
        """Один кадр. region = (left, top, width, height) относительно окна/экрана."""
        ...


class FolderSource:
    """Кадры из папки по очереди — для тестов и прогона датасета."""

    name = "folder"

    def __init__(self, folder: Path) -> None:
        self.files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
        if not self.files:
            raise CaptureError(f"в папке {folder} нет изображений")
        self.i = 0

    def grab(self, region=None) -> Image.Image:
        img = Image.open(self.files[self.i % len(self.files)]).convert("RGB")
        self.i += 1
        return img.crop(_box(region)) if region else img


def _box(region: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top, w, h = region
    return (left, top, left + w, top + h)


class MssSource:
    """Захват прямоугольника экрана. Если найдено окно FM27 — его область."""

    name = "mss"

    def __init__(self) -> None:
        import mss  # noqa: F401  (проверка наличия)

        self._local = threading.local()

    def _sct(self):
        import mss

        if not hasattr(self._local, "sct"):
            self._local.sct = mss.mss()
        return self._local.sct

    def grab(self, region=None) -> Image.Image:
        sct = self._sct()
        win = find_fm_window()
        if win:
            mon = {"left": win[0], "top": win[1], "width": win[2], "height": win[3]}
        else:
            mon = sct.monitors[1]
        if region:
            mon = {
                "left": mon["left"] + region[0],
                "top": mon["top"] + region[1],
                "width": region[2],
                "height": region[3],
            }
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


class WindowsGraphicsCaptureSource:
    """Захват окна FM27 через Windows.Graphics.Capture (пакет windows-capture).

    Библиотека работает по событиям: держим последний кадр и отдаём его по запросу.
    """

    name = "windows_graphics_capture"

    def __init__(self, window_title: str | None = None) -> None:
        from windows_capture import WindowsCapture  # type: ignore

        title = window_title or _match_title()
        if not title:
            raise CaptureError("окно Football Manager 27 не найдено — запустите игру")
        self._frame: Image.Image | None = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        cap = WindowsCapture(cursor_capture=False, draw_border=False, window_name=title)

        @cap.event
        def on_frame_arrived(frame, control):  # noqa: ANN001
            arr = frame.frame_buffer  # BGRA numpy
            img = Image.fromarray(arr[:, :, [2, 1, 0]])
            with self._lock:
                self._frame = img
            self._ready.set()

        @cap.event
        def on_closed():
            self._ready.clear()

        self._control = cap.start_free_threaded()

    def grab(self, region=None) -> Image.Image:
        if not self._ready.wait(timeout=2.0):
            raise CaptureError("нет кадров от окна FM27 (окно свёрнуто?)")
        with self._lock:
            assert self._frame is not None
            img = self._frame.copy()
        return img.crop(_box(region)) if region else img


def _match_title() -> str | None:
    try:
        import pygetwindow as gw  # type: ignore
    except ImportError:
        return None
    for t in gw.getAllTitles():
        if any(k.lower() in t.lower() for k in FM_WINDOW_TITLES):
            return t
    return None


def find_fm_window() -> tuple[int, int, int, int] | None:
    """(left, top, width, height) окна FM27 или None."""
    try:
        import pygetwindow as gw  # type: ignore
    except ImportError:
        return None
    title = _match_title()
    if not title:
        return None
    w = gw.getWindowsWithTitle(title)[0]
    if w.isMinimized:
        return None
    return (w.left, w.top, w.width, w.height)


def get_default_source() -> FrameSource:
    errors = []
    if sys.platform == "win32":
        try:
            return WindowsGraphicsCaptureSource()
        except ImportError:
            errors.append("не установлен пакет windows-capture")
        except Exception as e:  # окно не найдено и т.п.
            errors.append(str(e))
    try:
        return MssSource()
    except ImportError:
        errors.append("не установлен пакет mss")
    except Exception as e:
        errors.append(str(e))
    hint = (
        "Установите зависимости для Windows: pip install -e core[windows]"
        if sys.platform == "win32"
        else "захват экрана работает на Windows рядом с FM27"
    )
    raise CaptureError(f"Захват экрана недоступен ({'; '.join(errors)}). {hint}")
