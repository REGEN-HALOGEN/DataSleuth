#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
root=$PWD
python="$root/.venv-linux/bin/python"
api_pid=
frontend_pid=

fail() {
    printf '%s\n' "$*" >&2
    exit 1
}

cleanup() {
    local pid
    for pid in "$frontend_pid" "$api_pid"; do
        if [[ -n $pid ]]; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for command in docker python3 node npm curl flock; do
    command -v "$command" >/dev/null || fail "Install $command in WSL before starting DataSleuth."
done
mkdir -p .venv-linux
exec 9>.venv-linux/start.lock
flock -n 9 || fail "DataSleuth is already starting or running from this checkout."

docker compose version >/dev/null
docker info >/dev/null 2>&1 || fail "Start Docker Desktop and enable its WSL integration."

# Catch existing listeners before starting or migrating anything.
python3 - <<'PYTHON'
import socket

for port in (8000, 5173):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit(f"Port {port} is busy. Stop the existing server and try again.") from None
PYTHON

if [[ ! -f .env ]]; then
    python3 scripts/setup_env.py
fi
if [[ ! -x $python ]]; then
    python3 -m venv .venv-linux
fi

backend_stamp="$root/.venv-linux/.datasleuth-backend"
backend_key=$(sha256sum backend/pyproject.toml)
if [[ ! -f $backend_stamp || $(<"$backend_stamp") != "$backend_key" ]]; then
    "$python" -m pip install -e 'backend[dev]'
    printf '%s\n' "$backend_key" > "$backend_stamp"
fi

frontend_stamp="$root/frontend/node_modules/.datasleuth-lock"
frontend_key="$(sha256sum frontend/package-lock.json) $(node -p 'process.platform + "/" + process.arch + "/" + process.version')"
if [[ ! -f $frontend_stamp || $(<"$frontend_stamp") != "$frontend_key" ]]; then
    staging=$(mktemp -d "$root/.venv-linux/frontend-deps.XXXXXX")
    cp frontend/package.json frontend/package-lock.json "$staging/"
    npm --prefix "$staging" ci
    if [[ -d frontend/node_modules || -L frontend/node_modules ]]; then
        mv frontend/node_modules "$staging/previous-node_modules"
        printf 'Previous frontend dependencies saved in %s\n' "$staging/previous-node_modules"
    fi
    mv "$staging/node_modules" frontend/node_modules
    printf '%s\n' "$frontend_key" > "$frontend_stamp"
fi

docker compose up -d --wait --wait-timeout 90

cd -- "$root/backend"
"$python" -m alembic upgrade head
if "$python" -m app.manage_users --check-admin; then
    :
else
    result=$?
    [[ $result == 3 ]] || exit "$result"
    [[ -t 0 ]] || fail "Run start.sh in an interactive terminal to create the first administrator."
    printf 'Create the first DataSleuth administrator.\n'
    read -r -p 'Administrator username [local-admin]: ' username
    "$python" -m app.manage_users --bootstrap-admin -- "${username:-local-admin}"
fi

"$python" -m app.serve &
api_pid=$!

cd -- "$root/frontend"
node node_modules/vite/bin/vite.js &
frontend_pid=$!

for ((attempt = 0; attempt < 60; attempt++)); do
    kill -0 "$api_pid" "$frontend_pid" 2>/dev/null || fail "An application server exited during startup."
    if curl --noproxy '*' --fail --silent --max-time 2 http://127.0.0.1:8000/health/ready >/dev/null &&
       curl --noproxy '*' --fail --silent --max-time 2 http://127.0.0.1:5173/ >/dev/null; then
        printf '\nDataSleuth is ready at http://127.0.0.1:5173\n'
        printf 'Press Ctrl+C to stop the API and frontend. Docker services stay running.\n'
        wait -n "$api_pid" "$frontend_pid" || exit "$?"
        fail "An application server stopped."
    fi
    sleep 1
done
fail "DataSleuth did not become ready. Check the service output above."
