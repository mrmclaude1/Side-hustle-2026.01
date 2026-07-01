#!/usr/bin/env bash
# Quick start: create venv, install deps, run the dashboard.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "Marketsonar running at http://127.0.0.1:8000  (Ctrl-C to stop)"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
