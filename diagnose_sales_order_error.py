#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import traceback
from app import create_app

def diagnose_sales_order_issues():
    """诊断 SalesOrder 相关的 NameError 问题"""
    print("🔍 开始诊断 SalesOrder 相关问题...")
    
    try:
        # 1. 测试应用创建
        print("\n1. 测试应用创建")
        app = create_app()
        print("✅ 应用创建成功")
        
        with app.app_context():
            # 2. 测试基本模型导入
            print("\n2. 测试基本模型导入")
            try:
                from app.models import SalesOrder, SalesOrderItem
                print("✅ SalesOrder 和 SalesOrderItem 导入成功")
            except NameError as e:
                print(f"❌ 模型导入失败: {e}")
                return
            
            # 3. 测试路由文件导入
            print("\n3. 测试路由文件导入")
            try:
                import app.main.routes
                print("✅ 路由文件导入成功")
            except NameError as e:
                print(f"❌ 路由文件导入失败: {e}")
                print("🔧 这可能是路由文件中缺少 SalesOrder 导入")
                traceback.print_exc()
                return
            except Exception as e:
                print(f"⚠️ 路由文件导入时出现其他错误: {e}")
            
            # 4. 测试表单文件导入
            print("\n4. 测试表单文件导入")
            try:
                from app.main.forms import SalesOrderForm, SalesOrderItemForm
                print("✅ 销售订单表单导入成功")
            except NameError as e:
                print(f"❌ 表单导入失败: {e}")
                traceback.print_exc()
                return
            
            # 5. 测试具体路由函数
            print("\n5. 测试具体路由函数")
            try:
                from app.main.routes import manage_sales_orders
                print("✅ manage_sales_orders 函数导入成功")
            except NameError as e:
                print(f"❌ manage_sales_orders 函数导入失败: {e}")
                traceback.print_exc()
                return
            
            # 6. 测试模型查询
            print("\n6. 测试模型查询")
            try:
                count = SalesOrder.query.count()
                print(f"✅ SalesOrder 查询成功，记录数: {count}")
            except NameError as e:
                print(f"❌ SalesOrder 查询失败: {e}")
                traceback.print_exc()
                return
            
            # 7. 测试模板渲染相关
            print("\n7. 测试模板渲染相关")
            try:
                # 模拟模板中可能使用的变量
                orders = SalesOrder.query.all()
                for order in orders:
                    # 测试属性访问
                    _ = order.order_number
                    _ = order.customer
                    _ = order.order_items
                print("✅ 模板相关属性访问成功")
            except NameError as e:
                print(f"❌ 模板相关测试失败: {e}")
                traceback.print_exc()
                return
            
            # 8. 测试 Flask 应用上下文中的使用
            print("\n8. 测试 Flask 应用上下文中的使用")
            try:
                with app.test_request_context():
                    from flask import request
                    # 模拟在请求上下文中使用 SalesOrder
                    orders = SalesOrder.query.limit(1).all()
                    print("✅ 请求上下文中 SalesOrder 使用成功")
            except NameError as e:
                print(f"❌ 请求上下文中使用失败: {e}")
                traceback.print_exc()
                return
            
            print("\n🎉 所有诊断测试通过！")
            print("✅ 没有发现 'NameError: name SalesOrder is not defined' 问题")
            print("\n💡 如果您仍然遇到这个错误，可能的原因包括:")
            print("   1. 在特定的模板文件中使用了未定义的变量")
            print("   2. 在某个特定的路由函数中缺少导入")
            print("   3. 在 JavaScript 代码中引用了未定义的变量")
            print("   4. 在某个特定的表单处理过程中出现问题")
            print("\n🔧 建议:")
            print("   1. 检查具体出错的文件和行号")
            print("   2. 查看完整的错误堆栈跟踪")
            print("   3. 确认错误发生的具体操作步骤")
            
    except Exception as e:
        print(f"❌ 诊断过程中发生意外错误: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    diagnose_sales_order_issues() 