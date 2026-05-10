"""
agents/risk_agent.py — Risk Manager Agent
Enforces strict capital protection rules. If risk says NO, no signal fires.
Non-negotiable: this agent has veto power over all signals.
"""
import logging
from datetime import date, datetime
from typing import Dict, Tuple
import config
from core import database as db

logger = logging.getLogger(__name__)


class RiskAgent:
    """
    Risk Manager Agent — strict capital protection.

    Rules (non-negotiable):
    1. Max 0.5–1% risk per trade
    2. Max 2–3% daily risk
    3. Stop after 2 consecutive losses
    4. Drawdown protection
    5. Position size calculation
    """

    def __init__(self):
        self.name = "RiskAgent"
        self.status = "idle"
        self.halted = False
        self.halt_reason = ""
        self.daily_risk_used = 0.0
        self._last_check_date = None

    def _reset_daily_if_new_day(self):
        today = date.today().isoformat()
        if self._last_check_date != today:
            self._last_check_date = today
            self.daily_risk_used = 0.0
            if self.halted and "daily" in self.halt_reason.lower():
                self.halted = False
                self.halt_reason = ""
                logger.info("RiskAgent: New trading day — daily limits reset")

    def run(self, analysis: Dict, expiry: int) -> Dict:
        """
        Evaluate whether a trade is allowed.

        Returns:
            {
              "approved": bool,
              "reason": str,           # why approved or denied
              "position_size": float,  # % of capital to risk
              "max_loss_usd": float,   # dollar amount at risk
              "risk_level": str,       # LOW / MEDIUM / HIGH
              "daily_risk_used": float,
              "consecutive_losses": int,
              "warnings": list[str],
            }
        """
        self.status = "running"
        self._reset_daily_if_new_day()

        warnings = []
        today_stat = db.get_todays_stat()
        consec_losses = db.get_consecutive_losses()
        daily_signals = today_stat.get("total_signals", 0)
        daily_losses  = today_stat.get("losses", 0)
        daily_wins    = today_stat.get("wins", 0)

        # ── Rule 1: Halt Check ─────────────────────────────────────────────
        if self.halted:
            return self._denied(f"HALT: {self.halt_reason}", consec_losses, warnings)

        # ── Rule 2: Consecutive Loss Limit ─────────────────────────────────
        if consec_losses >= config.MAX_CONSECUTIVE_LOSSES:
            self.halted = True
            self.halt_reason = f"{consec_losses} consecutive losses — cooling off"
            db.log_risk_event("HALT_CONSECUTIVE_LOSSES",
                              f"{consec_losses} consecutive losses", consec_losses)
            return self._denied(self.halt_reason, consec_losses, warnings)

        # ── Rule 3: Daily Risk Limit ───────────────────────────────────────
        # Estimate daily risk used from daily losses
        estimated_daily_risk = (daily_losses * config.MAX_RISK_PER_TRADE)
        if estimated_daily_risk >= config.MAX_DAILY_RISK:
            self.halted = True
            self.halt_reason = f"Daily risk limit reached ({estimated_daily_risk:.1f}% of capital)"
            db.log_risk_event("HALT_DAILY_RISK", self.halt_reason, estimated_daily_risk)
            return self._denied(self.halt_reason, consec_losses, warnings)

        # ── Warning: approaching daily limit ──────────────────────────────
        if estimated_daily_risk >= config.MAX_DAILY_RISK * 0.7:
            warnings.append(
                f"⚠️ Daily risk at {estimated_daily_risk:.1f}% — "
                f"limit {config.MAX_DAILY_RISK:.1f}%"
            )

        # ── Rule 4: Warn on high signals count ────────────────────────────
        if daily_signals >= 10:
            warnings.append(f"⚠️ {daily_signals} signals today — quality may be declining")

        # ── Rule 5: Consecutive loss warning ──────────────────────────────
        if consec_losses == config.MAX_CONSECUTIVE_LOSSES - 1:
            warnings.append(
                f"⚠️ {consec_losses} consecutive loss(es) — one more triggers halt"
            )

        # ── Position Sizing ────────────────────────────────────────────────
        confidence = analysis.get("confidence", 75.0)
        atr        = analysis.get("atr", 0.0)
        price      = analysis.get("price", 1.0)

        # Scale position size with confidence (lower confidence = smaller size)
        confidence_scalar = min(confidence / 100.0, 1.0)
        position_size = round(
            config.MAX_RISK_PER_TRADE * confidence_scalar * 0.8, 2
        )  # 80% of max to be conservative
        position_size = max(0.25, min(position_size, config.MAX_RISK_PER_TRADE))
        max_loss_usd  = round(config.CAPITAL * position_size / 100, 2)

        # ── Risk Level ─────────────────────────────────────────────────────
        vol_pct = (atr / price * 100) if price > 0 else 0.0
        if vol_pct > 1.0 or expiry <= 5:
            risk_level = "HIGH"
        elif vol_pct > 0.5 or expiry <= 15:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        result = {
            "approved": True,
            "reason": "Risk checks passed ✅",
            "position_size": position_size,
            "max_loss_usd": max_loss_usd,
            "risk_level": risk_level,
            "daily_risk_used": estimated_daily_risk,
            "consecutive_losses": consec_losses,
            "warnings": warnings,
        }

        self.status = "done"
        logger.info(
            "RiskAgent: APPROVED — size=%.2f%% maxLoss=$%.2f risk=%s",
            position_size, max_loss_usd, risk_level
        )
        return result

    def record_trade_result(self, win: bool):
        """Called after a signal outcome is known."""
        if win:
            logger.info("RiskAgent: WIN recorded")
        else:
            self.daily_risk_used += config.MAX_RISK_PER_TRADE
            logger.info("RiskAgent: LOSS recorded (daily risk used: %.2f%%)",
                        self.daily_risk_used)

    def force_halt(self, reason: str):
        """Manually halt trading."""
        self.halted = True
        self.halt_reason = reason
        db.log_risk_event("MANUAL_HALT", reason)
        logger.warning("RiskAgent: MANUAL HALT — %s", reason)

    def resume(self):
        """Resume trading after manual review."""
        self.halted = False
        self.halt_reason = ""
        logger.info("RiskAgent: Trading resumed")

    @staticmethod
    def _denied(reason: str, consec: int, warnings: list) -> Dict:
        return {
            "approved": False,
            "reason": f"❌ {reason}",
            "position_size": 0.0,
            "max_loss_usd": 0.0,
            "risk_level": "BLOCKED",
            "daily_risk_used": 0.0,
            "consecutive_losses": consec,
            "warnings": warnings,
        }

    def get_status(self) -> Dict:
        """Return current risk status for dashboard."""
        today = db.get_todays_stat()
        consec = db.get_consecutive_losses()
        return {
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "consecutive_losses": consec,
            "daily_losses": today.get("losses", 0),
            "daily_wins":   today.get("wins", 0),
            "daily_signals": today.get("total_signals", 0),
            "daily_risk_used": today.get("losses", 0) * config.MAX_RISK_PER_TRADE,
            "max_daily_risk": config.MAX_DAILY_RISK,
            "max_consecutive": config.MAX_CONSECUTIVE_LOSSES,
            "capital": config.CAPITAL,
        }
