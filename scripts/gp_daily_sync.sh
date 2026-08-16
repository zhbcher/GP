#!/bin/bash
# GP 每日数据同步 wrapper — 时区无关（内部强制北京时间）
# 每交易日（北京时间）15:30~15:50 触发：自选股 K 线增量 + 全市场当日同步
# 通过后端 API 触发（后端由 launchd 守护，KeepAlive 保活）

export TZ=Asia/Shanghai
DOW=$(date +%u)
HM=$(date +%H%M)
TODAY=$(date +%Y%m%d)
MARK="/tmp/gp_daily_sync_${TODAY}"
LOG="/Users/zhoubo/GP/backend/data/sync_daily.log"
BASE="http://localhost:8000"
KEY="GP_9c443859328e6d3ea4211b4a"

if [ "$DOW" -ge 1 ] && [ "$DOW" -le 5 ] && [ "$HM" -ge 1530 ] && [ "$HM" -le 1550 ] && [ ! -f "$MARK" ]; then
    touch "$MARK"
    echo "===== $(date '+%F %T %Z') 每日同步开始 =====" >> "$LOG"
    # 1. 自选股 K 线增量
    r1=$(curl -s -m 30 -X POST "$BASE/api/sync/watchlist?key=$KEY" 2>&1)
    echo "自选股同步: $r1" >> "$LOG"
    # 2. 全市场当日同步
    r2=$(curl -s -m 30 -X POST "$BASE/api/sync/daily/all-stocks?key=$KEY" 2>&1)
    echo "全市场同步: $r2" >> "$LOG"
    echo "===== 同步完成 =====" >> "$LOG"
fi
