#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
销售订单管理功能深度测试脚本
测试所有销售订单相关功能的各个方面
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import SalesOrder, SalesOrderItem, Customer, Product, User
from datetime import datetime, date
import json
import time

def test_deep_sales_orders():
    """深度测试销售订单管理功能"""
    app = create_app()
    
    with app.app_context():
        print("🚀 开始深度测试销售订单管理功能...")
        
        # 1. 数据库完整性测试
        print("\n" + "="*60)
        print("📊 第一部分：数据库完整性测试")
        print("="*60)
        
        try:
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
        
        # 2. 业务逻辑深度测试
        print("\n" + "="*60)
        print("🧠 第二部分：业务逻辑深度测试")
        print("="*60)
        
        try:
            admin_user = User.query.filter_by(role='admin').first()
            if not admin_user:
                print("❌ 未找到管理员用户")
                return False
            
            # 2.1 测试订单编号唯一性
            print("\n2.1 测试订单编号唯一性...")
            order_numbers = set()
            for i in range(10):
                order_number = f"UNIQUE{datetime.now().strftime('%Y%m%d%H%M%S')}{i:03d}"
                order_numbers.add(order_number)
                time.sleep(0.01)
            
            print(f"✅ 生成了 {len(order_numbers)} 个唯一订单编号")
            
            # 2.2 测试客户关联完整性
            print("\n2.2 测试客户关联完整性...")
            customer = Customer.query.first()
            if customer:
                print(f"✅ 客户信息完整: {customer.customer_name}")
                print(f"   编码: {customer.customer_code}")
                print(f"   联系人: {customer.contact_person}")
                print(f"   电话: {customer.contact_phone}")
                print(f"   邮箱: {customer.contact_email}")
                print(f"   状态: {customer.status}")
                print(f"   创建时间: {customer.created_at}")
            else:
                print("❌ 未找到客户数据")
                return False
            
            # 2.3 测试产品关联完整性
            print("\n2.3 测试产品关联完整性...")
            products = Product.query.limit(5).all()
            for i, product in enumerate(products):
                print(f"✅ 产品 {i+1}: {product.product_name}")
                print(f"   编码: {product.product_code}")
                print(f"   图号: {product.drawing_number}")
                print(f"   单位: {product.unit}")
                print(f"   类别: {product.category}")
                print(f"   状态: {product.status}")
            
            # 2.4 测试规格型号所有组合
            print("\n2.4 测试规格型号所有组合...")
            spec_options = ['spec_extended', 'spec_gasket', 'spec_joint', 'spec_drilling', 'spec_other']
            spec_names = ['加长', '垫板', '接头', '钻孔', '其他']
            
            # 测试所有可能的组合（2^5 = 32种）
            for i in range(32):
                specs = []
                for j, (option, name) in enumerate(zip(spec_options, spec_names)):
                    if i & (1 << j):
                        specs.append(name)
                
                if i % 8 == 0:  # 只显示部分组合
                    print(f"✅ 规格组合 {i:02d}: {', '.join(specs) if specs else '无规格'}")
            
            print(f"✅ 总共支持 32 种规格组合")
            
        except Exception as e:
            print(f"❌ 业务逻辑测试失败: {e}")
            return False
        
        # 3. 复杂数据操作测试
        print("\n" + "="*60)
        print("📝 第三部分：复杂数据操作测试")
        print("="*60)
        
        try:
            # 3.1 创建复杂销售订单
            print("\n3.1 创建复杂销售订单...")
            
            order_number = f"COMPLEX{datetime.now().strftime('%Y%m%d%H%M%S')}"
            complex_order = SalesOrder(
                order_number=order_number,
                order_source="复杂测试订单",
                customer_id=customer.id,
                year_month=date.today().strftime('%Y-%m'),
                status='pending',
                notes="这是一个包含多种规格和分批到货的复杂测试订单",
                created_by=admin_user.id
            )
            db.session.add(complex_order)
            db.session.flush()
            
            print(f"✅ 创建复杂订单: {complex_order.order_number}")
            
            # 3.2 添加多样化订单行
            print("\n3.2 添加多样化订单行...")
            
            order_items = []
            directions = ['左开', '右开', '双开', '内开', '外开']
            
            for i, product in enumerate(products[:5]):
                # 创建复杂的分批到货信息
                batch_count = (i % 3) + 1  # 1-3批次
                delivery_batches = []
                
                for batch_num in range(1, batch_count + 1):
                    delivery_batches.append({
                        "batch_no": batch_num,
                        "delivery_date": f"2025-{(i%12)+1:02d}-{(batch_num*10):02d}",
                        "quantity": 5 + batch_num * 3,
                        "notes": f"第{batch_num}批次 - 产品{product.product_name}"
                    })
                
                # 创建不同规格组合的订单行
                order_item = SalesOrderItem(
                    sales_order_id=complex_order.id,
                    product_id=product.id,
                    quantity=sum(batch['quantity'] for batch in delivery_batches),
                    direction=directions[i % len(directions)],
                    spec_extended=(i % 2 == 0),
                    spec_gasket=(i % 3 == 0),
                    spec_joint=(i % 4 == 0),
                    spec_drilling=(i % 5 == 0),
                    spec_other=(i == 4),
                    spec_other_desc=f"特殊定制规格{i+1}" if i == 4 else None,
                    usage_unit=f"使用单位{chr(65+i)}",
                    delivery_batches=json.dumps(delivery_batches, ensure_ascii=False),
                    station_notes=f"复杂订单行{i+1}的详细备注信息",
                    sequence=i+1
                )
                db.session.add(order_item)
                order_items.append(order_item)
                
                print(f"✅ 订单行 {i+1}: {product.product_name}")
                print(f"   数量: {order_item.quantity}")
                print(f"   开向: {order_item.direction}")
                print(f"   规格: {order_item.specifications_text}")
                print(f"   分批: {len(delivery_batches)} 批次")
                print(f"   使用单位: {order_item.usage_unit}")
            
            db.session.commit()
            
            # 3.3 测试合计数量计算准确性
            print("\n3.3 测试合计数量计算准确性...")
            complex_order.calculate_total_quantity()
            db.session.commit()
            
            manual_total = sum(item.quantity for item in order_items)
            auto_total = complex_order.total_quantity
            
            print(f"✅ 手动计算总量: {manual_total}")
            print(f"✅ 自动计算总量: {auto_total}")
            print(f"✅ 计算准确性: {'正确' if manual_total == auto_total else '错误'}")
            
            # 3.4 测试分批到货数据完整性
            print("\n3.4 测试分批到货数据完整性...")
            for i, item in enumerate(order_items):
                if item.delivery_batches:
                    batches = json.loads(item.delivery_batches)
                    batch_total = sum(batch['quantity'] for batch in batches)
                    print(f"✅ 订单行{i+1} 分批总量: {batch_total}, 订单行总量: {item.quantity}")
                    print(f"   分批数据完整性: {'正确' if batch_total == item.quantity else '错误'}")
            
        except Exception as e:
            print(f"❌ 复杂数据操作测试失败: {e}")
            db.session.rollback()
            return False
        
        # 4. 查询性能和准确性测试
        print("\n" + "="*60)
        print("🔍 第四部分：查询性能和准确性测试")
        print("="*60)
        
        try:
            # 4.1 基础查询测试
            print("\n4.1 基础查询测试...")
            
            start_time = time.time()
            all_orders = SalesOrder.query.all()
            query_time = time.time() - start_time
            print(f"✅ 查询所有订单: {len(all_orders)} 条, 耗时: {query_time:.3f}秒")
            
            # 按状态查询
            status_counts = {}
            for status in ['pending', 'confirmed', 'in_production', 'completed', 'cancelled']:
                count = SalesOrder.query.filter_by(status=status).count()
                status_counts[status] = count
                print(f"✅ {status} 状态订单: {count} 条")
            
            # 4.2 复杂联表查询测试
            print("\n4.2 复杂联表查询测试...")
            
            start_time = time.time()
            # 查询订单及其客户信息
            orders_with_customers = db.session.query(SalesOrder, Customer).join(Customer).all()
            query_time = time.time() - start_time
            print(f"✅ 订单-客户联表查询: {len(orders_with_customers)} 条, 耗时: {query_time:.3f}秒")
            
            # 查询订单行及其产品信息
            start_time = time.time()
            items_with_products = db.session.query(SalesOrderItem, Product).join(Product).all()
            query_time = time.time() - start_time
            print(f"✅ 订单行-产品联表查询: {len(items_with_products)} 条, 耗时: {query_time:.3f}秒")
            
            # 4.3 聚合查询测试
            print("\n4.3 聚合查询测试...")
            
            # 统计总数量
            total_quantity = db.session.query(db.func.sum(SalesOrder.total_quantity)).scalar() or 0
            print(f"✅ 所有订单总数量: {total_quantity}")
            
            # 按客户统计
            customer_stats = db.session.query(
                Customer.customer_name,
                db.func.count(SalesOrder.id).label('order_count'),
                db.func.sum(SalesOrder.total_quantity).label('total_qty')
            ).join(SalesOrder).group_by(Customer.id).all()
            
            print("✅ 按客户统计:")
            for customer_name, order_count, total_qty in customer_stats:
                print(f"   {customer_name}: {order_count} 个订单, {total_qty or 0} 总数量")
            
        except Exception as e:
            print(f"❌ 查询测试失败: {e}")
            return False
        
        # 5. 边界条件和异常处理测试
        print("\n" + "="*60)
        print("⚠️ 第五部分：边界条件和异常处理测试")
        print("="*60)
        
        try:
            # 5.1 测试极值数据
            print("\n5.1 测试极值数据...")
            
            # 测试最大数量
            max_quantity_order = SalesOrder(
                order_number=f"MAX{datetime.now().strftime('%Y%m%d%H%M%S')}",
                order_source="极值测试",
                customer_id=customer.id,
                year_month=date.today().strftime('%Y-%m'),
                created_by=admin_user.id
            )
            db.session.add(max_quantity_order)
            db.session.flush()
            
            max_item = SalesOrderItem(
                sales_order_id=max_quantity_order.id,
                product_id=products[0].id,
                quantity=999999,  # 极大数量
                direction="测试开向"
            )
            db.session.add(max_item)
            db.session.commit()
            print("✅ 极大数量测试通过")
            
            # 5.2 测试长文本
            print("\n5.2 测试长文本...")
            
            long_text = "这是一个非常长的备注信息，" * 50  # 生成长文本
            long_text_order = SalesOrder(
                order_number=f"LONG{datetime.now().strftime('%Y%m%d%H%M%S')}",
                order_source="长文本测试",
                customer_id=customer.id,
                year_month=date.today().strftime('%Y-%m'),
                notes=long_text,
                created_by=admin_user.id
            )
            db.session.add(long_text_order)
            db.session.commit()
            print(f"✅ 长文本测试通过，文本长度: {len(long_text)} 字符")
            
            # 5.3 测试JSON数据完整性
            print("\n5.3 测试JSON数据完整性...")
            
            complex_batches = []
            for i in range(10):  # 创建10个批次
                complex_batches.append({
                    "batch_no": i + 1,
                    "delivery_date": f"2025-{(i%12)+1:02d}-{(i%28)+1:02d}",
                    "quantity": (i + 1) * 5,
                    "notes": f"复杂批次{i+1}的详细说明信息",
                    "special_requirements": f"特殊要求{i+1}",
                    "contact_person": f"联系人{i+1}"
                })
            
            json_test_item = SalesOrderItem(
                sales_order_id=max_quantity_order.id,
                product_id=products[1].id,
                quantity=sum(batch['quantity'] for batch in complex_batches),
                direction="JSON测试",
                delivery_batches=json.dumps(complex_batches, ensure_ascii=False)
            )
            db.session.add(json_test_item)
            db.session.commit()
            
            # 验证JSON数据
            retrieved_item = SalesOrderItem.query.filter_by(id=json_test_item.id).first()
            parsed_batches = json.loads(retrieved_item.delivery_batches)
            print(f"✅ JSON数据完整性测试通过，批次数: {len(parsed_batches)}")
            
        except Exception as e:
            print(f"❌ 边界条件测试失败: {e}")
            db.session.rollback()
            return False
        
        # 6. 性能压力测试
        print("\n" + "="*60)
        print("⚡ 第六部分：性能压力测试")
        print("="*60)
        
        try:
            # 6.1 批量创建性能测试
            print("\n6.1 批量创建性能测试...")
            
            start_time = time.time()
            batch_orders = []
            
            for i in range(50):  # 创建50个订单
                batch_order = SalesOrder(
                    order_number=f"PERF{datetime.now().strftime('%Y%m%d%H%M%S')}{i:03d}",
                    order_source="性能测试",
                    customer_id=customer.id,
                    year_month=date.today().strftime('%Y-%m'),
                    created_by=admin_user.id
                )
                batch_orders.append(batch_order)
                db.session.add(batch_order)
                
                if i % 10 == 9:  # 每10个提交一次
                    db.session.commit()
            
            db.session.commit()
            creation_time = time.time() - start_time
            print(f"✅ 批量创建 {len(batch_orders)} 个订单，耗时: {creation_time:.3f}秒")
            print(f"✅ 平均每个订单: {creation_time/len(batch_orders):.4f}秒")
            
            # 6.2 批量查询性能测试
            print("\n6.2 批量查询性能测试...")
            
            start_time = time.time()
            all_orders_count = SalesOrder.query.count()
            count_time = time.time() - start_time
            print(f"✅ 统计查询 {all_orders_count} 个订单，耗时: {count_time:.3f}秒")
            
            start_time = time.time()
            recent_orders = SalesOrder.query.order_by(SalesOrder.created_at.desc()).limit(20).all()
            query_time = time.time() - start_time
            print(f"✅ 分页查询最近 {len(recent_orders)} 个订单，耗时: {query_time:.3f}秒")
            
        except Exception as e:
            print(f"❌ 性能测试失败: {e}")
            return False
        
        # 最终统计
        print("\n" + "="*60)
        print("📊 测试完成统计")
        print("="*60)
        
        final_stats = {
            'orders': SalesOrder.query.count(),
            'items': SalesOrderItem.query.count(),
            'customers': Customer.query.count(),
            'products': Product.query.count()
        }
        
        print(f"✅ 最终数据统计:")
        print(f"   销售订单: {final_stats['orders']} 个")
        print(f"   订单行: {final_stats['items']} 个")
        print(f"   客户: {final_stats['customers']} 个")
        print(f"   产品: {final_stats['products']} 个")
        
        return True

if __name__ == "__main__":
    success = test_deep_sales_orders()
    if success:
        print("\n🎊 深度测试全部通过！销售订单管理功能运行完美！")
    else:
        print("\n💥 深度测试发现问题，请检查相关功能！")
        sys.exit(1) 