from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable, Deque, Dict, List

import numpy as np

from app.storage.database import save_features
from app.utils.logger import get_logger

log = get_logger(__name__)

_ROLLING_WINDOW = 20  # candles kept in memory per symbol for volatility


class FeatureEngine:
    """
    Receives closed candle dicts from CandleEngine, computes financial
    microstructure features, persists them, and notifies downstream callbacks.
    """

    def __init__(self) -> None:
        self._close_history: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=_ROLLING_WINDOW)
        )
        self._callbacks: List[Callable[[Dict[str, Any]], Awaitable[None]]] = []

    def add_callback(self, cb: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        self._callbacks.append(cb)

    async def on_candle(self, candle: Dict[str, Any]) -> None:
        symbol: str = candle["symbol"]
        ts: str = candle["timestamp"]
        close: float = candle["close"]
        open_: float = candle["open"]
        high: float = candle["high"]
        low: float = candle["low"]
        volume: float = candle["volume"]
        buy_vol: float = candle["buy_volume"]
        trade_count: int = candle["trade_count"]

        self._close_history[symbol].append(close)

        # ── Volatility: std of log-returns over rolling window ────────────────
        closes = list(self._close_history[symbol])
        if len(closes) >= 2:
            log_returns = [
                math.log(closes[i] / closes[i - 1])
                for i in range(1, len(closes))
                if closes[i - 1] > 0
            ]
            volatility = float(np.std(log_returns)) if log_returns else 0.0
        else:
            volatility = 0.0

        # ── Delta: signed buy pressure ────────────────────────────────────────
        sell_vol: float = candle["sell_volume"]
        delta = buy_vol - sell_vol

        # ── Imbalance: buy fraction of total volume ───────────────────────────
        imbalance = buy_vol / volume if volume > 0 else 0.5

        # ── Trade intensity: trades per second (candle = 60 s) ────────────────
        trade_intensity = trade_count / 60.0

        # ── Candle efficiency: directional / total range ──────────────────────
        price_range = high - low
        candle_efficiency = abs(close - open_) / price_range if price_range > 0 else 0.0

        # ── Price change % ────────────────────────────────────────────────────
        price_change = ((close - open_) / open_) * 100.0 if open_ > 0 else 0.0

        features: Dict[str, Any] = {
            "timestamp": ts,
            "symbol": symbol,
            "volatility": volatility,
            "delta": delta,
            "imbalance": imbalance,
            "trade_intensity": trade_intensity,
            "candle_efficiency": candle_efficiency,
            "price_change": price_change,
        }

        try:
            await save_features(**features)
            log.debug(
                "features_computed",
                symbol=symbol,
                timestamp=ts,
                volatility=round(volatility, 6),
                delta=round(delta, 4),
                imbalance=round(imbalance, 4),
                price_change=round(price_change, 4),
            )
        except Exception as exc:
            log.error("features_save_error", symbol=symbol, error=str(exc))

        payload = {**features, "candle": candle}
        for cb in self._callbacks:
            try:
                await cb(payload)
            except Exception as exc:
                log.error("features_callback_error", error=str(exc))
