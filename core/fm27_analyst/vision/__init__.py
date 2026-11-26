"""Компьютерное зрение (этап 3).

Сейчас готовы: фильтр изменений по регионам и каркас конвейера.
Классификатор экранов и экстракторы обучаются на датасете русских
скриншотов FM27 (см. docs/DATASET.md) — до этого конвейер честно
отвечает «не распознано» и просит ручной ввод.
"""

from .pipeline import ChangeFilter, Pipeline, PipelineResult, ScreenType

__all__ = ["ChangeFilter", "Pipeline", "PipelineResult", "ScreenType"]
