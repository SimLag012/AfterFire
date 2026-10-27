#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Running AfterFire Full Verification Suite ==="

echo "1. Backend Tests (Pytest)..."
cd "$DIR/backend"
if [ -d ".venv" ]; then
    .venv/bin/pytest app/tests/ -v
else
    pytest app/tests/ -v
fi

echo "2. Frontend Build Verification (Vite / TypeScript)..."
cd "$DIR/frontend"
npm run build

echo "=== All Tests & Builds Passed Successfully! ==="

