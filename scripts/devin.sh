#!/usr/bin/env bash
# devin-proxy launcher — stable copy in ~/venvs/devin-proxy
# Usage: devin.sh [PORT] [--install]
#   devin.sh            -> starts on 127.0.0.1:8390
#   devin.sh 8400       -> starts on 127.0.0.1:8400
#   devin.sh --install  -> (re)builds the stable copy from this repo
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$HOME/venvs/devin-proxy"
PORT=8390

install() {
    echo "[devin] creating $VENV ..."
    [ -d "$VENV" ] || python -m venv "$VENV"
    echo "[devin] installing stable copy ..."
    "$VENV/bin/python" -m pip install -q --upgrade pip
    "$VENV/bin/python" -m pip install -q --force-reinstall --no-deps "$REPO"
    "$VENV/bin/python" -m pip install -q \
        "fastapi>=0.128" "uvicorn[standard]>=0.40" "httpx[http2]>=0.28" \
        "pydantic>=2.13" "pydantic-settings>=2.12" "sse-starlette>=3.3" "anyio>=4.12"
    echo "[devin] done. Run: devin.sh [PORT]"
}

case "${1:-}" in
    --install|--update) install; exit 0 ;;
    "") ;;
    *) PORT="$1" ;;
esac

[ -x "$VENV/bin/python" ] || { echo "[devin] stable venv missing, building from $REPO ..."; install; }

export DEVIN_PROXY_HOST=127.0.0.1
export DEVIN_PROXY_PORT="$PORT"
echo "[devin] starting on 127.0.0.1:$PORT (venv: $VENV)"
exec "$VENV/bin/python" -m devin_proxy
