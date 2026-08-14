#!/usr/bin/env python3
"""
全面修复 K 线数据异常（经验证确认）
"""

import sqlite3
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = '/Users/zhoubo/GP/data/stock.db'

def fix_all_anomalies():
    """修复所有被错误除以100的交易量"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 统计当前状态
    cursor.execute("SELECT COUNT(*) FROM kline_data WHERE volume < 100000 AND volume > 0")
    before_count = cursor.fetchone()[0]
    
    logger.info(f"📊 数据修复开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   待修复记录数: {before_count:,} (volume < 10万)")
    
    if before_count == 0:
        logger.info("✅ 无需修复")
        conn.close()
        return
    
    # 按时间段统计
    cursor.execute("""
        SELECT 
            CASE 
                WHEN trade_date >= '2025-01-01' THEN '2025+ (本年)'
                WHEN trade_date >= '2020-01-01' THEN '2020-2024'
                ELSE '2020 前'
            END as period,
            COUNT(*) as count,
            ROUND(AVG(volume), 0) as avg_vol
        FROM kline_data
        WHERE volume < 100000 AND volume > 0
        GROUP BY period
    """)
    
    logger.info("\n📅 异常分布:")
    for row in cursor.fetchall():
        logger.info(f"   {row[0]}: {row[1]:,} 条 (平均 vol: {row[2]:,.0f})")
    
    # 执行修复：将 volume < 100000 且 > 0 的记录乘以 100
    cursor.execute("""
        SELECT id, stock_code, trade_date, volume
        FROM kline_data
        WHERE volume < 100000 AND volume > 0
        ORDER BY trade_date DESC
    """)
    
    records = cursor.fetchall()
    fixed = 0
    
    logger.info(f"\n🔧 开始修复 {len(records):,} 条记录...")
    
    for row_id, code, date, vol in records:
        corrected = vol * 100
        cursor.execute("""
            UPDATE kline_data
            SET volume = ?, amount = ? * close / 100
            WHERE id = ?
        """, (corrected, corrected, row_id))
        fixed += cursor.rowcount
    
    conn.commit()
    logger.info(f"✅ 已修复 {fixed} 条记录")
    
    # 验证结果
    cursor.execute("SELECT COUNT(*) FROM kline_data WHERE volume < 100000 AND volume > 0")
    after_count = cursor.fetchone()[0]
    
    logger.info(f"\n📊 验证结果:")
    logger.info(f"   修复前: {before_count:,} 条异常")
    logger.info(f"   修复后: {after_count:,} 条异常")
    logger.info(f"   减少: {before_count - after_count:,} 条")
    
    if after_count > 0:
        logger.info(f"\n⚠️ 仍有 {after_count} 条异常，检查是否真实低成交量")
        cursor.execute("""
            SELECT stock_code, COUNT(*) as cnt
            FROM kline_data
            WHERE volume < 100000 AND volume > 0
            GROUP BY stock_code
            ORDER BY cnt DESC
            LIMIT 10
        """)
        for row in cursor.fetchall():
            logger.info(f"   {row[0]}: {row[1]} 条")
    
    conn.close()
    logger.info("\n✅ 修复完成")

if __name__ == '__main__':
    fix_all_anomalies()
