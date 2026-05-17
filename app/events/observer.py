from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any, Dict, List, Tuple

from app.storage.database import save_event
from app.utils.logger import get_logger

log = get_logger(__name__)

_HISTORY_LEN = 20  # candles used to compute rolling means


class EventObserver:
    """
    Receives feature payloads from FeatureEngine and detects market events.

    Events emitted:
        volatility_expansion  — vol spike above 2× rolling mean
        aggressive_buying     — imbalance > 0.70, positive delta
        aggressive_selling    — imbalance < 0.30, negative delta
        compression           — vol AND intensity both below 30% of mean
        exhaustion            — high activity but tiny net price movement
    """

    def __init__(self) -> None:
        self._vol_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=_HISTORY_LEN))
        self._int_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=_HISTORY_LEN))

    async def on_features(self, data: Dict[str, Any]) -> None:
        symbol: str = data["symbol"]
        ts: str = data["timestamp"]
        volatility: float = data["volatility"]
        imbalance: float = data["imbalance"]
        delta: float = data["delta"]
        trade_intensity: float = data["trade_intensity"]
        candle_efficiency: float = data["candle_efficiency"]
        price_change: float = data["price_change"]

        self._vol_history[symbol].append(volatility)
        self._int_history[symbol].append(trade_intensity)

        vol_hist = list(self._vol_history[symbol])
        int_hist = list(self._int_history[symbol])
        mean_vol = sum(vol_hist) / len(vol_hist)
        mean_intensity = sum(int_hist) / len(int_hist)

        events = _detect_events(
            volatility=volatility,
            imbalance=imbalance,
            delta=delta,
            trade_intensity=trade_intensity,
            candle_efficiency=candle_efficiency,
            price_change=price_change,
            mean_vol=mean_vol,
            mean_intensity=mean_intensity,
        )

        for event_type, confidence, metadata in events:
            try:
                await save_event(
                    timestamp=ts,
                    symbol=symbol,
                    event_type=event_type,
                    confidence=round(confidence, 4),
                    metadata_json=json.dumps(
                        {k: round(v, 6) if isinstance(v, float) else v
                         for k, v in metadata.items()}
                    ),
                )
                log.info(
                    "market_event",
                    symbol=symbol,
                    event_type=event_type,
                    confidence=round(confidence, 3),
                    **{k: round(v, 4) if isinstance(v, float) else v
                       for k, v in metadata.items()},
                )
            except Exception as exc:
                log.error("event_save_error", event_type=event_type, error=str(exc))


# ── Detection logic (pure function — easy to unit-test) ──────────────────────

def _detect_events(
    *,
    volatility: float,
    imbalance: float,
    delta: float,
    trade_intensity: float,
    candle_efficiency: float,
    price_change: float,
    mean_vol: float,
    mean_intensity: float,
) -> List[Tuple[str, float, Dict[str, Any]]]:
    events: List[Tuple[str, float, Dict[str, Any]]] = []

    # ── volatility_expansion ─────────────────────────────────────────────────
    if mean_vol > 0 and volatility > mean_vol * 2.0:
        ratio = volatility / mean_vol
        confidence = min(1.0, 0.5 + (ratio - 2.0) / 2.0)
        events.append((
            "volatility_expansion", confidence,
            {"volatility": volatility, "mean_vol": mean_vol, "ratio": ratio},
        ))

    # ── aggressive_buying ────────────────────────────────────────────────────
    if imbalance > 0.70 and delta > 0:
        confidence = min(1.0, 0.5 + (imbalance - 0.70) / 0.30 * 0.5)
        events.append((
            "aggressive_buying", confidence,
            {"imbalance": imbalance, "delta": delta, "price_change": price_change},
        ))

    # ── aggressive_selling ───────────────────────────────────────────────────
    if imbalance < 0.30 and delta < 0:
        confidence = min(1.0, 0.5 + (0.30 - imbalance) / 0.30 * 0.5)
        events.append((
            "aggressive_selling", confidence,
            {"imbalance": imbalance, "delta": delta, "price_change": price_change},
        ))

    # ── compression ──────────────────────────────────────────────────────────
    vol_compressed = mean_vol > 0 and volatility < mean_vol * 0.30
    int_compressed = mean_intensity > 0 and trade_intensity < mean_intensity * 0.50
    if vol_compressed and int_compressed:
        vol_ratio = volatility / mean_vol if mean_vol > 0 else 0.0
        confidence = min(1.0, 0.6 + (1.0 - min(1.0, vol_ratio / 0.30)) * 0.4)
        events.append((
            "compression", confidence,
            {"volatility": volatility, "trade_intensity": trade_intensity,
             "vol_ratio": vol_ratio},
        ))

    # ── exhaustion ───────────────────────────────────────────────────────────
    high_activity = mean_intensity > 0 and trade_intensity > mean_intensity * 1.5
    if high_activity and candle_efficiency < 0.15:
        confidence = min(1.0, 0.5 + (0.15 - candle_efficiency) / 0.15 * 0.5)
        events.append((
            "exhaustion", confidence,
            {"candle_efficiency": candle_efficiency, "trade_intensity": trade_intensity},
        ))

    return events
