#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[dev]
python scripts/preflight.py

python -m tcp_sim
