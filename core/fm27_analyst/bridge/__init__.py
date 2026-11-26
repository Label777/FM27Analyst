"""Мост с игрой: приём данных от плагина FM27 Analyst Bridge (BepInEx), который читает интерфейс FM27."""

from .state import BridgeState
from .api import register_bridge

__all__ = ["BridgeState", "register_bridge"]
