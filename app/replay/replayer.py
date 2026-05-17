from __future__ import annotations

import asyncio
import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.storage.database import get_recent_trades
from app.utils.logger import get_logger

log = get_logger(__name__)


class Replayer:
    """
    Loads historical trades from SQLite and replays them through a pipeline
    at a configurable speed multiplier.

    Usage (backtesting / replay):
        replayer = Replayer(speed=10.0)  # 10× real-time
        await replayer.replay(
            symbol="BTCUSDT",
            limit=5000,
            on_trade=candle_engine.on_trade,
        )
    """

    def __init__(self, speed: float = 1.0) -> None:
        if speed <= 0:
            raise ValueError("speed must be > 0")
        self.speed = speed

    async def replay(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 10_000,
        on_trade: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> ReplayResult:
        trades = await get_recent_trades(symbol=symbol, limit=limit)
        if not trades:
            log.warning("replayer_no_trades", symbol=symbol, limit=limit)
            return ReplayResult(total=0, replayed=0, elapsed=0.0)

        # Reverse so oldest comes first
        trades = list(reversed(trades))
        log.info(
            "replay_starting",
            symbol=symbol,
            total=len(trades),
            speed=self.speed,
        )

        start_wall = asyncio.get_event_loop().time()
        prev_ts: Optional[datetime.datetime] = None
        replayed = 0

        for raw in trades:
            ts = datetime.datetime.fromisoformat(raw["timestamp"])

            if prev_ts is not None and self.speed > 0:
                gap = (ts - prev_ts).total_seconds()
                sleep = gap / self.speed
                if 0 < sleep < 10:
                    await asyncio.sleep(sleep)

            if on_trade is not None:
                try:
                    await on_trade(
                        symbol=raw["symbol"],
                        price=raw["price"],
                        qty=raw["quantity"],
                        side=raw["side"],
                        timestamp=ts,
                    )
                except Exception as exc:
                    log.error("replay_callback_error", trade_id=raw.get("trade_id"), error=str(exc))

            prev_ts = ts
            replayed += 1

        elapsed = asyncio.get_event_loop().time() - start_wall
        log.info(
            "replay_complete",
            symbol=symbol,
            total=len(trades),
            replayed=replayed,
            elapsed_seconds=round(elapsed, 2),
        )
        return ReplayResult(total=len(trades), replayed=replayed, elapsed=elapsed)


class ReplayResult:
    def __init__(self, total: int, replayed: int, elapsed: float) -> None:
        self.total = total
        self.replayed = replayed
        self.elapsed = elapsed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "replayed": self.replayed,
            "elapsed_seconds": round(self.elapsed, 2),
        }
