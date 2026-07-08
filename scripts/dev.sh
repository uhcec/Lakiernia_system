#!/usr/bin/env bash
# dev.sh -- check migrations then start backend + frontend (Linux port of dev.ps1)
# Usage: ./scripts/dev.sh
#        ./scripts/dev.sh --skip-migration-check
set -euo pipefail

SKIP_MIGRATION_CHECK=0
for arg in "$@"; do
    case "$arg" in
        --skip-migration-check) SKIP_MIGRATION_CHECK=1 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ALEMBIC="$REPO_ROOT/.venv/bin/alembic"
UVICORN="$REPO_ROOT/.venv/bin/uvicorn"
FRONTEND_DIR="$REPO_ROOT/frontend"
LOG_DIR="${TMPDIR:-/tmp}/lakiernia-dev"
mkdir -p "$LOG_DIR"

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
ok()   { printf '    \033[32mOK  %s\033[0m\n' "$1"; }
fail() { printf '    \033[31mERR %s\033[0m\n' "$1"; }

if [ ! -x "$UVICORN" ]; then
    fail ".venv missing -- create it first:  uv venv --python 3.12 .venv && uv pip install -e '.[dev]' --python .venv/bin/python"
    exit 1
fi
command -v npm >/dev/null || { fail "npm not on PATH (node lives in ~/.local/opt/node-v22, symlinked into ~/.local/bin)"; exit 1; }

# Stop any stale dev servers from a previous run. uvicorn --reload and npm/vite spawn child
# processes that survive a naive kill and keep holding :8000 / :5173 -- so a new run would fail
# to bind and the browser would be served STALE code. We match this repo's backend (app.main:app)
# and frontend (vite under this repo), then reclaim the ports from any orphan still squatting.
stop_dev_servers() {
    local found=0
    pkill -f 'app\.main:app' 2>/dev/null && found=1
    pkill -f "$FRONTEND_DIR/node_modules/.*vite" 2>/dev/null && found=1
    local port
    for port in 8000 5173; do
        fuser -k -TERM "$port/tcp" >/dev/null 2>&1 && found=1
    done
    if [ "$found" = 1 ]; then
        echo "    stopped stale dev processes"
        sleep 0.7
    fi
    return 0
}

BACKEND_PID=""
FRONTEND_PID=""
TAIL_PIDS=()

cleanup() {
    trap - EXIT INT TERM
    local p
    for p in "${TAIL_PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
    # kill the whole process group (setsid) so reload workers / vite children die too
    [ -n "$BACKEND_PID" ]  && kill -- -"$BACKEND_PID"  2>/dev/null || true
    [ -n "$FRONTEND_PID" ] && kill -- -"$FRONTEND_PID" 2>/dev/null || true
    stop_dev_servers >/dev/null
}
trap cleanup EXIT INT TERM

# -- 1. Alembic checks ---------------------------------------------------
if [ "$SKIP_MIGRATION_CHECK" != 1 ]; then
    step "Alembic: applying pending migrations"
    "$ALEMBIC" upgrade head || { fail "alembic upgrade head failed"; exit 1; }
    ok "upgrade head"

    step "Alembic: verifying no unapplied migrations"
    if ! "$ALEMBIC" check; then
        fail "alembic check failed -- models and migrations are out of sync"
        exit 1
    fi
    ok "check passed -- migrations are up to date"
else
    printf '\n    \033[90m[skipping migration check]\033[0m\n'
fi

# -- 2. Start backend ----------------------------------------------------
step "Reclaiming dev ports (stopping any stale servers from a previous run)"
stop_dev_servers

step "Starting backend (uvicorn) on http://127.0.0.1:8000"
setsid "$UVICORN" app.main:app --reload >"$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

backend_ready=0
for _ in $(seq 1 30); do
    sleep 0.5
    if curl -sf -o /dev/null --max-time 1 http://127.0.0.1:8000/health; then
        backend_ready=1
        break
    fi
done
if [ "$backend_ready" != 1 ]; then
    fail "backend did not respond within 15 s"
    tail -n 20 "$LOG_DIR/backend.log" | sed 's/^/    /'
    exit 1
fi
ok "backend is up -> http://127.0.0.1:8000"

# -- 3. Start frontend ---------------------------------------------------
step "Starting frontend (vite) on http://127.0.0.1:5173"
# --host 127.0.0.1 overrides vite.config's host 0.0.0.0 (meant for shop-LAN dev):
# this VPS has a public IP, and Vite's proxy would expose the whole backend API.
setsid bash -c "cd '$FRONTEND_DIR' && exec npm run dev -- --host 127.0.0.1" >"$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

frontend_ready=0
for _ in $(seq 1 30); do
    sleep 0.5
    if curl -sf -o /dev/null --max-time 1 http://127.0.0.1:5173/; then
        frontend_ready=1
        break
    fi
done
if [ "$frontend_ready" = 1 ]; then
    ok "frontend is up -> http://127.0.0.1:5173"
else
    printf '    \033[90m(frontend may still be starting -- check browser)\033[0m\n'
fi

# -- 4. Summary ----------------------------------------------------------
echo
echo "  Backend  ->  http://127.0.0.1:8000"
echo "  API docs ->  http://127.0.0.1:8000/docs"
echo "  Frontend ->  http://127.0.0.1:5173"
echo
echo "  Remote browser: ssh -L 5173:127.0.0.1:5173 -L 8000:127.0.0.1:8000 <vps>"
echo "  Press Ctrl+C to stop both servers."
echo

# stream output from both servers until interrupted
tail -n +1 -F "$LOG_DIR/backend.log"  2>/dev/null | sed -u 's/^/[backend]  /' &
TAIL_PIDS+=($!)
tail -n +1 -F "$LOG_DIR/frontend.log" 2>/dev/null | sed -u 's/^/[frontend] /' &
TAIL_PIDS+=($!)

while sleep 1; do
    kill -0 "$BACKEND_PID"  2>/dev/null || { fail "backend process exited unexpectedly";  exit 1; }
    kill -0 "$FRONTEND_PID" 2>/dev/null || { fail "frontend process exited unexpectedly"; exit 1; }
done
