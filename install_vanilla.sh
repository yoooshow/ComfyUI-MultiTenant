#!/bin/bash
# 安装独立纯原版 ComfyUI（测试用，可 git pull 实时更新官方代码）
# 用法: bash install_vanilla.sh [目录] [端口]
set -e

VANILLA_DIR="${1:-$HOME/ComfyUI-Vanilla}"
PORT="${2:-8189}"

echo "=== 安装原版 ComfyUI 到 $VANILLA_DIR (端口 $PORT) ==="

# 0. 选择 Python >= 3.10（官方新版要求）
PYTHON=""
for p in python3.12 python3.11 python3.10 python3; do
  if command -v "$p" >/dev/null 2>&1; then
    VER=$("$p" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
    MAJOR=${VER%%.*}
    MINOR=${VER#*.}
    MINOR=${MINOR%%.*}
    if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 10 ]; then
      PYTHON="$p"
      echo "Using Python: $p ($VER)"
      break
    fi
  fi
done
if [ -z "$PYTHON" ]; then
  echo "错误: 需要 Python >=3.10，当前机器没有。"
  echo "安装方法: brew install python@3.11"
  exit 1
fi

mkdir -p "$VANILLA_DIR"
cd "$VANILLA_DIR"

# 1. Clone 官方仓库（如果还没有）
if [ ! -d ".git" ]; then
  echo "Cloning official ComfyUI..."
  git clone https://github.com/comfyanonymous/ComfyUI.git .
else
  echo "Repo exists, pulling latest..."
  git pull
fi

# 2. Python venv（如果不存在或版本过旧，重建）
if [ ! -d "venv" ]; then
  echo "Creating venv..."
  "$PYTHON" -m venv venv
else
  VENV_VER="$(venv/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo '0.0')"
  VENV_MAJOR=${VENV_VER%%.*}
  VENV_MINOR=${VENV_VER#*.}
  VENV_MINOR=${VENV_MINOR%%.*}
  if [ "$VENV_MAJOR" -lt 3 ] || [ "$VENV_MINOR" -lt 10 ]; then
    echo "现有 venv 是 Python $VENV_VER，太旧，重建..."
    rm -rf venv
    "$PYTHON" -m venv venv
  fi
fi
source venv/bin/activate

# 3. 依赖
echo "Installing requirements..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 4. Manager
echo "Installing ComfyUI-Manager..."
pip install -U --pre comfyui-manager -q || true

# 5. 启动
echo "Starting vanilla ComfyUI on port $PORT ..."
nohup venv/bin/python3 main.py \
  --listen 0.0.0.0 --port "$PORT" --enable-manager \
  > comfyui.log 2>&1 &
echo "PID: $!"
echo "Open: http://<本机IP>:$PORT"
echo "Log:  $VANILLA_DIR/comfyui.log"
