#!/usr/bin/env bash
# ============================================================
#  Soulforge one-click launcher (Linux / macOS)
#
#  Mirrors start.bat behaviour:
#    1. Detect OpenClaw root (containing openclaw.json)
#    2. Prepare the data directory and probe write access
#    3. Create backend/.venv on demand and install dependencies
#    4. Resolve the port, check if it is occupied, and clean up stale ones
#    5. Launch uvicorn and (by default) open the browser
#
#  Important: a venv is NOT portable across platforms.
#    A backend/.venv created on Windows only has Scripts/python.exe, which is
#    unusable on Linux/macOS (needs bin/python). This script detects such a
#    directory and aborts with a clear instruction so users do not silently
#    ship a Windows venv into a Unix environment.
#
#  Usage:
#    bash start.sh                         # or: chmod +x start.sh && ./start.sh
#    SOULFORGE_NO_BROWSER=1 bash start.sh  # do NOT open the browser automatically
# ============================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"
FRONTEND="$SCRIPT_DIR/frontend"
VENV="$BACKEND/.venv"
HOST="${SOULFORGE_HOST:-127.0.0.1}"
MIN_PY="import sys; raise SystemExit(sys.version_info < (3, 10))"

step() { printf '\n[%s] %s\n' "$1" "$2"; }
warn() { printf '[WARN] %s\n' "$*"; }
fail() { printf '\n[ERROR] %s\n' "$*" >&2; exit 1; }

printf '============================================================\n'
printf '  Soulforge Launcher (Linux / macOS)\n'
printf '============================================================\n'

# ---------- 1. Project layout ----------
if [ ! -f "$BACKEND/main.py" ]; then
    fail "Could not find $BACKEND/main.py. Please run this script from inside the soulforge directory."
fi

# ---------- 2. Detect OpenClaw root ----------
OPENCLAW_DIR=""
if [ -n "${SOULFORGE_OPENCLAW_DIR:-}" ]; then
    OPENCLAW_DIR="$SOULFORGE_OPENCLAW_DIR"
    step OpenClaw "Using directory from environment: $OPENCLAW_DIR"
else
    # soulforge lives at <OpenClaw-root>/workspace/projects/soulforge -> three levels up
    CANDIDATE="$(cd "$SCRIPT_DIR/../../.." 2>/dev/null && pwd || true)"
    if [ -n "$CANDIDATE" ] && [ -f "$CANDIDATE/openclaw.json" ]; then
        OPENCLAW_DIR="$CANDIDATE"
        step OpenClaw "Auto-detected root: $OPENCLAW_DIR"
    elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
        OPENCLAW_DIR="$HOME/.openclaw"
        step OpenClaw "Fallback root: $OPENCLAW_DIR"
    else
        warn "Could not locate the OpenClaw root (openclaw.json not found)."
        warn "Set SOULFORGE_OPENCLAW_DIR=<OpenClaw-root> before running, or the Agent list will be empty."
    fi
fi

# ---------- 3. Data directory ----------
DATA_DIR="${SOULFORGE_DATA_DIR:-$SCRIPT_DIR/.soulforge}"
mkdir -p "$DATA_DIR" 2>/dev/null || fail "Could not create data directory: $DATA_DIR"
PROBE="$DATA_DIR/.soulforge_write_test.tmp"
if ! ( : > "$PROBE" ) 2>/dev/null; then
    fail "Data directory is not writable: $DATA_DIR (override with SOULFORGE_DATA_DIR=<other path>)"
fi
rm -f "$PROBE"
step Data "Data directory: $DATA_DIR"

# ---------- 4. Python and virtual environment ----------
find_system_python() {
    for cand in python3 python; do
        if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "$MIN_PY" >/dev/null 2>&1; then
            command -v "$cand"
            return 0
        fi
    done
    return 1
}

PYTHON="$VENV/bin/python"
if [ -x "$PYTHON" ]; then
    if ! "$PYTHON" -c "$MIN_PY" >/dev/null 2>&1; then
        fail "Existing virtual environment is broken or uses Python < 3.10: $VENV
  Please delete it and retry: rm -rf \"$VENV\""
    fi
    step Python "Reusing existing virtual environment: $VENV"
else
    if [ -d "$VENV" ]; then
        # Typical "Windows venv synced to Linux": only Scripts/, no bin/python
        fail "Detected $VENV is missing bin/python (likely a virtual environment synced from Windows).
  Please delete it and retry: rm -rf \"$VENV\"
  A virtual environment is NOT portable across platforms and must be created locally on each machine."
    fi
    SYS_PY="$(find_system_python)" || fail "No Python 3.10+ found. Install it first (Debian/Ubuntu: apt install python3 python3-venv)."
    step Python "Using system Python: $SYS_PY"
    step Python "Creating virtual environment: $VENV"
    "$SYS_PY" -m venv "$VENV" || fail "Failed to create virtual environment (Debian/Ubuntu needs python3-venv installed)."
    PYTHON="$VENV/bin/python"
fi

# ---------- 5. Dependencies ----------
DEPS=(
    "fastapi>=0.110"
    "uvicorn[standard]>=0.29"
    "sqlalchemy>=2.0"
    "pydantic>=2.6"
    "python-multipart>=0.0.9"
    "loguru>=0.7"
    "send2trash>=1.8"
    "cryptography>=42"
    "PyYAML>=6.0"
)
DEPS_IMPORT='import fastapi, uvicorn, sqlalchemy, pydantic, loguru, send2trash, cryptography, yaml'
if "$PYTHON" -c "$DEPS_IMPORT" >/dev/null 2>&1; then
    step Deps "Dependencies are ready"
else
    step Deps "Installing dependencies (first run may be slow)..."
    if ! "$PYTHON" -m pip install --disable-pip-version-check "${DEPS[@]}"; then
        warn "Default PyPI failed. Retrying with the Tsinghua mirror..."
        "$PYTHON" -m pip install --disable-pip-version-check \
            -i https://pypi.tuna.tsinghua.edu.cn/simple "${DEPS[@]}" \
            || fail "Failed to install dependencies. Please check your network or proxy."
    fi
    "$PYTHON" -c "$DEPS_IMPORT" >/dev/null 2>&1 || fail "Dependencies still cannot be imported after install. Please investigate manually."
    step Deps "Dependencies installed"
fi

# ---------- 6. Port ----------
read_configured_port() {
    "$PYTHON" - "$DATA_DIR" <<'PY'
import pathlib, sys
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        raise SystemExit(0)
p = pathlib.Path(sys.argv[1]) / "config.toml"
print(tomllib.loads(p.read_text(encoding="utf-8")).get("server", {}).get("port", 8848) if p.exists() else 8848)
PY
}
if [ -n "${SOULFORGE_PORT:-}" ]; then
    PORT="$SOULFORGE_PORT"
else
    PORT="$(read_configured_port 2>/dev/null || true)"
fi
PORT="${PORT:-8848}"
step Port "Listening on: $PORT"

# Best-effort port-occupancy check: only treat as ours if PID is known and cmdline contains uvicorn.
port_pid() {
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp 2>/dev/null | awk -v p=":$1" '$4 ~ p"$" {print $0}' \
            | grep -o 'pid=[0-9]*' | head -n 1 | cut -d= -f2
    elif command -v lsof >/dev/null 2>&1; then
        lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -n 1
    fi
}
OCCUPIED="$(port_pid "$PORT" || true)"
if [ -n "$OCCUPIED" ]; then
    CMDLINE="$(tr '\0' ' ' < "/proc/$OCCUPIED/cmdline" 2>/dev/null || ps -p "$OCCUPIED" -o command= 2>/dev/null || true)"
    if [ "${CMDLINE#*uvicorn}" != "$CMDLINE" ]; then
        step Port "Port occupied by a stale instance (PID $OCCUPIED), stopping it..."
        kill "$OCCUPIED" 2>/dev/null || true
        sleep 2
        kill -9 "$OCCUPIED" 2>/dev/null || true
        sleep 1
    else
        fail "Port $PORT is held by another process (PID $OCCUPIED: ${CMDLINE:-unknown}).
  Free the port or set SOULFORGE_PORT=<other_port> and retry."
    fi
fi

# ---------- 7. Frontend build artefacts ----------
if [ ! -f "$FRONTEND/dist/index.html" ]; then
    warn "Could not find frontend/dist. The web UI will not be served."
    warn "Build the frontend first: cd frontend && npm install && npm run build"
fi

# ---------- 8. Launch ----------
if [ -n "$OPENCLAW_DIR" ]; then
    export SOULFORGE_OPENCLAW_DIR="$OPENCLAW_DIR"
fi
export SOULFORGE_DATA_DIR="$DATA_DIR"

printf '\n============================================================\n'
printf '  Starting Soulforge ...\n'
printf '  OpenClaw root: %s\n' "${OPENCLAW_DIR:-<not detected>}"
printf '  Data directory: %s\n' "$DATA_DIR"
printf '  URL: http://%s:%s\n' "$HOST" "$PORT"
printf '  Press Ctrl+C to stop the server\n'
printf '============================================================\n\n'

if [ "${SOULFORGE_NO_BROWSER:-0}" != "1" ]; then
    (
        sleep 3
        if command -v xdg-open >/dev/null 2>&1; then
            xdg-open "http://$HOST:$PORT"
        elif command -v open >/dev/null 2>&1; then
            open "http://$HOST:$PORT"
        fi
    ) >/dev/null 2>&1 &
fi

cd "$BACKEND" || fail "Could not enter directory: $BACKEND"
exec "$PYTHON" -m uvicorn main:app --host "$HOST" --port "$PORT"
