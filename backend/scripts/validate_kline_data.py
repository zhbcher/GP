#!/usr/bin/env python3
"""
K 线数据质量验证
在同步完成后自动运行，检测并修复系统性异常
"""

import sqlite3
import sys
from datetime import datetime

DB_PATH = '/Users/zhoubo/GP/data/stock.db'

def validate_and_fix():
    """验证并修复异常数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 统计当前异常
    cursor.execute("SELECT COUNT(*) FROM kline_data WHERE volume < 100000 AND volume > 0")
    before_anomalies = cursor.fetchone()[0]
    
    print(f"📊 数据验证开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   当前异常记录数: {before_anomalies:,}")
    
    if before_anomalies == 0:
        print("✅ 数据验证通过，无需修复")
        conn.close()
        return True
    
    # 查找 2020 年以后的系统性异常
    cursor.execute("""
        SELECT id, stock_code, trade_date, volume
        FROM kline_data
        WHERE volume < 100000 AND volume > 0
        AND trade_date >= '2020-01-01'
        ORDER BY trade_date DESC
    """)
    
    systematic_anomalies = cursor.fetchall()
    
    if systematic_anomalies:
        print(f"\n⚠️ 发现 {len(systematic_anomalies)} 条系统性异常 (2020年后):")
        
        # 批量修复
        fixed = 0
        for rid, code, date, vol in systematic_anomalies:
            corrected = vol * 100
            cursor.execute("""
                UPDATE kline_data
                SET volume = ?, amount = ? * close / 100
                WHERE id = ?
            """, (corrected, corrected, rid))
            fixed += cursor.rowcount
        
        conn.commit()
        print(f"✅ 已修复 {fixed} 条系统性异常")
    
    # 重新统计
    cursor.execute("SELECT COUNT(*) FROM kline_data WHERE volume < 100000 AND volume > 0")
    after_anomalies = cursor.fetchone()[0]
    
    print(f"\n📊 验证结果:")
    print(f"   修复前: {before_anomalies:,} 条异常")
    print(f"   修复后: {after_anomalies:,} 条异常")
    print(f"   减少: {before_anomalies - after_anomalies:,} 条")
    
    # 分类统计
    cursor.execute("""
        SELECT 
            CASE 
                WHEN trade_date >= '2025-01-01' THEN '2025+ (近期)'
                WHEN trade_date >= '2020-01-01' THEN '2020-2024 (中期)'
                ELSE '2020前 (历史)'
            END as period,
            COUNT(*) as count
        FROM kline_data
        WHERE volume < 100000 AND volume > 0
        GROUP BY period
        ORDER BY MIN(trade_date)
    """)
    
    print("\n📅 剩余异常分布:")
    for row in cursor.fetchall():
        print(f"   {row[0]}: {row[1]:,} 条")
    
    conn.close()
    return True

if __name__ == '__main__':
    validate_and_fix()
