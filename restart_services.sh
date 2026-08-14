#!/bin/bash
# 服务重启脚本 - 修复PATH问题

# 设置完整PATH
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

FRONTEND_DIR="/Users/zhoubo/GP/frontend"
BACKEND_DIR="/Users/zhoubo/GP/backend"
LOG_FILE="/tmp/service_restart.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 检查并重启前端
if ! lsof -i :5173 >/dev/null 2>&1; then
    log "前端服务未运行，尝试启动..."
    cd "$FRONTEND_DIR" && npm run dev > /tmp/vite.log 2>&1 &
    sleep 3
    if lsof -i :5173 >/dev/null 2>&1; then
        log "前端服务启动成功 (PID: $(lsof -t -i :5173 | head -1))"
    else
        log "前端服务启动失败，检查: /tmp/vite.log"
    fi
else
    log "前端服务正在运行 (PID: $(lsof -t -i :5173 | head -1))"
fi

# 检查并重启后端
if ! lsof -i :8000 >/dev/null 2>&1; then
    log "后端服务未运行，尝试启动..."
    cd "$BACKEND_DIR" && source .venv/bin/activate && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
    sleep 3
    if lsof -i :8000 >/dev/null 2>&1; then
        log "后端服务启动成功 (PID: $(lsof -t -i :8000 | head -1))"
    else
        log "后端服务启动失败，检查: /tmp/uvicorn.log"
    fi
else
    log "后端服务正在运行 (PID: $(lsof -t -i :8000 | head -1))"
fi
