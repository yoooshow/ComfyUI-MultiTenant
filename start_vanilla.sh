#!/bin/bash
# 单独启动独立原版 ComfyUI（装好之后用，不安装不更新）
# 前台运行: bash start_vanilla.sh
# 后台运行: bash start_vanilla.sh --bg
# 自定义目录/端口: bash start_vanilla.sh /Users/comfyui/ComfyUI-Vanilla 8189
set -e

VANILLA_DIR="${1:-$HOME/ComfyUI-Vanilla}"
PORT="${2:-8189}"
MODE="fg"

if [ "$1" = "--bg" ] || [ "$2" = "--bg" ] || [ "$3" = "--bg" ]; then
  MODE="bg"
fi

# 兼容 --bg 位置参数（--bg 目录 端口 或 目录 --bg 端口 等）
if [ "$1" = "--bg" ]; then VANILLA_DIR="${2:-$HOME/ComfyUI-Vanilla}"; PORT="${3:-8189}"; fi
if [ "$2" = "--bg" ]; then PORT="${3:-8189}"; fi

if [ ! -d "$VANILLA_DIR/venv" ]; then
  echo "错误: $VANILLA_DIR/venv 不存在，先运行 install_vanilla.sh 安装"
  exit 1
fi

cd "$VANILLA_DIR"

if [ "$MODE" = "bg" ]; then
  nohup venv/bin/python3 main.py \
    --listen 0.0.0.0 --port "$PORT" --enable-manager \
    > comfyui.log 2>&1 &
  echo "已后台启动，PID $!"
  echo "http://<本机IP>:$PORT"
  echo "日志: $VANILLA_DIR/comfyui.log"
else
  echo "前台启动，Ctrl+C 停止..."
  exec venv/bin/python3 main.py --listen 0.0.0.0 --port "$PORT" --enable-manager
fi
