from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from PIL import Image

from ..models import Snapshot


class ScreenType(str, Enum):
    MATCH = "match"  # экран матча (2D/3D + плашка счёта)
    MATCH_STATS = "match_stats"  # статистика матча
    TACTICS = "tactics"  # тактика (в владении / без мяча)
    SQUAD = "squad"  # состав / squad bar с усталостью
    PLAYER_PROFILE = "player_profile"
    ANALYSIS = "analysis"  # Heat Maps, Action Zones, Pass Maps
    OPPONENT_PREVIEW = "opponent_preview"
    UNKNOWN = "unknown"


def ahash(img: Image.Image, size: int = 16) -> int:
    """Средний хэш: устойчив к сжатию, чувствителен к смене цифр и панелей."""
    g = img.convert("L").resize((size, size), Image.Resampling.BILINEAR)
    px = list(g.tobytes())
    avg = sum(px) / len(px)
    bits = 0
    for p in px:
        bits = (bits << 1) | (1 if p > avg else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


@dataclass
class ChangeFilter:
    """Пропускает кадр дальше, только если изменился хотя бы один регион.

    Регионы задаются в долях размера кадра, чтобы не зависеть от разрешения.
    """

    regions: dict[str, tuple[float, float, float, float]] = field(
        default_factory=lambda: {"full": (0.0, 0.0, 1.0, 1.0)}
    )
    threshold: int = 6
    _last: dict[str, int] = field(default_factory=dict)

    def changed(self, img: Image.Image) -> list[str]:
        w, h = img.size
        out = []
        for name, (x, y, rw, rh) in self.regions.items():
            crop = img.crop((int(x * w), int(y * h), int((x + rw) * w), int((y + rh) * h)))
            hsh = ahash(crop)
            prev = self._last.get(name)
            if prev is None or hamming(prev, hsh) > self.threshold:
                out.append(name)
            self._last[name] = hsh
        return out


@dataclass
class PipelineResult:
    screen: ScreenType
    changed_regions: list[str]
    snapshot: Snapshot | None
    message: str


Classifier = Callable[[Image.Image], tuple[ScreenType, float]]
Extractor = Callable[[Image.Image], Snapshot | None]


def _untrained_classifier(img: Image.Image) -> tuple[ScreenType, float]:
    return ScreenType.UNKNOWN, 0.0


@dataclass
class Pipeline:
    classifier: Classifier = _untrained_classifier
    extractors: dict[ScreenType, Extractor] = field(default_factory=dict)
    change_filter: ChangeFilter = field(default_factory=ChangeFilter)
    min_confidence: float = 0.8

    def process(self, img: Image.Image) -> PipelineResult:
        changed = self.change_filter.changed(img)
        if not changed:
            return PipelineResult(ScreenType.UNKNOWN, [], None, "Экран не изменился с прошлого снимка")
        screen, conf = self.classifier(img)
        if screen == ScreenType.UNKNOWN or conf < self.min_confidence:
            return PipelineResult(
                ScreenType.UNKNOWN,
                changed,
                None,
                "Тип экрана не распознан: классификатор обучается на датасете (этап 3). "
                "Пока введите данные вручную или загрузите снимок.",
            )
        ex = self.extractors.get(screen)
        if ex is None:
            return PipelineResult(screen, changed, None, f"Экстрактор для экрана «{screen.value}» ещё не готов")
        snap = ex(img)
        msg = "Данные извлечены" if snap else "Не удалось извлечь данные с уверенностью"
        return PipelineResult(screen, changed, snap, msg)
