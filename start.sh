#!/usr/bin/env bash
# ============================================================
#  Soulforge 一键启动器（Linux / macOS）
#
#  与 start.bat 行为对齐：
#    1. 探测 OpenClaw 根目录（含 openclaw.json）
#    2. 准备数据目录并做可写性探测
#    3. 按需创建 backend/.venv 并安装依赖
#    4. 解析端口、检查占用（若是旧 uvicorn 实例则清理）
#    5. 启动 uvicorn，并（默认）打开浏览器
#
#  重要：venv 不可跨平台复用。
#    在 Windows 上创建的 backend/.venv 里只有 Scripts/python.exe，
#    在 Linux/macOS 上不可用（需要 bin/python）。本脚本检测到这种目录会
#    直接报错并要求重建，避免「从 Windows 同步过来的 venv」导致莫名失败。
#
#  用法：
#    bash start.sh            # 或先 chmod +x start.sh && ./start.sh
#    SOULFORGE_NO_BROWSER=1 bash start.sh    # 不自动打开浏览器
# ============================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"
FRONTEND="$SCRIPT_DIR/frontend"
VENV="$BACKEND/.venv"
HOST="${SOULFORGE_HOST:-127.0.0.1}"
MIN_PY="import sys; raise SystemExit(sys.version_info < (3, 10))"

step() { printf '\n[%s] %s\n' "$1" "$2"; }
warn() { printf '[警告] %s\n' "$*"; }
fail() { printf '\n[错误] %s\n' "$*" >&2; exit 1; }

printf '============================================================\n'
printf '  Soulforge 启动器（Linux / macOS）\n'
printf '============================================================\n'

# ---------- 1. 目录结构 ----------
if [ ! -f "$BACKEND/main.py" ]; then
    fail "未找到 $BACKEND/main.py，请在 soulforge 目录下运行本脚本。"
fi

# ---------- 2. 探测 OpenClaw 根目录 ----------
OPENCLAW_DIR=""
if [ -n "${SOULFORGE_OPENCLAW_DIR:-}" ]; then
    OPENCLAW_DIR="$SOULFORGE_OPENCLAW_DIR"
    step OpenClaw "使用环境变量指定的根目录：$OPENCLAW_DIR"
else
    # soulforge 位于 <OpenClaw根>/workspace/projects/soulforge，向上三级即 OpenClaw 根
    CANDIDATE="$(cd "$SCRIPT_DIR/../../.." 2>/dev/null && pwd || true)"
    if [ -n "$CANDIDATE" ] && [ -f "$CANDIDATE/openclaw.json" ]; then
        OPENCLAW_DIR="$CANDIDATE"
        step OpenClaw "自动探测到根目录：$OPENCLAW_DIR"
    elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
        OPENCLAW_DIR="$HOME/.openclaw"
        step OpenClaw "回退到默认根目录：$OPENCLAW_DIR"
    else
        warn "未能定位 OpenClaw 根目录（找不到 openclaw.json）。"
        warn "请设置 SOULFORGE_OPENCLAW_DIR=<OpenClaw根目录> 后重试，否则 Agent 列表可能为空。"
    fi
fi

# ---------- 3. 数据目录 ----------
DATA_DIR="${SOULFORGE_DATA_DIR:-$SCRIPT_DIR/.soulforge}"
mkdir -p "$DATA_DIR" 2>/dev/null || fail "无法创建数据目录：$DATA_DIR"
PROBE="$DATA_DIR/.soulforge_write_test.tmp"
if ! ( : > "$PROBE" ) 2>/dev/null; then
    fail "数据目录不可写：$DATA_DIR（可通过 SOULFORGE_DATA_DIR 指定其它位置）"
fi
rm -f "$PROBE"
step 数据 "数据目录：$DATA_DIR"

# ---------- 4. Python 与虚拟环境 ----------
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
        fail "现有虚拟环境不可用或 Python 版本低于 3.10：$VENV
  请删除后重试：rm -rf \"$VENV\""
    fi
    step Python "复用已有虚拟环境：$VENV"
else
    if [ -d "$VENV" ]; then
        # 典型的「Windows venv 被同步到 Linux」：只有 Scripts/，没有 bin/python
        fail "检测到 $VENV 缺少 bin/python（很可能是从 Windows 同步过来的虚拟环境）。
  请删除后重试：rm -rf \"$VENV\"
  虚拟环境不可跨平台复用，必须在每台机器上各自创建。"
    fi
    SYS_PY="$(find_system_python)" || fail "未找到 Python 3.10+。请先安装（Debian/Ubuntu: apt install python3 python3-venv）。"
    step Python "使用系统 Python：$SYS_PY"
    step Python "创建虚拟环境：$VENV"
    "$SYS_PY" -m venv "$VENV" || fail "创建虚拟环境失败（Debian/Ubuntu 需先安装 python3-venv）。"
    PYTHON="$VENV/bin/python"
fi

# ---------- 5. 依赖 ----------
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
    step 依赖 "依赖已就绪"
else
    step 依赖 "安装依赖（首次运行会稍慢）..."
    if ! "$PYTHON" -m pip install --disable-pip-version-check "${DEPS[@]}"; then
        warn "默认源安装失败，改用清华镜像重试..."
        "$PYTHON" -m pip install --disable-pip-version-check \
            -i https://pypi.tuna.tsinghua.edu.cn/simple "${DEPS[@]}" \
            || fail "依赖安装失败，请检查网络或代理设置。"
    fi
    "$PYTHON" -c "$DEPS_IMPORT" >/dev/null 2>&1 || fail "依赖安装后仍无法导入，请手动排查。"
    step 依赖 "依赖安装完成"
fi

# ---------- 6. 端口 ----------
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
step 端口 "监听端口：$PORT"

# 占用检查（尽力而为）：能找到 PID 且命令行含 uvicorn 才当作旧实例清理
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
        step 端口 "端口被旧实例占用（PID $OCCUPIED），正在停止..."
        kill "$OCCUPIED" 2>/dev/null || true
        sleep 2
        kill -9 "$OCCUPIED" 2>/dev/null || true
        sleep 1
    else
        fail "端口 $PORT 已被其它进程占用（PID $OCCUPIED：${CMDLINE:-未知进程}）。
  请释放该端口，或设置 SOULFORGE_PORT=<其它端口> 后重试。"
    fi
fi

# ---------- 7. 前端构建产物 ----------
if [ ! -f "$FRONTEND/dist/index.html" ]; then
    warn "未找到 frontend/dist，界面将无法访问。"
    warn "请先构建前端：cd frontend && npm install && npm run build"
fi

# ---------- 8. 启动 ----------
if [ -n "$OPENCLAW_DIR" ]; then
    export SOULFORGE_OPENCLAW_DIR="$OPENCLAW_DIR"
fi
export SOULFORGE_DATA_DIR="$DATA_DIR"

printf '\n============================================================\n'
printf '  正在启动 Soulforge ...\n'
printf '  OpenClaw 根目录：%s\n' "${OPENCLAW_DIR:-<未探测到>}"
printf '  数据目录：%s\n' "$DATA_DIR"
printf '  访问地址：http://%s:%s\n' "$HOST" "$PORT"
printf '  按 Ctrl+C 停止服务\n'
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

cd "$BACKEND" || fail "无法进入目录：$BACKEND"
exec "$PYTHON" -m uvicorn main:app --host "$HOST" --port "$PORT"
