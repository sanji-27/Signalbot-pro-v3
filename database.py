"""
core/database.py — SQLite signal journal and performance tracking.
Logs every signal, outcome, and daily stats for learning & improvement.
"""
import sqlite3
import json
import logging
from datetime import datetime, date
from typing import List, Dict, Optional
import config

logger = logging.getLogger(__name__)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS signals (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp         TEXT NOT NULL,
        asset             TEXT NOT NULL,
        asset_type        TEXT NOT NULL DEFAULT 'forex',
        direction         TEXT NOT NULL,
        expiry            INTEGER NOT NULL,
        confidence        REAL NOT NULL,
        entry_price       REAL NOT NULL,
        tp1               REAL,
        tp2               REAL,
        stop_loss         REAL,
        atr               REAL,
        regime            TEXT,
        gates_passed      INTEGER,
        gates_total       INTEGER,
        agent_data        TEXT,
        key_reasons       TEXT,
        outcome           TEXT DEFAULT 'PENDING',
        exit_price        REAL,
        pnl_pct           REAL,
        created_at        TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS daily_stats (
        date              TEXT PRIMARY KEY,
        total_signals     INTEGER DEFAULT 0,
        calls             INTEGER DEFAULT 0,
        puts              INTEGER DEFAULT 0,
        wins              INTEGER DEFAULT 0,
        losses            INTEGER DEFAULT 0,
        pending           INTEGER DEFAULT 0,
        avg_confidence    REAL DEFAULT 0,
        max_drawdown_pct  REAL DEFAULT 0,
        daily_risk_used   REAL DEFAULT 0,
        consecutive_losses INTEGER DEFAULT 0,
        trading_halted    INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS risk_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT NOT NULL,
        event       TEXT NOT NULL,
        detail      TEXT,
        value       REAL
    );
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized: %s", config.DB_PATH)


# ── SIGNALS ───────────────────────────────────────────────────────────────────

def save_signal(sig: Dict) -> int:
    """Insert a new signal record. Returns the new row id."""
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("""
        INSERT INTO signals
          (timestamp, asset, asset_type, direction, expiry, confidence,
           entry_price, tp1, tp2, stop_loss, atr, regime,
           gates_passed, gates_total, agent_data, key_reasons, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        sig.get("timestamp", now),
        sig["asset"],
        sig.get("asset_type", "forex"),
        sig["direction"],
        sig["expiry"],
        sig["confidence"],
        sig["entry_price"],
        sig.get("tp1"),
        sig.get("tp2"),
        sig.get("stop_loss"),
        sig.get("atr"),
        sig.get("regime"),
        sig.get("gates_passed"),
        sig.get("gates_total"),
        json.dumps(sig.get("agent_data", {})),
        json.dumps(sig.get("key_reasons", [])),
        now,
    ))
    row_id = c.lastrowid
    conn.commit()
    conn.close()
    _update_daily_stats()
    return row_id


def update_signal_outcome(signal_id: int, outcome: str, exit_price: float = None,
                           pnl_pct: float = None):
    """Mark a signal as WIN, LOSS, or EXPIRED."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE signals SET outcome=?, exit_price=?, pnl_pct=?
        WHERE id=?
    """, (outcome, exit_price, pnl_pct, signal_id))
    conn.commit()
    conn.close()
    _update_daily_stats()
    logger.info("Signal #%d outcome: %s", signal_id, outcome)


def get_recent_signals(limit: int = 50) -> List[Dict]:
    """Fetch most recent signals."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM signals ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for r in rows:
        try:
            r["agent_data"]  = json.loads(r.get("agent_data") or "{}")
            r["key_reasons"] = json.loads(r.get("key_reasons") or "[]")
        except Exception:
            pass
    return rows


def get_todays_signals() -> List[Dict]:
    today = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM signals WHERE timestamp LIKE ? ORDER BY id DESC",
              (today + "%",))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_consecutive_losses() -> int:
    """Count consecutive losses from most recent signals."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT outcome FROM signals
        WHERE outcome IN ('WIN','LOSS')
        ORDER BY id DESC LIMIT 10
    """)
    rows = c.fetchall()
    conn.close()
    count = 0
    for row in rows:
        if row["outcome"] == "LOSS":
            count += 1
        else:
            break
    return count


# ── DAILY STATS ───────────────────────────────────────────────────────────────

def _update_daily_stats():
    """Recompute today's stats from signals table."""
    today = date.today().isoformat()
    sigs = get_todays_signals()
    total   = len(sigs)
    calls   = sum(1 for s in sigs if s["direction"] == "CALL")
    puts    = sum(1 for s in sigs if s["direction"] == "PUT")
    wins    = sum(1 for s in sigs if s["outcome"] == "WIN")
    losses  = sum(1 for s in sigs if s["outcome"] == "LOSS")
    pending = sum(1 for s in sigs if s["outcome"] == "PENDING")
    avg_conf = (sum(s["confidence"] for s in sigs) / total) if total > 0 else 0.0
    consec   = get_consecutive_losses()

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO daily_stats
          (date, total_signals, calls, puts, wins, losses, pending,
           avg_confidence, consecutive_losses)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(date) DO UPDATE SET
          total_signals=excluded.total_signals,
          calls=excluded.calls,
          puts=excluded.puts,
          wins=excluded.wins,
          losses=excluded.losses,
          pending=excluded.pending,
          avg_confidence=excluded.avg_confidence,
          consecutive_losses=excluded.consecutive_losses
    """, (today, total, calls, puts, wins, losses, pending, avg_conf, consec))
    conn.commit()
    conn.close()


def get_daily_stats(days: int = 7) -> List[Dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (days,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_todays_stat() -> Dict:
    today = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM daily_stats WHERE date=?", (today,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "date": today, "total_signals": 0, "calls": 0, "puts": 0,
        "wins": 0, "losses": 0, "pending": 0, "avg_confidence": 0,
        "consecutive_losses": 0, "trading_halted": 0, "daily_risk_used": 0,
    }


def get_overall_stats() -> Dict:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT
          COUNT(*) as total,
          SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
          SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
          AVG(confidence) as avg_confidence,
          MAX(confidence) as best_signal
        FROM signals
        WHERE outcome IN ('WIN','LOSS')
    """)
    row = c.fetchone()
    conn.close()
    r = dict(row) if row else {}
    total = r.get("total") or 0
    wins  = r.get("wins") or 0
    win_rate = round(wins / total * 100, 1) if total > 0 else 0.0
    r["win_rate"] = win_rate
    return r


# ── RISK LOG ──────────────────────────────────────────────────────────────────

def log_risk_event(event: str, detail: str = None, value: float = None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO risk_log (timestamp, event, detail, value) VALUES (?,?,?,?)",
              (datetime.utcnow().isoformat(), event, detail, value))
    conn.commit()
    conn.close()
    logger.warning("RISK EVENT: %s | %s | %s", event, detail, value)
