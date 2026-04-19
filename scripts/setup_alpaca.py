#!/usr/bin/env python3
"""Setup script for Alpaca API configuration.

Writes credentials to .env in the project root — the canonical credential
source. Supports separate paper and live key pairs. Migrates legacy
config/secrets/alpaca_config.json automatically when detected.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / '.env'

# Legacy JSON path (migration source only)
_LEGACY_CONFIG = PROJECT_ROOT / 'config' / 'secrets' / 'alpaca_config.json'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_env_file() -> dict[str, str]:
    """Parse existing .env file into a key→value dict."""
    result: dict[str, str] = {}
    if not ENV_FILE.exists():
        return result
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        result[k.strip()] = v.strip()
    return result


def _write_env_file(values: dict[str, str]) -> None:
    """Merge values into .env, preserving comments and unrelated keys."""
    existing_lines: list[str] = []
    if ENV_FILE.exists():
        existing_lines = ENV_FILE.read_text().splitlines()

    # Track which keys we've already updated in existing lines
    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            k = stripped.split('=', 1)[0].strip()
            if k in values:
                new_lines.append(f'{k}={values[k]}')
                updated_keys.add(k)
                continue
        new_lines.append(line)

    # Append any keys not already in the file
    remaining = {k: v for k, v in values.items() if k not in updated_keys}
    if remaining:
        if new_lines and new_lines[-1].strip():
            new_lines.append('')
        for k, v in remaining.items():
            new_lines.append(f'{k}={v}')

    ENV_FILE.write_text('\n'.join(new_lines) + '\n')
    os.chmod(ENV_FILE, 0o600)


def _load_legacy_config() -> dict | None:
    """Load legacy alpaca_config.json. Returns None if not found."""
    if not _LEGACY_CONFIG.exists():
        return None
    import json
    try:
        return json.loads(_LEGACY_CONFIG.read_text())
    except Exception:
        return None


def _prompt(label: str, default: str = '') -> str:
    hint = f' [{default}]' if default else ''
    try:
        val = input(f'{label}{hint}: ').strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val or default


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def _maybe_migrate() -> bool:
    """Detect legacy JSON config and offer to migrate keys to .env.

    Returns True if migration happened (or user skipped), False if aborted.
    """
    legacy = _load_legacy_config()
    if not legacy:
        return True  # nothing to migrate

    print()
    print('⚠️  Legacy config detected: config/secrets/alpaca_config.json')
    print('   This file is no longer used. Keys are now stored in .env.')
    answer = _prompt('   Migrate keys from JSON to .env now? (Y/n)', default='y').lower()
    if answer not in ('y', 'yes', ''):
        print('   Skipping migration — existing JSON will be ignored.')
        return True

    to_write: dict[str, str] = {}

    paper = legacy.get('paper', {})
    if paper.get('api_key'):
        to_write['ALPACA_PAPER_API_KEY'] = paper['api_key']
    if paper.get('secret_key'):
        to_write['ALPACA_PAPER_SECRET_KEY'] = paper['secret_key']

    live = legacy.get('live', {})
    if live.get('api_key'):
        to_write['ALPACA_LIVE_API_KEY'] = live['api_key']
    if live.get('secret_key'):
        to_write['ALPACA_LIVE_SECRET_KEY'] = live['secret_key']

    if legacy.get('historical_days') and int(legacy['historical_days']) != 365:
        to_write['ALPACA_HISTORICAL_DAYS'] = str(legacy['historical_days'])

    if to_write:
        _write_env_file(to_write)
        print(f'   ✅ Migrated {len(to_write)} key(s) to {ENV_FILE}')

    delete = _prompt('   Delete the old JSON file? (Y/n)', default='y').lower()
    if delete in ('y', 'yes', ''):
        _LEGACY_CONFIG.unlink()
        print('   🗑️  Deleted config/secrets/alpaca_config.json')
    else:
        print('   Keeping old JSON (it is gitignored and will not be loaded).')

    return True


# ---------------------------------------------------------------------------
# Main setup flow
# ---------------------------------------------------------------------------

def setup() -> None:
    print()
    print('🔌 Alpaca API Setup')
    print('=' * 60)
    print()
    print('Credentials are stored in .env at the project root.')
    print('Get keys from: https://app.alpaca.markets')
    print()

    _maybe_migrate()

    current = _read_env_file()

    # ---- Paper keys --------------------------------------------------------
    print('── Paper account keys ─────────────────────────────────────')
    existing_paper_key = current.get('ALPACA_PAPER_API_KEY') or current.get('ALPACA_API_KEY', '')
    if existing_paper_key:
        masked = existing_paper_key[:6] + '...' + existing_paper_key[-4:]
        print(f'   Current paper API key: {masked}')
        if _prompt('   Keep existing paper keys? (Y/n)', 'y').lower() in ('y', 'yes', ''):
            paper_key = current.get('ALPACA_PAPER_API_KEY', '')
            paper_secret = current.get('ALPACA_PAPER_SECRET_KEY', '')
        else:
            paper_key = _prompt('   Paper API Key')
            paper_secret = _prompt('   Paper Secret Key')
    else:
        print('   No paper keys configured.')
        paper_key = _prompt('   Paper API Key (leave blank to skip)')
        paper_secret = _prompt('   Paper Secret Key (leave blank to skip)') if paper_key else ''

    # ---- Live keys ---------------------------------------------------------
    print()
    print('── Live account keys (optional) ────────────────────────────')
    existing_live_key = current.get('ALPACA_LIVE_API_KEY', '')
    if existing_live_key:
        masked = existing_live_key[:6] + '...' + existing_live_key[-4:]
        print(f'   Current live API key: {masked}')
        if _prompt('   Keep existing live keys? (Y/n)', 'y').lower() in ('y', 'yes', ''):
            live_key = current.get('ALPACA_LIVE_API_KEY', '')
            live_secret = current.get('ALPACA_LIVE_SECRET_KEY', '')
        else:
            live_key = _prompt('   Live API Key (leave blank to skip)')
            live_secret = _prompt('   Live Secret Key (leave blank to skip)') if live_key else ''
    else:
        live_key = _prompt('   Live API Key (leave blank to skip)')
        live_secret = _prompt('   Live Secret Key (leave blank to skip)') if live_key else ''

    # ---- Historical days ---------------------------------------------------
    print()
    existing_days = current.get('ALPACA_HISTORICAL_DAYS', '365')
    days_input = _prompt(f'   Historical days', default=existing_days)
    try:
        historical_days = int(days_input)
    except ValueError:
        historical_days = 365

    # ---- Write -------------------------------------------------------------
    to_write: dict[str, str] = {}
    if paper_key:
        to_write['ALPACA_PAPER_API_KEY'] = paper_key
    if paper_secret:
        to_write['ALPACA_PAPER_SECRET_KEY'] = paper_secret
    if live_key:
        to_write['ALPACA_LIVE_API_KEY'] = live_key
    if live_secret:
        to_write['ALPACA_LIVE_SECRET_KEY'] = live_secret
    if historical_days != 365:
        to_write['ALPACA_HISTORICAL_DAYS'] = str(historical_days)

    if not to_write:
        print()
        print('⚠️  No credentials entered — nothing saved.')
        return

    _write_env_file(to_write)

    print()
    print(f'✅ Saved to: {ENV_FILE}')
    print('   Permissions: 600 (owner read/write only)')
    print()
    print('Next steps:')
    print('  Test the connection:')
    print('    python3 scripts/setup_alpaca.py --test')
    print()
    print('  Start the paper engine:')
    print('    python3 scripts/paper_engine_alpaca.py')


def test_connection() -> bool:
    """Test Alpaca connection."""
    print()
    print('🔍 Testing Alpaca connection...')
    print()

    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / '.env')

        from traderlib.alpaca_client import AlpacaClient

        client = AlpacaClient(mode='paper')
        account = client.get_account()

        print('✅ Connection successful!')
        print()
        print('📊 Account Info:')
        print(f"   Status:        {account['status']}")
        print(f"   Cash:          ${account['cash']:,.2f}")
        print(f"   Equity:        ${account['equity']:,.2f}")
        print(f"   Buying Power:  ${account['buying_power']:,.2f}")

        positions = client.list_positions()
        print()
        print(f'📋 Open Positions: {len(positions)}')
        for p in positions:
            print(f"   {p['symbol']}: {p['qty']} shares")

        return True

    except Exception as e:
        print(f'❌ {e}')
        print()
        print('To configure Alpaca, run:')
        print('   python3 scripts/setup_alpaca.py')
        return False


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        sys.exit(0 if test_connection() else 1)
    else:
        setup()
