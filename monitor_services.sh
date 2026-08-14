#!/bin/bash
# 服务监控脚本 - 每30秒检查一次，自动恢复

LOG="/tmp/service_monitor_$(date +%Y%m%d).log"
CHECK_INTERVAL=30
MAX_MEMORY_MB=400  # 内存超过此值则重启

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"
}

check_frontend() {
    local pid=$(lsof -t -i :5173 2>/dev/null | head -1)
    
    if [ -z "$pid" ]; then
        log "前端服务未运行，尝试启动..."
        cd /Users/zhoubo/GP/frontend && npm run dev > /tmp/vite.log 2>&1 &
        sleep 3
        if lsof -i :5173 >/dev/null 2>&1; then
            log "前端启动成功 (PID: $(lsof -t -i :5173 | head -1))"
        else
            log "前端启动失败，检查: /tmp/vite.log"
        fi
    else
        # 检查内存
        local mem=$(ps -p $pid -o rss= 2>/dev/null | tr -d ' ')
        if [ -n "$mem" ]; then
            local mem_mb=$((mem / 1024))
            if [ $mem_mb -gt $MAX_MEMORY_MB ]; then
                log "前端内存过高 (${mem_mb}MB)，重启..."
                kill $pid 2>/dev/null
                sleep 2
                cd /Users/zhoubo/GP/frontend && npm run dev > /tmp/vite.log 2>&1 &
                sleep 3
                if lsof -i :5173 >/dev/null 2>&1; then
                    log "前端重启成功 (PID: $(lsof -t -i :5173 | head -1))"
                fi
            fi
        fi
    fi
}

check_backend() {
    local pid=$(lsof -t -i :8000 2>/dev/null | head -1)
    
    if [ -z "$pid" ]; then
        log "后端服务未运行，尝试启动..."
        cd /Users/zhoubo/GP/backend && source .venv/bin/activate && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
        sleep 3
        if lsof -i :8000 >/dev/null 2>&1; then
            log "后端启动成功 (PID: $(lsof -t -i :8000 | head -1))"
        else
            log "后端启动失败，检查: /tmp/uvicorn.log"
        fi
    fi
}

# 主循环
while true; do
    check_frontend
    check_backend
    sleep $CHECK_INTERVAL
done
