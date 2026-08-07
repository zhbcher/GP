#!/bin/bash
# run_all.sh —— 投资资讯完整管线：抓取 → 全文提取 → 翻译 → 要点
# 用法: bash run_all.sh
# 定时任务调用此脚本。日志写到 logs/run_YYYYMMDD_HHMM.log
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# GP venv 的 python（有 trafilatura/bs4）
GP_PY="/Users/zhoubo/GP/backend/.venv/bin/python3"
# 系统 python（跑纯标准库脚本）
SYS_PY="python3"

LOG_DIR="$HERE/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/run_$(date +%Y%m%d_%H%M).log"

echo "=== 投资资讯管线开始 $(date) ===" | tee "$LOG"

# 1. 抓取 RSS
echo "[1/4] 抓取 RSS..." | tee -a "$LOG"
$SYS_PY scripts/fetch.py >> "$LOG" 2>&1 || echo "⚠️ fetch 有警告" | tee -a "$LOG"

# 2. 全文提取（用 GP venv）
echo "[2/4] 全文提取..." | tee -a "$LOG"
$GP_PY scripts/fulltext.py >> "$LOG" 2>&1 || echo "⚠️ fulltext 有警告" | tee -a "$LOG"

# 3. 翻译（标题+全文）
echo "[3/4] 翻译..." | tee -a "$LOG"
$SYS_PY scripts/translate.py >> "$LOG" 2>&1 || echo "⚠️ translate 有警告" | tee -a "$LOG"

# 4. AI 要点
echo "[4/4] 生成要点..." | tee -a "$LOG"
$SYS_PY scripts/digest.py >> "$LOG" 2>&1 || echo "⚠️ digest 有警告" | tee -a "$LOG"

# 5. 清理 30 天前的日志
find "$LOG_DIR" -name "run_*.log" -mtime +30 -delete 2>/dev/null || true

echo "=== 管线完成 $(date) ===" | tee -a "$LOG"
