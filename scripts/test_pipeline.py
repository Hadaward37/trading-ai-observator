"""End-to-end Phase 2 pipeline test — simulates trades through the full stack."""
import asyncio
import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

UTC = datetime.timezone.utc


async def main():
    from app.storage.database import (
        init_db, get_recent_candles, get_recent_features, get_recent_events,
    )
    from app.features.candle_engine import CandleEngine
    from app.features.feature_engine import FeatureEngine
    from app.events.observer import EventObserver

    await init_db()

    engine = CandleEngine()
    feat = FeatureEngine()
    obs = EventObserver()
    engine.add_callback(feat.on_candle)
    feat.add_callback(obs.on_features)

    # Simulate 2 minutes of BTCUSDT trades
    base = datetime.datetime(2026, 1, 2, 10, 0, 0, tzinfo=UTC)
    minute0 = base
    minute1 = base + datetime.timedelta(minutes=1)

    trades_m0 = [
        (67000.0, 0.5, "buy"),
        (67050.0, 0.3, "buy"),
        (67020.0, 0.2, "sell"),
        (67100.0, 0.8, "buy"),
        (67080.0, 0.4, "sell"),
    ]
    trades_m1 = [
        (67200.0, 1.0, "buy"),
        (67150.0, 0.5, "sell"),
        (67300.0, 2.0, "buy"),
    ]

    print("--- Feeding minute 0 trades ---")
    for i, (price, qty, side) in enumerate(trades_m0):
        ts = minute0 + datetime.timedelta(seconds=i * 10)
        await engine.on_trade("BTCUSDT", price, qty, side, ts)

    print("--- Feeding minute 1 trades (closes minute 0 candle) ---")
    for i, (price, qty, side) in enumerate(trades_m1):
        ts = minute1 + datetime.timedelta(seconds=i * 10)
        await engine.on_trade("BTCUSDT", price, qty, side, ts)

    print("--- Flushing remaining open candle (minute 1) ---")
    await engine.flush_all()

    # Inspect DB results
    candles = await get_recent_candles(symbol="BTCUSDT", limit=5)
    features = await get_recent_features(symbol="BTCUSDT", limit=5)
    events = await get_recent_events(symbol="BTCUSDT", limit=10)

    print()
    print(f"Candles persisted:  {len(candles)}")
    for c in reversed(candles):
        print(
            f"  [{c['timestamp']}]  open={c['open']}  close={c['close']}"
            f"  vwap={c['vwap']:.2f}  buy_vol={c['buy_volume']}  sell_vol={c['sell_volume']}"
            f"  trades={c['trade_count']}"
        )

    print(f"\nFeatures persisted: {len(features)}")
    for f in reversed(features):
        print(
            f"  [{f['timestamp']}]  vol={f['volatility']:.6f}"
            f"  imbalance={f['imbalance']:.4f}  delta={f['delta']:.4f}"
            f"  efficiency={f['candle_efficiency']:.4f}  pct_chg={f['price_change']:.4f}"
        )

    print(f"\nEvents persisted:   {len(events)}")
    for e in events:
        print(f"  [{e['timestamp']}]  {e['event_type']}  conf={e['confidence']}")

    assert len(candles) >= 2, "Expected at least 2 candles"
    assert len(features) >= 1, "Expected at least 1 feature row"
    print()
    print("=== END-TO-END PIPELINE TEST PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
