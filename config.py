"""
config.py — Loads all settings from .env file.
No sensitive info is ever hardcoded here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── SIGNAL THRESHOLDS ────────────────────────────────────────────────────────
MIN_CONFIDENCE    = float(os.getenv("MIN_CONFIDENCE", "75"))
ELITE_CONFIDENCE  = float(os.getenv("ELITE_CONFIDENCE", "88"))
HIGH_QUALITY_ONLY = os.getenv("HIGH_QUALITY_ONLY", "true").lower() == "true"

# ─── RISK MANAGEMENT ──────────────────────────────────────────────────────────
MAX_RISK_PER_TRADE     = float(os.getenv("MAX_RISK_PER_TRADE", "1.0"))
MAX_DAILY_RISK         = float(os.getenv("MAX_DAILY_RISK", "3.0"))
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "2"))
CAPITAL                = float(os.getenv("CAPITAL", "1000"))
SL_ATR_MULT            = float(os.getenv("STOP_LOSS_ATR_MULT", "1.5"))
TP_ATR_MULT            = float(os.getenv("TAKE_PROFIT_ATR_MULT", "2.5"))

# ─── SCAN SETTINGS ────────────────────────────────────────────────────────────
SCAN_ENABLED  = os.getenv("SCAN_ENABLED", "true").lower() == "true"
SCAN_EXPIRIES = [int(x) for x in os.getenv("SCAN_EXPIRIES", "5,10,15,20,30,40,60").split(",")]

# ─── DATA ─────────────────────────────────────────────────────────────────────
TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_KEY", "")

# ─── WEB DASHBOARD ────────────────────────────────────────────────────────────
FLASK_PORT       = int(os.getenv("FLASK_PORT", "5000"))
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

# ─── LOGGING ──────────────────────────────────────────────────────────────────
LOG_LEVEL   = os.getenv("LOG_LEVEL", "INFO")
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").lower() == "true"
DB_PATH     = os.getenv("DB_PATH", "signals.db")

# ─── ASSETS ───────────────────────────────────────────────────────────────────
FOREX_ASSETS = [
    # symbol,        yfinance_ticker,  display_name,   type
    ("AUD/CAD",      "AUDCAD=X",       "AUD/CAD",      "forex"),
    ("AUD/JPY",      "AUDJPY=X",       "AUD/JPY",      "forex"),
    ("AUD/USD",      "AUDUSD=X",       "AUD/USD",      "forex"),
    ("EUR/USD",      "EURUSD=X",       "EUR/USD",      "forex"),
    ("EUR/JPY",      "EURJPY=X",       "EUR/JPY",      "forex"),
    ("EUR/GBP",      "EURGBP=X",       "EUR/GBP",      "forex"),
    ("EUR/AUD",      "EURAUD=X",       "EUR/AUD",      "forex"),
    ("EUR/CAD",      "EURCAD=X",       "EUR/CAD",      "forex"),
    ("EUR/CHF",      "EURCHF=X",       "EUR/CHF",      "forex"),
    ("GBP/USD",      "GBPUSD=X",       "GBP/USD",      "forex"),
    ("GBP/AUD",      "GBPAUD=X",       "GBP/AUD",      "forex"),
    ("GBP/CAD",      "GBPCAD=X",       "GBP/CAD",      "forex"),
    ("CAD/JPY",      "CADJPY=X",       "CAD/JPY",      "forex"),
    ("NZD/USD",      "NZDUSD=X",       "NZD/USD",      "forex"),
    ("USD/JPY",      "USDJPY=X",       "USD/JPY",      "forex"),
    ("GBP/JPY",      "GBPJPY=X",       "GBP/JPY",      "forex"),
]

OTC_ASSETS = [
    ("EUR/USD_OTC",  "EURUSD=X",       "EUR/USD OTC",  "otc"),
    ("GBP/USD_OTC",  "GBPUSD=X",       "GBP/USD OTC",  "otc"),
    ("AUD/USD_OTC",  "AUDUSD=X",       "AUD/USD OTC",  "otc"),
    ("USD/JPY_OTC",  "USDJPY=X",       "USD/JPY OTC",  "otc"),
    ("EUR/JPY_OTC",  "EURJPY=X",       "EUR/JPY OTC",  "otc"),
    ("GBP/JPY_OTC",  "GBPJPY=X",       "GBP/JPY OTC",  "otc"),
    ("EUR/GBP_OTC",  "EURGBP=X",       "EUR/GBP OTC",  "otc"),
    ("AUD/JPY_OTC",  "AUDJPY=X",       "AUD/JPY OTC",  "otc"),
    ("CAD/JPY_OTC",  "CADJPY=X",       "CAD/JPY OTC",  "otc"),
]

CRYPTO_ASSETS = [
    ("BTC/USD",      "BTC-USD",        "BTC/USD",      "crypto"),
    ("ETH/USD",      "ETH-USD",        "ETH/USD",      "crypto"),
]

# Composite indices (computed from component weights)
COMPOSITE_ASSETS = [
    {
        "symbol": "ASIA_IDX",
        "name": "Asia Composite Index",
        "type": "composite",
        "components": [
            ("USDJPY=X", 0.35),
            ("AUDUSD=X", 0.30),
            ("NZDUSD=X", 0.20),
            ("AUDJPY=X", 0.15),
        ],
    },
    {
        "symbol": "CRYPTO_IDX",
        "name": "Crypto Composite Index",
        "type": "composite",
        "components": [
            ("BTC-USD", 0.50),
            ("ETH-USD", 0.35),
            ("BNB-USD", 0.15),
        ],
    },
    {
        "symbol": "COMPOUND_IDX",
        "name": "Compound Index",
        "type": "composite",
        "components": [
            ("EURUSD=X", 0.25),
            ("GBPUSD=X", 0.25),
            ("AUDUSD=X", 0.25),
            ("USDJPY=X", 0.25),
        ],
    },
]

ALL_SIMPLE_ASSETS = FOREX_ASSETS + OTC_ASSETS + CRYPTO_ASSETS

# Timeframe map: expiry_minutes -> (yfinance_interval, yfinance_period, confirm_interval)
TIMEFRAME_MAP = {
    5:  ("5m",  "2d",  "15m"),
    10: ("5m",  "2d",  "15m"),
    15: ("15m", "5d",  "1h"),
    20: ("15m", "5d",  "1h"),
    30: ("30m", "10d", "1h"),
    40: ("30m", "10d", "1h"),
    60: ("1h",  "30d", "4h"),
}
