#!/bin/bash
# 更新独立原版 ComfyUI 到官方最新版并重启
# 用法: bash update_vanilla.sh [目录] [端口]
set -e

VANILLA_DIR="${1:-$HOME/ComfyUI-Vanilla}"
PORT="${2:-8189}"

cd "$VANILLA_DIR"

echo "=== 停止当前实例 ==="
pkill -f "port $PORT" 2>/dev/null || true
sleep 2

echo "=== git pull 官方最新版 ==="
git pull

# 检查 venv 版本，过旧则用系统里合适的 Python 重建
VENV_VER="$(venv/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo '0.0')"
VENV_MAJOR=${VENV_VER%%.*}
VENV_MINOR=${VENV_VER#*.}
VENV_MINOR=${VENV_MINOR%%.*}

if [ "$VENV_MAJOR" -lt 3 ] || [ "$VENV_MINOR" -lt 10 ]; then
  echo "venv 是 Python $VENV_VER，太旧，自动选择新 Python 重建..."
  PYTHON=""
  for p in python3.12 python3.11 python3.10 python3; do
    if command -v "$p" >/dev/null 2>&1; then
      VER=$("$p" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
      PM=${VER%%.*}
      PN=${VER#*.}; PN=${PN%%.*}
      if [ "$PM" -eq 3 ] && [ "$PN" -ge 10 ]; then
        PYTHON="$p"; break
      fi
    fi
  done
  if [ -z "$PYTHON" ]; then
    echo "错误: 需要 Python >=3.10，请先 brew install python@3.11"
    exit 1
  fi
  rm -rf venv
  "$PYTHON" -m venv venv
fi

echo "=== 更新依赖 ==="
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install -U --pre comfyui-manager -q || true

echo "=== 重启 ==="
nohup venv/bin/python3 main.py \
  --listen 0.0.0.0 --port "$PORT" --enable-manager \
  > comfyui.log 2>&1 &
echo "PID: $!"
echo "Open: http://<本机IP>:$PORT"
