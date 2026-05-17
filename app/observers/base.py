"""
Base Observer — future expansion point.

Planned: abstract observer that subscribes to the trade stream and
computes derived metrics (VWAP, spread, order flow imbalance, etc.)
incrementally using River online-learning primitives.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseObserver(ABC):
    """Abstract base for all market observers."""

    @abstractmethod
    async def on_trade(self, trade: Dict[str, Any]) -> None:
        ...

    @abstractmethod
    def snapshot(self) -> Dict[str, Any]:
        ...
