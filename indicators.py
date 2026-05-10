"""
core/indicators.py — All technical indicator calculations.
Pure math functions. No I/O. Fast numpy-based implementations.
"""
import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional


def safe_divide(a, b, default=0.0):
    """Safe division avoiding ZeroDivisionError."""
    return a / b if (b != 0 and not np.isnan(b)) else default


def ema(series: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    k = 2.0 / (period + 1)
    result = np.zeros(len(series))
    result[0] = series[0]
    for i in range(1, len(series)):
        result[i] = series[i] * k + result[i - 1] * (1 - k)
    return result


def sma(series: np.ndarray, period: int) -> float:
    """Simple Moving Average (last value)."""
    if len(series) < period:
        return float(np.mean(series))
    return float(np.mean(series[-period:]))


def rsi(close: np.ndarray, period: int = 14) -> float:
    """Relative Strength Index."""
    if len(close) < period + 1:
        return 50.0
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def macd(close: np.ndarray, fast=12, slow=26, signal=9) -> Dict:
    """MACD line, signal line, histogram."""
    if len(close) < slow + signal:
        return {"line": 0.0, "signal": 0.0, "hist": 0.0}
    e_fast = ema(close, fast)
    e_slow = ema(close, slow)
    macd_line = e_fast - e_slow
    sig_line = ema(macd_line, signal)
    return {
        "line": float(macd_line[-1]),
        "signal": float(sig_line[-1]),
        "hist": float(macd_line[-1] - sig_line[-1]),
    }


def bollinger_bands(close: np.ndarray, period=20, std_dev=2.0) -> Dict:
    """Bollinger Bands: upper, lower, middle, %B, bandwidth, squeeze."""
    n = min(period, len(close))
    window = close[-n:]
    mid = float(np.mean(window))
    std = float(np.std(window)) or 1e-10
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    price = close[-1]
    pct_b = (price - lower) / (upper - lower) * 100
    bw = (upper - lower) / (mid or 1e-10)
    return {
        "upper": upper, "lower": lower, "mid": mid,
        "pct_b": float(np.clip(pct_b, 0, 100)),
        "bw": float(bw),
        "squeeze": bw < 0.015,
    }


def stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               k_period=14, d_period=3) -> Dict:
    """Stochastic Oscillator %K and %D."""
    n = min(k_period, len(close))
    hh = np.max(high[-n:])
    ll = np.min(low[-n:])
    k = safe_divide(close[-1] - ll, hh - ll, 0.5) * 100
    # %D as simple average of last 3 %K values
    k_vals = []
    for i in range(d_period):
        idx = len(close) - d_period + i
        if idx >= n:
            h_ = np.max(high[max(0, idx - n + 1):idx + 1])
            l_ = np.min(low[max(0, idx - n + 1):idx + 1])
            k_vals.append(safe_divide(close[idx] - l_, h_ - l_, 0.5) * 100)
    d = float(np.mean(k_vals)) if k_vals else k
    return {"k": float(np.clip(k, 0, 100)), "d": float(np.clip(d, 0, 100))}


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period=14) -> float:
    """Average True Range."""
    if len(close) < 2:
        return float(np.mean(high - low))
    tr = np.maximum(high[1:] - low[1:],
          np.maximum(np.abs(high[1:] - close[:-1]),
                     np.abs(low[1:] - close[:-1])))
    return float(np.mean(tr[-period:]))


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period=14) -> Dict:
    """Average Directional Index with +DI/-DI."""
    if len(close) < period + 1:
        return {"adx": 0.0, "pdi": 0.0, "ndi": 0.0}
    tr_list, pdm_list, ndm_list = [], [], []
    for i in range(1, len(close)):
        tr_val = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        pdm_list.append(up if up > down and up > 0 else 0.0)
        ndm_list.append(down if down > up and down > 0 else 0.0)
        tr_list.append(tr_val)
    tr_arr = np.array(tr_list[-period:])
    pdm_arr = np.array(pdm_list[-period:])
    ndm_arr = np.array(ndm_list[-period:])
    atr_val = np.mean(tr_arr) or 1e-10
    pdi = float(np.mean(pdm_arr) / atr_val * 100)
    ndi = float(np.mean(ndm_arr) / atr_val * 100)
    dx = abs(pdi - ndi) / (pdi + ndi or 1e-10) * 100
    return {"adx": float(dx), "pdi": pdi, "ndi": ndi}


def ichimoku(high: np.ndarray, low: np.ndarray) -> Dict:
    """Ichimoku Cloud: Tenkan, Kijun, Senkou A, Senkou B."""
    def mid_line(h, l, n):
        n = min(n, len(h))
        return (np.max(h[-n:]) + np.min(l[-n:])) / 2

    tenkan = mid_line(high, low, 9)
    kijun  = mid_line(high, low, 26)
    senkou_a = (tenkan + kijun) / 2
    senkou_b = mid_line(high, low, 52)
    cloud_top = max(senkou_a, senkou_b)
    cloud_bot = min(senkou_a, senkou_b)
    return {
        "tenkan": float(tenkan),
        "kijun":  float(kijun),
        "senkou_a": float(senkou_a),
        "senkou_b": float(senkou_b),
        "cloud_top": float(cloud_top),
        "cloud_bot": float(cloud_bot),
    }


def williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               period=14) -> float:
    """Williams %R."""
    n = min(period, len(close))
    hh = np.max(high[-n:])
    ll = np.min(low[-n:])
    return float(-safe_divide(hh - close[-1], hh - ll, 0.5) * 100)


def cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period=20) -> float:
    """Commodity Channel Index."""
    n = min(period, len(close))
    tp = (high[-n:] + low[-n:] + close[-n:]) / 3
    m = np.mean(tp)
    md = np.mean(np.abs(tp - m)) or 1e-10
    return float((tp[-1] - m) / (0.015 * md))


def vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray,
          volume: np.ndarray, period=20) -> float:
    """Volume-Weighted Average Price."""
    n = min(period, len(close))
    tp = (high[-n:] + low[-n:] + close[-n:]) / 3
    vol = volume[-n:]
    total_vol = np.sum(vol) or 1e-10
    return float(np.sum(tp * vol) / total_vol)


def ema_ribbon(close: np.ndarray) -> Dict:
    """EMA ribbon: 8, 13, 21, 55, 200."""
    return {
        "e8":   float(ema(close, 8)[-1]),
        "e13":  float(ema(close, 13)[-1]),
        "e21":  float(ema(close, 21)[-1]),
        "e55":  float(ema(close, 55)[-1]),
        "e200": float(ema(close, min(200, len(close)))[-1]),
    }


def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """Convert OHLCV to Heikin-Ashi candles."""
    ha = pd.DataFrame(index=df.index)
    ha["close"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha["open"]  = 0.0
    ha.iloc[0, ha.columns.get_loc("open")] = (df["open"].iloc[0] + df["close"].iloc[0]) / 2
    for i in range(1, len(ha)):
        ha.iloc[i, ha.columns.get_loc("open")] = (
            ha["open"].iloc[i - 1] + ha["close"].iloc[i - 1]) / 2
    ha["high"]   = np.maximum(df["high"], np.maximum(ha["open"], ha["close"]))
    ha["low"]    = np.minimum(df["low"],  np.minimum(ha["open"], ha["close"]))
    ha["volume"] = df["volume"] if "volume" in df.columns else 1.0
    # Derived fields
    ha["green"]  = ha["close"] >= ha["open"]
    rng = (ha["high"] - ha["low"]).replace(0, 1e-9)
    ha["no_upper_wick"] = (ha["high"] - ha[["open", "close"]].max(axis=1)) / rng < 0.05
    ha["no_lower_wick"] = (ha[["open", "close"]].min(axis=1) - ha["low"]) / rng < 0.05
    return ha


def ha_stats(ha: pd.DataFrame) -> Dict:
    """Summarize recent Heikin-Ashi candle state."""
    if ha is None or len(ha) < 3:
        return {"bull": True, "count": 1, "changed": False, "strong": False}
    last_green = bool(ha["green"].iloc[-1])
    prev_green = bool(ha["green"].iloc[-2])
    changed    = last_green != prev_green
    # Count consecutive same-color candles
    count = 1
    for i in range(len(ha) - 2, -1, -1):
        if ha["green"].iloc[i] == last_green:
            count += 1
        else:
            break
    strong = changed and (
        (last_green and bool(ha["no_lower_wick"].iloc[-1])) or
        (not last_green and bool(ha["no_upper_wick"].iloc[-1]))
    )
    return {
        "bull": last_green,
        "count": count,
        "changed": changed,
        "strong": strong,
        "no_upper_wick": bool(ha["no_upper_wick"].iloc[-1]),
        "no_lower_wick": bool(ha["no_lower_wick"].iloc[-1]),
    }


def support_resistance(high: np.ndarray, low: np.ndarray,
                        close: np.ndarray, period=20) -> Dict:
    """Basic support and resistance levels from recent pivots."""
    n = min(period, len(close))
    resistance = float(np.max(high[-n:]))
    support    = float(np.min(low[-n:]))
    price      = float(close[-1])
    mid        = (resistance + support) / 2
    near_support    = (price - support) / (resistance - support or 1) < 0.15
    near_resistance = (resistance - price) / (resistance - support or 1) < 0.15
    return {
        "support": support,
        "resistance": resistance,
        "mid": mid,
        "near_support": near_support,
        "near_resistance": near_resistance,
    }


def volatility_score(atr_val: float, close: float) -> float:
    """Normalize ATR as % of price."""
    return safe_divide(atr_val, close, 0.0) * 100
