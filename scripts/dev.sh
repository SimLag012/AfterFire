
#!/usr/bin/env bash
set -Ee

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "=== Starting AfterFire Local Development ==="
echo "Project: $PROJECT_ROOT"

if [[ ! -d "$BACKEND_DIR" ]]; then
    echo "ERRORE: cartella backend non trovata: $BACKEND_DIR"
    exit 1
fi

if [[ ! -d "$FRONTEND_DIR" ]]; then
    echo "ERRORE: cartella frontend non trovata: $FRONTEND_DIR"
    echo "Cartelle presenti nella root:"
    ls -la "$PROJECT_ROOT"
    exit 1
fi

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
    echo "ERRORE: package.json non trovato nel frontend."
    exit 1
fi

cleanup() {
    trap - EXIT INT TERM
    if [[ -n "${BACKEND_PID:-}" ]]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [[ -n "${FRONTEND_PID:-}" ]]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    wait 2>/dev/null || true
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Starting Backend on http://localhost:8000..."
cd "$BACKEND_DIR"

if [[ -x ".venv/bin/uvicorn" ]]; then
    .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
elif command -v uvicorn >/dev/null 2>&1; then
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
else
    echo "ERRORE: uvicorn non trovato. Controlla il virtualenv del backend."
    exit 1
fi
BACKEND_PID=$!

echo "Starting Frontend on http://localhost:3000..."
cd "$FRONTEND_DIR"

npm run dev &
FRONTEND_PID=$!

wait
