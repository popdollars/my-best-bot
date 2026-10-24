"""Central configuration for Alpaca BTC/USD."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

def _env(name: str, default=None, cast=str):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "": return default
    raw = raw.strip()
    try:
        if cast is bool: return raw.lower() in ("1", "true", "yes", "on")
        return cast(raw)
    except ValueError: return default

@dataclass(frozen=True)
class Config:
    # --- Alpaca Connection ---
    ALPACA_API_KEY: str = _env("ALPACA_API_KEY", "")
    ALPACA_SECRET_KEY: str = _env("ALPACA_SECRET_KEY", "")
    ALLOW_LIVE_TRADING: bool = _env("ALLOW_LIVE_TRADING", False, bool)

    # --- Instrument (BTC ONLY) ---
    SYMBOL: str = "BTC/USD"
    MAGIC_NUMBER: int = 26102401
    
    # --- Indicators (M15) ---
    SMA_PERIOD: int = 20
    BB_STD: float = 2.0
    RSI_PERIOD: int = 14
    RSI_OVERBOUGHT: float = 70.0
    RSI_OVERSOLD: float = 30.0
    CANDLES_TO_FETCH: int = 400
    DATA_REFRESH_SEC: float = 5.0
    SPREAD_LOOKBACK_BARS: int = 96

    # --- Session (Crypto trades 24/7, but we keep session logic for grid) ---
    SESSION_START_HOUR_UTC: int = 0
    SESSION_END_HOUR_UTC: int = 23
    SKIP_WEEKEND: bool = False

    # --- Grid (Tuned for Bitcoin) ---
    BASE_LOT: float = 0.001 # 0.001 BTC (~)
    MAX_POSITIONS: int = 3
    GRID_STEP_PIPS: float = 100.0 #  movement per grid level
    GROUP_SL_BUFFER_PIPS: float = 50.0
    TP_BREAKEVEN_FLOOR: bool = True
    TP_MIN_PROFIT_PIPS: float = 10.0
    GROUP_SL_COOLDOWN_MIN: float = 60.0

    # --- Risk ---
    KILL_SWITCH_PCT: float = 5.0
    TRAILING_DD_PCT: float = 1.5
    SPREAD_MULTIPLIER: float = 1.5
    MAX_SPREAD_PIPS: float = 50.0
    SPREAD_FLOOR_POINTS: float = 5.0

    # --- Loop timings ---
    RISK_INTERVAL_SEC: float = 0.5
    STRATEGY_INTERVAL_SEC: float = 1.0
    HEARTBEAT_INTERVAL_SEC: float = 5.0

    # --- Execution ---
    MAX_RETRIES: int = 3
    CLOSE_RETRIES: int = 3
    RETRY_DELAY_SEC: float = 0.5

    # --- Telegram ---
    TELEGRAM_TOKEN: str | None = _env("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID: str | None = _env("TELEGRAM_CHAT_ID")

    # --- Paths / logging ---
    LOG_DIR: str = str(ROOT / "logs")
    STATE_DIR: str = str(ROOT / "state")
    LOG_LEVEL: str = "INFO"

def load_config() -> Config:
    return Config()
