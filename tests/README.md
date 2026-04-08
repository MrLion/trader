# Alpaca Integration Tests

Test suite for Alpaca paper trading integration.

## Running Tests

### Quick Validation

```bash
# Run full validation suite
python3 scripts/validate_alpaca.py
```

### Unit Tests

```bash
# Run all unit tests
python3 tests/test_alpaca_integration.py

# Run specific test class
python3 -m unittest tests.test_alpaca_integration.TestRateLimiter
```

## Test Coverage

### Rate Limiter Tests (`TestRateLimiter`)
- Initialization
- Request tracking
- Exponential backoff
- Circuit breaker
- Success recovery

### Health Monitor Tests (`TestAPIHealthMonitor`)
- Provider health tracking
- Failure detection
- Recovery detection
- Fallback logic

### Order Manager Tests (`TestOrderManager`)
- Order submission (entry/exit)
- Order status tracking
- Duplicate prevention
- Position sync
- Order summary

## Mock Alpaca Client

Tests use `MockAlpacaClient` which simulates:
- Account info
- Price data
- Historical bars
- Order submission
- Position management

This allows testing without real API calls.

## CI/CD Integration

```yaml
# Example GitHub Actions
- name: Run Tests
  run: python3 tests/test_alpaca_integration.py
  env:
    ALPACA_API_KEY: ${{ secrets.ALPACA_API_KEY }}
    ALPACA_SECRET_KEY: ${{ secrets.ALPACA_SECRET_KEY }}
```
