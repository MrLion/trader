#!/bin/bash
export FMP_API_KEY=VrkrfljAVCtE6xCzECcZQDmaHsEr1mAu
cd /Users/mintmrlion/.openclaw/workspaces/trader
python3 scripts/premarket_report.py --html --output /Users/mintmrlion/.openclaw/workspaces/trader/reports/premarket_report_$(date +%Y-%m-%d).html
