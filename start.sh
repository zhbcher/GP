#!/bin/bash
cd /Users/zhoubo/GP/frontend

# 检查前端是否运行
if ! lsof -i :5173 >/dev/null 2>&1; then
    echo "启动前端服务..."
    npm run dev > /tmp/vite.log 2>&1 &
    sleep 3
fi

# 检查后端是否运行
if ! lsof -i :8000 >/dev/null 2>&1; then
    echo "启动后端服务..."
    cd /Users/zhoubo/GP/backend
    source .venv/bin/activate
    nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
    sleep 2
fi

echo "服务已就绪"
echo "前端: http://localhost:5173/"
echo "后端: http://localhost:8000/"
