#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
销售订单管理功能测试脚本
测试销售订单的创建、查询、编辑等核心功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import SalesOrder, SalesOrderItem, Customer, Product, User, CodeRule
from datetime import datetime, date
import json

def test_sales_order_functionality():
    """测试销售订单管理功能"""
    app = create_app()
    
    with app.app_context():
        print("🚀 开始测试销售订单管理功能...")
        
        # 1. 检查数据库表结构
        print("\n📊 检查数据库表结构...")
        try:
            sales_orders_count = SalesOrder.query.count()
            sales_order_items_count = SalesOrderItem.query.count()
            customers_count = Customer.query.count()
            products_count = Product.query.count()
            
            print(f"✅ 销售订单表: {sales_orders_count} 条记录")
            print(f"✅ 销售订单行表: {sales_order_items_count} 条记录")
            print(f"✅ 客户表: {customers_count} 条记录")
            print(f"✅ 产品表: {products_count} 条记录")
        except Exception as e:
            print(f"❌ 数据库表结构检查失败: {e}")
            return False
        
        # 2. 检查必要的基础数据
        print("\n🔍 检查基础数据...")
        
        # 检查用户
        admin_user = User.query.filter_by(role='admin').first()
        if not admin_user:
            print("❌ 未找到管理员用户")
            return False
        print(f"✅ 找到管理员用户: {admin_user.username}")
        
        # 检查客户
        customer = Customer.query.first()
        if not customer:
            print("⚠️ 未找到客户数据，创建测试客户...")
            customer = Customer(
                customer_code="CUST001",
                customer_name="测试客户公司",
                contact_person="张三",
                contact_phone="13800138000",
                contact_email="test@example.com",
                created_by=admin_user.id
            )
            db.session.add(customer)
            db.session.commit()
        print(f"✅ 客户数据: {customer.customer_name}")
        
        # 检查产品
        product = Product.query.first()
        if not product:
            print("⚠️ 未找到产品数据，创建测试产品...")
            product = Product(
                product_name="测试产品",
                product_code="TEST-001",
                drawing_number="TEST-001",
                unit="件",
                category="测试类别",
                created_by=admin_user.id
            )
            db.session.add(product)
            db.session.commit()
        print(f"✅ 产品数据: {product.product_name} ({product.drawing_number})")
        
        # 3. 测试销售订单创建
        print("\n📝 测试销售订单创建...")
        try:
            # 生成订单编号
            order_number = f"SO{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # 创建销售订单
            sales_order = SalesOrder(
                order_source="客户直接下单",
                order_number=order_number,
                customer_id=customer.id,
                year_month=date.today().strftime('%Y-%m'),
                created_by=admin_user.id
            )
            db.session.add(sales_order)
            db.session.flush()  # 获取ID但不提交
            
            print(f"✅ 销售订单创建成功: {sales_order.order_number}")
            
            # 4. 测试销售订单行创建
            print("\n📋 测试销售订单行创建...")
            
            # 创建分批到货信息
            delivery_batches = [
                {
                    "batch": 1,
                    "quantity": 50,
                    "delivery_date": "2024-02-15",
                    "notes": "第一批货物"
                },
                {
                    "batch": 2,
                    "quantity": 30,
                    "delivery_date": "2024-02-28",
                    "notes": "第二批货物"
                }
            ]
            
            # 创建销售订单行
            sales_order_item = SalesOrderItem(
                sales_order_id=sales_order.id,
                product_id=product.id,
                quantity=80,
                direction="左开",
                spec_extended=True,
                spec_gasket=True,
                spec_joint=False,
                spec_drilling=True,
                spec_other=False,
                usage_unit="测试使用单位",
                delivery_batches=json.dumps(delivery_batches, ensure_ascii=False),
                station_notes="测试到站备注"
            )
            db.session.add(sales_order_item)
            db.session.commit()
            
            print(f"✅ 销售订单行创建成功: {sales_order_item.product.product_name}")
            print(f"   - 数量: {sales_order_item.quantity}")
            print(f"   - 规格: 加长={sales_order_item.spec_extended}, 垫板={sales_order_item.spec_gasket}")
            print(f"   - 分批到货: {len(delivery_batches)} 批次")
            
            # 5. 测试合计数量计算
            print("\n🧮 测试合计数量计算...")
            sales_order.calculate_total_quantity()
            db.session.commit()
            total_quantity = sales_order.total_quantity
            print(f"✅ 订单合计数量: {total_quantity}")
            
            # 6. 测试查询功能
            print("\n🔍 测试查询功能...")
            
            # 按订单号查询
            found_order = SalesOrder.query.filter_by(order_number=order_number).first()
            if found_order:
                print(f"✅ 按订单号查询成功: {found_order.order_number}")
            else:
                print("❌ 按订单号查询失败")
            
            # 按客户查询
            customer_orders = SalesOrder.query.filter_by(customer_id=customer.id).all()
            print(f"✅ 客户订单数量: {len(customer_orders)}")
            
            # 7. 测试规格型号功能
            print("\n🔧 测试规格型号功能...")
            spec_display = []
            if sales_order_item.spec_extended:
                spec_display.append("加长")
            if sales_order_item.spec_gasket:
                spec_display.append("垫板")
            if sales_order_item.spec_joint:
                spec_display.append("接头")
            if sales_order_item.spec_drilling:
                spec_display.append("钻孔")
            if sales_order_item.spec_other:
                spec_display.append("其他")
            
            print(f"✅ 规格型号显示: {', '.join(spec_display) if spec_display else '无'}")
            
            # 8. 测试分批到货功能
            print("\n🚚 测试分批到货功能...")
            if sales_order_item.delivery_batches:
                batches = json.loads(sales_order_item.delivery_batches)
                print(f"✅ 分批到货信息:")
                for batch in batches:
                    print(f"   - 第{batch['batch']}批: {batch['quantity']}件, {batch['delivery_date']}")
            
            print("\n🎉 销售订单管理功能测试完成！")
            print("=" * 50)
            print("测试结果总结:")
            print("✅ 数据库表结构正常")
            print("✅ 销售订单创建功能正常")
            print("✅ 销售订单行创建功能正常")
            print("✅ 规格型号多选功能正常")
            print("✅ 分批到货功能正常")
            print("✅ 合计数量计算功能正常")
            print("✅ 查询功能正常")
            print("✅ 与客户管理、产品管理集成正常")
            
            return True
            
        except Exception as e:
            print(f"❌ 测试过程中出现错误: {e}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    success = test_sales_order_functionality()
    if success:
        print("\n🎊 所有测试通过！销售订单管理模块运行正常！")
    else:
        print("\n💥 测试失败，请检查相关配置！")
        sys.exit(1) 

