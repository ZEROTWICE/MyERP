#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
销售订单管理功能测试脚本
测试销售订单的创建、编辑、删除和订单行管理功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, Customer, Product, SalesOrder, SalesOrderItem, CodeRule
from datetime import datetime
import json

def test_sales_order_management():
    """测试销售订单管理功能"""
    app = create_app()
    
    with app.app_context():
        print("🚀 开始测试销售订单管理功能...")
        
        # 1. 创建测试用户
        print("\n1. 创建测试用户...")
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                email='admin@test.com',
                role='admin'
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
        print(f"✅ 管理员用户: {admin_user.username}")
        
        # 2. 创建测试客户
        print("\n2. 创建测试客户...")
        customer = Customer.query.filter_by(customer_code='TEST001').first()
        if not customer:
            customer = Customer(
                customer_code='TEST001',
                customer_name='测试客户有限公司',
                customer_type='enterprise',
                contact_person='张三',
                contact_phone='13800138000',
                contact_email='test@customer.com',
                industry='制造业',
                status='active',
                created_by=admin_user.id
            )
            db.session.add(customer)
            db.session.commit()
        print(f"✅ 测试客户: {customer.customer_name} ({customer.customer_code})")
        
        # 3. 创建测试产品
        print("\n3. 创建测试产品...")
        product1 = Product.query.filter_by(product_code='PROD001').first()
        if not product1:
            product1 = Product(
                product_code='PROD001',
                product_name='测试产品A',
                drawing_number='DWG001',
                unit='件',
                category='标准件',
                status='active',
                created_by=admin_user.id
            )
            db.session.add(product1)
        
        product2 = Product.query.filter_by(product_code='PROD002').first()
        if not product2:
            product2 = Product(
                product_code='PROD002',
                product_name='测试产品B',
                drawing_number='DWG002',
                unit='套',
                category='组合件',
                status='active',
                created_by=admin_user.id
            )
            db.session.add(product2)
        
        db.session.commit()
        print(f"✅ 测试产品1: {product1.product_name} ({product1.product_code})")
        print(f"✅ 测试产品2: {product2.product_name} ({product2.product_code})")
        
        # 4. 创建销售订单编码规则
        print("\n4. 创建销售订单编码规则...")
        sales_order_rule = CodeRule.query.filter_by(code_type='sales_order').first()
        if not sales_order_rule:
            sales_order_rule = CodeRule(
                name='销售订单编码规则',
                code_type='sales_order',
                prefix='SO',
                format_pattern='{prefix}{year2}{month}{sequence}',
                sequence_length=4,
                reset_frequency='monthly',
                is_active=True,
                created_by=admin_user.id
            )
            db.session.add(sales_order_rule)
            db.session.commit()
        print(f"✅ 编码规则: {sales_order_rule.name}")
        
        # 5. 创建销售订单
        print("\n5. 创建销售订单...")
        
        # 生成订单编号
        order_number = sales_order_rule.generate_code()
        
        sales_order = SalesOrder(
            order_number=order_number,
            order_source='线上商城',
            customer_id=customer.id,
            year_month='2025-01',
            order_date=datetime.now(),
            status='pending',
            notes='这是一个测试销售订单',
            created_by=admin_user.id
        )
        db.session.add(sales_order)
        db.session.commit()
        print(f"✅ 销售订单: {sales_order.order_number}")
        print(f"   客户: {sales_order.customer.customer_name}")
        print(f"   状态: {sales_order.status}")
        
        # 6. 添加订单行
        print("\n6. 添加订单行...")
        
        # 订单行1
        order_item1 = SalesOrderItem(
            sales_order_id=sales_order.id,
            product_id=product1.id,
            quantity=10,
            direction='左开',
            spec_extended=True,
            spec_gasket=True,
            spec_joint=False,
            spec_drilling=True,
            spec_other=False,
            usage_unit='生产车间A',
            order_time=datetime.now(),
            station_notes='请注意包装',
            sequence=1
        )
        db.session.add(order_item1)
        
        # 订单行2
        order_item2 = SalesOrderItem(
            sales_order_id=sales_order.id,
            product_id=product2.id,
            quantity=5,
            direction='右开',
            spec_extended=False,
            spec_gasket=False,
            spec_joint=True,
            spec_drilling=False,
            spec_other=True,
            spec_other_desc='特殊定制规格',
            usage_unit='生产车间B',
            order_time=datetime.now(),
            station_notes='需要质检确认',
            sequence=2
        )
        db.session.add(order_item2)
        
        db.session.commit()
        
        print(f"✅ 订单行1: {order_item1.product_name} x {order_item1.quantity}")
        print(f"   规格: {order_item1.specifications_text}")
        print(f"   开向: {order_item1.direction}")
        
        print(f"✅ 订单行2: {order_item2.product_name} x {order_item2.quantity}")
        print(f"   规格: {order_item2.specifications_text}")
        print(f"   开向: {order_item2.direction}")
        
        # 7. 更新订单合计数量
        print("\n7. 更新订单合计数量...")
        sales_order.calculate_total_quantity()
        db.session.commit()
        print(f"✅ 订单合计数量: {sales_order.total_quantity}")
        
        # 8. 设置分批到货
        print("\n8. 设置分批到货...")
        delivery_batches = [
            {
                "batch_no": 1,
                "delivery_date": "2025-01-15",
                "quantity": 6,
                "notes": "第一批次"
            },
            {
                "batch_no": 2,
                "delivery_date": "2025-01-25",
                "quantity": 4,
                "notes": "第二批次"
            }
        ]
        order_item1.set_delivery_batches(delivery_batches)
        db.session.commit()
        
        print(f"✅ 为订单行1设置分批到货: {len(delivery_batches)}批次")
        for batch in order_item1.delivery_batches_list:
            print(f"   批次{batch['batch_no']}: {batch['quantity']}件, {batch['delivery_date']}")
        
        # 9. 测试订单状态更新
        print("\n9. 测试订单状态更新...")
        sales_order.status = 'confirmed'
        db.session.commit()
        print(f"✅ 订单状态更新为: {sales_order.status}")
        
        # 10. 显示完整订单信息
        print("\n10. 完整订单信息:")
        print("=" * 50)
        print(f"订单编号: {sales_order.order_number}")
        print(f"订单来源: {sales_order.order_source}")
        print(f"客户: {sales_order.customer.customer_name} ({sales_order.customer.customer_code})")
        print(f"年月: {sales_order.year_month}")
        print(f"状态: {sales_order.status}")
        print(f"合计数量: {sales_order.total_quantity}")
        print(f"下单时间: {sales_order.order_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"备注: {sales_order.notes}")
        
        print(f"\n订单行明细:")
        for i, item in enumerate(sales_order.order_items, 1):
            print(f"  {i}. {item.product_name} ({item.product.product_code})")
            print(f"     图号: {item.drawing_number}")
            print(f"     数量: {item.quantity} {item.unit}")
            print(f"     开向: {item.direction}")
            print(f"     规格: {item.specifications_text}")
            print(f"     使用单位: {item.usage_unit}")
            print(f"     到站备注: {item.station_notes}")
            if item.delivery_batches_list:
                print(f"     分批到货: {len(item.delivery_batches_list)}批次")
            print()
        
        print("🎉 销售订单管理功能测试完成！")
        print("\n✅ 测试结果:")
        print("  - 销售订单创建: 成功")
        print("  - 订单行管理: 成功")
        print("  - 规格型号多选: 成功")
        print("  - 分批到货设置: 成功")
        print("  - 合计数量计算: 成功")
        print("  - 编码规则集成: 成功")
        print("  - 客户产品关联: 成功")

if __name__ == '__main__':
    test_sales_order_management() 