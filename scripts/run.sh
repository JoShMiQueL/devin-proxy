#!/usr/bin/env bash
# devin-proxy - dev launcher (runs the repo checkout)
set -euo pipefail
export DEVIN_PROXY_HOST="${DEVIN_PROXY_HOST:-127.0.0.1}"
export DEVIN_PROXY_PORT="${DEVIN_PROXY_PORT:-8390}"
cd "$(dirname "$0")/.."
exec python -m devin_proxy "$@"
