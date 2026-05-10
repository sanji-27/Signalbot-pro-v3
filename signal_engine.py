"""
core/signal_engine.py — Signal Engine
Orchestrates all agents in sequence, enforces quality gates,
and returns a complete signal or rejection for each asset/expiry pair.
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime

import config
from agents.data_agent import DataAgent
from agents.technical_agent import TechnicalAgent
from agents.regime_agent import RegimeAgent
from agents.risk_agent import RiskAgent
from agents.oracle_agent import OracleAgent
from core import database as db

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Multi-Agent Signal Engine.
    Runs the full agent pipeline for a single asset/expiry pair.
    """

    def __init__(self, risk_agent: RiskAgent):
        self.data_agent      = DataAgent()
        self.technical_agent = TechnicalAgent()
        self.regime_agent    = RegimeAgent()
        self.risk_agent      = risk_agent  # shared instance (tracks daily state)
        self.oracle_agent    = OracleAgent()

        self.total_analyzed  = 0
        self.total_signals   = 0
        self.total_filtered  = 0

    def analyze(self, asset_config: Dict, expiry: int) -> Optional[Dict]:
        """
        Run the full pipeline for one asset + expiry.

        Args:
            asset_config: dict with symbol, ticker, type, name, components
            expiry: signal duration in minutes

        Returns:
            Signal dict if a signal fires, None otherwise.
        """
        symbol = asset_config.get("symbol", "UNKNOWN")
        self.total_analyzed += 1

        logger.debug("SignalEngine: analyzing %s @ %dmin", symbol, expiry)

        # ── Step 1: Data Agent ─────────────────────────────────────────────
        data = self.data_agent.run(asset_config, expiry)
        if data["primary"] is None:
            logger.debug("SignalEngine: no data for %s", symbol)
            return None

        # ── Step 2: Technical Agent ────────────────────────────────────────
        tech = self.technical_agent.run(data["primary"], data.get("confirm"))
        if "error" in tech:
            logger.debug("SignalEngine: technical error for %s: %s", symbol, tech["error"])
            return None

        # ── Step 3: Regime Agent ───────────────────────────────────────────
        regime = self.regime_agent.run(tech)

        # Early exit: ranging market in high-quality-only mode
        if config.HIGH_QUALITY_ONLY and not regime.get("tradeable", False):
            logger.debug("SignalEngine: %s skipped — regime=%s", symbol, regime["regime"])
            self.total_filtered += 1
            return None

        # ── Step 4: Risk Agent ─────────────────────────────────────────────
        risk_input = {
            "confidence": tech.get("confidence", 0),
            "atr": tech.get("atr", 0),
            "price": tech.get("price", 1),
        }
        risk = self.risk_agent.run(risk_input, expiry)

        if not risk.get("approved", False):
            logger.info("SignalEngine: %s BLOCKED by risk — %s", symbol, risk.get("reason"))
            return None

        # ── Step 5: Oracle Agent ───────────────────────────────────────────
        oracle = self.oracle_agent.run(tech, regime, risk, symbol, expiry)

        # ── Step 6: Build signal object ────────────────────────────────────
        if oracle.get("signal", False):
            signal = self._build_signal(oracle, tech, regime, risk, asset_config, expiry, data)
            self.total_signals += 1
            # Save to database
            try:
                sig_id = db.save_signal(signal)
                signal["id"] = sig_id
                logger.info(
                    "SignalEngine: 🎯 %s %s | %.1f%% (%s) | %dmin | gates=%d/%d",
                    signal["direction"], symbol, signal["confidence"],
                    signal["tier"], expiry,
                    oracle["gates_passed"], oracle["gates_total"]
                )
            except Exception as e:
                logger.error("DB save error: %s", e)
            return signal
        else:
            self.total_filtered += 1
            logger.debug(
                "SignalEngine: %s filtered | conf=%.1f%% tier=%s",
                symbol, oracle.get("confidence", 0), oracle.get("tier", "?")
            )
            return None

    @staticmethod
    def _build_signal(oracle: Dict, tech: Dict, regime: Dict, risk: Dict,
                       asset_cfg: Dict, expiry: int, data: Dict) -> Dict:
        """Build the final signal dict for DB storage and Telegram."""
        now = datetime.utcnow()
        return {
            "timestamp":   now.isoformat(),
            "asset":       asset_cfg.get("symbol", "UNKNOWN"),
            "asset_name":  asset_cfg.get("name", asset_cfg.get("symbol", "")),
            "asset_type":  asset_cfg.get("type", "forex"),
            "direction":   oracle["direction"],
            "expiry":      expiry,
            "confidence":  oracle["confidence"],
            "tier":        oracle["tier"],
            "entry_price": oracle["entry_price"],
            "tp1":         oracle["tp1"],
            "tp2":         oracle["tp2"],
            "stop_loss":   oracle["stop_loss"],
            "atr":         oracle["atr"],
            "regime":      regime.get("regime", ""),
            "regime_label": regime.get("label", ""),
            "gates_passed": oracle["gates_passed"],
            "gates_total":  oracle["gates_total"],
            "gates":        oracle.get("gates", []),
            "key_reasons":  oracle.get("key_reasons", []),
            "agent_data": {
                "rsi":    tech.get("rsi"),
                "macd":   tech.get("macd"),
                "adx":    tech.get("adx"),
                "bb_pct": tech.get("bb", {}).get("pct_b"),
                "stoch":  tech.get("stoch"),
                "wr":     tech.get("williams_r"),
                "cci":    tech.get("cci"),
                "ribbon": tech.get("ribbon"),
                "ha":     tech.get("ha"),
                "regime": regime,
                "risk":   risk,
                "raw_score":    oracle.get("raw_score"),
                "regime_mult":  oracle.get("regime_mult"),
                "data_source":  data.get("source"),
                "bars":         data.get("bars"),
                "confirm_dir":  tech.get("confirm_direction"),
            },
            "risk_position_size": risk.get("position_size", 0),
            "risk_max_loss_usd":  risk.get("max_loss_usd", 0),
            "risk_level":         risk.get("risk_level", "?"),
            "risk_warnings":      risk.get("warnings", []),
        }

    def scan_all(self, expiry: int) -> List[Dict]:
        """Scan all configured assets for a given expiry."""
        signals = []

        # Forex + OTC
        for sym, ticker, name, atype in (config.FOREX_ASSETS + config.OTC_ASSETS):
            try:
                asset_cfg = {"symbol": sym, "ticker": ticker, "name": name, "type": atype}
                sig = self.analyze(asset_cfg, expiry)
                if sig:
                    signals.append(sig)
            except Exception as e:
                logger.error("Error scanning %s: %s", sym, e)

        # Crypto
        for sym, ticker, name, atype in config.CRYPTO_ASSETS:
            try:
                asset_cfg = {"symbol": sym, "ticker": ticker, "name": name, "type": atype}
                sig = self.analyze(asset_cfg, expiry)
                if sig:
                    signals.append(sig)
            except Exception as e:
                logger.error("Error scanning %s: %s", sym, e)

        # Composites
        for comp in config.COMPOSITE_ASSETS:
            try:
                sig = self.analyze(comp, expiry)
                if sig:
                    signals.append(sig)
            except Exception as e:
                logger.error("Error scanning composite %s: %s", comp.get("symbol"), e)

        # Sort by confidence descending
        signals.sort(key=lambda s: s["confidence"], reverse=True)
        logger.info(
            "SignalEngine scan complete: expiry=%dmin | %d signals | %d filtered",
            expiry, len(signals), self.total_filtered
        )
        return signals
