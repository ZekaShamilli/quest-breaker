#!/usr/bin/env sh
# Boots Quest-Breaker: builds the UI, then serves UI + API on http://localhost:8000
set -e
cd "$(dirname "$0")"
[ -d backend/.venv ] || python3 -m venv backend/.venv
PY=backend/.venv/bin/python; [ -f "$PY" ] || PY=backend/.venv/Scripts/python
"$PY" -m pip install -q -r backend/requirements.txt
(cd frontend && npm install --silent && npm run build)
cd backend && exec "../$PY" -m uvicorn main:app --host 0.0.0.0 --port 8000
