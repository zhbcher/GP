#!/bin/bash
# 选股信号定时推送 wrapper — 时区无关（内部强制北京时间）
# launchd 每 5 分钟触发本脚本；仅在工作日（北京时间）15:35~15:55 且当天未推送时执行。
# 这样不受系统时区（PDT/PST）影响，A 股 15:00 收盘后自动推送。

export TZ=Asia/Shanghai
DOW=$(date +%u)        # 1=周一 ... 7=周日
HM=$(date +%H%M)       # 北京时间 时分
TODAY=$(date +%Y%m%d)  # 北京日期
MARK="/tmp/signal_pushed_${TODAY}"
LOG="/Users/zhoubo/GP/scripts/v2/signal_push.log"

# 北京时间工作日 15:35~15:55 窗口内，且当天未推送过
if [ "$DOW" -ge 1 ] && [ "$DOW" -le 5 ] && [ "$HM" -ge 1535 ] && [ "$HM" -le 1555 ] && [ ! -f "$MARK" ]; then
    touch "$MARK"
    echo "===== $(date '+%F %T %Z') 自动推送开始 =====" >> "$LOG"
    cd /Users/zhoubo/GP/scripts/v2 && /Users/zhoubo/GP/backend/.venv/bin/python signals_v2.py --push >> "$LOG" 2>&1
    echo "===== 推送完成 =====" >> "$LOG"
fi
# 非窗口期/非工作日/已推送：静默退出
