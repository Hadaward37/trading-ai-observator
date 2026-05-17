from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


class Base(DeclarativeBase):
    pass


# ── Existing model ─────────────────────────────────────────────────────────────

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    side = Column(String(4), nullable=False)
    trade_id = Column(String(32), nullable=True, index=True, unique=True)
    raw_data = Column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "symbol": self.symbol,
            "price": self.price,
            "quantity": self.quantity,
            "side": self.side,
            "trade_id": self.trade_id,
        }


# ── Phase 2 models ─────────────────────────────────────────────────────────────

class Candle1m(Base):
    __tablename__ = "candles_1m"
    __table_args__ = (
        UniqueConstraint("timestamp", "symbol", name="uq_candle_ts_symbol"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    trade_count = Column(Integer, nullable=False)
    vwap = Column(Float, nullable=False)
    buy_volume = Column(Float, nullable=False)
    sell_volume = Column(Float, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "symbol": self.symbol,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "trade_count": self.trade_count,
            "vwap": self.vwap,
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
        }


class MarketFeature(Base):
    __tablename__ = "market_features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    volatility = Column(Float)
    delta = Column(Float)
    imbalance = Column(Float)
    trade_intensity = Column(Float)
    candle_efficiency = Column(Float)
    price_change = Column(Float)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "symbol": self.symbol,
            "volatility": self.volatility,
            "delta": self.delta,
            "imbalance": self.imbalance,
            "trade_intensity": self.trade_intensity,
            "candle_efficiency": self.candle_efficiency,
            "price_change": self.price_change,
        }


class MarketEvent(Base):
    __tablename__ = "market_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    metadata_json = Column(Text)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "symbol": self.symbol,
            "event_type": self.event_type,
            "confidence": self.confidence,
            "metadata_json": self.metadata_json,
        }


# ── Engine / session ──────────────────────────────────────────────────────────

_engine: Any = None
_session_factory: Any = None


def get_engine() -> Any:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.is_development,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("database_initialized", url=settings.database_url)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _coerce_dt(ts: Any) -> datetime.datetime:
    """Accept datetime or ISO string, always return datetime."""
    if isinstance(ts, str):
        return datetime.datetime.fromisoformat(ts)
    return ts


# ── trades CRUD ───────────────────────────────────────────────────────────────

async def save_trade(
    *,
    timestamp: datetime.datetime,
    symbol: str,
    price: float,
    quantity: float,
    side: str,
    trade_id: Optional[str] = None,
    raw_data: Optional[str] = None,
) -> Optional[Trade]:
    factory = get_session_factory()
    async with factory() as session:
        if trade_id is not None:
            existing = await session.scalar(
                select(Trade).where(Trade.trade_id == trade_id)
            )
            if existing:
                return existing

        trade = Trade(
            timestamp=timestamp,
            symbol=symbol,
            price=price,
            quantity=quantity,
            side=side,
            trade_id=trade_id,
            raw_data=raw_data,
        )
        session.add(trade)
        await session.commit()
        await session.refresh(trade)
        return trade


async def get_recent_trades(
    symbol: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Trade).order_by(Trade.timestamp.desc()).limit(limit)
        if symbol:
            stmt = stmt.where(Trade.symbol == symbol.upper())
        result = await session.execute(stmt)
        rows: Sequence[Trade] = result.scalars().all()
        return [r.to_dict() for r in rows]


async def get_trade_stats() -> Dict[str, Any]:
    factory = get_session_factory()
    async with factory() as session:
        total = await session.scalar(select(func.count(Trade.id)))
        symbols_result = await session.execute(
            select(Trade.symbol, func.count(Trade.id).label("count"))
            .group_by(Trade.symbol)
        )
        symbols = {row.symbol: row.count for row in symbols_result}
        last_trade = await session.scalar(
            select(Trade.timestamp).order_by(Trade.timestamp.desc()).limit(1)
        )
        return {
            "total_trades": total or 0,
            "symbols": symbols,
            "last_trade_at": last_trade.isoformat() if last_trade else None,
        }


# ── candles_1m CRUD ───────────────────────────────────────────────────────────

async def save_candle(
    *,
    timestamp: Any,
    symbol: str,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    trade_count: int,
    vwap: float,
    buy_volume: float,
    sell_volume: float,
) -> Candle1m:
    ts = _coerce_dt(timestamp)
    factory = get_session_factory()
    async with factory() as session:
        candle = Candle1m(
            timestamp=ts,
            symbol=symbol,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
            trade_count=trade_count,
            vwap=vwap,
            buy_volume=buy_volume,
            sell_volume=sell_volume,
        )
        session.add(candle)
        try:
            await session.commit()
            await session.refresh(candle)
        except Exception:
            await session.rollback()
            raise
        return candle


async def get_recent_candles(
    symbol: Optional[str] = None,
    limit: int = 60,
) -> List[Dict[str, Any]]:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Candle1m).order_by(Candle1m.timestamp.desc()).limit(limit)
        if symbol:
            stmt = stmt.where(Candle1m.symbol == symbol.upper())
        result = await session.execute(stmt)
        return [r.to_dict() for r in result.scalars().all()]


# ── market_features CRUD ──────────────────────────────────────────────────────

async def save_features(
    *,
    timestamp: Any,
    symbol: str,
    volatility: float,
    delta: float,
    imbalance: float,
    trade_intensity: float,
    candle_efficiency: float,
    price_change: float,
) -> MarketFeature:
    ts = _coerce_dt(timestamp)
    factory = get_session_factory()
    async with factory() as session:
        feat = MarketFeature(
            timestamp=ts,
            symbol=symbol,
            volatility=volatility,
            delta=delta,
            imbalance=imbalance,
            trade_intensity=trade_intensity,
            candle_efficiency=candle_efficiency,
            price_change=price_change,
        )
        session.add(feat)
        await session.commit()
        await session.refresh(feat)
        return feat


async def get_recent_features(
    symbol: Optional[str] = None,
    limit: int = 60,
) -> List[Dict[str, Any]]:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(MarketFeature).order_by(MarketFeature.timestamp.desc()).limit(limit)
        if symbol:
            stmt = stmt.where(MarketFeature.symbol == symbol.upper())
        result = await session.execute(stmt)
        return [r.to_dict() for r in result.scalars().all()]


# ── market_events CRUD ────────────────────────────────────────────────────────

async def save_event(
    *,
    timestamp: Any,
    symbol: str,
    event_type: str,
    confidence: float,
    metadata_json: Optional[str] = None,
) -> MarketEvent:
    ts = _coerce_dt(timestamp)
    factory = get_session_factory()
    async with factory() as session:
        event = MarketEvent(
            timestamp=ts,
            symbol=symbol,
            event_type=event_type,
            confidence=confidence,
            metadata_json=metadata_json,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def get_recent_events(
    symbol: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(MarketEvent).order_by(MarketEvent.timestamp.desc()).limit(limit)
        if symbol:
            stmt = stmt.where(MarketEvent.symbol == symbol.upper())
        if event_type:
            stmt = stmt.where(MarketEvent.event_type == event_type)
        result = await session.execute(stmt)
        return [r.to_dict() for r in result.scalars().all()]
