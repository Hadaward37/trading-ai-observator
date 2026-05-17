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
