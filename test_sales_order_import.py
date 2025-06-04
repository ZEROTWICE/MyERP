#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from app import create_app

def test_sales_order_import():
    """测试 SalesOrder 导入"""
    app = create_app()
    
    with app.app_context():
        try:
            # 测试模型导入
            from app.models import SalesOrder, SalesOrderItem
            print("✅ SalesOrder 和 SalesOrderItem 模型导入成功")
            
            # 测试查询
            count = SalesOrder.query.count()
            print(f"✅ 当前有 {count} 条销售订单记录")
            
            # 测试路由导入
            from app.main.routes import manage_sales_orders, add_sales_order
            print("✅ 销售订单路由导入成功")
            
            # 测试表单导入
            from app.main.forms import SalesOrderForm, SalesOrderItemForm
            print("✅ 销售订单表单导入成功")
            
            print("\n🎉 所有 SalesOrder 相关组件导入测试通过！")
            
        except Exception as e:
            print(f"❌ 导入失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_sales_order_import() 