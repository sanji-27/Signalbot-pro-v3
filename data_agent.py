"""
agents/data_agent.py — Data Agent
Fetches OHLCV price data from Yahoo Finance and Binance.
Handles caching, retries, and multi-timeframe data.
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import pandas as pd
import numpy as np
import requests
import yfinance as yf
import config

logger = logging.getLogger(__name__)

# Simple in-memory cache: key -> (timestamp, DataFrame)
_cache: Dict[str, Tuple[float, pd.DataFrame]] = {}
CACHE_TTL = 60  # seconds


def _cache_key(ticker: str, interval: str) -> str:
    return f"{ticker}_{interval}"


def _from_cache(ticker: str, interval: str) -> Optional[pd.DataFrame]:
    key = _cache_key(ticker, interval)
    if key in _cache:
        ts, df = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return df.copy()
    return None


def _to_cache(ticker: str, interval: str, df: pd.DataFrame):
    key = _cache_key(ticker, interval)
    _cache[key] = (time.time(), df.copy())


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names to lowercase and fill NaN."""
    df.columns = [c.lower() for c in df.columns]
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" not in df.columns:
        df["volume"] = 1.0
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    return df


def fetch_yahoo(ticker: str, interval: str, period: str,
                retries: int = 3) -> Optional[pd.DataFrame]:
    """Fetch OHLCV from Yahoo Finance with retry logic."""
    cached = _from_cache(ticker, interval)
    if cached is not None and len(cached) >= 50:
        logger.debug("Cache hit: %s %s (%d bars)", ticker, interval, len(cached))
        return cached

    for attempt in range(retries):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval, auto_adjust=True)
            if df is None or len(df) < 30:
                raise ValueError(f"Not enough data ({len(df) if df is not None else 0} bars)")
            df = _normalize(df)
            _to_cache(ticker, interval, df)
            logger.debug("Yahoo: %s %s → %d bars", ticker, interval, len(df))
            return df
        except Exception as e:
            logger.warning("Yahoo attempt %d/%d failed for %s: %s",
                           attempt + 1, retries, ticker, e)
            time.sleep(2 ** attempt)
    return None


def fetch_binance(symbol: str, interval: str, limit: int = 200) -> Optional[pd.DataFrame]:
    """Fetch OHLCV from Binance public API."""
    # Map intervals to Binance format
    interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                    "1h": "1h", "4h": "4h", "1d": "1d"}
    b_interval = interval_map.get(interval, interval)
    cached = _from_cache(symbol, b_interval)
    if cached is not None and len(cached) >= 50:
        return cached

    try:
        url = "https://api.binance.com/api/v3/klines"
        resp = requests.get(url, params={
            "symbol": symbol, "interval": b_interval, "limit": limit
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("timestamp")
        df = _normalize(df)
        _to_cache(symbol, b_interval, df)
        logger.debug("Binance: %s %s → %d bars", symbol, b_interval, len(df))
        return df
    except Exception as e:
        logger.warning("Binance fetch failed for %s: %s", symbol, e)
        return None


def fetch_asset(ticker: str, interval: str, period: str,
                asset_type: str = "forex") -> Optional[pd.DataFrame]:
    """Main entry point: fetch data for any asset type."""
    if asset_type == "crypto":
        # Try Binance first, fall back to Yahoo
        binance_sym = ticker.replace("-USD", "USDT").replace("/", "")
        df = fetch_binance(binance_sym, interval)
        if df is None or len(df) < 30:
            df = fetch_yahoo(ticker, interval, period)
    else:
        df = fetch_yahoo(ticker, interval, period)
    return df


def fetch_composite(components: list, interval: str, period: str) -> Optional[pd.DataFrame]:
    """Build composite index from weighted component assets."""
    dfs = []
    for ticker, weight in components:
        asset_type = "crypto" if "BTC" in ticker or "ETH" in ticker or "BNB" in ticker else "forex"
        df = fetch_asset(ticker, interval, period, asset_type)
        if df is not None and len(df) >= 30:
            # Normalize to % returns for compositing
            ref = df["close"].iloc[0] or 1.0
            df[f"norm_{ticker}"] = df["close"] / ref * weight
            dfs.append((ticker, weight, df))

    if not dfs:
        return None

    # Align on common index and sum weighted normalized prices
    base = dfs[0][2].copy()
    composite_close = base[f"norm_{dfs[0][0]}"].copy()
    for ticker, weight, df in dfs[1:]:
        aligned = df[f"norm_{ticker}"].reindex(base.index, method="ffill")
        composite_close = composite_close + aligned.fillna(0)

    result = pd.DataFrame(index=base.index)
    result["close"]  = composite_close * 100  # scale to readable number
    result["open"]   = composite_close.shift(1).fillna(composite_close) * 100
    result["high"]   = result[["open", "close"]].max(axis=1) * 1.001
    result["low"]    = result[["open", "close"]].min(axis=1) * 0.999
    result["volume"] = 1.0
    return result.dropna()


class DataAgent:
    """
    Data Agent — responsible for:
    - Fetching primary timeframe data
    - Fetching confirmation timeframe data
    - Handling rate limits and errors
    - Providing clean OHLCV DataFrames
    """

    def __init__(self):
        self.name = "DataAgent"
        self.status = "idle"
        self.last_fetch = None
        self.error_count = 0

    def run(self, asset_config: Dict, expiry: int) -> Dict:
        """
        Fetch data for primary and confirmation timeframes.

        Returns:
            {
              "primary": DataFrame,
              "confirm": DataFrame,
              "source": str,
              "bars": int,
            }
        """
        self.status = "running"
        result = {"primary": None, "confirm": None, "source": "unknown", "bars": 0}

        tf_config = config.TIMEFRAME_MAP.get(expiry, ("15m", "5d", "1h"))
        primary_interval, period, confirm_interval = tf_config

        try:
            asset_type = asset_config.get("type", "forex")
            ticker     = asset_config.get("ticker", "")
            is_composite = asset_type == "composite"

            if is_composite:
                components = asset_config.get("components", [])
                primary = fetch_composite(components, primary_interval, period)
                confirm = fetch_composite(components, confirm_interval, "30d")
                source = "composite"
            else:
                primary = fetch_asset(ticker, primary_interval, period, asset_type)
                confirm = fetch_asset(ticker, confirm_interval, "30d", asset_type)
                source = "yahoo" if asset_type in ("forex", "otc") else "binance"

            if primary is None or len(primary) < 50:
                logger.warning("DataAgent: insufficient primary data for %s",
                               asset_config.get("symbol"))
                self.status = "error"
                self.error_count += 1
                return result

            result["primary"] = primary
            result["confirm"] = confirm
            result["source"]  = source
            result["bars"]    = len(primary)
            self.status = "done"
            self.last_fetch = datetime.utcnow().isoformat()
            self.error_count = 0
            logger.debug("DataAgent: %s → %d bars (%s)",
                         asset_config.get("symbol"), len(primary), primary_interval)

        except Exception as e:
            logger.error("DataAgent error for %s: %s",
                         asset_config.get("symbol", "?"), e, exc_info=True)
            self.status = "error"
            self.error_count += 1

        return result
