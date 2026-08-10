#!/bin/bash
# 独立原版 ComfyUI 启动/停止控制
#
# 用法:
#   bash start_vanilla.sh              # 前台启动（Ctrl+C 停止）
#   bash start_vanilla.sh --bg         # 后台启动
#   bash start_vanilla.sh stop         # 停止实例
#   bash start_vanilla.sh restart      # 后台重启
#   bash start_vanilla.sh status       # 查看运行状态
#   bash start_vanilla.sh <目录> <端口>
set -e

VANILLA_DIR="${1:-$HOME/ComfyUI-Vanilla}"
PORT="${2:-8189}"
CMD=""

# 解析命令参数（支持 stop/status/restart 和 --bg 任意位置）
for arg in "$@"; do
  case "$arg" in
    stop|status|restart|--bg) CMD="$arg" ;;
    *) ;;
  esac
done
if [ "$1" = "stop" ] || [ "$1" = "status" ] || [ "$1" = "restart" ]; then
  VANILLA_DIR="${2:-$HOME/ComfyUI-Vanilla}"
  PORT="${3:-8189}"
elif [ "$2" = "stop" ] || [ "$2" = "status" ] || [ "$2" = "restart" ]; then
  PORT="${3:-8189}"
fi

PID_FILE="$VANILLA_DIR/.vanilla-$PORT.pid"

if [ ! -d "$VANILLA_DIR/venv" ]; then
  echo "错误: $VANILLA_DIR/venv 不存在，先运行 install_vanilla.sh 安装"
  exit 1
fi

running_pid() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "$(cat "$PID_FILE")"
    return 0
  fi
  # 回退：按端口找进程
  local p
  p=$(pgrep -f "main.py --listen 0.0.0.0 --port $PORT" 2>/dev/null | head -1)
  if [ -n "$p" ]; then
    echo "$p"
    return 0
  fi
  return 1
}

do_stop() {
  local pid
  pid=$(running_pid) && {
    echo "停止 PID $pid (端口 $PORT)..."
    kill "$pid"
    sleep 2
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
  } || {
    echo "端口 $PORT 没有运行中的实例"
    rm -f "$PID_FILE"
  }
}

case "$CMD" in
  stop)
    do_stop
    exit 0
    ;;
  status)
    if pid=$(running_pid); then
      echo "运行中: PID $pid, 端口 $PORT"
      echo "http://<本机IP>:$PORT"
    else
      echo "未运行: 端口 $PORT"
    fi
    exit 0
    ;;
  restart)
    do_stop
    sleep 1
    CMD="--bg"
    ;;
esac

cd "$VANILLA_DIR"

# 启动前检查是否已占用
if pid=$(running_pid); then
  echo "端口 $PORT 已在运行 (PID $pid)，如需重启请用: bash start_vanilla.sh restart"
  exit 1
fi

if [ "$CMD" = "--bg" ]; then
  nohup venv/bin/python3 main.py \
    --listen 0.0.0.0 --port "$PORT" --enable-manager \
    > comfyui.log 2>&1 &
  echo "$!" > "$PID_FILE"
  echo "已后台启动，PID $(cat "$PID_FILE")"
  echo "http://<本机IP>:$PORT"
  echo "日志: $VANILLA_DIR/comfyui.log"
  echo "停止: bash start_vanilla.sh stop"
else
  echo "前台启动，Ctrl+C 停止..."
  rm -f "$PID_FILE"
  exec venv/bin/python3 main.py --listen 0.0.0.0 --port "$PORT" --enable-manager
fi
