"""Захват экрана FM27.

Порядок выбора источника на Windows:
1. Windows.Graphics.Capture (пакет `windows-capture`) — захват окна fm.exe на GPU,
   работает, даже если окно частично перекрыто.
2. `mss` — захват области экрана (запасной вариант).
Для тестов и воспроизведения — FolderSource (папка с PNG).
"""

from .base import CaptureError, FolderSource, FrameSource, get_default_source

__all__ = ["CaptureError", "FolderSource", "FrameSource", "get_default_source"]
