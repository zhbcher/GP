#!/usr/bin/env python3
"""
批量检查并修复 K 线数据中的异常交易量
"""

import sqlite3
import os
import sys
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'stock.db')

def get_db():
    """获取数据库连接"""
    return sqlite3.connect(DB_PATH)

def check_anomalies(db_path=None, threshold=1_000_000):
    """检查异常数据"""
    conn = get_db() if not db_path else sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 找出所有 volume < threshold 的记录（排除新股和 ST 股）
    cursor.execute("""
        SELECT stock_code, trade_date, volume, close
        FROM kline_data
        WHERE volume < ?
        AND volume > 0
        ORDER BY trade_date DESC
        LIMIT 100
    """, (threshold,))
    
    rows = cursor.fetchall()
    
    print(f"\n发现 {len(rows)} 条异常记录 (volume < {threshold:,}):")
    print("-" * 80)
    
    anomalies = []
    for row in rows:
        stock_code, trade_date, volume, close = row
        # 估算正确值（乘以100）
        estimated_correct = volume * 100
        anomalies.append({
            'stock_code': stock_code,
            'trade_date': trade_date,
            'current_volume': volume,
            'estimated_correct': estimated_correct,
            'close': close
        })
        print(f"{stock_code} | {trade_date} | current: {volume:>10,} | est_correct: {estimated_correct:>12,}")
    
    conn.close()
    return anomalies

def fix_anomalies(anomalies, dry_run=True):
    """修复异常数据"""
    conn = get_db()
    cursor = conn.cursor()
    
    fixed = 0
    skipped = 0
    
    for item in anomalies:
        # 跳过明显正确的值（比如新股首日成交量小）
        if item['estimated_correct'] < 100_000:
            skipped += 1
            print(f"跳过 {item['stock_code']} {item['trade_date']}: 估算值 {item['estimated_correct']:,} 仍过小")
            continue
        
        cursor.execute("""
            UPDATE kline_data
            SET volume = ?, amount = ? * close / 100
            WHERE stock_code = ? AND trade_date = ?
        """, (item['estimated_correct'], item['estimated_correct'], item['stock_code'], item['trade_date']))
        
        if cursor.rowcount > 0:
            fixed += 1
            print(f"修复 {item['stock_code']} {item['trade_date']}: {item['current_volume']:,} → {item['estimated_correct']:,}")
    
    conn.commit()
    conn.close()
    
    print(f"\n{'[DRY RUN]' if dry_run else ''} 完成: 修复 {fixed} 条，跳过 {skipped} 条")
    return fixed, skipped

def check_by_stock(stock_code, days=30):
    """检查单只股票的历史数据"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT trade_date, volume, close
        FROM kline_data
        WHERE stock_code = ?
        ORDER BY trade_date DESC
        LIMIT ?
    """, (stock_code, days))
    
    rows = cursor.fetchall()
    conn.close()
    
    print(f"\n{stock_code} 最近 {len(rows)} 个交易日:")
    print("-" * 60)
    for row in rows:
        trade_date, volume, close = row
        status = "⚠️" if volume < 100_000 else "✅"
        print(f"{status} {trade_date} | vol: {volume:>12,} | close: {close:.2f}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='检查和修复 K 线数据异常')
    parser.add_argument('--check', action='store_true', help='检查所有异常数据')
    parser.add_argument('--fix', action='store_true', help='修复异常数据（会修改数据库）')
    parser.add_argument('--stock', type=str, help='检查单只股票')
    parser.add_argument('--days', type=int, default=30, help='检查最近 N 天')
    parser.add_argument('--dry-run', action='store_true', help='修复时预览不实际修改')
    parser.add_argument('--threshold', type=int, default=1_000_000, help='异常阈值')
    
    args = parser.parse_args()
    
    if not any([args.check, args.fix, args.stock]):
        print("请指定操作: --check, --fix, 或 --stock <code>")
        sys.exit(1)
    
    if args.check or args.stock:
        if args.stock:
            check_by_stock(args.stock, args.days)
        else:
            check_anomalies(threshold=args.threshold)
    
    if args.fix:
        anomalies = check_anomalies(threshold=args.threshold)
        if anomalies:
            print("\n即将修复以下数据:")
            for a in anomalies[:10]:
                print(f"  {a['stock_code']} {a['trade_date']}: {a['current_volume']:,} → {a['estimated_correct']:,}")
            if not args.dry_run:
                fix = input("\n确认修复？(yes/no): ").strip().lower()
                if fix == 'yes':
                    fix_anomalies(anomalies, dry_run=False)
                else:
                    print("已取消")
            else:
                fix_anomalies(anomalies, dry_run=True)

if __name__ == '__main__':
    main()
