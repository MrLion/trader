#!/bin/bash
set -a
[ -f "$(dirname "$0")/.env" ] && . "$(dirname "$0")/.env"
set +a
cd "$(dirname "$0")"
mkdir -p reports
python3 scripts/premarket_report.py --html --output reports/premarket_report_$(date +%Y-%m-%d).html
