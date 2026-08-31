#!/bin/bash
# 每天重启原版 ComfyUI（8189）
# launchd KeepAlive 会在进程退出后自动重新拉起，这里只负责停掉旧进程并等待健康。

LOG="$HOME/ComfyUI-Vanilla/daily-restart.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Daily restart: stopping vanilla 8189..." >> "$LOG"

bash "$HOME/ComfyUI-MultiTenant/start_vanilla.sh" stop >> "$LOG" 2>&1

# 等待 launchd 自动拉起（最多 90 秒）
for i in $(seq 1 18); do
  if curl -s -o /dev/null -m 3 http://127.0.0.1:8189/api/health 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarted OK" >> "$LOG"
    exit 0
  fi
  sleep 5
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN: not healthy after 90s, launchd should retry" >> "$LOG"
exit 1
