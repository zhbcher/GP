#!/bin/bash
# GP 日志轮转：每天压缩并保留最近 7 份（launchd 触发，无需 root）
LOGS=(
  "/Users/zhoubo/GP/backend/data/sync_daily.log"
  "/Users/zhoubo/GP/scripts/v2/signal_push.log"
  "/tmp/gp-backend.log"
  "/tmp/gp-backend.err.log"
  "/tmp/gp-frontend.log"
  "/tmp/gp-frontend.err.log"
  "/Users/zhoubo/GP/lark-bridge/lark_bridge.log"
)
KEEP=7

for f in "${LOGS[@]}"; do
  [ -f "$f" ] || continue
  # 空文件或上次轮转后无新增则跳过
  if [ ! -s "$f" ]; then
    continue
  fi
  # 压缩轮转：log.1.gz <- log.2.gz <- ... <- log.KEEP.gz
  for i in $(seq $((KEEP - 1)) -1 1); do
    if [ -f "${f}.${i}.gz" ]; then
      mv "${f}.${i}.gz" "${f}.$((i + 1)).gz" 2>/dev/null
    fi
  done
  [ -f "${f}.1.gz" ] && rm -f "${f}.1.gz" 2>/dev/null
  gzip -c "$f" > "${f}.1.gz" 2>/dev/null
  : > "$f"  # 截断
done
