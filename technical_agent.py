"""
agents/technical_agent.py — Technical Analyst Agent
Runs all indicators on OHLCV data and produces a structured analysis dict.
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, Optional
from core import indicators as ind

logger = logging.getLogger(__name__)


class TechnicalAgent:
    """
    Technical Analyst Agent — responsible for:
    - Computing all technical indicators
    - Building Heikin-Ashi candles
    - Producing structured analysis for the Oracle
    """

    def __init__(self):
        self.name = "TechnicalAgent"
        self.status = "idle"
        self.last_analysis = None

    def run(self, df: pd.DataFrame, df_confirm: Optional[pd.DataFrame] = None) -> Dict:
        """
        Analyze OHLCV DataFrame.

        Returns comprehensive analysis dict with all indicators.
        """
        self.status = "running"

        if df is None or len(df) < 50:
            self.status = "error"
            return {"error": "insufficient_data"}

        try:
            close  = df["close"].values.astype(float)
            high   = df["high"].values.astype(float)
            low    = df["low"].values.astype(float)
            volume = df["volume"].values.astype(float) if "volume" in df.columns else np.ones(len(close))

            # Heikin-Ashi
            ha_df  = ind.heikin_ashi(df)
            ha_st  = ind.ha_stats(ha_df)
            ha_c   = ha_df["close"].values.astype(float)
            ha_h   = ha_df["high"].values.astype(float)
            ha_l   = ha_df["low"].values.astype(float)

            # All indicators on HA candles for better signal quality
            rsi_val   = ind.rsi(ha_c)
            macd_val  = ind.macd(ha_c)
            bb_val    = ind.bollinger_bands(ha_c)
            stoch_val = ind.stochastic(ha_h, ha_l, ha_c)
            atr_val   = ind.atr(ha_h, ha_l, ha_c)
            adx_val   = ind.adx(ha_h, ha_l, ha_c)
            ich_val   = ind.ichimoku(ha_h, ha_l)
            wr_val    = ind.williams_r(ha_h, ha_l, ha_c)
            cci_val   = ind.cci(ha_h, ha_l, ha_c)
            vwap_val  = ind.vwap(ha_h, ha_l, ha_c, volume)
            ribbon    = ind.ema_ribbon(ha_c)
            sr        = ind.support_resistance(ha_h, ha_l, ha_c)
            vol_score = ind.volatility_score(atr_val, float(close[-1]))

            # Confirmation timeframe (higher TF direction)
            confirm_direction = 0
            if df_confirm is not None and len(df_confirm) >= 30:
                try:
                    c2 = df_confirm["close"].values.astype(float)
                    h2 = df_confirm["high"].values.astype(float)
                    l2 = df_confirm["low"].values.astype(float)
                    ha2  = ind.heikin_ashi(df_confirm)
                    ha2c = ha2["close"].values.astype(float)
                    ha2h = ha2["high"].values.astype(float)
                    ha2l = ha2["low"].values.astype(float)
                    ha2_st = ind.ha_stats(ha2)
                    macd2  = ind.macd(ha2c)
                    adx2   = ind.adx(ha2h, ha2l, ha2c)
                    rib2   = ind.ema_ribbon(ha2c)
                    # Simple consensus: HA + MACD + EMA ribbon
                    bull2 = sum([
                        1 if ha2_st["bull"] else -1,
                        1 if macd2["hist"] > 0 else -1,
                        1 if rib2["e8"] > rib2["e21"] else -1,
                    ])
                    confirm_direction = 1 if bull2 > 0 else -1 if bull2 < 0 else 0
                except Exception as e:
                    logger.debug("Confirm TF analysis failed: %s", e)

            price = float(close[-1])

            result = {
                "price": price,
                "ha": ha_st,
                "rsi": rsi_val,
                "macd": macd_val,
                "bb": bb_val,
                "stoch": stoch_val,
                "atr": atr_val,
                "adx": adx_val,
                "ichimoku": ich_val,
                "williams_r": wr_val,
                "cci": cci_val,
                "vwap": vwap_val,
                "ribbon": ribbon,
                "sr": sr,
                "vol_score": vol_score,
                "confirm_direction": confirm_direction,
                "bars": len(df),
            }

            self.status = "done"
            self.last_analysis = result
            logger.debug("TechnicalAgent: RSI=%.1f MACD=%.5f ADX=%.1f",
                         rsi_val, macd_val["hist"], adx_val["adx"])
            return result

        except Exception as e:
            logger.error("TechnicalAgent error: %s", e, exc_info=True)
            self.status = "error"
            return {"error": str(e)}
