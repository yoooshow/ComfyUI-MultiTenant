#!/bin/bash
# ComfyUI-MultiTenant watchdog - auto-restart if the service stops responding.
# Usage: nohup bash watchdog.sh > /dev/null 2>&1 &

cd "$(dirname "$0")"

HEALTH_URL="http://127.0.0.1:8188/api/health"
LOG_FILE="watchdog.log"
CHECK_INTERVAL=15
STARTUP_GRACE=120   # after (re)start, wait this long before declaring it dead

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

is_alive() {
  curl -s -o /dev/null -m 5 "$HEALTH_URL"
}

restart_server() {
  log "Service not responding, restarting..."
  pkill -f "main.py --listen" 2>/dev/null
  sleep 5
  if [ -x venv/bin/python3 ]; then
    nohup venv/bin/python3 main.py --listen 0.0.0.0 --enable-manager >> "$LOG_FILE" 2>&1 &
  else
    nohup python3 main.py --listen 0.0.0.0 --enable-manager >> "$LOG_FILE" 2>&1 &
  fi
  log "Restart issued (PID $!)"
  sleep "$STARTUP_GRACE"
}

log "Watchdog started (pid $$)"
restart_server  # ensure it's running on first launch

while true; do
  sleep "$CHECK_INTERVAL"
  if ! is_alive; then
    restart_server
  fi
done
