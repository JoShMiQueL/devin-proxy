#!/usr/bin/env bash
# devin-proxy installer — Linux/macOS
#   curl -fsSL https://raw.githubusercontent.com/JoShMiQueL/devin-proxy/master/install.sh | bash
# Env knobs: DEVIN_PROXY_PREFIX, DEVIN_PROXY_BINDIR, DEVIN_PROXY_REF (default: latest release)
set -euo pipefail

REPO="JoShMiQueL/devin-proxy"
PREFIX="${DEVIN_PROXY_PREFIX:-$HOME/.local/share/devin-proxy}"
BINDIR="${DEVIN_PROXY_BINDIR:-$HOME/.local/bin}"
REF="${DEVIN_PROXY_REF:-}"

say() { printf '[devin-proxy] %s\n' "$*"; }
die() { say "ERROR: $*"; exit 1; }

# --- auth (needed while the repo is private) -------------------------------
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [ -z "$TOKEN" ] && command -v gh >/dev/null 2>&1; then
    TOKEN="$(gh auth token 2>/dev/null || true)"
fi
AUTH=()
[ -n "$TOKEN" ] && AUTH=(-H "Authorization: Bearer $TOKEN")

# --- python ------------------------------------------------------------------
PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || die "python3 not found"
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || die "python >= 3.11 required ($("$PY" -V 2>&1))"

# --- resolve what to install -------------------------------------------------
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [ -z "$REF" ]; then
    say "resolving latest release..."
    curl -fsSL "${AUTH[@]}" \
        "https://api.github.com/repos/$REPO/releases/latest" -o "$TMP/rel.json" \
        || die "cannot fetch latest release (private repo? set GH_TOKEN or gh auth login)"
    TAG="$(grep -o '"tag_name"[^,]*' "$TMP/rel.json" | head -1 | cut -d'"' -f4)"
    WHEEL_NAME="$(grep -o '"name"[^,]*\.whl"' "$TMP/rel.json" | head -1 \
                  | sed 's/.*"\([^"]*\.whl\)"/\1/')"
    [ -n "$WHEEL_NAME" ] || die "no wheel asset on release $TAG"
    # asset URLs redirect to signed storage — gh handles auth+redirects cleanly
    if command -v gh >/dev/null 2>&1; then
        gh release download "$TAG" --repo "$REPO" \
            --pattern "$WHEEL_NAME" --dir "$TMP" --clobber
    else
        WHEEL_URL="$(grep -o '"browser_download_url"[^,]*\.whl"' "$TMP/rel.json" \
                     | head -1 | sed 's/.*"\(http[^"]*\)"/\1/')"
        curl -fSL "${AUTH[@]}" -o "$TMP/$WHEEL_NAME" "$WHEEL_URL" \
            || die "wheel download failed"
    fi
    PKG="$TMP/$WHEEL_NAME"
else
    TAG="$REF"
    PKG="git+https://github.com/$REPO@$REF"
fi

# --- install ------------------------------------------------------------------
say "installing $TAG -> $PREFIX"
[ -d "$PREFIX/venv" ] || "$PY" -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/python" -m pip install -q --upgrade pip
"$PREFIX/venv/bin/python" -m pip install -q --force-reinstall "$PKG" \
    || die "pip install failed"

# --- shim ---------------------------------------------------------------------
mkdir -p "$BINDIR"
ln -sf "$PREFIX/venv/bin/devin-proxy" "$BINDIR/devin-proxy"

say "done: $($BINDIR/devin-proxy --version 2>/dev/null || echo installed)"
case ":$PATH:" in
    *":$BINDIR:"*) ;;
    *) say "NOTE: add $BINDIR to your PATH" ;;
esac
say "run: devin-proxy doctor"
