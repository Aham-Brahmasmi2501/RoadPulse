#!/usr/bin/env bash
# Starts the React dashboard on http://localhost:5173 (proxies /api to :8000).
set -e
cd "$(dirname "$0")/frontend"
[ -d node_modules ] || npm install
exec npm run dev
