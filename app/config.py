from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    app_log_level: str = "INFO"

    # Binance WebSocket
    binance_ws_url: str = "wss://stream.binance.com:9443/ws"
    binance_symbols: str = "BTCUSDT,ETHUSDT"
    binance_reconnect_delay: int = 5
    binance_max_reconnects: int = 0  # 0 = unlimited

    # Database
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR}/data/market.db"

    # Dashboard
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000
    dashboard_reload: bool = False

    # MT5
    mt5_enabled: bool = False
    mt5_symbols: str = "WINM25,WDOM25"
    mt5_poll_interval: int = 1  # seconds between tick polls

    # Paths
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"

    @field_validator("app_log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log level must be one of {valid}")
        return upper

    @property
    def symbols_list(self) -> List[str]:
        return [s.strip().upper() for s in self.binance_symbols.split(",") if s.strip()]

    @property
    def mt5_symbols_list(self) -> List[str]:
        return [s.strip().upper() for s in self.mt5_symbols.split(",") if s.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "raw").mkdir(exist_ok=True)
        (self.data_dir / "processed").mkdir(exist_ok=True)
        (self.data_dir / "features").mkdir(exist_ok=True)
        (self.data_dir / "snapshots").mkdir(exist_ok=True)
        (self.data_dir / "models").mkdir(exist_ok=True)


settings = Settings()
