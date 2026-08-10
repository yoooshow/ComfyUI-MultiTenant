#!/bin/bash
# 双实例启动：8188 多租户 + 8189 原版 ComfyUI
# 共享 models / custom_nodes，独立 user 目录和数据库
cd "$(dirname "$0")"

BASE_DIR="$(pwd)"
mkdir -p user_vanilla

# 1. 原版实例（MT_BYPASS=1，端口 8189，独立用户目录）
MT_BYPASS=1 nohup venv/bin/python3 main.py \
  --listen 0.0.0.0 --port 8189 --enable-manager \
  --user-directory "$BASE_DIR/user_vanilla" \
  > vanilla.log 2>&1 &
echo "原版实例 PID $! -> http://<本机IP>:8189"

# 2. 多租户实例（端口 8188，默认用户目录）
nohup venv/bin/python3 main.py \
  --listen 0.0.0.0 --port 8188 --enable-manager \
  > multitenant.log 2>&1 &
echo "多租户实例 PID $! -> http://<本机IP>:8188"

echo "日志: vanilla.log / multitenant.log"
echo "停止: kill \$(pgrep -f 'port 8188') \$(pgrep -f 'port 8189')"
