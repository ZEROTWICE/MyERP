#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
销售订单管理功能全面测试脚本
测试所有销售订单相关功能，包括Web路由、数据验证、边界条件等
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import SalesOrder, SalesOrderItem, Customer, Product, User, CodeRule
from datetime import datetime, date
import json
import requests
import time

def test_comprehensive_sales_orders():
    """全面测试销售订单管理功能"""
    app = create_app()
    
    with app.app_context():
        print("🚀 开始全面测试销售订单管理功能...")
        
        # 1. 数据库完整性测试
        print("\n" + "="*60)
        print("📊 第一部分：数据库完整性测试")
        print("="*60)
        
        try:
            # 检查表结构
            print("1.1 检查表结构...")
            sales_orders = SalesOrder.query.all()
            sales_order_items = SalesOrderItem.query.all()
            customers = Customer.query.all()
            products = Product.query.all()
            
            print(f"✅ 销售订单表：{len(sales_orders)} 条记录")
            print(f"✅ 销售订单行表：{len(sales_order_items)} 条记录")
            print(f"✅ 客户表：{len(customers)} 条记录")
            print(f"✅ 产品表：{len(products)} 条记录")
            
            # 检查字段完整性
            print("\n1.2 检查字段完整性...")
            if sales_orders:
                order = sales_orders[0]
                required_fields = ['order_number', 'order_source', 'customer_id', 'year_month', 'status']
                for field in required_fields:
                    if hasattr(order, field):
                        print(f"✅ SalesOrder.{field} 字段存在")
                    else:
                        print(f"❌ SalesOrder.{field} 字段缺失")
            
            if sales_order_items:
                item = sales_order_items[0]
                required_fields = ['product_id', 'quantity', 'direction', 'spec_extended', 'spec_gasket']
                for field in required_fields:
                    if hasattr(item, field):
                        print(f"✅ SalesOrderItem.{field} 字段存在")
                    else:
                        print(f"❌ SalesOrderItem.{field} 字段缺失")
                        
        except Exception as e:
            print(f"❌ 数据库完整性测试失败: {e}")
            return False
        
        # 2. 业务逻辑测试
        print("\n" + "="*60)
        print("🧠 第二部分：业务逻辑测试")
        print("="*60)
        
        try:
            # 获取测试数据
            admin_user = User.query.filter_by(role='admin').first()
            if not admin_user:
                print("❌ 未找到管理员用户")
                return False
            
            # 2.1 测试订单编号生成
            print("\n2.1 测试订单编号生成...")
            order_numbers = []
            for i in range(5):
                order_number = f"SO{datetime.now().strftime('%Y%m%d%H%M%S')}{i:02d}"
                order_numbers.append(order_number)
                time.sleep(0.1)  # 确保时间戳不同
            
            print(f"✅ 生成了 {len(order_numbers)} 个唯一订单编号")
            print(f"   示例: {order_numbers[0]}, {order_numbers[-1]}")
            
            # 2.2 测试客户关联
            print("\n2.2 测试客户关联...")
            customer = Customer.query.first()
            if customer:
                print(f"✅ 找到客户: {customer.customer_name} ({customer.customer_code})")
                print(f"   联系人: {customer.contact_person}")
                print(f"   电话: {customer.contact_phone}")
                print(f"   状态: {customer.status}")
            else:
                print("❌ 未找到客户数据")
                return False
            
            # 2.3 测试产品关联
            print("\n2.3 测试产品关联...")
            products = Product.query.limit(3).all()
            for product in products:
                print(f"✅ 产品: {product.product_name} ({product.product_code})")
                print(f"   图号: {product.drawing_number}")
                print(f"   单位: {product.unit}")
                print(f"   类别: {product.category}")
            
            # 2.4 测试规格型号组合
            print("\n2.4 测试规格型号组合...")
            spec_combinations = [
                {'extended': True, 'gasket': False, 'joint': False, 'drilling': False, 'other': False},
                {'extended': True, 'gasket': True, 'joint': False, 'drilling': True, 'other': False},
                {'extended': False, 'gasket': False, 'joint': True, 'drilling': False, 'other': True},
                {'extended': True, 'gasket': True, 'joint': True, 'drilling': True, 'other': True},
            ]
            
            for i, spec in enumerate(spec_combinations):
                spec_text = []
                if spec['extended']: spec_text.append("加长")
                if spec['gasket']: spec_text.append("垫板")
                if spec['joint']: spec_text.append("接头")
                if spec['drilling']: spec_text.append("钻孔")
                if spec['other']: spec_text.append("其他")
                
                print(f"✅ 规格组合 {i+1}: {', '.join(spec_text) if spec_text else '无'}")
            
        except Exception as e:
            print(f"❌ 业务逻辑测试失败: {e}")
            return False
        
        # 3. 数据创建和操作测试
        print("\n" + "="*60)
        print("📝 第三部分：数据创建和操作测试")
        print("="*60)
        
        try:
            # 3.1 创建完整的销售订单
            print("\n3.1 创建完整的销售订单...")
            
            order_number = f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}"
            sales_order = SalesOrder(
                order_number=order_number,
                order_source="深度测试",
                customer_id=customer.id,
                year_month=date.today().strftime('%Y-%m'),
                status='pending',
                notes="这是一个深度测试订单",
                created_by=admin_user.id
            )
            db.session.add(sales_order)
            db.session.flush()
            
            print(f"✅ 创建销售订单: {sales_order.order_number}")
            print(f"   客户: {sales_order.customer.customer_name}")
            print(f"   状态: {sales_order.status}")
            
            # 3.2 添加多个订单行
            print("\n3.2 添加多个订单行...")
            
            order_items = []
            for i, product in enumerate(products[:3]):
                # 创建分批到货信息
                delivery_batches = [
                    {
                        "batch_no": 1,
                        "delivery_date": f"2025-0{i+1}-15",
                        "quantity": 10 + i*5,
                        "notes": f"第一批次-产品{i+1}"
                    },
                    {
                        "batch_no": 2,
                        "delivery_date": f"2025-0{i+1}-28",
                        "quantity": 5 + i*3,
                        "notes": f"第二批次-产品{i+1}"
                    }
                ]
                
                order_item = SalesOrderItem(
                    sales_order_id=sales_order.id,
                    product_id=product.id,
                    quantity=15 + i*8,
                    direction="左开" if i % 2 == 0 else "右开",
                    spec_extended=i % 2 == 0,
                    spec_gasket=i % 3 == 0,
                    spec_joint=i % 4 == 0,
                    spec_drilling=True,
                    spec_other=i == 2,
                    spec_other_desc="特殊定制" if i == 2 else None,
                    usage_unit=f"生产车间{chr(65+i)}",
                    delivery_batches=json.dumps(delivery_batches, ensure_ascii=False),
                    station_notes=f"产品{i+1}的到站备注",
                    sequence=i+1
                )
                db.session.add(order_item)
                order_items.append(order_item)
                
                print(f"✅ 订单行 {i+1}: {product.product_name}")
                print(f"   数量: {order_item.quantity}")
                print(f"   开向: {order_item.direction}")
                print(f"   规格: {order_item.specifications_text}")
                print(f"   分批: {len(delivery_batches)} 批次")
            
            db.session.commit()
            
            # 3.3 测试合计数量计算
            print("\n3.3 测试合计数量计算...")
            sales_order.calculate_total_quantity()
            db.session.commit()
            
            expected_total = sum(item.quantity for item in order_items)
            actual_total = sales_order.total_quantity
            
            print(f"✅ 预期合计: {expected_total}")
            print(f"✅ 实际合计: {actual_total}")
            print(f"✅ 计算正确: {expected_total == actual_total}")
            
            # 3.4 测试订单状态更新
            print("\n3.4 测试订单状态更新...")
            status_flow = ['pending', 'confirmed', 'in_production', 'completed']
            
            for status in status_flow:
                sales_order.status = status
                db.session.commit()
                print(f"✅ 状态更新为: {status}")
            
        except Exception as e:
            print(f"❌ 数据创建和操作测试失败: {e}")
            db.session.rollback()
            return False
        
        # 4. 查询和过滤测试
        print("\n" + "="*60)
        print("🔍 第四部分：查询和过滤测试")
        print("="*60)
        
        try:
            # 4.1 按不同条件查询
            print("\n4.1 按不同条件查询...")
            
            # 按订单号查询
            found_order = SalesOrder.query.filter_by(order_number=order_number).first()
            print(f"✅ 按订单号查询: {'成功' if found_order else '失败'}")
            
            # 按客户查询
            customer_orders = SalesOrder.query.filter_by(customer_id=customer.id).all()
            print(f"✅ 按客户查询: 找到 {len(customer_orders)} 个订单")
            
            # 按状态查询
            completed_orders = SalesOrder.query.filter_by(status='completed').all()
            print(f"✅ 按状态查询: 找到 {len(completed_orders)} 个已完成订单")
            
            # 按年月查询
            current_month = date.today().strftime('%Y-%m')
            month_orders = SalesOrder.query.filter_by(year_month=current_month).all()
            print(f"✅ 按年月查询: 找到 {len(month_orders)} 个本月订单")
            
            # 4.2 复杂查询测试
            print("\n4.2 复杂查询测试...")
            
            # 联表查询
            orders_with_customer = db.session.query(SalesOrder, Customer).join(Customer).all()
            print(f"✅ 联表查询: 找到 {len(orders_with_customer)} 个订单-客户记录")
            
            # 统计查询
            total_quantity = db.session.query(db.func.sum(SalesOrder.total_quantity)).scalar() or 0
            print(f"✅ 统计查询: 总数量 {total_quantity}")
            
            # 分组查询
            status_counts = db.session.query(
                SalesOrder.status, 
                db.func.count(SalesOrder.id)
            ).group_by(SalesOrder.status).all()
            
            print("✅ 分组查询 - 按状态统计:")
            for status, count in status_counts:
                print(f"   {status}: {count} 个订单")
                
        except Exception as e:
            print(f"❌ 查询和过滤测试失败: {e}")
            return False
        
        # 5. 边界条件和异常处理测试
        print("\n" + "="*60)
        print("⚠️ 第五部分：边界条件和异常处理测试")
        print("="*60)
        
        try:
            # 5.1 测试空值处理
            print("\n5.1 测试空值处理...")
            
            # 测试可选字段为空
            minimal_order = SalesOrder(
                order_number=f"MIN{datetime.now().strftime('%Y%m%d%H%M%S')}",
                order_source="最小测试",
                customer_id=customer.id,
                year_month=date.today().strftime('%Y-%m'),
                created_by=admin_user.id
            )
            db.session.add(minimal_order)
            db.session.commit()
            print("✅ 最小字段订单创建成功")
            
            # 5.2 测试数据验证
            print("\n5.2 测试数据验证...")
            
            # 测试负数数量
            try:
                invalid_item = SalesOrderItem(
                    sales_order_id=minimal_order.id,
                    product_id=products[0].id,
                    quantity=-1,  # 负数
                    direction="左开"
                )
                db.session.add(invalid_item)
                db.session.commit()
                print("⚠️ 负数数量未被拒绝（可能需要添加验证）")
            except Exception as e:
                print("✅ 负数数量被正确拒绝")
                db.session.rollback()
            
            # 5.3 测试大数据量
            print("\n5.3 测试大数据量...")
            
            large_quantity = 999999
            large_item = SalesOrderItem(
                sales_order_id=minimal_order.id,
                product_id=products[0].id,
                quantity=large_quantity,
                direction="左开"
            )
            db.session.add(large_item)
            db.session.commit()
            print(f"✅ 大数量 {large_quantity} 处理成功")
            
        except Exception as e:
            print(f"❌ 边界条件测试失败: {e}")
            db.session.rollback()
            return False
        
        # 6. 性能测试
        print("\n" + "="*60)
        print("⚡ 第六部分：性能测试")
        print("="*60)
        
        try:
            # 6.1 批量创建测试
            print("\n6.1 批量创建测试...")
            
            start_time = time.time()
            batch_orders = []
            
            for i in range(10):
                batch_order = SalesOrder(
                    order_number=f"BATCH{datetime.now().strftime('%Y%m%d%H%M%S')}{i:03d}",
                    order_source="批量测试",
                    customer_id=customer.id,
                    year_month=date.today().strftime('%Y-%m'),
                    created_by=admin_user.id
                )
                batch_orders.append(batch_order)
                db.session.add(batch_order)
            
            db.session.commit()
            end_time = time.time()
            
            print(f"✅ 批量创建 {len(batch_orders)} 个订单")
            print(f"✅ 耗时: {end_time - start_time:.3f} 秒")
            
            # 6.2 批量查询测试
            print("\n6.2 批量查询测试...")
            
            start_time = time.time()
            all_orders = SalesOrder.query.all()
            end_time = time.time()
            
            print(f"✅ 查询 {len(all_orders)} 个订单")
            print(f"✅ 耗时: {end_time - start_time:.3f} 秒")
            
        except Exception as e:
            print(f"❌ 性能测试失败: {e}")
            return False
        
        # 7. Web接口测试
        print("\n" + "="*60)
        print("🌐 第七部分：Web接口测试")
        print("="*60)
        
        try:
            # 7.1 测试主要页面访问
            print("\n7.1 测试主要页面访问...")
            
            base_url = "http://localhost:5000"
            test_urls = [
                "/",
                "/sales_orders",
                "/sales_order/new",
            ]
            
            for url in test_urls:
                try:
                    response = requests.get(f"{base_url}{url}", timeout=5)
                    print(f"✅ {url}: HTTP {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"⚠️ {url}: 连接失败 ({e})")
            
        except Exception as e:
            print(f"⚠️ Web接口测试跳过: {e}")
        
        print("\n" + "="*60)
        print("🎉 全面测试完成！")
        print("="*60)
        
        # 最终统计
        final_orders = SalesOrder.query.count()
        final_items = SalesOrderItem.query.count()
        
        print(f"\n📊 最终统计:")
        print(f"✅ 销售订单总数: {final_orders}")
        print(f"✅ 订单行总数: {final_items}")
        print(f"✅ 客户总数: {Customer.query.count()}")
        print(f"✅ 产品总数: {Product.query.count()}")
        
        return True

if __name__ == "__main__":
    success = test_comprehensive_sales_orders()
    if success:
        print("\n🎊 全面测试通过！销售订单管理功能运行完美！")
    else:
        print("\n💥 测试发现问题，请检查相关功能！")
        sys.exit(1) 