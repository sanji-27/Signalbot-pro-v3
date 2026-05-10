"""
main.py — SureShot Pro Multi-Agent Signal Bot
Orchestrates everything: Flask dashboard, APScheduler scan jobs, signal pipeline.
Runs continuously with graceful shutdown and error recovery.
"""
import logging
import signal
import sys
import os
import threading
from datetime import datetime, time as dtime

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import config
from core import database as db
from core.signal_engine import SignalEngine
from agents.risk_agent import RiskAgent
import telegram_bot as tg

# ── Logging Setup ─────────────────────────────────────────────────────────────
def setup_logging():
    handlers = [logging.StreamHandler(sys.stdout)]
    if config.LOG_TO_FILE:
        os.makedirs("logs", exist_ok=True)
        handlers.append(logging.FileHandler(
            f"logs/signalbot_{datetime.utcnow().strftime('%Y%m%d')}.log"
        ))
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
    # Suppress noisy libraries
    for lib in ["yfinance", "urllib3", "requests", "httpx", "peewee"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger("main")

# ── Global State ──────────────────────────────────────────────────────────────
risk_agent   = RiskAgent()
signal_engine = SignalEngine(risk_agent)
scheduler    = BackgroundScheduler(timezone="UTC")
app_state    = {
    "running": False,
    "start_time": None,
    "last_scan": {},       # expiry -> ISO timestamp
    "scan_count": 0,
    "signal_count": 0,
    "agents": {
        "data":       {"status": "idle"},
        "technical":  {"status": "idle"},
        "regime":     {"status": "idle"},
        "risk":       {"status": "idle"},
        "oracle":     {"status": "idle"},
    }
}

# ── Scan Jobs ─────────────────────────────────────────────────────────────────

def run_scan(expiry: int):
    """Run a full market scan for the given expiry duration."""
    logger.info("=" * 60)
    logger.info("SCAN START | expiry=%dmin | %s UTC", expiry, datetime.utcnow().strftime("%H:%M:%S"))
    logger.info("=" * 60)

    try:
        signals = signal_engine.scan_all(expiry)
        app_state["last_scan"][expiry] = datetime.utcnow().isoformat()
        app_state["scan_count"] += 1

        for sig in signals:
            # Send via Telegram
            tg.send_signal(sig)
            app_state["signal_count"] += 1

        logger.info("SCAN END | expiry=%dmin | signals=%d", expiry, len(signals))

        # Update agent statuses
        app_state["agents"]["data"]      = {"status": signal_engine.data_agent.status,
                                             "last": signal_engine.data_agent.last_fetch}
        app_state["agents"]["technical"] = {"status": signal_engine.technical_agent.status}
        app_state["agents"]["regime"]    = {"status": signal_engine.regime_agent.status,
                                             "last": signal_engine.regime_agent.last_regime}
        app_state["agents"]["risk"]      = risk_agent.get_status()
        app_state["agents"]["oracle"]    = {"status": signal_engine.oracle_agent.status}

    except Exception as e:
        logger.error("Scan error (expiry=%d): %s", expiry, e, exc_info=True)


def daily_summary_job():
    """Send daily performance summary at 23:55 UTC."""
    try:
        stats = db.get_todays_stat()
        tg.send_daily_summary(stats)
        logger.info("Daily summary sent")
    except Exception as e:
        logger.error("Daily summary error: %s", e)


def setup_scheduler():
    """Configure scan jobs for all expiry timeframes."""
    if not config.SCAN_ENABLED:
        logger.info("Scanning is disabled in config")
        return

    for expiry in config.SCAN_EXPIRIES:
        # Run scan every `expiry` minutes with some jitter
        scheduler.add_job(
            func=run_scan,
            args=[expiry],
            trigger=IntervalTrigger(minutes=expiry),
            id=f"scan_{expiry}min",
            name=f"Scan {expiry}min expiry",
            misfire_grace_time=60,
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Scheduled: scan %dmin every %d minutes", expiry, expiry)

    # Daily summary
    scheduler.add_job(
        func=daily_summary_job,
        trigger=CronTrigger(hour=23, minute=55),
        id="daily_summary",
        name="Daily summary",
        replace_existing=True,
    )
    logger.info("Scheduled: daily summary at 23:55 UTC")


# ── Flask App ─────────────────────────────────────────────────────────────────
flask_app = Flask(__name__, static_folder="dashboard")
flask_app.secret_key = config.FLASK_SECRET_KEY
CORS(flask_app)


@flask_app.route("/")
def index():
    return send_from_directory("dashboard", "index.html")


@flask_app.route("/api/health")
def health():
    return jsonify({
        "status": "running" if app_state["running"] else "starting",
        "uptime_seconds": (
            (datetime.utcnow() - app_state["start_time"]).total_seconds()
            if app_state["start_time"] else 0
        ),
        "scan_count": app_state["scan_count"],
        "signal_count": app_state["signal_count"],
        "timestamp": datetime.utcnow().isoformat(),
    })


@flask_app.route("/api/signals")
def api_signals():
    limit = int(request.args.get("limit", 50))
    signals = db.get_recent_signals(limit)
    return jsonify(signals)


@flask_app.route("/api/stats")
def api_stats():
    return jsonify({
        "today": db.get_todays_stat(),
        "overall": db.get_overall_stats(),
        "weekly": db.get_daily_stats(7),
    })


@flask_app.route("/api/risk")
def api_risk():
    return jsonify(risk_agent.get_status())


@flask_app.route("/api/agents")
def api_agents():
    return jsonify({
        "agents": app_state["agents"],
        "last_scans": app_state["last_scan"],
        "scan_count": app_state["scan_count"],
        "signal_count": app_state["signal_count"],
    })


@flask_app.route("/api/signal/<int:signal_id>/outcome", methods=["POST"])
def api_update_outcome(signal_id):
    data = request.get_json() or {}
    outcome = data.get("outcome", "").upper()
    if outcome not in ("WIN", "LOSS", "EXPIRED"):
        return jsonify({"error": "outcome must be WIN, LOSS, or EXPIRED"}), 400
    exit_price = data.get("exit_price")
    pnl_pct    = data.get("pnl_pct")
    db.update_signal_outcome(signal_id, outcome, exit_price, pnl_pct)
    risk_agent.record_trade_result(outcome == "WIN")
    return jsonify({"success": True, "signal_id": signal_id, "outcome": outcome})


@flask_app.route("/api/scan/now/<int:expiry>", methods=["POST"])
def api_scan_now(expiry):
    """Trigger an immediate scan from the dashboard."""
    if expiry not in config.SCAN_EXPIRIES:
        return jsonify({"error": f"expiry must be one of {config.SCAN_EXPIRIES}"}), 400
    threading.Thread(target=run_scan, args=[expiry], daemon=True).start()
    return jsonify({"success": True, "message": f"Scan started for {expiry}min"})


@flask_app.route("/api/risk/resume", methods=["POST"])
def api_risk_resume():
    risk_agent.resume()
    return jsonify({"success": True, "message": "Trading resumed"})


@flask_app.route("/api/telegram/test", methods=["POST"])
def api_telegram_test():
    ok = tg.test_connection()
    return jsonify({"success": ok, "message": "Test message sent" if ok else "Telegram not configured"})


# ── Graceful Shutdown ─────────────────────────────────────────────────────────

def shutdown(sig=None, frame=None):
    logger.info("Shutdown signal received — stopping gracefully...")
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    app_state["running"] = False
    logger.info("SureShot Pro Bot stopped.")
    sys.exit(0)


signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("  SureShot Pro — Multi-Agent Signal Bot")
    logger.info("  Starting up...")
    logger.info("=" * 60)

    # Init DB
    db.init_db()
    logger.info("Database ready: %s", config.DB_PATH)

    # Validate Telegram
    if not config.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set — signals won't be sent")
    else:
        tg.send_startup_message()
        logger.info("Telegram startup notification sent")

    # Setup scheduler
    setup_scheduler()
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    # Initial scan on startup
    if config.SCAN_ENABLED and config.SCAN_EXPIRIES:
        first_expiry = config.SCAN_EXPIRIES[0]
        logger.info("Running initial scan (expiry=%dmin)...", first_expiry)
        threading.Thread(target=run_scan, args=[first_expiry], daemon=True).start()

    app_state["running"]    = True
    app_state["start_time"] = datetime.utcnow()

    logger.info("Dashboard: http://localhost:%d", config.FLASK_PORT)
    logger.info("Assets: %d forex | %d OTC | %d crypto | %d composites",
                len(config.FOREX_ASSETS), len(config.OTC_ASSETS),
                len(config.CRYPTO_ASSETS), len(config.COMPOSITE_ASSETS))
    logger.info("Expiries: %s", config.SCAN_EXPIRIES)
    logger.info("Min confidence: %.0f%% | Elite: %.0f%%",
                config.MIN_CONFIDENCE, config.ELITE_CONFIDENCE)

    # Start Flask
    flask_app.run(
        host="0.0.0.0",
        port=config.FLASK_PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()
