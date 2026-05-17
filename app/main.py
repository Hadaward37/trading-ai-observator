from __future__ import annotations

import asyncio
import platform
import signal
import sys

import uvicorn

from app.config import settings
from app.storage.database import init_db
from app.utils.logger import get_logger, setup_logging

setup_logging(log_level=settings.app_log_level, logs_dir=settings.logs_dir)
log = get_logger(__name__)


async def _run_binance_collector() -> None:
    from app.collectors.binance_ws import run_collector
    await run_collector()


async def _run_mt5_collector() -> None:
    from app.collectors.mt5_collector import run_mt5_collector
    await run_mt5_collector()


async def _run_dashboard() -> None:
    from app.dashboard.server import app as dashboard_app

    config = uvicorn.Config(
        app=dashboard_app,
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        log_level=settings.app_log_level.lower(),
        reload=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    settings.ensure_dirs()

    is_windows = platform.system() == "Windows"
    mt5_active = settings.mt5_enabled and is_windows

    log.info(
        "system_starting",
        env=settings.app_env,
        binance_symbols=settings.symbols_list,
        mt5_enabled=settings.mt5_enabled,
        mt5_active=mt5_active,
        mt5_symbols=settings.mt5_symbols_list if mt5_active else [],
        dashboard_port=settings.dashboard_port,
        platform=platform.system(),
    )

    if settings.mt5_enabled and not is_windows:
        log.warning(
            "mt5_skipped_non_windows",
            platform=platform.system(),
            reason="MT5 Python API is Windows-only",
        )

    await init_db()

    loop = asyncio.get_running_loop()

    def _handle_shutdown(sig_name: str) -> None:
        log.info("shutdown_signal_received", signal=sig_name)
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_shutdown, sig.name)
        except NotImplementedError:
            # Windows does not support add_signal_handler for all signals
            pass

    coroutines = [
        _run_binance_collector(),
        _run_dashboard(),
    ]

    if mt5_active:
        coroutines.append(_run_mt5_collector())

    try:
        await asyncio.gather(*coroutines, return_exceptions=True)
    except asyncio.CancelledError:
        log.info("system_shutdown_complete")
    except Exception as exc:
        log.error("fatal_error", error=str(exc), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
