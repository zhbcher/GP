#!/bin/bash
LOG="/tmp/gp-service.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"
}

case "${1:-status}" in
    start)
        log "启动服务..."
        cd /Users/zhoubo/GP/frontend && npm run dev > /tmp/vite.log 2>&1 &
        cd /Users/zhoubo/GP/backend && source .venv/bin/activate && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
        sleep 3
        log "服务启动完成"
        ;;
    stop)
        log "停止服务..."
        pkill -f "vite" 2>/dev/null || true
        pkill -f "uvicorn app.main" 2>/dev/null || true
        sleep 2
        log "服务已停止"
        ;;
    restart)
        log "重启服务..."
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        echo "=== 服务状态 ==="
        echo -n "前端 (5173): "
        lsof -i :5173 >/dev/null 2>&1 && echo "✓ 运行中" || echo "✗ 未运行"
        echo -n "后端 (8000): "
        lsof -i :8000 >/dev/null 2>&1 && echo "✓ 运行中" || echo "✗ 未运行"
        echo ""
        echo "访问地址: http://localhost:5173/"
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        ;;
esac
