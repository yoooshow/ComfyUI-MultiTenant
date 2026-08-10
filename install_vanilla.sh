#!/bin/bash
# 安装独立纯原版 ComfyUI（测试用，可 git pull 实时更新官方代码）
# 用法: bash install_vanilla.sh [目录] [端口]
set -e

VANILLA_DIR="${1:-$HOME/ComfyUI-Vanilla}"
PORT="${2:-8189}"

echo "=== 安装原版 ComfyUI 到 $VANILLA_DIR (端口 $PORT) ==="
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

# 2. Python venv
if [ ! -d "venv" ]; then
  echo "Creating venv..."
  python3 -m venv venv
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
