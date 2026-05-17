# Trading AI Observator

A professional-grade, modular market observation and analysis system built in Python.

> **Observer only** — no orders, no execution, no bot. Pure data collection, memory, and pattern analysis.

---

## Architecture Overview

```
trading-ai-observator/
├── app/
│   ├── api/             # Future: REST API extensions
│   ├── collectors/      # WebSocket data collectors (Binance, etc.)
│   ├── dashboard/       # FastAPI dashboard endpoints
│   ├── hypotheses/      # Hypothesis generation and testing engine
│   ├── learning/        # River-based online ML pipeline
│   ├── metrics/         # Financial microstructure metrics
│   ├── observers/       # Streaming observers (VWAP, imbalance, etc.)
│   ├── regimes/         # Market regime detection
│   ├── similarity/      # Historical context similarity engine
│   ├── storage/         # SQLite database layer (SQLAlchemy async)
│   ├── utils/           # Logging, helpers
│   ├── config.py        # Centralized settings via pydantic-settings
│   └── main.py          # Entry point: db init + collector + dashboard
│
├── data/
│   ├── raw/             # Raw tick data (future storage)
│   ├── processed/       # Cleaned, resampled data
│   ├── features/        # Computed feature sets
│   ├── snapshots/       # Periodic market snapshots
│   ├── models/          # Persisted ML model states
│   └── market.db        # SQLite database (auto-created)
│
├── logs/                # Structured JSON logs (auto-created)
├── configs/             # YAML configs for future use
├── notebooks/           # Jupyter analysis notebooks
├── scripts/             # Startup scripts
└── tests/               # Test suite
```

---

## Data Flow

```
Binance WebSocket
      │
      ▼
binance_ws.py  ──► _process_message()
      │
      ▼
save_trade()   ──► SQLite (trades table)
      │
      ▼  (future)
BaseObserver   ──► metrics / regimes / similarity
      │
      ▼  (future)
HypothesisEngine ──► validated patterns
      │
      ▼
FastAPI Dashboard (/health, /stats, /recent-trades)
```

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- pip
- (Optional) Docker

### 2. Clone and set up

```powershell
# Windows
cd c:\Users\Lenovo\trading-ai-observator

# Create virtual environment
python -m venv venv
venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

```bash
# Linux / macOS
cd ~/trading-ai-observator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```powershell
# Copy example and edit if needed
Copy-Item .env.example .env
```

Default `.env` works out of the box for BTCUSDT + ETHUSDT observation.

### 4. Run the system

```powershell
# Option A — direct
python -m app.main

# Option B — startup script (Windows)
.\scripts\start.ps1

# Option B — startup script (first run with setup)
.\scripts\start.ps1 -Setup
```

```bash
# Linux / macOS
./scripts/start.sh
./scripts/start.sh --setup   # first run
```

### 5. Access the dashboard

| URL | Description |
|-----|-------------|
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/health` | System health + uptime |
| `http://localhost:8000/stats` | DB stats + collector stats |
| `http://localhost:8000/recent-trades` | Last N trades |
| `http://localhost:8000/recent-trades?symbol=BTCUSDT&limit=100` | Filtered trades |

---

## Docker

```bash
docker-compose up --build
```

---

## Database Schema

### `trades` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `timestamp` | DATETIME | UTC trade timestamp |
| `symbol` | TEXT | e.g. BTCUSDT |
| `price` | FLOAT | Execution price |
| `quantity` | FLOAT | Trade volume |
| `side` | TEXT | `buy` or `sell` |
| `trade_id` | TEXT UNIQUE | Binance trade ID |
| `raw_data` | TEXT | Full JSON payload |

---

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `BINANCE_SYMBOLS` | `BTCUSDT,ETHUSDT` | Comma-separated symbols |
| `BINANCE_RECONNECT_DELAY` | `5` | Seconds between reconnects |
| `BINANCE_MAX_RECONNECTS` | `0` | 0 = unlimited |
| `DATABASE_URL` | SQLite local | Async SQLAlchemy URL |
| `DASHBOARD_PORT` | `8000` | FastAPI port |
| `APP_LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING |

---

## Expansion Points

### Adding a new symbol

```env
BINANCE_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
```

Restart — the WebSocket combined stream handles N symbols automatically.

### Adding Regime Detection (`app/regimes/`)

1. Implement `RegimeDetector` in `app/regimes/detector.py`
2. Subscribe it to the trade stream inside `run_collector()`
3. Store regime labels in a new `regimes` table
4. Expose via `/regime/current` endpoint

Suggested approach: Hidden Markov Model (HMM) on rolling volatility + volume using `hmmlearn`, or change-point detection with `ruptures`.

### Adding Similarity Engine (`app/similarity/`)

1. Build feature vectors from rolling windows of trades
2. Store vectors in a `feature_snapshots` table
3. At query time, compute cosine similarity or DTW distance against historical vectors
4. Return the top-K most similar historical periods

Suggested libraries: `scikit-learn` NearestNeighbors, `tslearn` for DTW.

### Adding Online Learning (`app/learning/`)

1. Use `River` library — already installed
2. Build a `Pipeline` of feature transformers + an online classifier/regressor
3. Call `model.learn_one(x, y)` on each trade event
4. Track drift with `river.drift.ADWIN`

### Migrating from SQLite to PostgreSQL

1. Install `asyncpg`: `pip install asyncpg`
2. Change `DATABASE_URL` in `.env`:
   ```
   DATABASE_URL=postgresql+asyncpg://user:pass@localhost/observator
   ```
3. Uncomment the `postgres` service in `docker-compose.yml`

---

## Tech Stack

| Layer | Library |
|-------|---------|
| Async runtime | `asyncio` |
| Web framework | `FastAPI` + `uvicorn` |
| WebSocket client | `websockets` |
| Database ORM | `SQLAlchemy 2.0` async |
| Database driver | `aiosqlite` |
| Data manipulation | `pandas`, `numpy` |
| ML (batch) | `scikit-learn` |
| ML (online/streaming) | `River` |
| Exchange integration | `CCXT` |
| Visualization | `Plotly` |
| Logging | `structlog` (JSON) |
| Config | `pydantic-settings` |

---

## Next Steps (Roadmap)

- [ ] OHLCV aggregation observer (1m, 5m, 15m candles)
- [ ] Tick imbalance and Kyle's lambda metrics
- [ ] Volatility regime detector (HMM-based)
- [ ] Similarity search on 30-minute market windows
- [ ] Plotly dashboard with live charts
- [ ] Hypothesis: "does volume > 2σ precede a 0.3% price move?"
- [ ] PostgreSQL migration for production scale
- [ ] Prometheus metrics endpoint `/metrics`
- [ ] Alerting on regime transitions

---

## License

MIT
