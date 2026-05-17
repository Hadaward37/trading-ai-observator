from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.storage.database import get_recent_trades, get_trade_stats
from app.utils.logger import get_logger

log = get_logger(__name__)

app = FastAPI(
    title="Trading AI Observator",
    description="Market observation and analysis system — read-only dashboard",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_UTC = datetime.timezone.utc
_start_time = datetime.datetime.now(_UTC)


def _get_collector_stats() -> Dict[str, Any]:
    try:
        from app.collectors.binance_ws import stats
        return stats.to_dict()
    except Exception:
        return {}


@app.get("/health", tags=["System"])
async def health() -> JSONResponse:
    uptime = (datetime.datetime.now(_UTC) - _start_time).total_seconds()
    return JSONResponse({
        "status": "ok",
        "uptime_seconds": round(uptime, 1),
        "timestamp": datetime.datetime.now(_UTC).isoformat(),
        "version": "0.1.0",
        "env": settings.app_env,
    })


@app.get("/stats", tags=["Market"])
async def stats_endpoint() -> JSONResponse:
    try:
        db_stats = await get_trade_stats()
        collector_stats = _get_collector_stats()
        return JSONResponse({
            "database": db_stats,
            "collector": collector_stats,
        })
    except Exception as exc:
        log.error("stats_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to retrieve stats")


@app.get("/mt5/stats", tags=["MT5"])
async def mt5_stats_endpoint() -> JSONResponse:
    try:
        from app.collectors.mt5_collector import mt5_stats
        return JSONResponse(mt5_stats.to_dict())
    except ImportError:
        raise HTTPException(status_code=503, detail="MT5 collector not loaded")
    except Exception as exc:
        log.error("mt5_stats_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to retrieve MT5 stats")


@app.get("/recent-trades", tags=["Market"])
async def recent_trades(
    symbol: Optional[str] = Query(None, description="Filter by symbol, e.g. BTCUSDT"),
    limit: int = Query(50, ge=1, le=500, description="Number of trades to return"),
) -> JSONResponse:
    try:
        trades = await get_recent_trades(symbol=symbol, limit=limit)
        return JSONResponse({
            "symbol": symbol,
            "limit": limit,
            "count": len(trades),
            "trades": trades,
        })
    except Exception as exc:
        log.error("recent_trades_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to retrieve trades")
