#!/bin/bash
LOG="/tmp/service_health.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

restart_backend() {
    pkill -9 -f "uvicorn app.main:app" 2>/dev/null
    sleep 2
    cd /Users/zhoubo/GP/backend && source .venv/bin/activate && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 > /tmp/uvicorn.log 2>&1 &
    sleep 3
}

restart_frontend() {
    pkill -9 -f "npm run dev" 2>/dev/null
    sleep 2
    cd /Users/zhoubo/GP/frontend && npm run dev > /tmp/vite.log 2>&1 &
    sleep 3
}

# 检查后端
if ! lsof -i :8000 >/dev/null 2>&1; then
    echo "[$TIMESTAMP] Backend DOWN - restarting..." >> "$LOG"
    restart_backend
    if lsof -i :8000 >/dev/null 2>&1; then
        echo "[$TIMESTAMP] Backend started successfully" >> "$LOG"
    else
        echo "[$TIMESTAMP] Backend restart FAILED" >> "$LOG"
    fi
fi

# 检查前端
if ! lsof -i :5173 >/dev/null 2>&1; then
    echo "[$TIMESTAMP] Frontend DOWN - restarting..." >> "$LOG"
    restart_frontend
    if lsof -i :5173 >/dev/null 2>&1; then
        echo "[$TIMESTAMP] Frontend started successfully" >> "$LOG"
    else
        echo "[$TIMESTAMP] Frontend restart FAILED" >> "$LOG"
    fi
fi

# 检查后端uvicorn进程数（超过3个说明堆积了）
UVICORN_COUNT=$(ps aux | grep "uvicorn app.main:app" | grep -v grep | wc -l)
if [ "$UVICORN_COUNT" -gt 3 ]; then
    echo "[$TIMESTAMP] Backend worker count=$UVICORN_COUNT - cleaning..." >> "$LOG"
    pkill -9 -f "uvicorn app.main:app" 2>/dev/null
    sleep 2
    cd /Users/zhoubo/GP/backend && source .venv/bin/activate && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 > /tmp/uvicorn.log 2>&1 &
    sleep 3
    echo "[$TIMESTAMP] Backend restarted after cleanup" >> "$LOG"
fi

# 检查Vite内存使用
VITE_PID=$(lsof -t -i :5173 2>/dev/null | head -1)
if [ -n "$VITE_PID" ]; then
    MEM=$(ps -p $VITE_PID -o rss= 2>/dev/null | tr -d ' ')
    if [ -n "$MEM" ] && [ "$MEM" -gt 204800 ]; then
        echo "[$TIMESTAMP] Frontend high memory (${MEM}KB) - restarting..." >> "$LOG"
        restart_frontend
    fi
fi
