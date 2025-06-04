#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
手动创建销售订单表的脚本
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text

def create_sales_order_tables():
    """手动创建销售订单表"""
    app = create_app()
    
    with app.app_context():
        print("🚀 开始创建销售订单表...")
        
        # 检查表是否存在
        result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='sales_orders'"))
        if result.fetchone():
            print("📋 销售订单表已存在，删除重建...")
            db.session.execute(text("DROP TABLE IF EXISTS sales_order_items"))
            db.session.execute(text("DROP TABLE IF EXISTS sales_orders"))
            db.session.commit()
        
        # 创建销售订单表
        print("📋 创建销售订单表...")
        create_sales_orders_sql = """
        CREATE TABLE sales_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            global_sn VARCHAR(8) NOT NULL UNIQUE,
            order_number VARCHAR(50) NOT NULL UNIQUE,
            order_source VARCHAR(50) NOT NULL,
            customer_id INTEGER NOT NULL,
            year_month VARCHAR(7) NOT NULL,
            total_quantity INTEGER DEFAULT 0,
            order_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'pending',
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id),
            FOREIGN KEY (created_by) REFERENCES user (id)
        )
        """
        db.session.execute(text(create_sales_orders_sql))
        
        # 创建销售订单行表
        print("📋 创建销售订单行表...")
        create_sales_order_items_sql = """
        CREATE TABLE sales_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            global_sn VARCHAR(8) NOT NULL UNIQUE,
            sales_order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            direction VARCHAR(50),
            spec_extended BOOLEAN DEFAULT 0,
            spec_gasket BOOLEAN DEFAULT 0,
            spec_joint BOOLEAN DEFAULT 0,
            spec_drilling BOOLEAN DEFAULT 0,
            spec_other BOOLEAN DEFAULT 0,
            spec_other_desc VARCHAR(200),
            usage_unit VARCHAR(100),
            order_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            station_notes TEXT,
            delivery_batches TEXT,
            sequence INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sales_order_id) REFERENCES sales_orders (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
        """
        db.session.execute(text(create_sales_order_items_sql))
        
        db.session.commit()
        print("✅ 销售订单表创建成功！")
        
        # 验证表结构
        print("\n📋 验证表结构...")
        
        # 检查销售订单表
        result = db.session.execute(text("PRAGMA table_info(sales_orders)"))
        columns = result.fetchall()
        print(f"销售订单表字段数: {len(columns)}")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        # 检查销售订单行表
        result = db.session.execute(text("PRAGMA table_info(sales_order_items)"))
        columns = result.fetchall()
        print(f"\n销售订单行表字段数: {len(columns)}")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        print("\n🎉 销售订单表创建完成！")

if __name__ == '__main__':
    create_sales_order_tables() 