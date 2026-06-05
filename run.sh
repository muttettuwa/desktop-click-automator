#!/bin/bash
# Clicker Tool launcher
# Prefer Homebrew framework Python when available, otherwise use python3 from PATH.
FRAMEWORK_PYTHON="/opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -x "$FRAMEWORK_PYTHON" ]; then
	exec "$FRAMEWORK_PYTHON" "$SCRIPT_DIR/clicker_tool.py"
fi

exec python3 "$SCRIPT_DIR/clicker_tool.py"
