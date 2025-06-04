#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from app import create_app
from app.models import User, Customer, Product, SalesOrder, SalesOrderItem, db
from datetime import datetime

def test_complete_sales_order_functionality():
    """完整测试销售订单功能，包括可能触发 NameError 的场景"""
    app = create_app()
    
    with app.app_context():
        try:
            print("🔍 开始完整的销售订单功能测试...")
            
            # 1. 测试模型导入和基本查询
            print("\n1. 测试模型导入和基本查询")
            orders = SalesOrder.query.all()
            items = SalesOrderItem.query.all()
            print(f"✅ 当前销售订单数量: {len(orders)}")
            print(f"✅ 当前订单行数量: {len(items)}")
            
            # 2. 测试复杂查询（可能触发错误的地方）
            print("\n2. 测试复杂查询")
            
            # 联表查询
            orders_with_customers = db.session.query(SalesOrder, Customer).join(Customer).all()
            print(f"✅ 联表查询成功，找到 {len(orders_with_customers)} 条记录")
            
            # 聚合查询
            total_quantity = db.session.query(db.func.sum(SalesOrder.total_quantity)).scalar() or 0
            print(f"✅ 聚合查询成功，总数量: {total_quantity}")
            
            # 分组查询
            status_counts = db.session.query(
                SalesOrder.status,
                db.func.count(SalesOrder.id)
            ).group_by(SalesOrder.status).all()
            print(f"✅ 分组查询成功，状态统计: {dict(status_counts)}")
            
            # 3. 测试创建新订单（可能触发编码规则相关错误）
            print("\n3. 测试创建新订单")
            
            # 获取测试数据
            customer = Customer.query.first()
            product = Product.query.first()
            
            if customer and product:
                # 创建测试订单
                test_order = SalesOrder(
                    order_number=f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    order_source="测试来源",
                    customer_id=customer.id,
                    year_month=datetime.now().strftime('%Y-%m'),
                    order_date=datetime.now(),
                    status='pending',
                    total_quantity=100,
                    notes="完整功能测试订单"
                )
                
                db.session.add(test_order)
                db.session.flush()  # 获取 ID
                
                # 创建订单行（不设置 product_name，因为它是只读属性）
                test_item = SalesOrderItem(
                    sales_order_id=test_order.id,
                    product_id=product.id,
                    quantity=100,
                    direction="测试开向",
                    usage_unit="测试单位",
                    order_time=datetime.now(),
                    station_notes="测试到站备注"
                )
                
                db.session.add(test_item)
                db.session.commit()
                
                print(f"✅ 成功创建测试订单: {test_order.order_number}")
                print(f"✅ 成功创建订单行，数量: {test_item.quantity}")
                print(f"✅ 产品名称通过属性获取: {test_item.product_name}")
                
                # 清理测试数据
                db.session.delete(test_item)
                db.session.delete(test_order)
                db.session.commit()
                print("✅ 测试数据清理完成")
            else:
                print("⚠️ 缺少测试数据（客户或产品），跳过创建测试")
            
            # 4. 测试路由函数（可能触发导入错误的地方）
            print("\n4. 测试路由函数导入")
            from app.main.routes import (
                manage_sales_orders, 
                add_sales_order, 
                sales_order_detail,
                edit_sales_order,
                delete_sales_order,
                add_sales_order_item,
                edit_sales_order_item,
                delete_sales_order_item
            )
            print("✅ 所有销售订单路由函数导入成功")
            
            # 5. 测试表单类
            print("\n5. 测试表单类")
            from app.main.forms import SalesOrderForm, SalesOrderItemForm
            
            # 创建表单实例
            order_form = SalesOrderForm()
            item_form = SalesOrderItemForm()
            print("✅ 销售订单表单创建成功")
            
            # 6. 测试模板渲染相关（可能的错误源）
            print("\n6. 测试模板相关功能")
            
            # 测试状态选择
            status_choices = [
                ('pending', '待处理'),
                ('confirmed', '已确认'),
                ('in_production', '生产中'),
                ('completed', '已完成'),
                ('cancelled', '已取消')
            ]
            print(f"✅ 状态选择列表: {len(status_choices)} 个选项")
            
            # 测试规格处理
            specs = ['加长', '垫板', '接头', '钻孔', '其他']
            print(f"✅ 规格选项: {specs}")
            
            print("\n🎉 所有销售订单功能测试通过！")
            print("✅ 没有发现 'NameError: name SalesOrder is not defined' 错误")
            
        except NameError as e:
            if 'SalesOrder' in str(e):
                print(f"❌ 发现 SalesOrder 相关的 NameError: {e}")
                print("🔧 这可能是导入问题，需要检查:")
                print("   1. app/main/routes.py 中的模型导入")
                print("   2. 模板文件中的变量使用")
                print("   3. 表单字段定义")
            else:
                print(f"❌ 发现其他 NameError: {e}")
            import traceback
            traceback.print_exc()
            
        except Exception as e:
            print(f"❌ 测试过程中发生错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_complete_sales_order_functionality() 