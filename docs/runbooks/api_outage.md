# Runbook: Alpaca API Outage

**Last Updated:** 2026-04-08  
**Severity:** Critical - Trading halted  
**Estimated Recovery Time:** 5-15 minutes

---

## Symptoms

- Engine logs show repeated connection timeouts
- `⚠️ Error syncing with Alpaca: Connection timeout`
- WebSocket disconnected, no price updates
- Orders failing to submit
- Price cache showing stale data (>60 seconds old)

## Diagnosis

### Step 1: Verify API Status
```bash
# Check Alpaca status page
curl -s https://status.alpaca.markets/api/v2/status.json | jq '.status.indicator'

# Expected: "none" (operational)
# If "major" or "critical": Alpaca is down
```

### Step 2: Verify Local Credentials
```bash
# Test API connectivity
python3 scripts/setup_alpaca.py --test

# Expected output:
# ✅ Alpaca connection successful
# 📊 Account: $100,000.00 equity
```

### Step 3: Check Network Connectivity
```bash
# Test basic connectivity
curl -I https://paper-api.alpaca.markets/v2/account

# Expected: HTTP/2 200
# If timeout: Network or Alpaca issue
```

## Recovery

### Option A: Automatic Fallback (Recommended)

The engine automatically falls back to yfinance after 3 consecutive Alpaca failures.

```
⚠️ Alpaca failed (3/3), switching to yfinance fallback
✅ Using yfinance for price data
```

**Action Required:** None. Monitor for data quality.

### Option B: Manual Fallback

If automatic fallback didn't trigger:

```bash
# Stop the engine
Ctrl+C

# Restart with explicit fallback mode
export ALPACA_FALLBACK_MODE=yfinance
python3 scripts/paper_engine_alpaca.py
```

### Option C: Circuit Breaker Reset

If circuit breaker opened and won't close:

```bash
# Check circuit status
python3 -c "from rate_limiter import RateLimiter; r = RateLimiter(); print(r.get_status())"

# Force reset (only if you're sure API is healthy)
python3 -c "from rate_limiter import RateLimiter; r = RateLimiter(); r._close_circuit()"
```

### Option D: Switch to Manual Trading

If API remains down >30 minutes:

```bash
# Stop automated engine
python3 scripts/paper_engine_alpaca.py --shutdown

# Use manual CLI for critical operations
python3 scripts/paper_portfolio.py live    # Check positions
python3 scripts/entry_signals.py           # Identify setups manually
```

## Prevention

1. **Monitor health endpoint:**
   ```bash
   # Add to cron every 5 minutes
   */5 * * * * python3 scripts/paper_portfolio.py status > /dev/null 2>&1 || echo "Engine down" | mail -s "Trading Alert" admin@example.com
   ```

2. **Set up alerts for circuit breaker events:**
   - Watch log for `⚠️ CIRCUIT BREAKER OPENED`
   - Alert if circuit stays open >5 minutes

3. **Test failover monthly:**
   ```bash
   python3 scripts/test_failover.py
   ```

## Related

- [Partial Fill Runbook](./partial_fill.md)
- [Stuck Position Runbook](./stuck_position.md)
- Alpaca Status: https://status.alpaca.markets
- Emergency Contact: support@alpaca.markets
