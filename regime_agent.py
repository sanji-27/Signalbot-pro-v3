"""
agents/regime_agent.py — Market Regime Agent
Detects whether the market is trending, ranging, volatile, or weak.
Used to adjust confidence scores and filter low-quality environments.
"""
import logging
from typing import Dict
from core import indicators as ind
import numpy as np

logger = logging.getLogger(__name__)

REGIME_TRENDING  = "trending"
REGIME_RANGING   = "ranging"
REGIME_VOLATILE  = "volatile"
REGIME_WEAK      = "weak"


class RegimeAgent:
    """
    Market Regime Agent — classifies market environment.
    Output is used by Oracle to adjust confidence and filter signals.
    """

    def __init__(self):
        self.name = "RegimeAgent"
        self.status = "idle"
        self.last_regime = None

    def run(self, analysis: Dict) -> Dict:
        """
        Classify market regime from technical analysis.

        Returns:
            {
              "regime": str,           # trending/ranging/volatile/weak
              "label": str,            # human-readable label
              "confidence_mult": float, # multiplier for Oracle confidence
              "tradeable": bool,       # whether this regime is worth trading
              "adx": float,
              "volatility": float,
              "squeeze": bool,
              "detail": str,
            }
        """
        self.status = "running"

        if "error" in analysis:
            return self._default()

        try:
            adx_data  = analysis.get("adx", {})
            bb_data   = analysis.get("bb", {})
            vol_score = analysis.get("vol_score", 0.0)
            adx_val   = adx_data.get("adx", 0.0)
            bb_sq     = bb_data.get("squeeze", False)
            bb_bw     = bb_data.get("bw", 0.02)

            # ── Regime Classification ────────────────────────────────────────
            if adx_val >= 30 and not bb_sq:
                regime = REGIME_TRENDING
                label  = "🟢 STRONG TREND"
                mult   = 1.05   # bonus for trending markets
                tradeable = True

            elif 20 <= adx_val < 30:
                regime = REGIME_TRENDING
                label  = "🟡 TRENDING"
                mult   = 1.0
                tradeable = True

            elif adx_val < 15 or bb_sq:
                regime = REGIME_RANGING
                label  = "🔴 RANGING"
                mult   = 0.60   # heavy penalty — avoid this
                tradeable = False

            elif vol_score > 1.5:
                regime = REGIME_VOLATILE
                label  = "🟠 HIGH VOLATILITY"
                mult   = 0.75
                tradeable = True  # high vol can still trend

            else:
                regime = REGIME_WEAK
                label  = "⚪ WEAK TREND"
                mult   = 0.80
                tradeable = True

            detail = (
                f"ADX={adx_val:.1f} | BW={bb_bw:.4f} | "
                f"Squeeze={'YES' if bb_sq else 'NO'} | Vol={vol_score:.3f}%"
            )

            result = {
                "regime": regime,
                "label": label,
                "confidence_mult": mult,
                "tradeable": tradeable,
                "adx": adx_val,
                "volatility": vol_score,
                "squeeze": bb_sq,
                "detail": detail,
            }

            self.status = "done"
            self.last_regime = result
            logger.debug("RegimeAgent: %s (ADX=%.1f, mult=%.2f)", regime, adx_val, mult)
            return result

        except Exception as e:
            logger.error("RegimeAgent error: %s", e, exc_info=True)
            self.status = "error"
            return self._default()

    @staticmethod
    def _default() -> Dict:
        return {
            "regime": REGIME_WEAK, "label": "⚪ UNKNOWN",
            "confidence_mult": 0.7, "tradeable": False,
            "adx": 0.0, "volatility": 0.0, "squeeze": False,
            "detail": "Insufficient data",
        }
