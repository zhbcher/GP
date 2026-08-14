#!/bin/bash

echo "=== 服务状态检查 $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

# 检查前端
FRONTEND_STATUS="✗ 未运行"
if lsof -i :5173 >/dev/null 2>&1; then
    VITE_PID=$(lsof -t -i :5173 | head -1)
    FRONTEND_STATUS="✓ 运行中 (PID: $VITE_PID)"
fi
echo "前端 (5173): $FRONTEND_STATUS"

# 检查后端
BACKEND_STATUS="✗ 未运行"
if lsof -i :8000 >/dev/null 2>&1; then
    BACKEND_PID=$(lsof -t -i :8000 | head -1)
    BACKEND_STATUS="✓ 运行中 (PID: $BACKEND_PID)"
fi
echo "后端 (8000): $BACKEND_STATUS"

# 测试页面
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:5173/ 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo "Web页面: ✓ 可访问 (HTTP $HTTP_CODE)"
else
    echo "Web页面: ✗ HTTP $HTTP_CODE"
fi

# 测试API
API_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:8000/api/stock/sh600188/kline?period=daily&count=1" 2>/dev/null)
if [ "$API_CODE" = "200" ]; then
    echo "K线API: ✓ 正常"
else
    echo "K线API: ✗ HTTP $API_CODE"
fi

echo ""
echo "访问地址:"
echo "  本地: http://127.0.0.1:5173/"
echo "  局域网: http://192.168.1.34:5173/"
