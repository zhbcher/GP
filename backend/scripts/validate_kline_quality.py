#!/usr/bin/env python3
"""
K线数据质量验证任务
在数据同步后运行，检测和修复异常交易量
"""

import asyncio
import logging
import sqlite3
import os
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = '/Users/zhoubo/GP/data/stock.db'

def validate_and_fix():
    """验证并修复异常数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 统计当前异常
    cursor.execute("SELECT COUNT(*) FROM kline_data WHERE volume < 100000 AND volume > 0")
    before = cursor.fetchone()[0]
    
    logger.info(f"📊 数据验证开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   当前异常记录数: {before:,}")
    
    if before == 0:
        logger.info("✅ 数据验证通过，无需修复")
        conn.close()
        return
    
    # 检查 2020 年后的系统性异常
    cursor.execute("""
        SELECT id, stock_code, trade_date, volume
        FROM kline_data
        WHERE volume < 100000 AND volume > 0
        AND trade_date >= '2020-01-01'
        ORDER BY trade_date DESC
    """)
    
    records = cursor.fetchall()
    
    if records:
        logger.warning(f"⚠️ 发现 {len(records)} 条系统性异常 (2020年后)")
        
        # 批量修复
        fixed = 0
        for row_id, code, date, vol in records:
            corrected = vol * 100
            cursor.execute("""
                UPDATE kline_data
                SET volume = ?, amount = ? * close / 100
                WHERE id = ?
            """, (corrected, corrected, row_id))
            fixed += cursor.rowcount
        
        conn.commit()
        logger.info(f"✅ 已修复 {fixed} 条系统性异常")
    
    # 重新统计
    cursor.execute("SELECT COUNT(*) FROM kline_data WHERE volume < 100000 AND volume > 0")
    after = cursor.fetchone()[0]
    
    logger.info(f"\n📊 验证结果:")
    logger.info(f"   修复前: {before:,} 条异常")
    logger.info(f"   修复后: {after:,} 条异常")
    logger.info(f"   减少: {before - after:,} 条")
    
    # 分类统计
    cursor.execute("""
        SELECT 
            CASE 
                WHEN trade_date >= '2026-01-01' THEN '2026 年 (本年)'
                WHEN trade_date >= '2025-01-01' THEN '2025 年'
                WHEN trade_date >= '2020-01-01' THEN '2020-2024 (中期)'
                ELSE '2020 前 (历史)'
            END as period,
            COUNT(*) as count,
            ROUND(AVG(volume), 0) as avg_vol
        FROM kline_data
        WHERE volume < 100000 AND volume > 0
        GROUP BY period
        ORDER BY MIN(trade_date)
    """)
    
    logger.info("\n📅 剩余异常分布:")
    for row in cursor.fetchall():
        logger.info(f"   {row[0]}: {row[1]:,} 条 (平均 vol: {row[2]:,.0f})")
    
    conn.close()

if __name__ == '__main__':
    validate_and_fix()
