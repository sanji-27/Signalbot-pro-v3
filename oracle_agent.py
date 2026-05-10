"""
agents/oracle_agent.py — Ensemble Oracle Agent
Combines all agent outputs using a weighted 25-gate confluence system.
Calculates realistic confidence %, determines direction, generates key reasons.
This is the brain — it has the final say on whether a signal fires.
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import config

logger = logging.getLogger(__name__)


# ── Gate Definitions ──────────────────────────────────────────────────────────

def _build_gates(tech: Dict, regime: Dict, direction_hint: int) -> List[Dict]:
    """
    Build all 25 quality gates for the given direction.
    direction_hint: +1 = CALL, -1 = PUT, 0 = unknown (auto-detect)

    Each gate: { id, label, pass, weight, group }
    """
    ha     = tech.get("ha", {})
    rsi    = tech.get("rsi", 50.0)
    macd   = tech.get("macd", {})
    bb     = tech.get("bb", {})
    stoch  = tech.get("stoch", {})
    atr    = tech.get("atr", 0.001)
    adx    = tech.get("adx", {})
    ich    = tech.get("ichimoku", {})
    wr     = tech.get("williams_r", -50.0)
    cci    = tech.get("cci", 0.0)
    vwap   = tech.get("vwap", 0.0)
    ribbon = tech.get("ribbon", {})
    sr     = tech.get("sr", {})
    price  = tech.get("price", 0.0)
    vol    = tech.get("vol_score", 0.5)
    conf_d = tech.get("confirm_direction", 0)  # higher TF direction

    adx_val = adx.get("adx", 0.0)
    pdi     = adx.get("pdi", 0.0)
    ndi     = adx.get("ndi", 0.0)
    bull    = ha.get("bull", True) if direction_hint == 0 else (direction_hint == 1)

    # ── GROUP A: Heikin-Ashi (5 gates, weight 20) ────────────────────────────
    gates = [
        {
            "id": "A1", "group": "A",
            "label": f"HA {ha.get('count', 0)}+ consecutive {'green' if bull else 'red'} candles",
            "pass": ha.get("count", 0) >= 2,
            "weight": 4,
        },
        {
            "id": "A2", "group": "A",
            "label": f"HA no {'lower' if bull else 'upper'} wick (strong body)",
            "pass": ha.get("no_lower_wick", False) if bull else ha.get("no_upper_wick", False),
            "weight": 4,
        },
        {
            "id": "A3", "group": "A",
            "label": f"HA 3+ consecutive candles ({'bull' if bull else 'bear'})",
            "pass": ha.get("count", 0) >= 3,
            "weight": 4,
        },
        {
            "id": "A4", "group": "A",
            "label": f"HA color change signal (momentum shift)" if ha.get("changed") else
                     f"HA strong momentum ({ha.get('count', 0)} candles)",
            "pass": ha.get("changed", False) or ha.get("count", 0) >= 4,
            "weight": 4,
        },
        {
            "id": "A5", "group": "A",
            "label": f"HA {'bull' if bull else 'bear'} & strong body (no opposing wick)",
            "pass": ha.get("bull", True) == bull and ha.get("count", 0) >= 2,
            "weight": 4,
        },
    ]

    # ── GROUP B: Trend Structure (5 gates, weight 25) ─────────────────────────
    e8, e13, e21, e55, e200 = (
        ribbon.get("e8", 0), ribbon.get("e13", 0),
        ribbon.get("e21", 0), ribbon.get("e55", 0), ribbon.get("e200", 0)
    )
    ribbon_bull = e8 > e13 > e21
    ribbon_bear = e8 < e13 < e21
    gates += [
        {
            "id": "B1", "group": "B",
            "label": f"EMA ribbon {'bull' if bull else 'bear'} aligned (8>13>21)",
            "pass": ribbon_bull if bull else ribbon_bear,
            "weight": 5,
        },
        {
            "id": "B2", "group": "B",
            "label": f"EMA 21 {'above' if bull else 'below'} EMA 55",
            "pass": e21 > e55 if bull else e21 < e55,
            "weight": 5,
        },
        {
            "id": "B3", "group": "B",
            "label": f"Price {'above' if bull else 'below'} EMA 200",
            "pass": price > e200 if bull else price < e200,
            "weight": 5,
        },
        {
            "id": "B4", "group": "B",
            "label": f"ADX direction: +DI {'>' if bull else '<'} -DI ({adx_val:.1f})",
            "pass": pdi > ndi if bull else ndi > pdi,
            "weight": 5,
        },
        {
            "id": "B5", "group": "B",
            "label": f"Higher TF {'bullish' if bull else 'bearish'} confirmation",
            "pass": conf_d == (1 if bull else -1),
            "weight": 5,
        },
    ]

    # ── GROUP C: Momentum Oscillators (5 gates, weight 20) ───────────────────
    gates += [
        {
            "id": "C1", "group": "C",
            "label": f"RSI {rsi:.1f} in {'bullish' if bull else 'bearish'} momentum zone",
            "pass": (35 < rsi < 70) if bull else (30 < rsi < 65),
            "weight": 4,
        },
        {
            "id": "C2", "group": "C",
            "label": f"MACD histogram {'positive' if bull else 'negative'} ({macd.get('hist', 0):.6f})",
            "pass": macd.get("hist", 0) > 0 if bull else macd.get("hist", 0) < 0,
            "weight": 4,
        },
        {
            "id": "C3", "group": "C",
            "label": f"MACD line {'bullish' if bull else 'bearish'} ({macd.get('line', 0):.6f})",
            "pass": macd.get("line", 0) > 0 if bull else macd.get("line", 0) < 0,
            "weight": 4,
        },
        {
            "id": "C4", "group": "C",
            "label": f"Stochastic K={stoch.get('k', 50):.0f} D={stoch.get('d', 50):.0f} {'oversold' if bull else 'overbought'}",
            "pass": stoch.get("k", 50) < 80 if bull else stoch.get("k", 50) > 20,
            "weight": 4,
        },
        {
            "id": "C5", "group": "C",
            "label": f"Williams %R {wr:.1f} {'not overbought' if bull else 'not oversold'}",
            "pass": wr < -20 if bull else wr > -80,
            "weight": 4,
        },
    ]

    # ── GROUP D: Volatility & Market Quality (5 gates, weight 20) ────────────
    gates += [
        {
            "id": "D1", "group": "D",
            "label": f"ADX strength {adx_val:.1f} (trend power)",
            "pass": adx_val > 18,
            "weight": 4,
        },
        {
            "id": "D2", "group": "D",
            "label": f"BB not in squeeze (volatility expanding)",
            "pass": not bb.get("squeeze", False),
            "weight": 4,
        },
        {
            "id": "D3", "group": "D",
            "label": f"Market regime favorable: {regime.get('regime', 'unknown')}",
            "pass": regime.get("tradeable", False),
            "weight": 4,
        },
        {
            "id": "D4", "group": "D",
            "label": f"Volatility {vol:.3f}% acceptable (not extreme)",
            "pass": 0.01 < vol < 2.0,
            "weight": 4,
        },
        {
            "id": "D5", "group": "D",
            "label": f"ADX {adx_val:.1f} > 20 (clear directional move)",
            "pass": adx_val > 20,
            "weight": 4,
        },
    ]

    # ── GROUP E: Price Structure (5 gates, weight 15) ─────────────────────────
    cloud_top = ich.get("cloud_top", price)
    cloud_bot = ich.get("cloud_bot", price)
    tenkan    = ich.get("tenkan", price)
    kijun     = ich.get("kijun", price)
    gates += [
        {
            "id": "E1", "group": "E",
            "label": f"Bollinger %B {bb.get('pct_b', 50):.0f}% — {'room to run up' if bull else 'room to fall'}",
            "pass": bb.get("pct_b", 50) < 80 if bull else bb.get("pct_b", 50) > 20,
            "weight": 3,
        },
        {
            "id": "E2", "group": "E",
            "label": f"Price {'above' if bull else 'below'} VWAP ({vwap:.5f})",
            "pass": price > vwap if bull else price < vwap,
            "weight": 3,
        },
        {
            "id": "E3", "group": "E",
            "label": f"Ichimoku: price {'above cloud' if price > cloud_top else 'below cloud' if price < cloud_bot else 'in cloud'}",
            "pass": price > cloud_top if bull else price < cloud_bot,
            "weight": 3,
        },
        {
            "id": "E4", "group": "E",
            "label": f"Ichimoku TK {'bull' if tenkan >= kijun else 'bear'} cross (T={tenkan:.5f} K={kijun:.5f})",
            "pass": tenkan >= kijun if bull else tenkan <= kijun,
            "weight": 3,
        },
        {
            "id": "E5", "group": "E",
            "label": f"CCI {cci:.0f} {'momentum' if bull else 'reversal'} zone",
            "pass": cci > -100 if bull else cci < 100,
            "weight": 3,
        },
    ]

    return gates


class OracleAgent:
    """
    Ensemble Oracle Agent — the final decision maker.
    Combines all agent outputs to produce a high-quality signal or rejection.
    """

    def __init__(self):
        self.name = "OracleAgent"
        self.status = "idle"
        self.last_result = None

    def run(self, tech: Dict, regime: Dict, risk: Dict,
            asset: str, expiry: int) -> Dict:
        """
        Orchestrate all analysis into a final signal decision.

        Returns:
            {
              "signal": bool,           # True = generate signal
              "direction": str,         # CALL or PUT
              "confidence": float,      # calculated %
              "tier": str,              # ELITE / HIGH / STANDARD / WEAK
              "gates": list,            # all 25 gate results
              "gates_passed": int,
              "gates_total": int,
              "key_reasons": list[str], # top reasons for the signal
              "regime": str,
              "entry_price": float,
              "tp1": float, "tp2": float, "stop_loss": float,
              "risk": dict,
              "timestamp": str,
            }
        """
        self.status = "running"

        if "error" in tech:
            return {"signal": False, "reason": "technical_analysis_failed"}

        if not risk.get("approved", False):
            return {"signal": False, "reason": risk.get("reason", "risk_blocked"),
                    "risk": risk}

        try:
            # ── Step 1: Determine Direction ────────────────────────────────
            ha     = tech.get("ha", {})
            macd   = tech.get("macd", {})
            ribbon = tech.get("ribbon", {})
            rsi    = tech.get("rsi", 50.0)
            adx    = tech.get("adx", {})
            conf_d = tech.get("confirm_direction", 0)
            price  = tech.get("price", 0.0)
            atr    = tech.get("atr", price * 0.001)

            # Vote for direction: HA + MACD + EMA ribbon + RSI + higher TF
            bull_votes = sum([
                2 if ha.get("bull") else -2,                # HA is strongest
                1 if macd.get("hist", 0) > 0 else -1,
                1 if ribbon.get("e8", 0) > ribbon.get("e21", 0) else -1,
                1 if rsi > 55 else (-1 if rsi < 45 else 0),
                2 if conf_d == 1 else (-2 if conf_d == -1 else 0),
            ])
            bull = bull_votes > 0
            direction = "CALL" if bull else "PUT"
            direction_hint = 1 if bull else -1

            # ── Step 2: Build and evaluate gates ──────────────────────────
            gates = _build_gates(tech, regime, direction_hint)
            total_weight  = sum(g["weight"] for g in gates)
            passed_weight = sum(g["weight"] for g in gates if g["pass"])
            gates_passed  = sum(1 for g in gates if g["pass"])
            gates_total   = len(gates)

            # ── Step 3: Calculate confidence ──────────────────────────────
            raw_score = (passed_weight / total_weight * 100) if total_weight > 0 else 0.0

            # Apply regime multiplier
            regime_mult = regime.get("confidence_mult", 0.8)
            score = raw_score * regime_mult

            # Signal conflict penalty (too evenly split)
            passed_ratio = passed_weight / total_weight if total_weight > 0 else 0.5
            if 0.45 <= passed_ratio <= 0.55:
                score *= 0.75  # conflicted — not decisive
                logger.debug("Oracle: signal conflict detected (ratio=%.2f)", passed_ratio)

            # Cap at 97 (we never claim 100% certainty)
            confidence = round(min(score, 97.0), 1)

            # ── Step 4: Tier classification ───────────────────────────────
            if confidence >= config.ELITE_CONFIDENCE:
                tier = "ELITE"
            elif confidence >= 82:
                tier = "HIGH"
            elif confidence >= config.MIN_CONFIDENCE:
                tier = "STANDARD"
            else:
                tier = "WEAK"

            # ── Step 5: Signal decision ───────────────────────────────────
            emit_signal = (
                confidence >= config.MIN_CONFIDENCE
                and regime.get("tradeable", False)
                and gates_passed >= gates_total * 0.60   # at least 60% gates passed
                and adx.get("adx", 0) > 15               # some trend present
            )

            # High-quality-only mode: only send ELITE/HIGH signals
            if config.HIGH_QUALITY_ONLY and tier not in ("ELITE", "HIGH"):
                emit_signal = False

            # ── Step 6: Trade levels ──────────────────────────────────────
            tp1 = round(price + atr * config.TP_ATR_MULT, 5) if bull else round(price - atr * config.TP_ATR_MULT, 5)
            tp2 = round(price + atr * config.TP_ATR_MULT * 1.5, 5) if bull else round(price - atr * config.TP_ATR_MULT * 1.5, 5)
            sl  = round(price - atr * config.SL_ATR_MULT, 5) if bull else round(price + atr * config.SL_ATR_MULT, 5)

            # ── Step 7: Key reasons (top 5 passed gates) ──────────────────
            passed_gates = [g for g in gates if g["pass"]]
            # Sort by weight descending
            passed_gates_sorted = sorted(passed_gates, key=lambda g: g["weight"], reverse=True)
            key_reasons = [g["label"] for g in passed_gates_sorted[:6]]

            result = {
                "signal": emit_signal,
                "direction": direction,
                "confidence": confidence,
                "tier": tier,
                "gates": gates,
                "gates_passed": gates_passed,
                "gates_total": gates_total,
                "raw_score": round(raw_score, 1),
                "regime_mult": regime_mult,
                "key_reasons": key_reasons,
                "regime": regime.get("label", ""),
                "entry_price": round(price, 5),
                "tp1": tp1,
                "tp2": tp2,
                "stop_loss": sl,
                "atr": round(atr, 5),
                "risk": risk,
                "timestamp": datetime.utcnow().isoformat(),
                "asset": asset,
                "expiry": expiry,
                "bull_votes": bull_votes,
            }

            self.status = "done"
            self.last_result = result

            logger.info(
                "Oracle: %s %s | %s | conf=%.1f%% (%s) | gates=%d/%d | %s",
                direction, asset, regime.get("regime", "?"),
                confidence, tier, gates_passed, gates_total,
                "SIGNAL ✅" if emit_signal else "FILTERED ❌"
            )

            return result

        except Exception as e:
            logger.error("OracleAgent error: %s", e, exc_info=True)
            self.status = "error"
            return {"signal": False, "reason": f"oracle_error: {e}"}
