from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.storage.database import save_candle
from app.utils.logger import get_logger

log = get_logger(__name__)

_UTC = datetime.timezone.utc


def _truncate_to_minute(dt: datetime.datetime) -> datetime.datetime:
    """Strip seconds and microseconds, keep timezone."""
    return dt.replace(second=0, microsecond=0)


# ── In-memory candle buffer ───────────────────────────────────────────────────

@dataclass
class CandleBuffer:
    symbol: str
    minute: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    _vwap_num: float = field(default=0.0, repr=False)
    trade_count: int = 0

    def update(self, price: float, qty: float, side: str) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += qty
        self._vwap_num += price * qty
        self.trade_count += 1
        if side == "buy":
            self.buy_volume += qty
        else:
            self.sell_volume += qty

    @property
    def vwap(self) -> float:
        return self._vwap_num / self.volume if self.volume > 0 else self.close

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.minute.isoformat(),
            "symbol": self.symbol,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "trade_count": self.trade_count,
            "vwap": round(self.vwap, 8),
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
        }


# ── Engine ────────────────────────────────────────────────────────────────────

class CandleEngine:
    """
    Consumes individual trades, aggregates them into 1-minute candles in memory,
    and flushes each closed candle to the DB, then notifies downstream callbacks.
    """

    def __init__(self) -> None:
        self._buffers: Dict[str, CandleBuffer] = {}
        self._callbacks: List[Callable[[Dict[str, Any]], Awaitable[None]]] = []

    def add_callback(self, cb: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Register a coroutine to call with the closed candle dict."""
        self._callbacks.append(cb)

    async def on_trade(
        self,
        symbol: str,
        price: float,
        qty: float,
        side: str,
        timestamp: datetime.datetime,
    ) -> None:
        minute = _truncate_to_minute(timestamp)
        buf = self._buffers.get(symbol)

        if buf is None:
            self._buffers[symbol] = _new_buffer(symbol, minute, price, qty, side)
            return

        if buf.minute != minute:
            await self._flush(buf)
            self._buffers[symbol] = _new_buffer(symbol, minute, price, qty, side)
        else:
            buf.update(price, qty, side)

    async def flush_all(self) -> None:
        """Force-close all open buffers (call on shutdown)."""
        for buf in list(self._buffers.values()):
            await self._flush(buf)
        self._buffers.clear()

    async def _flush(self, buf: CandleBuffer) -> None:
        try:
            await save_candle(
                timestamp=buf.minute,
                symbol=buf.symbol,
                open=buf.open,
                high=buf.high,
                low=buf.low,
                close=buf.close,
                volume=buf.volume,
                trade_count=buf.trade_count,
                vwap=buf.vwap,
                buy_volume=buf.buy_volume,
                sell_volume=buf.sell_volume,
            )
            log.info(
                "candle_closed",
                symbol=buf.symbol,
                minute=buf.minute.isoformat(),
                open=buf.open,
                close=buf.close,
                volume=round(buf.volume, 4),
                trades=buf.trade_count,
                vwap=round(buf.vwap, 2),
            )
        except Exception as exc:
            log.error("candle_save_error", symbol=buf.symbol, error=str(exc))
            return  # don't call downstream if save failed

        candle_dict = buf.to_dict()
        for cb in self._callbacks:
            try:
                await cb(candle_dict)
            except Exception as exc:
                log.error("candle_callback_error", callback=repr(cb), error=str(exc))


def _new_buffer(
    symbol: str, minute: datetime.datetime, price: float, qty: float, side: str
) -> CandleBuffer:
    buf = CandleBuffer(
        symbol=symbol,
        minute=minute,
        open=price,
        high=price,
        low=price,
        close=price,
    )
    buf.update(price, qty, side)
    return buf
