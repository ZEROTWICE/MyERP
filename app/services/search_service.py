"""
搜索服务模块
提供全局搜索和高级搜索功能
"""

from typing import Dict, List, Any, Optional, Union
from sqlalchemy import or_, and_, func, desc
from datetime import datetime, date
from app import db
from app.models import (
    Employee, ProcessPrice, ProductionRecord, BonusPenalty,
    Product, ProductBOM, ProductProcess, ProductionOrder, 
    ProductionBatch, ProductionBatchItem, Customer, CustomerAddress,
    SalesOrder, SalesOrderItem, FinishedProduct, RawMaterial,
    MaterialAllocation, TaskAssignment, InspectionRecord,
    AuditLog, NotificationRule, Notification
)


class SearchService:
    """搜索服务类"""
    
    @staticmethod
    def global_search(query: str, search_type: str = 'all', page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """
        全局搜索功能
        
        Args:
            query: 搜索关键词
            search_type: 搜索类型 (all, employees, process_prices, etc.)
            page: 页码
            per_page: 每页数量
            
        Returns:
            包含搜索结果的字典
        """
        results = {}
        search_term = f"%{query}%"
        
        if search_type == 'all' or search_type == 'employees':
            results['employees'] = SearchService._search_employees(search_term, page, per_page)
            
        if search_type == 'all' or search_type == 'process_prices':
            results['process_prices'] = SearchService._search_process_prices(search_term, page, per_page)
            
        if search_type == 'all' or search_type == 'production_records':
            results['production_records'] = SearchService._search_production_records(search_term, page, per_page)
            
        if search_type == 'all' or search_type == 'products':
            results['products'] = SearchService._search_products(search_term, page, per_page)
            
        if search_type == 'all' or search_type == 'inventory':
            results['inventory'] = SearchService._search_inventory(search_term, page, per_page)
            
        if search_type == 'all' or search_type == 'customers':
            results['customers'] = SearchService._search_customers(search_term, page, per_page)
            
        if search_type == 'all' or search_type == 'sales_orders':
            results['sales_orders'] = SearchService._search_sales_orders(search_term, page, per_page)
            
        if search_type == 'all' or search_type == 'production_orders':
            results['production_orders'] = SearchService._search_production_orders(search_term, page, per_page)
        
        # 计算总结果数量
        total_count = sum(result.get('total', 0) for result in results.values())
        
        return {
            'results': results,
            'total_count': total_count,
            'query': query,
            'search_type': search_type,
            'page': page,
            'per_page': per_page
        }
    
    @staticmethod
    def _search_employees(search_term: str, page: int, per_page: int) -> Dict[str, Any]:
        """搜索员工"""
        query = Employee.query.filter(
            or_(
                Employee.name.like(search_term),
                Employee.employee_id.like(search_term),
                Employee.department.like(search_term),
                Employee.position.like(search_term)
            )
        ).order_by(Employee.id.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _search_process_prices(search_term: str, page: int, per_page: int) -> Dict[str, Any]:
        """搜索工序价格"""
        query = ProcessPrice.query.filter(
            or_(
                ProcessPrice.process_code.like(search_term),
                ProcessPrice.process_name.like(search_term),
                ProcessPrice.component.like(search_term),
                ProcessPrice.drawing_no.like(search_term),
                ProcessPrice.model_no.like(search_term),
                ProcessPrice.notes.like(search_term)
            )
        ).order_by(ProcessPrice.id.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _search_production_records(search_term: str, page: int, per_page: int) -> Dict[str, Any]:
        """搜索生产记录"""
        query = ProductionRecord.query.join(Employee).join(ProcessPrice).filter(
            or_(
                Employee.name.like(search_term),
                Employee.employee_id.like(search_term),
                ProcessPrice.process_name.like(search_term),
                ProcessPrice.process_code.like(search_term),
                ProductionRecord.notes.like(search_term)
            )
        ).order_by(ProductionRecord.date.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _search_products(search_term: str, page: int, per_page: int) -> Dict[str, Any]:
        """搜索产品"""
        query = Product.query.filter(
            or_(
                Product.product_code.like(search_term),
                Product.product_name.like(search_term),
                Product.drawing_number.like(search_term),
                Product.model.like(search_term),
                Product.specification.like(search_term),
                Product.category.like(search_term),
                Product.notes.like(search_term)
            )
        ).order_by(Product.id.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _search_inventory(search_term: str, page: int, per_page: int) -> Dict[str, Any]:
        """搜索库存（原材料和成品）"""
        # 搜索原材料
        raw_materials = RawMaterial.query.filter(
            or_(
                RawMaterial.supplier.like(search_term),
                RawMaterial.material_name.like(search_term),
                RawMaterial.melt_number.like(search_term),
                RawMaterial.supplier_number.like(search_term),
                RawMaterial.internal_number.like(search_term),
                RawMaterial.notes.like(search_term)
            )
        ).order_by(RawMaterial.id.desc()).limit(per_page//2).all()
        
        # 搜索成品
        finished_products = FinishedProduct.query.filter(
            or_(
                FinishedProduct.product_number.like(search_term),
                FinishedProduct.drawing_number.like(search_term),
                FinishedProduct.model.like(search_term),
                FinishedProduct.inspector.like(search_term),
                FinishedProduct.notes.like(search_term)
            )
        ).order_by(FinishedProduct.id.desc()).limit(per_page//2).all()
        
        # 合并结果
        items = []
        for rm in raw_materials:
            items.append({
                'type': 'raw_material',
                'item': rm,
                'display_name': f"原材料: {rm.material_name} ({rm.supplier})"
            })
        
        for fp in finished_products:
            items.append({
                'type': 'finished_product',
                'item': fp,
                'display_name': f"成品: {fp.product_number} ({fp.model})"
            })
        
        total = len(raw_materials) + len(finished_products)
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': 1
        }
    
    @staticmethod
    def _search_customers(search_term: str, page: int, per_page: int) -> Dict[str, Any]:
        """搜索客户"""
        query = Customer.query.filter(
            or_(
                Customer.customer_code.like(search_term),
                Customer.customer_name.like(search_term),
                Customer.contact_person.like(search_term),
                Customer.contact_phone.like(search_term),
                Customer.contact_email.like(search_term),
                Customer.tax_number.like(search_term),
                Customer.industry.like(search_term),
                Customer.notes.like(search_term)
            )
        ).order_by(Customer.id.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _search_sales_orders(search_term: str, page: int, per_page: int) -> Dict[str, Any]:
        """搜索销售订单"""
        query = SalesOrder.query.join(Customer).filter(
            or_(
                SalesOrder.order_number.like(search_term),
                SalesOrder.order_source.like(search_term),
                SalesOrder.year_month.like(search_term),
                Customer.customer_name.like(search_term),
                Customer.customer_code.like(search_term),
                SalesOrder.notes.like(search_term)
            )
        ).order_by(SalesOrder.id.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _search_production_orders(search_term: str, page: int, per_page: int) -> Dict[str, Any]:
        """搜索生产订单"""
        query = ProductionOrder.query.join(Product).filter(
            or_(
                ProductionOrder.order_number.like(search_term),
                Product.product_name.like(search_term),
                Product.product_code.like(search_term),
                Product.drawing_number.like(search_term),
                Product.model.like(search_term),
                ProductionOrder.notes.like(search_term)
            )
        ).order_by(ProductionOrder.id.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def advanced_search(search_params: Dict[str, Any], page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """
        高级搜索功能
        
        Args:
            search_params: 搜索参数字典
            page: 页码
            per_page: 每页数量
            
        Returns:
            搜索结果字典
        """
        results = {}
        
        # 员工高级搜索
        if any(search_params.get(field) for field in ['employee_name', 'employee_id', 'department', 'position', 'is_active']):
            results['employees'] = SearchService._advanced_search_employees(search_params, page, per_page)
        
        # 工序价格高级搜索
        if any(search_params.get(field) for field in ['process_code', 'process_name', 'component', 'drawing_no', 'model_no']):
            results['process_prices'] = SearchService._advanced_search_process_prices(search_params, page, per_page)
        
        # 生产记录高级搜索
        if any(search_params.get(field) for field in ['production_date_start', 'production_date_end']):
            results['production_records'] = SearchService._advanced_search_production_records(search_params, page, per_page)
        
        # 产品高级搜索
        if any(search_params.get(field) for field in ['product_code', 'product_name', 'drawing_number', 'model']):
            results['products'] = SearchService._advanced_search_products(search_params, page, per_page)
        
        # 库存高级搜索
        if any(search_params.get(field) for field in ['inventory_type', 'supplier', 'material_name', 'storage_date_start', 'storage_date_end']):
            results['inventory'] = SearchService._advanced_search_inventory(search_params, page, per_page)
        
        # 客户高级搜索
        if any(search_params.get(field) for field in ['customer_code', 'customer_name', 'contact_person', 'customer_type']):
            results['customers'] = SearchService._advanced_search_customers(search_params, page, per_page)
        
        # 销售订单高级搜索
        if any(search_params.get(field) for field in ['sales_order_number', 'order_source', 'year_month', 'order_status']):
            results['sales_orders'] = SearchService._advanced_search_sales_orders(search_params, page, per_page)
        
        # 生产订单高级搜索
        if any(search_params.get(field) for field in ['production_order_number', 'production_status', 'planned_start_date', 'planned_end_date']):
            results['production_orders'] = SearchService._advanced_search_production_orders(search_params, page, per_page)
        
        # 计算总结果数量
        total_count = sum(result.get('total', 0) for result in results.values())
        
        return {
            'results': results,
            'total_count': total_count,
            'search_params': search_params,
            'page': page,
            'per_page': per_page
        }
    
    @staticmethod
    def _advanced_search_employees(search_params: Dict[str, Any], page: int, per_page: int) -> Dict[str, Any]:
        """员工高级搜索"""
        query = Employee.query
        
        if search_params.get('employee_name'):
            query = query.filter(Employee.name.like(f"%{search_params['employee_name']}%"))
        
        if search_params.get('employee_id'):
            query = query.filter(Employee.employee_id.like(f"%{search_params['employee_id']}%"))
        
        if search_params.get('department'):
            query = query.filter(Employee.department.like(f"%{search_params['department']}%"))
        
        if search_params.get('position'):
            query = query.filter(Employee.position.like(f"%{search_params['position']}%"))
        
        if search_params.get('is_active'):
            is_active = search_params['is_active'] == '1'
            query = query.filter(Employee.is_active == is_active)
        
        query = query.order_by(Employee.id.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _advanced_search_process_prices(search_params: Dict[str, Any], page: int, per_page: int) -> Dict[str, Any]:
        """工序价格高级搜索"""
        query = ProcessPrice.query
        
        if search_params.get('process_code'):
            query = query.filter(ProcessPrice.process_code.like(f"%{search_params['process_code']}%"))
        
        if search_params.get('process_name'):
            query = query.filter(ProcessPrice.process_name.like(f"%{search_params['process_name']}%"))
        
        if search_params.get('component'):
            query = query.filter(ProcessPrice.component.like(f"%{search_params['component']}%"))
        
        if search_params.get('drawing_no'):
            query = query.filter(ProcessPrice.drawing_no.like(f"%{search_params['drawing_no']}%"))
        
        if search_params.get('model_no'):
            query = query.filter(ProcessPrice.model_no.like(f"%{search_params['model_no']}%"))
        
        query = query.order_by(ProcessPrice.id.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _advanced_search_production_records(search_params: Dict[str, Any], page: int, per_page: int) -> Dict[str, Any]:
        """生产记录高级搜索"""
        query = ProductionRecord.query
        
        if search_params.get('production_date_start'):
            query = query.filter(ProductionRecord.date >= search_params['production_date_start'])
        
        if search_params.get('production_date_end'):
            query = query.filter(ProductionRecord.date <= search_params['production_date_end'])
        
        query = query.order_by(ProductionRecord.date.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _advanced_search_products(search_params: Dict[str, Any], page: int, per_page: int) -> Dict[str, Any]:
        """产品高级搜索"""
        query = Product.query
        
        if search_params.get('product_code'):
            query = query.filter(Product.product_code.like(f"%{search_params['product_code']}%"))
        
        if search_params.get('product_name'):
            query = query.filter(Product.product_name.like(f"%{search_params['product_name']}%"))
        
        if search_params.get('drawing_number'):
            query = query.filter(Product.drawing_number.like(f"%{search_params['drawing_number']}%"))
        
        if search_params.get('model'):
            query = query.filter(Product.model.like(f"%{search_params['model']}%"))
        
        query = query.order_by(Product.id.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _advanced_search_inventory(search_params: Dict[str, Any], page: int, per_page: int) -> Dict[str, Any]:
        """库存高级搜索"""
        items = []
        total = 0
        
        inventory_type = search_params.get('inventory_type')
        
        # 搜索原材料
        if not inventory_type or inventory_type == 'raw':
            query = RawMaterial.query
            
            if search_params.get('supplier'):
                query = query.filter(RawMaterial.supplier.like(f"%{search_params['supplier']}%"))
            
            if search_params.get('material_name'):
                query = query.filter(RawMaterial.material_name.like(f"%{search_params['material_name']}%"))
            
            if search_params.get('storage_date_start'):
                query = query.filter(func.date(RawMaterial.storage_date) >= search_params['storage_date_start'])
            
            if search_params.get('storage_date_end'):
                query = query.filter(func.date(RawMaterial.storage_date) <= search_params['storage_date_end'])
            
            raw_materials = query.order_by(RawMaterial.id.desc()).limit(per_page//2).all()
            
            for rm in raw_materials:
                items.append({
                    'type': 'raw_material',
                    'item': rm,
                    'display_name': f"原材料: {rm.material_name} ({rm.supplier})"
                })
            
            total += len(raw_materials)
        
        # 搜索成品
        if not inventory_type or inventory_type == 'finished':
            query = FinishedProduct.query
            
            if search_params.get('storage_date_start'):
                query = query.filter(func.date(FinishedProduct.created_at) >= search_params['storage_date_start'])
            
            if search_params.get('storage_date_end'):
                query = query.filter(func.date(FinishedProduct.created_at) <= search_params['storage_date_end'])
            
            finished_products = query.order_by(FinishedProduct.id.desc()).limit(per_page//2).all()
            
            for fp in finished_products:
                items.append({
                    'type': 'finished_product',
                    'item': fp,
                    'display_name': f"成品: {fp.product_number} ({fp.model})"
                })
            
            total += len(finished_products)
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': 1
        }
    
    @staticmethod
    def _advanced_search_customers(search_params: Dict[str, Any], page: int, per_page: int) -> Dict[str, Any]:
        """客户高级搜索"""
        query = Customer.query
        
        if search_params.get('customer_code'):
            query = query.filter(Customer.customer_code.like(f"%{search_params['customer_code']}%"))
        
        if search_params.get('customer_name'):
            query = query.filter(Customer.customer_name.like(f"%{search_params['customer_name']}%"))
        
        if search_params.get('contact_person'):
            query = query.filter(Customer.contact_person.like(f"%{search_params['contact_person']}%"))
        
        if search_params.get('customer_type'):
            query = query.filter(Customer.customer_type == search_params['customer_type'])
        
        query = query.order_by(Customer.id.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _advanced_search_sales_orders(search_params: Dict[str, Any], page: int, per_page: int) -> Dict[str, Any]:
        """销售订单高级搜索"""
        query = SalesOrder.query
        
        if search_params.get('sales_order_number'):
            query = query.filter(SalesOrder.order_number.like(f"%{search_params['sales_order_number']}%"))
        
        if search_params.get('order_source'):
            query = query.filter(SalesOrder.order_source.like(f"%{search_params['order_source']}%"))
        
        if search_params.get('year_month'):
            query = query.filter(SalesOrder.year_month == search_params['year_month'])
        
        if search_params.get('order_status'):
            query = query.filter(SalesOrder.status == search_params['order_status'])
        
        query = query.order_by(SalesOrder.id.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def _advanced_search_production_orders(search_params: Dict[str, Any], page: int, per_page: int) -> Dict[str, Any]:
        """生产订单高级搜索"""
        query = ProductionOrder.query
        
        if search_params.get('production_order_number'):
            query = query.filter(ProductionOrder.order_number.like(f"%{search_params['production_order_number']}%"))
        
        if search_params.get('production_status'):
            query = query.filter(ProductionOrder.status == search_params['production_status'])
        
        if search_params.get('planned_start_date'):
            query = query.filter(ProductionOrder.planned_start_date >= search_params['planned_start_date'])
        
        if search_params.get('planned_end_date'):
            query = query.filter(ProductionOrder.planned_end_date <= search_params['planned_end_date'])
        
        query = query.order_by(ProductionOrder.id.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    
    @staticmethod
    def get_search_suggestions(query: str, limit: int = 10) -> Dict[str, List[str]]:
        """
        获取搜索建议
        
        Args:
            query: 搜索关键词
            limit: 建议数量限制
            
        Returns:
            各类别的搜索建议
        """
        search_term = f"%{query}%"
        suggestions = {}
        
        # 员工姓名建议
        employee_names = db.session.query(Employee.name).filter(
            Employee.name.like(search_term)
        ).distinct().limit(limit).all()
        suggestions['employee_names'] = [name[0] for name in employee_names]
        
        # 工序名称建议
        process_names = db.session.query(ProcessPrice.process_name).filter(
            ProcessPrice.process_name.like(search_term)
        ).distinct().limit(limit).all()
        suggestions['process_names'] = [name[0] for name in process_names]
        
        # 产品名称建议
        product_names = db.session.query(Product.product_name).filter(
            Product.product_name.like(search_term)
        ).distinct().limit(limit).all()
        suggestions['product_names'] = [name[0] for name in product_names]
        
        # 客户名称建议
        customer_names = db.session.query(Customer.customer_name).filter(
            Customer.customer_name.like(search_term)
        ).distinct().limit(limit).all()
        suggestions['customer_names'] = [name[0] for name in customer_names]
        
        return suggestions 