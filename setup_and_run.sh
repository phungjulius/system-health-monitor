#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_and_run.sh
#
# Sets up the environment and runs the full system health monitor pipeline.
# Designed to work on any standard Linux system with Python 3.10+.
#
# Usage:
#   bash setup_and_run.sh           — full run (tests + monitor)
#   bash setup_and_run.sh --test-only  — run unit tests only
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

MODE="${1:-full}"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  System Health Monitor — setup script"
echo "════════════════════════════════════════════════════════"

# ── 1. check python ───────────────────────────────────────────────────────────
echo ""
echo "[1/4] Checking Python version..."
python3 --version
MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$MINOR" -lt 10 ]; then
  echo "ERROR: Python 3.10+ is required (you have 3.$MINOR)"
  exit 1
fi
echo "      OK"

# ── 2. install deps ───────────────────────────────────────────────────────────
echo ""
echo "[2/4] Installing dependencies..."
pip install --quiet -r requirements.txt
echo "      OK"

# ── 3. run unit tests ─────────────────────────────────────────────────────────
echo ""
echo "[3/4] Running unit tests..."
pytest tests/ -v --tb=short

if [ "$MODE" = "--test-only" ]; then
  echo ""
  echo "Test-only mode — done."
  exit 0
fi

# ── 4. run the monitor ────────────────────────────────────────────────────────
echo ""
echo "[4/4] Running system health monitor..."
python3 main.py
EXIT_CODE=$?

echo ""
if   [ $EXIT_CODE -eq 0 ]; then echo "Done — system looks healthy."
elif [ $EXIT_CODE -eq 1 ]; then echo "Done — warnings detected. Check reports/."
elif [ $EXIT_CODE -eq 2 ]; then echo "Done — critical issues found. Check reports/ immediately."
fi

exit $EXIT_CODE
