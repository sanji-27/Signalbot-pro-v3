# 🎯 SureShot Pro — Multi-Agent Signal Bot

A professional, multi-agent AI trading signal system with strict risk management,
Telegram delivery, and a mobile-responsive web dashboard.

---

## 🧠 Architecture: 5-Agent Pipeline

```
Market Data → [Data Agent] → [Technical Agent] → [Regime Agent] → [Risk Agent] → [Oracle Agent] → Signal
```

| Agent | Role |
|-------|------|
| **DataAgent** | Fetches OHLCV from Yahoo Finance & Binance. Caching + retries. |
| **TechnicalAgent** | Computes 15+ indicators: RSI, MACD, BB, ATR, ADX, Ichimoku, Stochastic, CCI, Williams%R, VWAP, EMA Ribbon, Heikin-Ashi |
| **RegimeAgent** | Classifies market: trending / ranging / volatile / weak. Adjusts confidence score. |
| **RiskAgent** | Enforces all risk rules. **Veto power** — no signal fires without risk approval. |
| **OracleAgent** | 25-gate confluence system → realistic confidence %. Final decision maker. |

---

## 📊 25-Gate Confluence System

```
GROUP A: Heikin-Ashi Momentum  (5 gates, weight 20)
GROUP B: Trend Structure        (5 gates, weight 25)
GROUP C: Momentum Oscillators   (5 gates, weight 20)
GROUP D: Volatility & Regime    (5 gates, weight 20)
GROUP E: Price Structure        (5 gates, weight 15)
```

**Confidence Score** = Weighted average of passed gates × Regime multiplier

| Tier | Threshold | Badge |
|------|-----------|-------|
| ELITE | ≥ 88% | 🏆 |
| HIGH | ≥ 82% | ⭐ |
| STANDARD | ≥ 75% | 📊 |

---

## 🛡 Risk Rules (Non-Negotiable)

- ✅ Max **1%** risk per trade (scales with confidence)
- ✅ Max **3%** daily risk → auto-halt
- ✅ Stop after **2 consecutive losses** → auto-halt
- ✅ Ranging markets **filtered automatically**
- ✅ Position size **calculated automatically**
- ✅ Daily reset: limits reset each new trading day

---

## 📱 Assets Supported

**Forex (16):** AUD/CAD, AUD/JPY, AUD/USD, EUR/USD, EUR/JPY, EUR/GBP, EUR/AUD, EUR/CAD, EUR/CHF, GBP/USD, GBP/AUD, GBP/CAD, CAD/JPY, NZD/USD, USD/JPY, GBP/JPY

**OTC (9):** EUR/USD, GBP/USD, AUD/USD, USD/JPY, EUR/JPY, GBP/JPY, EUR/GBP, AUD/JPY, CAD/JPY

**Crypto (2):** BTC/USD, ETH/USD

**Composites (3):** Asia Index, Crypto Composite, Compound Index

**Expiries:** 5, 10, 15, 20, 30, 40, 60 min (multi-timeframe confirmation)

---

## 🚀 Quick Start

### 1. Clone & Configure

```bash
git clone <your-repo>
cd signalbot-pro
cp .env.example .env
# Edit .env with your Telegram credentials
```

### 2. Install

```bash
pip install -r requirements.txt
```

### 3. Run

```bash
python main.py
```

Dashboard: **http://localhost:5000**

---

## ☁️ Free Deployment Options

### Railway.app (Recommended)

1. Push repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → GitHub
3. Add environment variables from `.env`
4. Deploy automatically — free tier included

### Render.com

1. New Web Service → connect repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn main:flask_app`
4. Add environment variables

### Replit

1. Import from GitHub
2. Set Secrets (= environment variables)
3. Run: `python main.py`

---

## ⚙️ Configuration (.env)

```env
# Required
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Signal Quality
MIN_CONFIDENCE=75          # 70-90 recommended
ELITE_CONFIDENCE=88        # Elite tier cutoff
HIGH_QUALITY_ONLY=true     # Only send HIGH/ELITE signals

# Risk Management
MAX_RISK_PER_TRADE=1.0     # Max % per trade
MAX_DAILY_RISK=3.0         # Max daily drawdown %
MAX_CONSECUTIVE_LOSSES=2   # Halt after this many losses
CAPITAL=1000               # Your trading capital

# Scanning
SCAN_EXPIRIES=5,10,15,20,30,40,60
```

---

## 📱 Telegram Message Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 SURESHOT PRO 🏆
──────────────────────────
💱 EUR/USD
📈 🟢 CALL  |  ⏱ 15min

🎯 CONFIDENCE
[████████░░] 87.3%
ELITE tier  |  22/25 gates

📌 TRADE LEVELS
⚡ Entry:      1.08542
🟢 Target 1:  1.08731
🔵 Target 2:  1.08856
🛡 Stop Loss: 1.08421

⏰ Entry: 14:30 UTC
⌛ Expiry: 14:45 UTC

💡 KEY CONFLUENCES
  ✅ EMA ribbon bull aligned (8>13>21)
  ✅ HA 4 consecutive green candles
  ✅ MACD histogram positive
  ✅ Higher TF bullish confirmation

⚠️ RISK NOTE
  Size: 0.87% | Max Loss: $8.70
  Level: LOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 📁 Project Structure

```
signalbot-pro/
├── main.py                    # Flask server + APScheduler + main loop
├── config.py                  # All configuration (loads from .env)
├── telegram_bot.py            # Telegram integration
├── requirements.txt
├── .env.example
├── Procfile                   # For Railway/Render
├── agents/
│   ├── data_agent.py          # OHLCV data fetching
│   ├── technical_agent.py     # All indicator calculations
│   ├── regime_agent.py        # Market regime detection
│   ├── risk_agent.py          # Risk management (veto power)
│   └── oracle_agent.py        # Ensemble decision + confidence
├── core/
│   ├── indicators.py          # Pure math indicator functions
│   ├── signal_engine.py       # Orchestrates agent pipeline
│   └── database.py            # SQLite logging + stats
├── dashboard/
│   └── index.html             # Mobile-responsive web dashboard
└── logs/                      # Auto-created log files
```

---

## ⚠️ Disclaimer

SureShot Pro is for **educational and analytical purposes only**. Binary options and 
forex trading involve significant risk of capital loss. Always test on a demo account 
first. The confidence scores are technical indicators only and do not guarantee outcomes.
Never invest money you cannot afford to lose.
