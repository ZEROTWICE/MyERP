#!/usr/bin/env python3
"""
客户管理功能测试脚本
"""

import requests
import json
from datetime import datetime

# 测试配置
BASE_URL = "http://127.0.0.1:5000"
session = requests.Session()

def login():
    """登录系统"""
    print("🔐 正在登录系统...")
    
    # 获取登录页面的CSRF token
    login_page = session.get(f"{BASE_URL}/auth/login")
    if login_page.status_code != 200:
        print(f"❌ 无法访问登录页面: {login_page.status_code}")
        return False
    
    # 登录
    login_data = {
        'username': 'admin',
        'password': 'admin123',
        'submit': 'Sign In'
    }
    
    response = session.post(f"{BASE_URL}/auth/login", data=login_data)
    if response.status_code == 200 and "客户管理" in response.text:
        print("✅ 登录成功")
        return True
    else:
        print(f"❌ 登录失败: {response.status_code}")
        return False

def test_customer_list():
    """测试客户列表页面"""
    print("\n📋 测试客户列表页面...")
    
    response = session.get(f"{BASE_URL}/customers")
    if response.status_code == 200:
        print("✅ 客户列表页面访问成功")
        if "客户管理" in response.text and "新增客户" in response.text:
            print("✅ 页面内容正确")
            return True
        else:
            print("❌ 页面内容不正确")
            return False
    else:
        print(f"❌ 客户列表页面访问失败: {response.status_code}")
        return False

def test_add_customer():
    """测试新增客户"""
    print("\n➕ 测试新增客户...")
    
    # 获取新增客户页面
    response = session.get(f"{BASE_URL}/customer/add")
    if response.status_code != 200:
        print(f"❌ 无法访问新增客户页面: {response.status_code}")
        return False
    
    # 提取CSRF token
    csrf_token = None
    for line in response.text.split('\n'):
        if 'csrf_token' in line and 'value=' in line:
            csrf_token = line.split('value="')[1].split('"')[0]
            break
    
    if not csrf_token:
        print("❌ 无法获取CSRF token")
        return False
    
    # 新增客户数据
    customer_data = {
        'csrf_token': csrf_token,
        'customer_code': f'TEST{datetime.now().strftime("%Y%m%d%H%M%S")}',
        'customer_name': '测试客户有限公司',
        'customer_type': 'enterprise',
        'contact_person': '张三',
        'contact_phone': '13800138000',
        'contact_email': 'test@example.com',
        'tax_number': '91110000000000000X',
        'credit_limit': '100000',
        'payment_terms': '月结30天',
        'industry': '制造业',
        'company_size': 'medium',
        'website': 'https://www.example.com',
        'status': 'active',
        'notes': '这是一个测试客户',
        'submit': '保存'
    }
    
    response = session.post(f"{BASE_URL}/customer/add", data=customer_data)
    if response.status_code == 200:
        if "客户新增成功" in response.text or "客户详情" in response.text:
            print("✅ 客户新增成功")
            return True
        else:
            print("❌ 客户新增失败")
            return False
    else:
        print(f"❌ 客户新增请求失败: {response.status_code}")
        return False

def test_customer_search_api():
    """测试客户搜索API"""
    print("\n🔍 测试客户搜索API...")
    
    response = session.get(f"{BASE_URL}/api/customers/search?search=测试")
    if response.status_code == 200:
        try:
            data = response.json()
            if data.get('success'):
                print(f"✅ 客户搜索API成功，找到 {len(data.get('data', []))} 个客户")
                return True
            else:
                print(f"❌ 客户搜索API返回失败: {data.get('message', '未知错误')}")
                return False
        except json.JSONDecodeError:
            print("❌ 客户搜索API返回格式错误")
            return False
    else:
        print(f"❌ 客户搜索API请求失败: {response.status_code}")
        return False

def test_customer_detail():
    """测试客户详情页面"""
    print("\n👁️ 测试客户详情页面...")
    
    # 先获取客户列表找到一个客户ID
    response = session.get(f"{BASE_URL}/customers")
    if response.status_code != 200:
        print("❌ 无法获取客户列表")
        return False
    
    # 简单的方式：尝试访问客户ID为1的详情页面
    response = session.get(f"{BASE_URL}/customer/1")
    if response.status_code == 200:
        if "客户详情" in response.text and "基本信息" in response.text:
            print("✅ 客户详情页面访问成功")
            return True
        else:
            print("❌ 客户详情页面内容不正确")
            return False
    elif response.status_code == 404:
        print("ℹ️ 客户不存在（正常情况）")
        return True
    else:
        print(f"❌ 客户详情页面访问失败: {response.status_code}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始测试客户管理功能")
    print("=" * 50)
    
    # 登录
    if not login():
        print("\n❌ 测试失败：无法登录")
        return
    
    # 测试各个功能
    tests = [
        ("客户列表页面", test_customer_list),
        ("新增客户", test_add_customer),
        ("客户搜索API", test_customer_search_api),
        ("客户详情页面", test_customer_detail),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} 测试失败")
        except Exception as e:
            print(f"❌ {test_name} 测试出错: {str(e)}")
    
    print("\n" + "=" * 50)
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！客户管理功能正常工作")
    else:
        print("⚠️ 部分测试失败，请检查相关功能")

if __name__ == "__main__":
    main() 