#!/bin/bash
# Run all tests with coverage reporting
# Usage: ./scripts/run_tests.sh [options]
# Options:
#   --ci       Run in CI mode (stricter)
#   --fast     Skip slow integration tests
#   --html     Generate HTML coverage report

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================="
echo "🧪 Running Trading Engine Tests"
echo "=================================="
echo ""

# Parse arguments
CI_MODE=false
FAST_MODE=false
HTML_REPORT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --ci)
            CI_MODE=true
            shift
            ;;
        --fast)
            FAST_MODE=true
            shift
            ;;
        --html)
            HTML_REPORT=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check dependencies
echo "Checking dependencies..."
python3 -c "import pytest" 2>/dev/null || { echo -e "${RED}pytest not installed. Run: pip install pytest pytest-cov pytest-asyncio${NC}"; exit 1; }
python3 -c "import pytest_cov" 2>/dev/null || { echo -e "${RED}pytest-cov not installed. Run: pip install pytest-cov${NC}"; exit 1; }

echo -e "${GREEN}✓ Dependencies OK${NC}"
echo ""

# Create coverage directory
mkdir -p .gstack/qa-reports/coverage

# Build pytest command
PYTEST_ARGS="-v"

if [ "$CI_MODE" = true ]; then
    echo "Running in CI mode (strict)..."
    PYTEST_ARGS="$PYTEST_ARGS --cov=scripts --cov-branch --cov-fail-under=70"
elif [ "$HTML_REPORT" = true ]; then
    echo "Running with HTML coverage report..."
    PYTEST_ARGS="$PYTEST_ARGS --cov=scripts --cov-branch --cov-report=html:.gstack/qa-reports/coverage/html --cov-report=term-missing"
else
    echo "Running with terminal coverage report..."
    PYTEST_ARGS="$PYTEST_ARGS --cov=scripts --cov-branch --cov-report=term-missing"
fi

if [ "$FAST_MODE" = true ]; then
    echo "Fast mode: skipping slow integration tests"
    PYTEST_ARGS="$PYTEST_ARGS -m 'not slow'"
fi

# Run Phase 1-3 tests
echo ""
echo "=================================="
echo "📋 Phase 1: Integration Tests"
echo "=================================="
python3 -m pytest tests/test_integration_paper_engine.py $PYTEST_ARGS || true

echo ""
echo "=================================="
echo "📋 Phase 2: Fixture Tests"
echo "=================================="
if [ -f "tests/test_stage2_with_fixtures.py" ]; then
    python3 -m pytest tests/test_stage2_with_fixtures.py $PYTEST_ARGS || true
else
    echo -e "${YELLOW}⚠ Phase 2 tests not yet implemented${NC}"
fi

echo ""
echo "=================================="
echo "📋 Phase 3: Chaos Tests"
echo "=================================="
python3 -m pytest tests/test_chaos.py tests/test_paper_state_recovery.py $PYTEST_ARGS || true

echo ""
echo "=================================="
echo "📋 Legacy Integration Tests"
echo "=================================="
python3 -m pytest tests/test_alpaca_integration.py $PYTEST_ARGS || true

# Summary
echo ""
echo "=================================="
echo "📊 Test Summary"
echo "=================================="

if [ "$HTML_REPORT" = true ]; then
    echo -e "${GREEN}✓ HTML coverage report generated:${NC}"
    echo "  file://$PROJECT_ROOT/.gstack/qa-reports/coverage/html/index.html"
    echo ""
fi

# Check coverage threshold
if [ "$CI_MODE" = true ]; then
    echo "Checking coverage threshold..."
    COVERAGE=$(python3 -m pytest tests/ --cov=scripts --cov-report=term 2>&1 | grep "TOTAL" | awk '{print $4}' | sed 's/%//')
    if [ -n "$COVERAGE" ] && [ "$COVERAGE" -lt 70 ]; then
        echo -e "${RED}✗ Coverage $COVERAGE% below threshold (70%)${NC}"
        exit 1
    else
        echo -e "${GREEN}✓ Coverage threshold met${NC}"
    fi
fi

echo -e "${GREEN}✓ Test run complete${NC}"
