# Deployment Guide

Production deployment, scheduling, and monitoring.

---

## Overview

The Trader system can run on any server with Python 3.11+ and cron. This guide covers headless deployment for automated scanning and paper trading.

---

## Prerequisites

- Linux/macOS server
- Python 3.11+
- Git
- Alpaca API credentials (for trading)
- Optional: Telegram Bot Token (for report delivery)

---

## Installation

```bash
# Clone
git clone https://github.com/MrLion/trader.git /opt/trader
cd /opt/trader

# Setup
./setup.sh

# Verify
make doctor
```

---

## Environment Configuration

Create a `.env` file or export variables:

```bash
# Required for trading
export ALPACA_API_KEY="your_key"
export ALPACA_SECRET_KEY="your_secret"

# Optional
export TELEGRAM_BOT_TOKEN="your_token"
export MCSTOCK_USER="your_user"
export MCSTOCK_PASS="your_pass"
```

For production, use a systemd service file or Docker secrets instead of `.env`.

---

## Cron Jobs

### Pre-Market Routine (6:00–9:30 ET)

```bash
# Sector scan (7:50 AM ET weekdays)
50 7 * * 1-5 cd /opt/trader && python3 scripts/sector_scan_comprehensive.py --top 15

# Pre-market report (8:00 AM ET)
0 8 * * 1-5 cd /opt/trader && python3 scripts/premarket_report.py --html

# Deliver to Telegram (8:05 AM ET)
5 8 * * 1-5 cd /opt/trader && python3 scripts/deliver_report.py --file reports/premarket_report.html
```

### Market Hours (9:30–16:00 ET)

```bash
# Paper trading engine (run once, daemon mode)
# Use systemd or screen/tmux for persistent process
```

### Post-Market (16:00–17:00 ET)

```bash
# Post-market report (16:05 ET)
5 16 * * 1-5 cd /opt/trader && python3 scripts/postmarket_report.py --html

# Deliver report (16:10 ET)
10 16 * * 1-5 cd /opt/trader && python3 scripts/deliver_report.py --file reports/postmarket_report.html

# Daily scans (16:30 ET)
30 16 * * 1-5 cd /opt/trader && python3 scripts/trend_screener.py --mode discovery
```

### Weekend (Sunday)

```bash
# Weekly review preparation
0 18 * * 0 cd /opt/trader && python3 scripts/mcstock_historical_scraper.py --weeks 4
```

---

## Running as a Service

### systemd Service (Paper Engine)

```ini
# /etc/systemd/system/trader-paper.service
[Unit]
Description=Trader Paper Trading Engine
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/opt/trader
Environment=ALPACA_API_KEY=your_key
Environment=ALPACA_SECRET_KEY=your_secret
Environment=PAPER_TRADING_DATA_DIR=/opt/trader/data
ExecStart=/usr/bin/python3 /opt/trader/scripts/paper_engine_alpaca.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable trader-paper
sudo systemctl start trader-paper
sudo systemctl status trader-paper
```

---

## Monitoring

### Logs

```bash
# Trading exceptions
tail -f data/logs/trading_exceptions.log

# Paper trades
tail -f data/paper_trades.jsonl

# systemd journal
sudo journalctl -u trader-paper -f
```

### Health Checks

```bash
# Run doctor daily via cron
0 6 * * * cd /opt/trader && python3 scripts/doctor.py
```

### Disk Space

Monitor these directories:

| Directory | What Grows | Rotation |
|-----------|-----------|----------|
| `data/logs/` | Exception logs | Daily rotation |
| `data/paper_trades.jsonl` | Trade history | Manual archive |
| `scans/` | Daily CSV scans | Manual cleanup |
| `reports/` | HTML reports | Weekly cleanup |
| `memory/` | Daily notes | Manual review |

---

## Backup

```bash
# Essential files to backup
data/watchlist.csv
data/paper_positions.json
data/paper_trades.jsonl
config/risk_config.yaml
config/screener_config.yaml
.env

# Exclude
data/logs/*.log
scans/*.csv
reports/*.html
__pycache__/
```

---

## Troubleshooting

### Engine won't start

```bash
# Check credentials
python3 scripts/validate_alpaca.py

# Check doctor
make doctor

# Check logs
journalctl -u trader-paper --no-pager -n 50
```

### Cron jobs not running

```bash
# Check cron logs
grep CRON /var/log/syslog

# Verify paths use absolute paths in crontab
cd /opt/trader && /usr/bin/python3 scripts/premarket_report.py
```

### Out of disk space

```bash
# Clean old scans and reports
find scans/ -name "*.csv" -mtime +30 -delete
find reports/ -name "*.html" -mtime +7 -delete
find data/logs/ -name "*.log.*" -mtime +14 -delete
```

---

## Related

- [Runbooks](runbooks/) — Troubleshooting guides
- [Getting Started](getting-started.md) — Local setup
- [DEVELOPMENT.md](DEVELOPMENT.md) — Development commands
