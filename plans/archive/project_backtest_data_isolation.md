---
name: Backtest Data Isolation Plan
description: Plan for isolating backtesting data source from production Alpaca account, deferred v2 data provider work
type: project
originSessionId: 924e735a-ab25-4b9e-8e67-42b6c0557d5d
---
Backtest data isolation implementation plan saved at `/Users/mintmrlion/.claude/plans/virtual-honking-wolf.md`.

**Key finding**: Alpaca does NOT support separate data-only API keys for Trading API accounts — same key pair is used for trading and data. Only Broker API partners can create fine-grained credentials. Real isolation requires alternative data sources (YFinance, file-based).

**Approach**: Make YFinance the default backtest data source (no Alpaca needed), add `data_only` mode to AlpacaClient (prevents code-level order submission), create FileDataProvider for offline backtests. 7 steps: protocol fix, remove isinstance coupling, data_only mode, new providers, CLI refactor, download script, docs.