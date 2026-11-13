#!/bin/bash
cd "$(dirname "$0")"
python3 scripts/deliver_report.py --file reports/premarket_report_$(date +%Y-%m-%d).html --caption "🌅 Pre-Market Report — $(date +%B\ %d,\ %Y)

Detailed regime and watchlist rankings attached as HTML." --chat-id -4872065090
