#!/bin/bash
cd /Users/mintmrlion/.openclaw/workspaces/trader
python3 scripts/deliver_report.py --file /Users/mintmrlion/.openclaw/workspaces/trader/reports/premarket_report_$(date +%Y-%m-%d).html --caption "🌅 Pre-Market Report — $(date +%B\ %d,\ %Y)

Detailed regime and watchlist rankings attached as HTML." --chat-id -4872065090
