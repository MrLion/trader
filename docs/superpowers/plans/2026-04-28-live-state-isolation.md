# Live State Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate paper and live trading state into separate directories so switching modes can't cross-contaminate positions, trades, or risk configs.

**Architecture:** Make `PaperState` and `OrderManager` accept a mode-specific `data_dir` instead of using module-level globals. The engine constructs `data/{mode}/` and `config/{mode}/risk_config.yaml` from the `--mode` flag. A one-time migration on startup moves existing files from `data/` root into `data/paper/`.

**Tech Stack:** Python 3.11+, pathlib, json, yaml, rich (dashboard)

---

### Task 1: Update PaperState to accept data_dir

**Files:**
- Modify: `traderlib/paper_state.py`

- [ ] **Step 1: Refactor PaperState to use instance-level paths instead of module globals**

In `paper_state.py`, replace the module-level file constants with instance attributes. The module-level `DATA_DIR`, `POSITIONS_FILE`, `DAILY_TRACKER_FILE`, `TRADES_FILE` become instance properties constructed from a `data_dir` parameter.

Change the module-level globals (lines 38-42):
```python
DEFAULT_DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
DATA_DIR = Path(os.environ.get('PAPER_TRADING_DATA_DIR', DEFAULT_DATA_DIR))
POSITIONS_FILE = DATA_DIR / 'paper_positions.json'
DAILY_TRACKER_FILE = DATA_DIR / 'daily_tracker.json'
TRADES_FILE = DATA_DIR / 'paper_trades.jsonl'
```

To keep backward compatibility but remove file-level construction:
```python
DEFAULT_ROOT_DATA_DIR = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
ROOT_DATA_DIR = Path(os.environ.get('PAPER_TRADING_DATA_DIR', DEFAULT_ROOT_DATA_DIR))
```

Then update `PaperState.__init__` (line 179) to accept `data_dir` and `mode`:
```python
def __init__(self, initial_capital: float = 100000, data_dir: Optional[Path] = None, mode: str = "paper"):
    self.initial_capital = initial_capital
    self.mode = mode
    self.positions: Dict[str, Position] = {}
    self.cash = initial_capital
    self.day_pnl = 0.0
    self.trade_count = 0
    self.entries_today = 0
    self.last_entry_reset = datetime.now().strftime('%Y-%m-%d')

    # Use mode-specific subdirectory
    if data_dir is not None:
        self.data_dir = data_dir
    else:
        self.data_dir = ROOT_DATA_DIR / mode

    self.data_dir.mkdir(parents=True, exist_ok=True)
    self.positions_file = self.data_dir / 'positions.json'
    self.daily_tracker_file = self.data_dir / 'daily_tracker.json'
    self.trades_file = self.data_dir / 'trades.jsonl'

    self._load_state()
```

Then update all references from module globals to instance attributes. Replace `POSITIONS_FILE` with `self.positions_file`, `DAILY_TRACKER_FILE` with `self.daily_tracker_file`, and `TRADES_FILE` with `self.trades_file` throughout the class methods. The `_load_state`, `save_positions`, `_log_trade`, `_reconcile_counters_from_log`, and any other methods that reference these globals must use `self.*` instead.

- [ ] **Step 2: Verify no remaining module-level file references in PaperState methods**

Run: `grep -n "POSITIONS_FILE\|DAILY_TRACKER_FILE\|TRADES_FILE\|DATA_DIR" /Users/mintmrlion/.openclaw/workspaces/trader/traderlib/paper_state.py`

Expected: Only `ROOT_DATA_DIR` and `DEFAULT_ROOT_DATA_DIR` at module level. All file references inside the class should use `self.positions_file`, `self.daily_tracker_file`, `self.trades_file`, `self.data_dir`.

- [ ] **Step 3: Run existing paper_state tests**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader && python3 -m pytest tests/ -k "paper_state" -v
```

Expected: Tests pass (or adjust if tests relied on old module globals).

- [ ] **Step 4: Commit**

```bash
git add traderlib/paper_state.py
git commit -m "refactor: make PaperState accept mode-specific data_dir instead of module globals"
```

---

### Task 2: Update OrderManager to accept data_dir

**Files:**
- Modify: `traderlib/order_manager.py`

- [ ] **Step 1: Add explicit data_dir parameter to OrderManager**

Change the init (line 126) to accept an optional `data_dir`:
```python
def __init__(self, alpaca_client, max_tps: float = 2.0, max_queue_size: int = 50, data_dir: Optional[Path] = None):
    self.alpaca = alpaca_client

    # ... order tracking, position tracking unchanged ...

    # Persistence - use provided data_dir or fall back to env var / default
    if data_dir is not None:
        self.data_dir = data_dir
    else:
        default_data_dir = Path('/Users/mintmrlion/.openclaw/workspaces/trader/data')
        self.data_dir = Path(os.environ.get('PAPER_TRADING_DATA_DIR', default_data_dir))

    self.orders_file = self.data_dir / 'orders.json'
    self.data_dir.mkdir(parents=True, exist_ok=True)

    # ... rest unchanged ...
```

- [ ] **Step 2: Run existing order_manager tests**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader && python3 -m pytest tests/ -k "order" -v
```

Expected: Tests pass.

- [ ] **Step 3: Commit**

```bash
git add traderlib/order_manager.py
git commit -m "refactor: make OrderManager accept explicit data_dir parameter"
```

---

### Task 3: Create risk config directories and files

**Files:**
- Create: `config/paper/risk_config.yaml`
- Create: `config/live/risk_config.yaml`

- [ ] **Step 1: Move existing risk config to paper subdirectory**

```bash
mkdir -p /Users/mintmrlion/.openclaw/workspaces/trader/config/paper
mkdir -p /Users/mintmrlion/.openclaw/workspaces/trader/config/live
cp /Users/mintmrlion/.openclaw/workspaces/trader/config/risk_config.yaml /Users/mintmrlion/.openclaw/workspaces/trader/config/paper/risk_config.yaml
```

- [ ] **Step 2: Create conservative live risk config**

Write `config/live/risk_config.yaml` as a copy of the paper config with tighter constraints. Key differences from paper:

```yaml
account_risk:
  max_risk_per_trade_pct: 0.25     # Paper: 0.5%
  max_daily_loss_pct: 1.0          # Paper: 2.0%
  max_position_size_pct: 5.0       # Paper: 10.0%

stop_loss:
  max_stop_distance_pct: 0.05      # Paper: 0.10
  atr_period: 14                   # Same
  atr_multiplier: 1.5              # Paper: 2.0

exit_strategy:
  mode: "hybrid"
  scale_out_enabled: true
  scale_out_1_pct: 30              # Paper: 50% at first target
  trailing_enabled: true
```

Copy the full YAML from `config/paper/risk_config.yaml` and adjust only the numeric risk values. Keep all other sections (cooldown, entry thresholds, market filters) identical.

- [ ] **Step 3: Commit**

```bash
git add config/paper/risk_config.yaml config/live/risk_config.yaml
git commit -m "feat: split risk config into paper/ and live/ subdirectories"
```

---

### Task 4: Update RiskConfigManager to support mode-based paths

**Files:**
- Modify: `traderlib/risk_config.py`

- [ ] **Step 1: Update _default_config_path to accept optional mode parameter**

Add a class-level helper and update the default path logic:

```python
@staticmethod
def default_config_path_for_mode(mode: str = "paper") -> Path:
    """Get default config path for a given mode."""
    repo_root = Path(__file__).parent.parent
    return repo_root / "config" / mode / "risk_config.yaml"
```

Update `_default_config_path` (line 251) to check for the new layout first, fall back to old:
```python
def _default_config_path(self) -> Path:
    repo_root = Path(__file__).parent.parent
    # New layout: config/{mode}/risk_config.yaml
    new_path = repo_root / "config" / "paper" / "risk_config.yaml"
    if new_path.exists():
        return new_path
    # Fallback: old layout
    old_path = repo_root / "config" / "risk_config.yaml"
    return old_path
```

- [ ] **Step 2: Run risk_config tests**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader && python3 -m pytest tests/ -k "risk" -v
```

Expected: Tests pass.

- [ ] **Step 3: Commit**

```bash
git add traderlib/risk_config.py
git commit -m "refactor: update RiskConfigManager default path for mode-based layout"
```

---

### Task 5: Add migration logic to the engine

**Files:**
- Modify: `scripts/paper_engine_alpaca.py`

- [ ] **Step 1: Add migration function**

Add a function that runs before engine init, migrating old flat-layout files into `data/paper/`:

```python
def _migrate_old_layout(data_root: Path) -> None:
    """One-time migration: move flat data/* files into data/paper/."""
    old_files = {
        'paper_positions.json': 'positions.json',
        'paper_positions.json.backup': 'positions.json.backup',
        'paper_trades.jsonl': 'trades.jsonl',
        'paper_trades.jsonl.backup': 'trades.jsonl.backup',
        'alpaca_orders.json': 'orders.json',
        'daily_tracker.json': 'daily_tracker.json',
    }

    # Check if migration is needed
    first_old_file = data_root / 'paper_positions.json'
    if not first_old_file.exists():
        return  # Already migrated or fresh install

    paper_dir = data_root / 'paper'
    paper_dir.mkdir(parents=True, exist_ok=True)

    for old_name, new_name in old_files.items():
        old_path = data_root / old_name
        if old_path.exists():
            # Create .bak copy before moving
            bak_path = data_root / f"{old_name}.bak"
            import shutil
            shutil.copy2(old_path, bak_path)
            # Move to new location
            new_path = paper_dir / new_name
            shutil.move(str(old_path), str(new_path))

    print("✅ Migrated trading state to data/paper/ (backups left as .bak files)")
```

- [ ] **Step 2: Wire migration into engine startup**

In the `AlpacaPaperEngine.__init__` or in `main()`, call migration before state initialization. The data root is `ROOT_DATA_DIR` (or `DATA_DIR` from env var). Call it early, before `PaperState(...)` is constructed:

```python
# In main(), before engine creation:
data_root = Path(os.environ.get('PAPER_TRADING_DATA_DIR', DEFAULT_DATA_DIR))
_migrate_old_layout(data_root)
```

- [ ] **Step 3: Commit**

```bash
git add scripts/paper_engine_alpaca.py
git commit -m "feat: add one-time migration from flat data/ to data/paper/"
```

---

### Task 6: Wire mode-based paths into the engine

**Files:**
- Modify: `scripts/paper_engine_alpaca.py`

- [ ] **Step 1: Construct mode-specific paths and pass to components**

In `AlpacaPaperEngine.__init__`, construct `mode_data_dir` and `mode_config_path`:

```python
class AlpacaPaperEngine:
    def __init__(self, mode: str = 'paper', risk_profile: Optional[str] = None, ...):
        self.mode = mode

        # Mode-specific paths
        data_root = Path(os.environ.get('PAPER_TRADING_DATA_DIR', DEFAULT_DATA_DIR))
        self.mode_data_dir = data_root / mode
        config_path = Path(__file__).parent.parent / 'config' / mode / 'risk_config.yaml'

        # Risk manager with mode-specific config
        self.risk_manager = RiskConfigManager(config_path=config_path, profile=risk_profile)
        self.risk_config = self.risk_manager.get_config()

        # State with mode-specific data dir
        self.state = PaperState(
            initial_capital=self._get_account_value(),
            data_dir=self.mode_data_dir,
            mode=mode,
        )

        # Order manager with mode-specific data dir
        self.order_manager = OrderManager(
            self.alpaca,
            data_dir=self.mode_data_dir,
        )
```

- [ ] **Step 2: Update imports**

Remove the old import of `TRADES_FILE` from paper_state if it was used:
```python
# Remove this line if present:
# from traderlib.paper_state import PaperState, Position, TRADES_FILE
# Replace with:
from traderlib.paper_state import PaperState, Position
```

- [ ] **Step 3: Commit**

```bash
git add scripts/paper_engine_alpaca.py
git commit -m "feat: wire mode-specific data_dir and config paths into engine"
```

---

### Task 7: Add mode indicator to dashboard

**Files:**
- Modify: `traderlib/dashboard.py`

- [ ] **Step 1: Add mode to dashboard state and color the header badge**

Update `_header` to accept and display the mode:

```python
def _header(self, state: Dict[str, Any]) -> Text:
    now = datetime.now().strftime("%H:%M:%S")
    mode = state.get("mode", "PAPER")
    market = state.get("market_status", "UNKNOWN")

    mode_color = "green" if mode.upper() == "LIVE" else "cornflower_blue"
    mode_display = mode.upper()

    # ... rest of header unchanged ...

    return Text.assemble(
        "  ",
        (f"{mode_display} ENGINE", f"bold {mode_color}"), "    ",
        (now, "bold white"), " ET    ",
        (f"MARKET {market}", f"bold {market_color}"), "    ",
        "VIX ", (f"{vix:.2f}" if isinstance(vix, (int, float)) else str(vix), f"bold {vix_color}"), "    ",
        "WS: ", (ws, f"bold {ws_color}"), "    ",
        "API: ", (api, f"bold {api_color}"),
    )
```

- [ ] **Step 2: Ensure engine passes mode to dashboard state**

In the engine's dashboard update method, include `mode` in the state dict:

```python
dashboard_state = {
    "mode": self.mode,
    "market_status": market_status,
    "equity": equity,
    # ... other fields ...
}
self.dashboard.update(dashboard_state)
```

Find the existing location where dashboard state is assembled (search for `self.dashboard.update`) and add `"mode": self.mode` to the dict.

- [ ] **Step 3: Commit**

```bash
git add traderlib/dashboard.py scripts/paper_engine_alpaca.py
git commit -m "feat: add color-coded mode indicator to dashboard (blue PAPER / green LIVE)"
```

---

### Task 8: Clean up old config file

**Files:**
- Modify: `config/risk_config.yaml` (remove after verifying everything works)

- [ ] **Step 1: Remove old config/risk_config.yaml**

After verifying the engine starts correctly with the new layout, remove the old config:

```bash
rm /Users/mintmrlion/.openclaw/workspaces/trader/config/risk_config.yaml
```

- [ ] **Step 2: Verify engine starts cleanly**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader && timeout 5 python3 scripts/paper_engine_alpaca.py --mode paper 2>&1 || true
```

Expected: No errors about missing config. Engine initializes and starts scan loop.

- [ ] **Step 3: Commit**

```bash
git add config/risk_config.yaml
git commit -m "chore: remove old flat config/risk_config.yaml (migrated to config/paper/)"
```

---

### Task 9: Integration verification

**Files:**
- None (verification only)

- [ ] **Step 1: Verify paper mode data isolation**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader && python3 -c "
from pathlib import Path
paper_dir = Path('data/paper')
print('Paper dir exists:', paper_dir.exists())
print('Files:', list(paper_dir.glob('*.json')) if paper_dir.exists() else 'N/A')
print('Config:', Path('config/paper/risk_config.yaml').exists())
"
```

Expected: `data/paper/` exists with `positions.json` (or empty). `config/paper/risk_config.yaml` exists.

- [ ] **Step 2: Verify live directory is created on demand**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader && python3 -c "
from pathlib import Path
live_dir = Path('data/live')
print('Live dir exists:', live_dir.exists())
# Don't run the engine in live mode, just verify config exists
print('Live config:', Path('config/live/risk_config.yaml').exists())
"
```

Expected: `data/live/` may not exist yet (gets created on first live run). `config/live/risk_config.yaml` exists.

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/mintmrlion/.openclaw/workspaces/trader && python3 -m pytest tests/ -v --timeout=60 2>&1 | tail -30
```

Expected: All tests pass (or pre-existing failures only, no new failures).

- [ ] **Step 4: Commit any final adjustments, then bump version**

```bash
echo "0.6.16.0" > VERSION
# Update CHANGELOG.md with release notes
git add VERSION CHANGELOG.md
git commit -m "chore: bump version to 0.6.16.0 and update changelog"
```
