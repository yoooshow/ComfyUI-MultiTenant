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
