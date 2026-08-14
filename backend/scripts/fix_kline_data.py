#!/usr/bin/env python3
"""
批量修复 K 线数据中的异常交易量
策略：对于 volume < 100,000 的记录，乘以 100 恢复正确值
"""

import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = '/Users/zhoubo/GP/data/stock.db'
BACKUP_DIR = '/Users/zhoubo/GP/data/backups'

def backup_database():
    """备份数据库"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'stock_{timestamp}.db')
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ 备份完成: {backup_path}")
    return backup_path

def check_anomalies():
    """检查异常数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 统计异常
    cursor.execute("""
        SELECT COUNT(*) FROM kline_data 
        WHERE volume < 100000 AND volume > 0
    """)
    total = cursor.fetchone()[0]
    
    # 按股票统计
    cursor.execute("""
        SELECT stock_code, COUNT(*) as cnt, AVG(volume) as avg_vol
        FROM kline_data 
        WHERE volume < 100000 AND volume > 0
        GROUP BY stock_code
        ORDER BY cnt DESC
        LIMIT 10
    """)
    stocks = cursor.fetchall()
    
    conn.close()
    
    print(f"\n📊 异常统计:")
    print(f"  总异常记录数: {total:,}")
    print(f"\n前10只股票:")
    for code, cnt, avg in stocks:
        print(f"  {code}: {cnt:,} 条异常, 平均 volume: {avg:,.0f}")
    
    return total

def fix_anomalies(dry_run=True):
    """修复异常数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 获取所有需要修复的记录
    cursor.execute("""
        SELECT id, stock_code, trade_date, volume
        FROM kline_data
        WHERE volume < 100000 AND volume > 0
        AND volume < 500000  -- 排除真正的低成交量股票
    """)
    records = cursor.fetchall()
    
    print(f"\n🔧 准备修复 {len(records):,} 条记录...")
    
    if dry_run:
        print("[预览模式] 以下记录将被修复:")
        for rid, code, date, vol in records[:20]:
            corrected = vol * 100
            print(f"  {code} {date}: {vol:,} → {corrected:,}")
        if len(records) > 20:
            print(f"  ... 还有 {len(records) - 20} 条")
    
    # 执行修复
    fixed = 0
    for rid, code, date, vol in records:
        corrected_vol = vol * 100
        cursor.execute("""
            UPDATE kline_data
            SET volume = ?, amount = ? * close / 100
            WHERE id = ?
        """, (corrected_vol, corrected_vol, rid))
        fixed += cursor.rowcount
    
    conn.commit()
    conn.close()
    
    status = "[DRY RUN] " if dry_run else ""
    print(f"\n✅ {status}修复完成: {fixed} 条记录已更新")
    
    return fixed

def verify_fix():
    """验证修复结果"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 检查剩余异常
    cursor.execute("""
        SELECT COUNT(*) FROM kline_data 
        WHERE volume < 100000 AND volume > 0
    """)
    remaining = cursor.fetchone()[0]
    
    # 检查特定股票
    cursor.execute("""
        SELECT trade_date, volume FROM kline_data 
        WHERE stock_code = 'sh600188' AND trade_date = '2026-07-06'
    """)
    result = cursor.fetchone()
    
    conn.close()
    
    print(f"\n🔍 验证结果:")
    print(f"  剩余异常记录: {remaining:,}")
    if result:
        print(f"  sh600188 2026-07-06 volume: {result[1]:,} {'✅' if result[1] >= 100000 else '❌'}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='修复 K 线数据异常')
    parser.add_argument('--check', action='store_true', help='检查异常数据')
    parser.add_argument('--fix', action='store_true', help='修复异常数据')
    parser.add_argument('--verify', action='store_true', help='验证修复结果')
    parser.add_argument('--dry-run', action='store_true', help='预览不实际修改')
    parser.add_argument('--backup', action='store_true', help='备份数据库')
    parser.add_argument('--yes', action='store_true', help='跳过确认直接修复')
    
    args = parser.parse_args()
    
    if args.backup:
        backup_database()
    
    if args.check:
        check_anomalies()
    
    if args.fix:
        if not args.dry_run and not args.yes:
            confirm = input("\n⚠️  将修改数据库，确认修复？(yes/no): ").strip().lower()
            if confirm != 'yes':
                print("已取消")
                return
        if not args.dry_run:
            backup_database()
        fix_anomalies(dry_run=args.dry_run)
    
    if args.verify:
        verify_fix()

if __name__ == '__main__':
    main()
