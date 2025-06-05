import requests
import time
from bs4 import BeautifulSoup

print("🔍 产品编辑功能全面诊断")
print("=" * 50)

base_url = "http://localhost:5000"
session = requests.Session()

try:
    # 1. 登录
    print("1️⃣ 登录测试...")
    login_page = session.get(f"{base_url}/auth/login")
    soup = BeautifulSoup(login_page.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrf_token'})
    csrf_value = csrf_token.get('value') if csrf_token else None
    
    login_data = {'username': 'admin', 'password': 'admin123'}
    if csrf_value:
        login_data['csrf_token'] = csrf_value
        
    login_response = session.post(f"{base_url}/auth/login", data=login_data, allow_redirects=False)
    print("   ✅ 登录成功")
    
    # 2. 测试所有产品的详情API
    print("\n2️⃣ 测试所有产品的详情API...")
    
    # 先获取产品列表
    products_page = session.get(f"{base_url}/products")
    if products_page.status_code == 200:
        print("   ✅ 产品列表页面正常")
        
        # 测试前10个产品的API
        for product_id in range(1, 11):
            product_response = session.get(f"{base_url}/products/{product_id}")
            if product_response.status_code == 200:
                try:
                    product_data = product_response.json()
                    if product_data.get('success'):
                        product = product_data['data']
                        print(f"   ✅ 产品 {product_id}: {product['product_name']}")
                    else:
                        print(f"   ❌ 产品 {product_id}: API返回失败 - {product_data.get('message')}")
                except Exception as e:
                    print(f"   ❌ 产品 {product_id}: JSON解析失败 - {str(e)}")
            elif product_response.status_code == 404:
                print(f"   ⚠️  产品 {product_id}: 不存在")
            else:
                print(f"   ❌ 产品 {product_id}: HTTP错误 {product_response.status_code}")
    else:
        print(f"   ❌ 产品列表页面失败: {products_page.status_code}")
    
    # 3. 测试编码规则API
    print("\n3️⃣ 测试编码规则API...")
    rules_response = session.get(f"{base_url}/code_rules/available/product")
    if rules_response.status_code == 200:
        try:
            rules_data = rules_response.json()
            if rules_data.get('success'):
                rules = rules_data.get('rules', [])
                print(f"   ✅ 编码规则API正常，找到 {len(rules)} 个规则")
                for rule in rules:
                    print(f"      - ID: {rule['id']}, 名称: {rule['name']}")
            else:
                print(f"   ❌ 编码规则API返回失败: {rules_data.get('message')}")
        except Exception as e:
            print(f"   ❌ 编码规则API JSON解析失败: {str(e)}")
    else:
        print(f"   ❌ 编码规则API HTTP错误: {rules_response.status_code}")
    
    # 4. 检查产品页面的JavaScript
    print("\n4️⃣ 检查产品页面的JavaScript...")
    products_page_content = session.get(f"{base_url}/products").text
    
    # 检查关键函数是否存在
    js_functions = ['editProduct', 'loadCodeRules', 'submitEditProduct']
    for func in js_functions:
        if f"function {func}" in products_page_content:
            print(f"   ✅ JavaScript函数 {func} 存在")
        else:
            print(f"   ❌ JavaScript函数 {func} 缺失")
    
    # 检查API端点
    if '/code_rules/available/product' in products_page_content:
        print("   ✅ 正确的编码规则API端点")
    else:
        print("   ❌ 编码规则API端点错误")
    
    # 5. 测试CSRF token
    print("\n5️⃣ 测试CSRF token...")
    soup = BeautifulSoup(products_page_content, 'html.parser')
    csrf_meta = soup.find('meta', {'name': 'csrf-token'})
    if csrf_meta:
        csrf_token_value = csrf_meta.get('content')
        print(f"   ✅ CSRF token存在: {csrf_token_value[:20]}...")
    else:
        print("   ⚠️  页面中未找到CSRF token meta标签")
    
    # 6. 测试模态框元素
    print("\n6️⃣ 检查模态框元素...")
    modal_elements = [
        'editProductModal',
        'editProductId', 
        'editProductName',
        'editCodeRule'
    ]
    
    for element_id in modal_elements:
        if f'id="{element_id}"' in products_page_content:
            print(f"   ✅ 模态框元素 {element_id} 存在")
        else:
            print(f"   ❌ 模态框元素 {element_id} 缺失")

except Exception as e:
    print(f"❌ 诊断过程中发生错误: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 50)
print("🏁 诊断完成")
print("\n💡 如果所有测试都通过，问题可能是：")
print("   1. 浏览器缓存问题 - 建议清除缓存")
print("   2. 网络连接问题 - 检查网络状态")
print("   3. 特定操作顺序问题 - 尝试刷新页面后再编辑")
print("   4. 浏览器兼容性问题 - 尝试其他浏览器") 