#!/bin/bash
# 快速诊断 K 线数据异常

DB="/Users/zhoubo/GP/data/stock.db"
BACKUP="/Users/zhoubo/GP/data/backups"

check() {
    echo "📊 K 线数据异常检查"
    echo "====================="
    sqlite3 "$DB" "SELECT '总记录数: ' || COUNT(*) FROM kline_data;"
    sqlite3 "$DB" "SELECT '异常记录 (vol < 10万): ' || COUNT(*) FROM kline_data WHERE volume < 100000 AND volume > 0;"
    sqlite3 "$DB" "SELECT '正常记录 (vol >= 10万): ' || COUNT(*) FROM kline_data WHERE volume >= 100000;"
    echo ""
    echo "前10只异常股票:"
    sqlite3 "$DB" "SELECT stock_code || ': ' || COUNT(*) || ' 条异常' FROM kline_data WHERE volume < 100000 AND volume > 0 GROUP BY stock_code ORDER BY COUNT(*) DESC LIMIT 10;"
}

fix() {
    echo "🔧 批量修复异常数据..."
    python3 /Users/zhoubo/GP/backend/scripts/fix_kline_data.py --fix --yes
}

check_single() {
    local code=$1
    local days=${2:-30}
    echo "📈 $code 最近 $days 个交易日:"
    echo "-------------------"
    sqlite3 "$DB" "SELECT trade_date || ' | vol: ' || printf('%10,d', volume) || ' | close: ' || printf('%.2f', close) FROM kline_data WHERE stock_code='$code' ORDER BY trade_date DESC LIMIT $days;"
}

# 主逻辑
case "$1" in
    check)
        check
        ;;
    fix)
        fix
        ;;
    stock)
        if [ -z "$2" ]; then
            echo "用法: $0 stock <股票代码> [最近天数]"
            exit 1
        fi
        check_single "$2" "${3:-30}"
        ;;
    *)
        echo "K 线数据诊断工具"
        echo ""
        echo "用法:"
        echo "  $0 check           # 检查异常数据"
        echo "  $0 fix             # 批量修复异常数据"
        echo "  $0 stock <代码> [天数]  # 检查单只股票"
        echo ""
        echo "示例:"
        echo "  $0 stock sh600188 60  # 查看兖矿能源最近 60 天"
        echo "  $0 fix                # 修复所有异常数据"
        ;;
esac
