#!/bin/bash
# AILinux Client Launcher

cd "$(dirname "$0")"

# Clear Python cache
find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
find . -name '*.pyc' -delete 2>/dev/null

# Run the client
exec python3 run.py "$@"
