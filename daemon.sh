#!/bin/bash
# 服务守护进程 - 自动管理前端和后端服务

LOG="/tmp/service_daemon.log"
RESTART_COUNT=0
MAX_RESTARTS=5

# 设置完整PATH
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"
}

check_and_restart() {
    local service=$1
    local port=$2
    local cmd=$3
    local desc=$4
    
    if ! lsof -i :$port >/dev/null 2>&1; then
        log "$desc 服务未运行，尝试启动..."
        
        # 清理可能的残留进程
        if [ "$port" = "5173" ]; then
            pkill -f "vite" 2>/dev/null
            sleep 1
            cd /Users/zhoubo/GP/frontend
            nohup npm run dev > /tmp/vite.log 2>&1 &
        elif [ "$port" = "8000" ]; then
            pkill -f "uvicorn app.main" 2>/dev/null
            sleep 1
            cd /Users/zhoubo/GP/backend
            source .venv/bin/activate
            nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
        fi
        
        # 等待启动
        sleep 3
        
        if lsof -i :$port >/dev/null 2>&1; then
            log "$desc 服务启动成功 (PID: $(lsof -t -i :$port | head -1))"
            RESTART_COUNT=0
        else
            log "ERROR: $desc 服务启动失败"
            RESTART_COUNT=$((RESTART_COUNT + 1))
            
            if [ $RESTART_COUNT -ge $MAX_RESTARTS ]; then
                log "ERROR: $desc 连续失败 $MAX_RESTARTS 次，停止自动重启"
                exit 1
            fi
        fi
    fi
}

check_memory() {
    local pid=$1
    local desc=$2
    local mem_limit=$3
    
    if [ -n "$pid" ]; then
        local mem=$(ps -p $pid -o rss= 2>/dev/null | tr -d ' ')
        if [ -n "$mem" ] && [ "$mem" -gt "$mem_limit" ]; then
            log "$desc 内存使用过高 (${mem}KB > ${mem_limit}KB)，重启..."
            kill $pid 2>/dev/null
            sleep 2
            check_and_restart "$desc" "$4" "" ""
        fi
    fi
}

log "=== 服务守护进程启动 ==="

# 主循环
while true; do
    # 检查前端
    VITE_PID=$(lsof -t -i :5173 2>/dev/null | head -1)
    check_and_restart "前端" "5173" "" "前端"
    
    # 检查后端
    check_and_restart "后端" "8000" "" "后端"
    
    # 检查内存（超过300MB重启）
    if [ -n "$VITE_PID" ]; then
        check_memory "$VITE_PID" "前端" 307200
    fi
    
    # 每30秒检查一次
    sleep 30
done
