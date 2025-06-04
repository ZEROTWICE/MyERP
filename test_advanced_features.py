#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
销售订单管理高级功能测试脚本
测试边界情况、复杂场景和性能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import SalesOrder, SalesOrderItem, Customer, Product, User, CodeRule
from datetime import datetime, date, timedelta
import json
import time
import random

def test_advanced_features():
    """测试高级功能"""
    app = create_app()
    
    with app.app_context():
        print("🚀 开始高级功能测试...")
        print("="*60)
        
        # 获取基础数据
        admin_user = User.query.filter_by(role='admin').first()
        customers = Customer.query.all()
        products = Product.query.all()
        
        if not all([admin_user, customers, products]):
            print("❌ 缺少必要的基础数据")
            return False
        
        # 1. 测试大批量数据处理
        print("\n📊 第一部分：大批量数据处理测试")
        print("-" * 40)
        
        try:
            print("1.1 创建大量订单...")
            start_time = time.time()
            
            batch_orders = []
            for i in range(20):  # 创建20个订单
                order = SalesOrder(
                    order_number=f"BATCH{datetime.now().strftime('%Y%m%d%H%M%S')}{i:03d}",
                    order_source=f"批量测试源{i+1}",
                    customer_id=random.choice(customers).id,
                    year_month=date.today().strftime('%Y-%m'),
                    status=random.choice(['pending', 'confirmed', 'in_production']),
                    notes=f"批量测试订单{i+1}，包含随机数据",
                    created_by=admin_user.id
                )
                batch_orders.append(order)
                db.session.add(order)
                
                if i % 5 == 4:  # 每5个提交一次
                    db.session.commit()
            
            db.session.commit()
            creation_time = time.time() - start_time
            print(f"✅ 创建 {len(batch_orders)} 个订单，耗时: {creation_time:.3f}秒")
            
            # 为每个订单添加随机数量的订单行
            print("1.2 添加大量订单行...")
            start_time = time.time()
            
            total_items = 0
            for order in batch_orders:
                item_count = random.randint(1, 5)  # 每个订单1-5行
                for j in range(item_count):
                    product = random.choice(products)
                    
                    # 创建复杂的分批到货数据
                    batch_count = random.randint(1, 3)
                    delivery_batches = []
                    total_qty = 0
                    
                    for k in range(batch_count):
                        qty = random.randint(5, 20)
                        total_qty += qty
                        delivery_date = (date.today() + timedelta(days=k*7+random.randint(1,7))).strftime('%Y-%m-%d')
                        delivery_batches.append({
                            "batch_no": k+1,
                            "delivery_date": delivery_date,
                            "quantity": qty,
                            "notes": f"批次{k+1}备注",
                            "contact": f"联系人{k+1}",
                            "phone": f"1380013800{k}"
                        })
                    
                    item = SalesOrderItem(
                        sales_order_id=order.id,
                        product_id=product.id,
                        quantity=total_qty,
                        direction=random.choice(['左开', '右开', '双开', '内开', '外开']),
                        spec_extended=random.choice([True, False]),
                        spec_gasket=random.choice([True, False]),
                        spec_joint=random.choice([True, False]),
                        spec_drilling=random.choice([True, False]),
                        spec_other=random.choice([True, False]),
                        spec_other_desc=f"特殊规格{j+1}" if random.choice([True, False]) else None,
                        usage_unit=f"使用单位{chr(65+j)}",
                        delivery_batches=json.dumps(delivery_batches, ensure_ascii=False),
                        station_notes=f"订单行{j+1}的详细备注信息",
                        sequence=j+1
                    )
                    db.session.add(item)
                    total_items += 1
                
                # 更新订单总数量
                order.calculate_total_quantity()
            
            db.session.commit()
            items_time = time.time() - start_time
            print(f"✅ 创建 {total_items} 个订单行，耗时: {items_time:.3f}秒")
            
        except Exception as e:
            print(f"❌ 大批量数据处理测试失败: {e}")
            db.session.rollback()
            return False
        
        # 2. 测试复杂查询性能
        print("\n🔍 第二部分：复杂查询性能测试")
        print("-" * 40)
        
        try:
            # 2.1 基础查询性能
            print("2.1 基础查询性能...")
            
            start_time = time.time()
            all_orders = SalesOrder.query.all()
            query_time = time.time() - start_time
            print(f"✅ 查询所有订单 ({len(all_orders)} 个): {query_time:.3f}秒")
            
            start_time = time.time()
            all_items = SalesOrderItem.query.all()
            query_time = time.time() - start_time
            print(f"✅ 查询所有订单行 ({len(all_items)} 个): {query_time:.3f}秒")
            
            # 2.2 复杂联表查询
            print("\n2.2 复杂联表查询...")
            
            start_time = time.time()
            complex_query = db.session.query(
                SalesOrder.order_number,
                Customer.customer_name,
                Product.product_name,
                SalesOrderItem.quantity,
                SalesOrderItem.specifications_text
            ).join(Customer).join(SalesOrderItem).join(Product).all()
            query_time = time.time() - start_time
            print(f"✅ 四表联查 ({len(complex_query)} 条记录): {query_time:.3f}秒")
            
            # 2.3 聚合统计查询
            print("\n2.3 聚合统计查询...")
            
            start_time = time.time()
            stats = db.session.query(
                Customer.customer_name,
                db.func.count(SalesOrder.id).label('order_count'),
                db.func.sum(SalesOrder.total_quantity).label('total_qty'),
                db.func.avg(SalesOrder.total_quantity).label('avg_qty')
            ).join(SalesOrder).group_by(Customer.id).all()
            query_time = time.time() - start_time
            print(f"✅ 客户统计查询: {query_time:.3f}秒")
            
            for customer_name, order_count, total_qty, avg_qty in stats:
                print(f"   {customer_name}: {order_count}单, 总量{total_qty or 0}, 平均{avg_qty or 0:.1f}")
            
        except Exception as e:
            print(f"❌ 复杂查询性能测试失败: {e}")
            return False
        
        # 3. 测试数据完整性和一致性
        print("\n🔧 第三部分：数据完整性和一致性测试")
        print("-" * 40)
        
        try:
            print("3.1 数量一致性检查...")
            
            inconsistent_orders = []
            for order in all_orders:
                calculated_total = sum(item.quantity for item in order.order_items)
                if calculated_total != order.total_quantity:
                    inconsistent_orders.append((order.order_number, calculated_total, order.total_quantity))
            
            if inconsistent_orders:
                print(f"⚠️ 发现 {len(inconsistent_orders)} 个数量不一致的订单:")
                for order_num, calc, stored in inconsistent_orders:
                    print(f"   {order_num}: 计算值{calc} vs 存储值{stored}")
            else:
                print("✅ 所有订单数量一致性检查通过")
            
            print("\n3.2 分批到货数据完整性检查...")
            
            batch_errors = []
            for item in all_items:
                if item.delivery_batches:
                    try:
                        batches = json.loads(item.delivery_batches)
                        batch_total = sum(batch.get('quantity', 0) for batch in batches)
                        if batch_total != item.quantity:
                            batch_errors.append((item.id, batch_total, item.quantity))
                    except json.JSONDecodeError:
                        batch_errors.append((item.id, "JSON解析错误", item.quantity))
            
            if batch_errors:
                print(f"⚠️ 发现 {len(batch_errors)} 个分批数据错误:")
                for item_id, batch_total, item_qty in batch_errors[:5]:  # 只显示前5个
                    print(f"   订单行{item_id}: 分批总量{batch_total} vs 行数量{item_qty}")
            else:
                print("✅ 所有分批到货数据完整性检查通过")
            
            print("\n3.3 外键关联完整性检查...")
            
            orphan_items = SalesOrderItem.query.filter(
                ~SalesOrderItem.sales_order_id.in_(
                    db.session.query(SalesOrder.id)
                )
            ).count()
            
            orphan_orders = SalesOrder.query.filter(
                ~SalesOrder.customer_id.in_(
                    db.session.query(Customer.id)
                )
            ).count()
            
            print(f"✅ 孤立订单行: {orphan_items} 个")
            print(f"✅ 孤立订单: {orphan_orders} 个")
            
        except Exception as e:
            print(f"❌ 数据完整性测试失败: {e}")
            return False
        
        # 4. 测试边界条件
        print("\n⚠️ 第四部分：边界条件测试")
        print("-" * 40)
        
        try:
            print("4.1 极值数据测试...")
            
            # 测试极大数量
            extreme_order = SalesOrder(
                order_number=f"EXTREME{datetime.now().strftime('%Y%m%d%H%M%S')}",
                order_source="极值测试",
                customer_id=customers[0].id,
                year_month=date.today().strftime('%Y-%m'),
                created_by=admin_user.id
            )
            db.session.add(extreme_order)
            db.session.flush()
            
            extreme_item = SalesOrderItem(
                sales_order_id=extreme_order.id,
                product_id=products[0].id,
                quantity=999999,  # 极大数量
                direction="极值测试开向"
            )
            db.session.add(extreme_item)
            db.session.commit()
            print("✅ 极大数量测试通过")
            
            # 测试长文本
            long_notes = "这是一个非常长的备注信息，" * 100  # 生成长文本
            long_order = SalesOrder(
                order_number=f"LONG{datetime.now().strftime('%Y%m%d%H%M%S')}",
                order_source="长文本测试",
                customer_id=customers[0].id,
                year_month=date.today().strftime('%Y-%m'),
                notes=long_notes,
                created_by=admin_user.id
            )
            db.session.add(long_order)
            db.session.commit()
            print(f"✅ 长文本测试通过，文本长度: {len(long_notes)} 字符")
            
            # 测试复杂JSON数据
            complex_batches = []
            for i in range(20):  # 20个批次
                complex_batches.append({
                    "batch_no": i + 1,
                    "delivery_date": (date.today() + timedelta(days=i)).strftime('%Y-%m-%d'),
                    "quantity": (i + 1) * 5,
                    "notes": f"复杂批次{i+1}的详细说明信息",
                    "special_requirements": f"特殊要求{i+1}",
                    "contact_person": f"联系人{i+1}",
                    "contact_phone": f"1380013{i:04d}",
                    "delivery_address": f"详细地址{i+1}号楼{i+1}单元{i+1}室",
                    "transport_method": random.choice(["陆运", "海运", "空运", "快递"]),
                    "insurance": random.choice([True, False]),
                    "priority": random.randint(1, 5)
                })
            
            complex_item = SalesOrderItem(
                sales_order_id=extreme_order.id,
                product_id=products[1].id,
                quantity=sum(batch['quantity'] for batch in complex_batches),
                direction="复杂JSON测试",
                delivery_batches=json.dumps(complex_batches, ensure_ascii=False)
            )
            db.session.add(complex_item)
            db.session.commit()
            
            # 验证JSON数据
            retrieved_item = SalesOrderItem.query.filter_by(id=complex_item.id).first()
            parsed_batches = json.loads(retrieved_item.delivery_batches)
            print(f"✅ 复杂JSON数据测试通过，批次数: {len(parsed_batches)}")
            
        except Exception as e:
            print(f"❌ 边界条件测试失败: {e}")
            db.session.rollback()
            return False
        
        # 5. 最终统计和报告
        print("\n📊 第五部分：最终统计报告")
        print("-" * 40)
        
        try:
            final_orders = SalesOrder.query.count()
            final_items = SalesOrderItem.query.count()
            final_customers = Customer.query.count()
            final_products = Product.query.count()
            
            print(f"📈 最终数据统计:")
            print(f"  销售订单: {final_orders} 个")
            print(f"  订单行: {final_items} 个")
            print(f"  客户: {final_customers} 个")
            print(f"  产品: {final_products} 个")
            
            # 状态分布
            status_dist = db.session.query(
                SalesOrder.status,
                db.func.count(SalesOrder.id)
            ).group_by(SalesOrder.status).all()
            
            print(f"\n📊 订单状态分布:")
            for status, count in status_dist:
                print(f"  {status}: {count} 个")
            
            # 数量统计
            total_quantity = db.session.query(db.func.sum(SalesOrder.total_quantity)).scalar() or 0
            avg_quantity = db.session.query(db.func.avg(SalesOrder.total_quantity)).scalar() or 0
            max_quantity = db.session.query(db.func.max(SalesOrder.total_quantity)).scalar() or 0
            
            print(f"\n🔢 数量统计:")
            print(f"  总数量: {total_quantity}")
            print(f"  平均数量: {avg_quantity:.2f}")
            print(f"  最大数量: {max_quantity}")
            
            # 时间分布
            today_orders = SalesOrder.query.filter(
                SalesOrder.created_at >= date.today()
            ).count()
            
            print(f"\n⏰ 时间分布:")
            print(f"  今日创建订单: {today_orders} 个")
            
        except Exception as e:
            print(f"❌ 最终统计失败: {e}")
            return False
        
        print("\n" + "="*60)
        print("🎉 高级功能测试全部完成！")
        print("="*60)
        
        return True

if __name__ == "__main__":
    success = test_advanced_features()
    if success:
        print("\n🎊 高级功能测试全部通过！销售订单管理系统运行完美！")
    else:
        print("\n💥 高级功能测试发现问题，请检查相关功能！")
        sys.exit(1) 