#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$ROOT_DIR"

LOOPS="${1:-1}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! [[ "$LOOPS" =~ ^[0-9]+$ ]] || [[ "$LOOPS" -lt 1 ]]; then
  echo "Usage: $0 [loops>=1]"
  exit 2
fi

failed=0

echo "AILinux Client Debug Loop"
echo "root:  $ROOT_DIR"
echo "loops: $LOOPS"
echo "python:$PYTHON_BIN"
echo ""

for i in $(seq 1 "$LOOPS"); do
  echo "=== Loop $i/$LOOPS ==="

  echo "[1/4] compileall"
  if ! "$PYTHON_BIN" -m compileall -q ailinux_client; then
    echo "compileall failed"
    failed=1
    continue
  fi

  echo "[2/4] import smoke"
  if ! "$PYTHON_BIN" - <<'PY'
import importlib
mods=[
    'ailinux_client.main',
    'ailinux_client.core.api_client',
    'ailinux_client.core.encrypted_settings',
    'ailinux_client.core.mcp_node_client',
    'ailinux_client.ui.main_window',
    'ailinux_client.ui.settings_dialog',
]
for m in mods:
    importlib.import_module(m)
print('import smoke: ok')
PY
  then
    echo "import smoke failed"
    failed=1
    continue
  fi

  echo "[3/4] hwinfo mode"
  if ! "$PYTHON_BIN" run.py --hwinfo >/tmp/ailinux-client-hwinfo.out 2>/tmp/ailinux-client-hwinfo.err; then
    echo "hwinfo failed"
    cat /tmp/ailinux-client-hwinfo.err || true
    failed=1
    continue
  fi

  echo "[4/4] safe-mode arg path"
  if ! "$PYTHON_BIN" - <<'PY'
from ailinux_client.main import parse_args
import sys
sys.argv = ['ailinux-client', '--safe-mode', '--no-local-mcp', '--no-mcp-node']
parse_args()
print('arg parse: ok')
PY
  then
    echo "safe-mode parse failed"
    failed=1
    continue
  fi

  echo "Loop $i passed"
  echo ""
done

if [[ "$failed" -ne 0 ]]; then
  echo "Debug loop finished with failures"
  exit 1
fi

echo "Debug loop finished successfully"
