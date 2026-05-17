from __future__ import annotations

import asyncio
import datetime
import json
from dataclasses import dataclass, field
from typing import List, Optional

UTC = datetime.timezone.utc

import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from typing import Awaitable, Callable

from app.config import settings
from app.storage.database import save_trade
from app.utils.logger import get_logger

log = get_logger(__name__)

# Optional pipeline callback set by main.py — called with every confirmed trade.
# Signature: async fn(symbol, price, qty, side, timestamp) -> None
_pipeline_cb: Optional[Callable[..., Awaitable[None]]] = None


def set_pipeline_callback(cb: Callable[..., Awaitable[None]]) -> None:
    """Register the downstream pipeline entry point (CandleEngine.on_trade)."""
    global _pipeline_cb
    _pipeline_cb = cb


@dataclass
class CollectorStats:
    started_at: datetime.datetime = field(default_factory=lambda: datetime.datetime.now(UTC))
    total_trades: int = 0
    reconnect_count: int = 0
    last_trade_at: Optional[datetime.datetime] = None
    last_error: Optional[str] = None

    @property
    def uptime_seconds(self) -> float:
        return (datetime.datetime.now(UTC) - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "uptime_seconds": round(self.uptime_seconds, 1),
            "total_trades": self.total_trades,
            "reconnect_count": self.reconnect_count,
            "last_trade_at": self.last_trade_at.isoformat() if self.last_trade_at else None,
            "last_error": self.last_error,
        }


stats = CollectorStats()


def _build_ws_url(symbols: List[str]) -> str:
    streams = "/".join(f"{s.lower()}@trade" for s in symbols)
    # # if len(symbols) == 1:
        # # return f"{settings.binance_ws_url}/{streams}"
    return f"wss://stream.binance.com:9443/stream?streams={streams}"


async def _process_message(raw: str) -> None:
    try:
        data = json.loads(raw)

        # Combined stream wraps payload under "data" key
        payload = data.get("data", data)

        if payload.get("e") != "trade":
            return

        ts_ms: int = payload["T"]
        timestamp = datetime.datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
        symbol: str = payload["s"]
        price: float = float(payload["p"])
        quantity: float = float(payload["q"])
        side: str = "sell" if payload["m"] else "buy"
        trade_id: str = str(payload["t"])

        await save_trade(
            timestamp=timestamp,
            symbol=symbol,
            price=price,
            quantity=quantity,
            side=side,
            trade_id=trade_id,
            raw_data=raw,
        )

        stats.total_trades += 1
        stats.last_trade_at = datetime.datetime.now(UTC)

        if _pipeline_cb is not None:
            try:
                await _pipeline_cb(
                    symbol=symbol,
                    price=price,
                    qty=quantity,
                    side=side,
                    timestamp=timestamp,
                )
            except Exception as exc:
                log.warning("pipeline_callback_error", error=str(exc))

        if stats.total_trades % 100 == 0:
            log.info(
                "collector_milestone",
                total_trades=stats.total_trades,
                symbol=symbol,
                price=price,
            )
        else:
            log.debug(
                "trade_received",
                symbol=symbol,
                price=price,
                quantity=quantity,
                side=side,
                trade_id=trade_id,
            )

    except Exception as exc:
        stats.last_error = str(exc)
        log.warning("message_processing_error", error=str(exc), raw=raw[:200])


async def _connect_and_listen(url: str) -> None:
    async with websockets.connect(
        url,
        ping_interval=20,
        ping_timeout=10,
        close_timeout=5,
    ) as ws:
        log.info("websocket_connected", url=url)
        async for message in ws:
            await _process_message(message)


async def run_collector() -> None:
    symbols = settings.symbols_list
    url = _build_ws_url(symbols)
    reconnect_delay = settings.binance_reconnect_delay
    max_reconnects = settings.binance_max_reconnects
    attempt = 0

    log.info("collector_starting", symbols=symbols, url=url)

    while True:
        try:
            await _connect_and_listen(url)
        except (ConnectionClosedOK,):
            log.info("websocket_closed_cleanly")
            break
        except (ConnectionClosedError, ConnectionRefusedError, OSError) as exc:
            stats.reconnect_count += 1
            stats.last_error = str(exc)
            attempt += 1
            log.warning(
                "websocket_disconnected",
                error=str(exc),
                reconnect_count=stats.reconnect_count,
                next_retry_seconds=reconnect_delay,
            )
        except Exception as exc:
            stats.reconnect_count += 1
            stats.last_error = str(exc)
            attempt += 1
            log.error(
                "collector_unexpected_error",
                error=str(exc),
                exc_info=True,
            )

        if max_reconnects > 0 and attempt >= max_reconnects:
            log.error("max_reconnects_reached", max=max_reconnects)
            break

        await asyncio.sleep(reconnect_delay)
        log.info("collector_reconnecting", attempt=attempt)
