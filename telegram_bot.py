"""
telegram_bot.py — Telegram Integration
Sends professionally formatted signal messages to Telegram.
Uses simple HTTP requests — no extra libraries needed beyond requests.
"""
import logging
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import config

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _send(method: str, payload: dict) -> bool:
    """Generic Telegram API call."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured — skipping send")
        return False
    url = TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN, method=method)
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error("Telegram %s failed: %s", method, e)
        return False


def send_message(text: str, parse_mode: str = "HTML",
                 chat_id: str = None) -> bool:
    """Send a plain text message."""
    return _send("sendMessage", {
        "chat_id": chat_id or config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    })


def _tier_emoji(tier: str) -> str:
    return {"ELITE": "🏆", "HIGH": "⭐", "STANDARD": "📊", "WEAK": "⚠️"}.get(tier, "📊")


def _direction_emoji(direction: str) -> str:
    return "📈" if direction == "CALL" else "📉"


def _confidence_bar(pct: float, length: int = 10) -> str:
    """Visual progress bar for confidence."""
    filled = round(pct / 100 * length)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {pct:.1f}%"


def _asset_type_badge(asset_type: str) -> str:
    return {"forex": "💱", "otc": "🔄", "crypto": "₿", "composite": "📊"}.get(
        asset_type, "💱")


def format_signal(signal: Dict) -> str:
    """
    Format a signal as a professional Telegram HTML message.
    """
    direction  = signal.get("direction", "?")
    asset      = signal.get("asset_name") or signal.get("asset", "?")
    asset_type = signal.get("asset_type", "forex")
    expiry     = signal.get("expiry", 0)
    confidence = signal.get("confidence", 0.0)
    tier       = signal.get("tier", "STANDARD")
    entry      = signal.get("entry_price", 0.0)
    tp1        = signal.get("tp1", 0.0)
    tp2        = signal.get("tp2", 0.0)
    sl         = signal.get("stop_loss", 0.0)
    regime_lbl = signal.get("regime_label", "")
    gates_p    = signal.get("gates_passed", 0)
    gates_t    = signal.get("gates_total", 0)
    reasons    = signal.get("key_reasons", [])[:4]
    risk_sz    = signal.get("risk_position_size", 0)
    risk_loss  = signal.get("risk_max_loss_usd", 0)
    risk_lvl   = signal.get("risk_level", "?")
    risk_warn  = signal.get("risk_warnings", [])

    tier_em  = _tier_emoji(tier)
    dir_em   = _direction_emoji(direction)
    type_em  = _asset_type_badge(asset_type)
    now      = datetime.utcnow()
    expiry_t = (now + timedelta(minutes=expiry)).strftime("%H:%M UTC")

    call_color = "🟢" if direction == "CALL" else "🔴"

    lines = [
        f"{'━' * 28}",
        f"{tier_em} <b>SURESHOT PRO</b> {tier_em}",
        f"<code>{'━' * 26}</code>",
        f"",
        f"{type_em} <b>{asset}</b>",
        f"{dir_em} <b>{call_color} {direction}</b>  |  ⏱ <b>{expiry}min</b>",
        f"",
        f"🎯 <b>CONFIDENCE</b>",
        f"<code>{_confidence_bar(confidence)}</code>",
        f"<b>{tier}</b> tier  |  {gates_p}/{gates_t} gates",
        f"",
        f"📌 <b>TRADE LEVELS</b>",
        f"⚡ Entry:      <code>{entry:.5f}</code>",
        f"🟢 Target 1:  <code>{tp1:.5f}</code>",
        f"🔵 Target 2:  <code>{tp2:.5f}</code>",
        f"🛡 Stop Loss: <code>{sl:.5f}</code>",
        f"",
        f"⏰ Entry: <b>{now.strftime('%H:%M UTC')}</b>",
        f"⌛ Expiry: <b>{expiry_t}</b>",
        f"",
    ]

    if reasons:
        lines.append(f"💡 <b>KEY CONFLUENCES</b>")
        for r in reasons:
            lines.append(f"  ✅ {r}")
        lines.append("")

    lines += [
        f"🌡 Market: {regime_lbl}",
        f"",
        f"⚠️ <b>RISK NOTE</b>",
        f"  Size: {risk_sz:.2f}% | Max Loss: ${risk_loss:.2f}",
        f"  Level: {risk_lvl}",
    ]

    if risk_warn:
        for w in risk_warn:
            lines.append(f"  {w}")

    lines += [
        f"",
        f"{'━' * 28}",
        f"<i>Educational only. Trade at your own risk.</i>",
    ]

    return "\n".join(lines)


def format_daily_summary(stats: Dict) -> str:
    """Format daily performance summary."""
    date   = stats.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
    total  = stats.get("total_signals", 0)
    wins   = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    pend   = stats.get("pending", 0)
    avg_c  = stats.get("avg_confidence", 0)
    wr     = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0.0

    return "\n".join([
        f"📊 <b>DAILY SUMMARY — {date}</b>",
        f"{'━' * 28}",
        f"📤 Signals: <b>{total}</b>",
        f"✅ Wins:    <b>{wins}</b>",
        f"❌ Losses:  <b>{losses}</b>",
        f"⏳ Pending: <b>{pend}</b>",
        f"🎯 Win Rate: <b>{wr}%</b>",
        f"📈 Avg Confidence: <b>{avg_c:.1f}%</b>",
        f"{'━' * 28}",
    ])


def format_risk_alert(event: str, detail: str) -> str:
    """Format a risk management alert."""
    return "\n".join([
        f"🚨 <b>RISK ALERT</b>",
        f"{'━' * 28}",
        f"Event: <b>{event}</b>",
        f"Detail: {detail}",
        f"{'━' * 28}",
        f"<i>Trading may be halted. Review conditions before resuming.</i>",
    ])


def send_signal(signal: Dict) -> bool:
    """Send a formatted signal to Telegram."""
    text = format_signal(signal)
    ok = send_message(text)
    if ok:
        logger.info("Telegram: signal sent for %s %s %.1f%%",
                    signal.get("direction"), signal.get("asset"),
                    signal.get("confidence", 0))
    return ok


def send_daily_summary(stats: Dict) -> bool:
    """Send daily stats summary."""
    return send_message(format_daily_summary(stats))


def send_risk_alert(event: str, detail: str) -> bool:
    """Send a risk event alert."""
    return send_message(format_risk_alert(event, detail))


def send_startup_message() -> bool:
    """Send bot online notification."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    msg = "\n".join([
        f"🤖 <b>SureShot Pro Bot — ONLINE</b>",
        f"{'━' * 28}",
        f"✅ Multi-agent system active",
        f"🧠 Agents: Data · Technical · Regime · Risk · Oracle",
        f"📊 Assets: {len(config.FOREX_ASSETS)} Forex | {len(config.OTC_ASSETS)} OTC | {len(config.CRYPTO_ASSETS)} Crypto",
        f"⏱ Expiries: {', '.join(str(e) + 'min' for e in config.SCAN_EXPIRIES)}",
        f"🎯 Min Confidence: {config.MIN_CONFIDENCE}%",
        f"⭐ Elite Threshold: {config.ELITE_CONFIDENCE}%",
        f"🛡 Max Risk/Trade: {config.MAX_RISK_PER_TRADE}%",
        f"⏰ Started: {now}",
        f"{'━' * 28}",
    ])
    return send_message(msg)


def test_connection() -> bool:
    """Test Telegram connectivity."""
    return send_message("🔌 <b>SureShot Pro — Connection Test</b>\n✅ Bot is connected and ready!")
