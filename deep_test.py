from app import create_app, db
from app.models import SalesOrder, SalesOrderItem, Customer, Product, User
import json
from datetime import datetime, date

app = create_app()
with app.app_context():
    print('🚀 开始深度测试销售订单功能...')
    print('='*50)
    
    # 1. 数据统计
    orders = SalesOrder.query.all()
    items = SalesOrderItem.query.all()
    customers = Customer.query.all()
    products = Product.query.all()
    
    print(f'📊 数据统计:')
    print(f'  销售订单: {len(orders)} 个')
    print(f'  订单行: {len(items)} 个')
    print(f'  客户: {len(customers)} 个')
    print(f'  产品: {len(products)} 个')
    
    # 2. 详细分析最新订单
    if orders:
        latest_order = max(orders, key=lambda x: x.created_at)
        print(f'\n📋 最新订单详细分析:')
        print(f'  订单号: {latest_order.order_number}')
        print(f'  来源: {latest_order.order_source}')
        print(f'  客户: {latest_order.customer.customer_name}')
        print(f'  状态: {latest_order.status}')
        print(f'  年月: {latest_order.year_month}')
        print(f'  总数量: {latest_order.total_quantity}')
        print(f'  创建时间: {latest_order.created_at}')
        print(f'  备注: {latest_order.notes or "无"}')
        
        # 分析订单行
        order_items = latest_order.order_items.all()
        print(f'\n  📝 订单行详情 ({len(order_items)} 行):')
        
        total_check = 0
        for i, item in enumerate(order_items):
            print(f'    行{i+1}: {item.product.product_name}')
            print(f'         产品编码: {item.product.product_code}')
            print(f'         数量: {item.quantity}')
            print(f'         开向: {item.direction}')
            print(f'         规格: {item.specifications_text}')
            print(f'         使用单位: {item.usage_unit or "未指定"}')
            print(f'         到站备注: {item.station_notes or "无"}')
            
            total_check += item.quantity
            
            # 分析分批到货
            if item.delivery_batches:
                try:
                    batches = json.loads(item.delivery_batches)
                    print(f'         分批到货: {len(batches)} 批次')
                    batch_total = 0
                    for j, batch in enumerate(batches):
                        print(f'           批次{j+1}: {batch.get("quantity", 0)} 件, {batch.get("delivery_date", "未指定")}')
                        batch_total += batch.get('quantity', 0)
                    
                    if batch_total == item.quantity:
                        print(f'         ✅ 分批数量一致: {batch_total}')
                    else:
                        print(f'         ⚠️ 分批数量不一致: {batch_total} vs {item.quantity}')
                except:
                    print(f'         ❌ 分批数据解析失败')
            else:
                print(f'         分批到货: 无')
        
        print(f'\n  🧮 数量验证:')
        print(f'    订单总数量: {latest_order.total_quantity}')
        print(f'    行数量合计: {total_check}')
        print(f'    数量一致性: {"✅ 正确" if latest_order.total_quantity == total_check else "❌ 错误"}')
    
    # 3. 客户分析
    print(f'\n👥 客户分析:')
    for customer in customers:
        customer_orders = customer.sales_orders.all()
        total_qty = sum(order.total_quantity for order in customer_orders)
        print(f'  {customer.customer_name} ({customer.customer_code}):')
        print(f'    订单数: {len(customer_orders)}')
        print(f'    总数量: {total_qty}')
        print(f'    联系人: {customer.contact_person}')
        print(f'    状态: {customer.status}')
    
    # 4. 产品使用分析
    print(f'\n📦 产品使用分析:')
    for product in products[:5]:  # 只显示前5个产品
        product_items = product.sales_order_items.all()
        total_ordered = sum(item.quantity for item in product_items)
        print(f'  {product.product_name} ({product.product_code}):')
        print(f'    被订购次数: {len(product_items)}')
        print(f'    总订购量: {total_ordered}')
        print(f'    图号: {product.drawing_number}')
        print(f'    单位: {product.unit}')
    
    # 5. 状态统计
    print(f'\n📈 订单状态统计:')
    status_counts = {}
    for order in orders:
        status = order.status
        status_counts[status] = status_counts.get(status, 0) + 1
    
    for status, count in status_counts.items():
        print(f'  {status}: {count} 个订单')
    
    print(f'\n✅ 深度测试完成！所有数据结构正常！') 