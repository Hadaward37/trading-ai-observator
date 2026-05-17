from __future__ import annotations

"""
MT5 Collector — polls ticks from MetaTrader5 terminal via mt5.copy_ticks_from().

Design notes:
- MT5 Python API is synchronous/blocking → entire collector runs in a thread
  via loop.run_in_executor(), keeping the asyncio event loop free.
- DB saves are async (SQLAlchemy async) → bridged via asyncio.run_coroutine_threadsafe().
- No credentials hardcoded. Uses the terminal session already open on this machine.
- One thread owns all MT5 calls (initialize + fetch), satisfying MT5 thread-affinity.
"""

import asyncio
import datetime
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytz

from app.utils.logger import get_logger

log = get_logger(__name__)

_SAO_PAULO = pytz.timezone("America/Sao_Paulo")
_MARKET_OPEN = datetime.time(9, 0)
_MARKET_CLOSE = datetime.time(18, 0)
_UTC = datetime.timezone.utc

# MT5 tick flag constants (same values as MetaTrader5 library)
_FLAG_BUY = 2
_FLAG_SELL = 4


# ── Stats ─────────────────────────────────────────────────────────────────────

@dataclass
class MT5CollectorStats:
    started_at: datetime.datetime = field(default_factory=lambda: datetime.datetime.now(_UTC))
    total_ticks: int = 0
    reconnect_count: int = 0
    skipped_off_hours: int = 0
    last_tick_at: Optional[datetime.datetime] = None
    last_error: Optional[str] = None
    connected: bool = False

    @property
    def uptime_seconds(self) -> float:
        return (datetime.datetime.now(_UTC) - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "uptime_seconds": round(self.uptime_seconds, 1),
            "total_ticks": self.total_ticks,
            "reconnect_count": self.reconnect_count,
            "skipped_off_hours": self.skipped_off_hours,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "last_error": self.last_error,
            "connected": self.connected,
        }


mt5_stats = MT5CollectorStats()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_market_open() -> bool:
    now_sp = datetime.datetime.now(_SAO_PAULO).time()
    return _MARKET_OPEN <= now_sp < _MARKET_CLOSE


def _infer_side(flags: int) -> str:
    if flags & _FLAG_BUY:
        return "buy"
    if flags & _FLAG_SELL:
        return "sell"
    return "unknown"


def _try_initialize() -> bool:
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            err = mt5.last_error()
            log.warning("mt5_initialize_failed", error=err)
            mt5_stats.last_error = str(err)
            mt5_stats.connected = False
            return False
        info = mt5.terminal_info()
        log.info(
            "mt5_connected",
            build=info.build if info else "unknown",
            connected=info.connected if info else False,
        )
        mt5_stats.connected = True
        return True
    except Exception as exc:
        log.error("mt5_initialize_exception", error=str(exc))
        mt5_stats.last_error = str(exc)
        mt5_stats.connected = False
        return False


def _fetch_ticks(symbol: str, from_dt: datetime.datetime, count: int = 2000) -> Optional[object]:
    try:
        import MetaTrader5 as mt5
        ticks = mt5.copy_ticks_from(symbol, from_dt, count, mt5.COPY_TICKS_ALL)
        return ticks
    except Exception as exc:
        log.error("mt5_fetch_error", symbol=symbol, error=str(exc))
        mt5_stats.last_error = str(exc)
        return None


def _poll_symbol(
    symbol: str,
    last_time_msc: Dict[str, int],
    loop: asyncio.AbstractEventLoop,
) -> int:
    """Fetch new ticks for one symbol, save to DB. Returns count of new ticks saved."""
    saved = 0

    # Start 2 seconds back on first run, else from last seen tick + 1 ms
    if symbol not in last_time_msc:
        from_dt = datetime.datetime.now(_UTC) - datetime.timedelta(seconds=2)
    else:
        from_dt = datetime.datetime.fromtimestamp(
            (last_time_msc[symbol] + 1) / 1000.0, tz=_UTC
        )

    ticks = _fetch_ticks(symbol, from_dt)
    if ticks is None or len(ticks) == 0:
        return 0

    for tick in ticks:
        time_msc: int = int(tick["time_msc"])

        # Skip already-seen ticks
        if symbol in last_time_msc and time_msc <= last_time_msc[symbol]:
            continue

        last_time_msc[symbol] = time_msc

        price: float = float(tick["last"]) if tick["last"] > 0 else (
            (float(tick["bid"]) + float(tick["ask"])) / 2.0
        )
        if price <= 0:
            continue

        volume: float = float(tick["volume_real"]) if tick["volume_real"] > 0 else float(tick["volume"])
        flags: int = int(tick["flags"])
        side: str = _infer_side(flags)
        tick_dt = datetime.datetime.fromtimestamp(time_msc / 1000.0, tz=_UTC)
        trade_id = f"mt5_{symbol}_{time_msc}"

        from app.storage.database import save_trade
        future = asyncio.run_coroutine_threadsafe(
            save_trade(
                timestamp=tick_dt,
                symbol=symbol,
                price=price,
                quantity=volume,
                side=side,
                trade_id=trade_id,
            ),
            loop,
        )
        try:
            future.result(timeout=5.0)
            saved += 1
        except Exception as exc:
            log.warning("mt5_save_error", symbol=symbol, trade_id=trade_id, error=str(exc))

    return saved


# ── Blocking loop (runs in thread pool executor) ──────────────────────────────

def _mt5_blocking_loop(
    symbols: List[str],
    poll_interval: int,
    loop: asyncio.AbstractEventLoop,
) -> None:
    reconnect_delay = 30
    last_time_msc: Dict[str, int] = {}

    log.info("mt5_collector_thread_started", symbols=symbols, poll_interval=poll_interval)

    while True:
        # ── Connect / reconnect ───────────────────────────────────────────────
        if not mt5_stats.connected:
            if not _try_initialize():
                mt5_stats.reconnect_count += 1
                log.info("mt5_waiting_reconnect", delay_seconds=reconnect_delay)
                time.sleep(reconnect_delay)
                continue

        # ── Market hours gate ─────────────────────────────────────────────────
        if not _is_market_open():
            mt5_stats.skipped_off_hours += 1
            if mt5_stats.skipped_off_hours % 60 == 1:  # log once per minute
                import datetime as _dt
                now_sp = _dt.datetime.now(_SAO_PAULO)
                log.info(
                    "mt5_market_closed",
                    local_time=now_sp.strftime("%H:%M:%S"),
                    next_open="09:00 America/Sao_Paulo",
                )
            time.sleep(poll_interval)
            continue

        # ── Poll each symbol ──────────────────────────────────────────────────
        total_new = 0
        for symbol in symbols:
            try:
                n = _poll_symbol(symbol, last_time_msc, loop)
                total_new += n
            except Exception as exc:
                mt5_stats.last_error = str(exc)
                log.error("mt5_poll_exception", symbol=symbol, error=str(exc))

        if total_new > 0:
            mt5_stats.total_ticks += total_new
            mt5_stats.last_tick_at = datetime.datetime.now(_UTC)
            log.debug("mt5_ticks_saved", new_ticks=total_new)

        time.sleep(poll_interval)


# ── Async entry point (called from main.py via asyncio.gather) ────────────────

async def run_mt5_collector() -> None:
    from app.config import settings

    symbols = settings.mt5_symbols_list
    poll_interval = settings.mt5_poll_interval
    loop = asyncio.get_running_loop()

    log.info("mt5_collector_starting", symbols=symbols, poll_interval=poll_interval)

    try:
        await loop.run_in_executor(
            None,
            _mt5_blocking_loop,
            symbols,
            poll_interval,
            loop,
        )
    except asyncio.CancelledError:
        log.info("mt5_collector_cancelled")
        try:
            import MetaTrader5 as mt5
            mt5.shutdown()
        except Exception:
            pass
        raise
    except Exception as exc:
        log.error("mt5_collector_fatal", error=str(exc), exc_info=True)
