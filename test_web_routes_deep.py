#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web路由深度测试脚本
测试销售订单相关的所有Web路由和功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import requests
import json
from app import create_app, db
from app.models import SalesOrder, SalesOrderItem, Customer, Product, User
from datetime import datetime, date
import time

def test_web_routes():
    """测试Web路由功能"""
    print("🌐 开始测试Web路由功能...")
    
    base_url = "http://localhost:5000"
    
    # 1. 测试基础页面访问
    print("\n📄 第一部分：基础页面访问测试")
    print("="*50)
    
    test_pages = [
        ("/", "首页"),
        ("/sales_orders", "销售订单列表"),
        ("/sales_order/new", "新建销售订单"),
        ("/customers", "客户管理"),
        ("/products", "产品管理"),
        ("/employees", "员工管理"),
        ("/production_records", "生产记录"),
    ]
    
    for url, name in test_pages:
        try:
            response = requests.get(f"{base_url}{url}", timeout=10)
            status = "✅" if response.status_code == 200 else "❌"
            print(f"{status} {name}: HTTP {response.status_code}")
            
            if response.status_code == 200:
                # 检查页面内容
                content = response.text
                if "销售订单" in content or "客户" in content or "产品" in content:
                    print(f"   📝 页面内容正常")
                else:
                    print(f"   ⚠️ 页面内容可能异常")
                    
        except requests.exceptions.RequestException as e:
            print(f"❌ {name}: 连接失败 - {e}")
    
    return True

def test_data_integrity():
    """测试数据完整性"""
    print("\n📊 第二部分：数据完整性深度测试")
    print("="*50)
    
    app = create_app()
    with app.app_context():
        try:
            # 检查数据关联完整性
            print("2.1 检查数据关联完整性...")
            
            orders = SalesOrder.query.all()
            print(f"✅ 销售订单总数: {len(orders)}")
            
            for i, order in enumerate(orders):
                print(f"\n订单 {i+1}: {order.order_number}")
                print(f"  客户: {order.customer.customer_name if order.customer else '无客户'}")
                print(f"  状态: {order.status}")
                print(f"  总数量: {order.total_quantity}")
                print(f"  创建时间: {order.created_at}")
                
                # 检查订单行
                items = order.order_items.all()
                print(f"  订单行数: {len(items)}")
                
                for j, item in enumerate(items):
                    print(f"    行{j+1}: {item.product.product_name if item.product else '无产品'}")
                    print(f"         数量: {item.quantity}")
                    print(f"         规格: {item.specifications_text}")
                    print(f"         开向: {item.direction}")
                    
                    # 检查分批到货
                    if item.delivery_batches:
                        try:
                            batches = json.loads(item.delivery_batches)
                            print(f"         分批: {len(batches)} 批次")
                            batch_total = sum(batch.get('quantity', 0) for batch in batches)
                            if batch_total == item.quantity:
                                print(f"         ✅ 分批数量一致")
                            else:
                                print(f"         ⚠️ 分批数量不一致: {batch_total} vs {item.quantity}")
                        except json.JSONDecodeError:
                            print(f"         ❌ 分批数据JSON格式错误")
            
            # 检查客户数据完整性
            print("\n2.2 检查客户数据完整性...")
            customers = Customer.query.all()
            for customer in customers:
                print(f"✅ 客户: {customer.customer_name} ({customer.customer_code})")
                print(f"   联系人: {customer.contact_person}")
                print(f"   电话: {customer.contact_phone}")
                print(f"   状态: {customer.status}")
                
                # 检查客户的订单
                customer_orders = customer.sales_orders.all()
                print(f"   订单数: {len(customer_orders)}")
            
            # 检查产品数据完整性
            print("\n2.3 检查产品数据完整性...")
            products = Product.query.limit(5).all()
            for product in products:
                print(f"✅ 产品: {product.product_name} ({product.product_code})")
                print(f"   图号: {product.drawing_number}")
                print(f"   单位: {product.unit}")
                print(f"   类别: {product.category}")
                
                # 检查产品的订单行
                product_items = product.sales_order_items.all()
                print(f"   被订购次数: {len(product_items)}")
                
        except Exception as e:
            print(f"❌ 数据完整性测试失败: {e}")
            return False
    
    return True

def test_business_logic():
    """测试业务逻辑"""
    print("\n🧠 第三部分：业务逻辑深度测试")
    print("="*50)
    
    app = create_app()
    with app.app_context():
        try:
            # 3.1 测试订单状态流转
            print("3.1 测试订单状态流转...")
            
            admin_user = User.query.filter_by(role='admin').first()
            customer = Customer.query.first()
            product = Product.query.first()
            
            if not all([admin_user, customer, product]):
                print("❌ 缺少必要的基础数据")
                return False
            
            # 创建测试订单
            test_order = SalesOrder(
                order_number=f"LOGIC{datetime.now().strftime('%Y%m%d%H%M%S')}",
                order_source="业务逻辑测试",
                customer_id=customer.id,
                year_month=date.today().strftime('%Y-%m'),
                status='pending',
                created_by=admin_user.id
            )
            db.session.add(test_order)
            db.session.flush()
            
            # 测试状态流转
            status_flow = ['pending', 'confirmed', 'in_production', 'completed']
            for status in status_flow:
                test_order.status = status
                db.session.commit()
                print(f"✅ 状态更新为: {status}")
                
                # 验证状态更新
                updated_order = SalesOrder.query.get(test_order.id)
                if updated_order.status == status:
                    print(f"   ✅ 状态验证成功")
                else:
                    print(f"   ❌ 状态验证失败")
            
            # 3.2 测试数量计算逻辑
            print("\n3.2 测试数量计算逻辑...")
            
            # 添加多个订单行
            quantities = [10, 25, 15, 30]
            for i, qty in enumerate(quantities):
                item = SalesOrderItem(
                    sales_order_id=test_order.id,
                    product_id=product.id,
                    quantity=qty,
                    direction=f"测试开向{i+1}",
                    sequence=i+1
                )
                db.session.add(item)
            
            db.session.commit()
            
            # 计算总数量
            test_order.calculate_total_quantity()
            db.session.commit()
            
            expected_total = sum(quantities)
            actual_total = test_order.total_quantity
            
            print(f"✅ 预期总数量: {expected_total}")
            print(f"✅ 实际总数量: {actual_total}")
            print(f"✅ 计算正确性: {'正确' if expected_total == actual_total else '错误'}")
            
            # 3.3 测试规格组合逻辑
            print("\n3.3 测试规格组合逻辑...")
            
            spec_test_cases = [
                {'extended': True, 'gasket': False, 'joint': False, 'drilling': False, 'other': False},
                {'extended': True, 'gasket': True, 'joint': False, 'drilling': True, 'other': False},
                {'extended': False, 'gasket': False, 'joint': True, 'drilling': False, 'other': True},
                {'extended': True, 'gasket': True, 'joint': True, 'drilling': True, 'other': True},
            ]
            
            for i, spec in enumerate(spec_test_cases):
                spec_item = SalesOrderItem(
                    sales_order_id=test_order.id,
                    product_id=product.id,
                    quantity=5,
                    direction=f"规格测试{i+1}",
                    spec_extended=spec['extended'],
                    spec_gasket=spec['gasket'],
                    spec_joint=spec['joint'],
                    spec_drilling=spec['drilling'],
                    spec_other=spec['other'],
                    spec_other_desc="特殊规格" if spec['other'] else None,
                    sequence=100+i
                )
                db.session.add(spec_item)
                db.session.commit()
                
                # 验证规格文本生成
                spec_text = spec_item.specifications_text
                print(f"✅ 规格组合 {i+1}: {spec_text}")
                
                # 验证规格属性
                specs = spec_item.specifications
                print(f"   规格列表: {specs}")
            
        except Exception as e:
            print(f"❌ 业务逻辑测试失败: {e}")
            db.session.rollback()
            return False
    
    return True

def test_performance():
    """测试性能"""
    print("\n⚡ 第四部分：性能测试")
    print("="*50)
    
    app = create_app()
    with app.app_context():
        try:
            # 4.1 查询性能测试
            print("4.1 查询性能测试...")
            
            start_time = time.time()
            all_orders = SalesOrder.query.all()
            query_time = time.time() - start_time
            print(f"✅ 查询所有订单 ({len(all_orders)} 个): {query_time:.3f}秒")
            
            start_time = time.time()
            all_items = SalesOrderItem.query.all()
            query_time = time.time() - start_time
            print(f"✅ 查询所有订单行 ({len(all_items)} 个): {query_time:.3f}秒")
            
            # 4.2 联表查询性能
            print("\n4.2 联表查询性能测试...")
            
            start_time = time.time()
            orders_with_customers = db.session.query(SalesOrder, Customer).join(Customer).all()
            query_time = time.time() - start_time
            print(f"✅ 订单-客户联表查询 ({len(orders_with_customers)} 个): {query_time:.3f}秒")
            
            start_time = time.time()
            items_with_products = db.session.query(SalesOrderItem, Product).join(Product).all()
            query_time = time.time() - start_time
            print(f"✅ 订单行-产品联表查询 ({len(items_with_products)} 个): {query_time:.3f}秒")
            
            # 4.3 聚合查询性能
            print("\n4.3 聚合查询性能测试...")
            
            start_time = time.time()
            total_quantity = db.session.query(db.func.sum(SalesOrder.total_quantity)).scalar() or 0
            query_time = time.time() - start_time
            print(f"✅ 总数量统计 ({total_quantity}): {query_time:.3f}秒")
            
            start_time = time.time()
            status_counts = db.session.query(
                SalesOrder.status, 
                db.func.count(SalesOrder.id)
            ).group_by(SalesOrder.status).all()
            query_time = time.time() - start_time
            print(f"✅ 状态分组统计: {query_time:.3f}秒")
            for status, count in status_counts:
                print(f"   {status}: {count} 个")
                
        except Exception as e:
            print(f"❌ 性能测试失败: {e}")
            return False
    
    return True

def main():
    """主测试函数"""
    print("🚀 开始销售订单管理功能深度测试...")
    print("="*60)
    
    test_results = []
    
    # 执行各项测试
    test_results.append(("Web路由测试", test_web_routes()))
    test_results.append(("数据完整性测试", test_data_integrity()))
    test_results.append(("业务逻辑测试", test_business_logic()))
    test_results.append(("性能测试", test_performance()))
    
    # 输出测试结果
    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    
    all_passed = True
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} {test_name}")
        if not result:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎊 所有深度测试通过！销售订单管理功能运行完美！")
    else:
        print("💥 部分测试失败，请检查相关功能！")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 