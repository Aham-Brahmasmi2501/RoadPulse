#!/usr/bin/env bash
# Starts the FastAPI backend on http://localhost:8000 (docs at /docs).
# Seeds the demo data automatically on the first run.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY=${PYTHON:-python}
[ -x "$ROOT/.venv/bin/python" ] && PY="$ROOT/.venv/bin/python"
"$PY" "$ROOT/scripts/seed.py"
cd "$ROOT/backend"
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
