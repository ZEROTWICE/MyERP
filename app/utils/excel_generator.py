from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from datetime import datetime

class ExcelGenerator:
    @staticmethod
    def _apply_header_style(cell):
        """应用表头样式"""
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

    @staticmethod
    def _apply_cell_style(cell):
        """应用单元格样式"""
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

    @staticmethod
    def create_employee_template():
        """创建员工导入模板"""
        wb = Workbook()
        ws = wb.active
        ws.title = "员工信息"
        
        # 设置表头
        headers = ['工号*', '姓名*', '职位*', '部门*', '基本工资*', '系数*', '入职时间*', '离职时间']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)
            
        # 添加说明行
        ws.cell(row=2, column=1, value='EMP001')
        ws.cell(row=2, column=2, value='张三')
        ws.cell(row=2, column=3, value='技术员')
        ws.cell(row=2, column=4, value='生产部')
        ws.cell(row=2, column=5, value=5000)
        ws.cell(row=2, column=6, value=1.0)
        ws.cell(row=2, column=7, value='2024-01-01')
        ws.cell(row=2, column=8, value='')
        
        # 添加格式说明
        ws.cell(row=4, column=1, value='说明：')
        ws.cell(row=5, column=1, value='入职时间格式：YYYY-MM-DD（必填）')
        ws.cell(row=6, column=1, value='离职时间格式：YYYY-MM-DD（可选，留空表示在职）')
        ws.cell(row=7, column=1, value='带*号的字段为必填项')
        
        # 调整列宽
        for col in ws.columns:
            max_length = 0
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col[0].column_letter].width = max_length + 2
        
        return wb

    @staticmethod
    def create_process_price_template():
        """创建工序价格导入模板"""
        wb = Workbook()
        ws = wb.active
        ws.title = "工序价格"
        
        # 设置表头
        headers = ['工序编号*', '工序名称*', '部件', '图号', '型号', '单价*', '生效日期*', '备注', '价格类型*', '包含工序']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)
            
        # 添加说明行
        ws.cell(row=2, column=1, value='P001')
        ws.cell(row=2, column=2, value='车削')
        ws.cell(row=2, column=3, value='轴承')
        ws.cell(row=2, column=4, value='DWG001')
        ws.cell(row=2, column=5, value='M001')
        ws.cell(row=2, column=6, value=10.5)
        ws.cell(row=2, column=7, value='2024-01-01')
        ws.cell(row=2, column=8, value='标准工序')
        ws.cell(row=2, column=9, value='normal')
        ws.cell(row=2, column=10, value='')
        
        ws.cell(row=3, column=1, value='P002')
        ws.cell(row=3, column=2, value='小计工序')
        ws.cell(row=3, column=3, value='轴承')
        ws.cell(row=3, column=4, value='DWG002')
        ws.cell(row=3, column=5, value='M002')
        ws.cell(row=3, column=6, value='') # 小计会自动计算
        ws.cell(row=3, column=7, value='2024-01-01')
        ws.cell(row=3, column=8, value='小计工序')
        ws.cell(row=3, column=9, value='subtotal')
        ws.cell(row=3, column=10, value='P001,P003') # 指定要包含的工序编号，用逗号分隔
        
        # 添加说明
        ws.cell(row=5, column=1, value='说明')
        ws.cell(row=6, column=1, value='价格类型')
        ws.cell(row=6, column=2, value='normal - 普通工价；subtotal - 小计')
        ws.cell(row=7, column=1, value='包含工序')
        ws.cell(row=7, column=2, value='当价格类型为subtotal时，填写包含的工序编号，用逗号分隔。小计价格将自动计算为包含工序价格的总和。')
        
        # 调整列宽
        for col in ws.columns:
            max_length = 0
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col[0].column_letter].width = max_length + 2
        
        return wb

    @staticmethod
    def create_production_record_template():
        """创建生产记录导入模板"""
        wb = Workbook()
        ws = wb.active
        ws.title = "生产记录"
        
        # 设置表头
        headers = ['日期*', '员工工号*', '工序编号*', '数量*']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)
            
        # 添加说明行
        ws.cell(row=2, column=1, value='2024-01-01')
        ws.cell(row=2, column=2, value='EMP001')
        ws.cell(row=2, column=3, value='P001')
        ws.cell(row=2, column=4, value=100)
        
        # 调整列宽
        for col in ws.columns:
            max_length = 0
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col[0].column_letter].width = max_length + 2
        
        return wb

    @staticmethod
    def create_bonus_penalty_template():
        """创建奖惩记录导入模板"""
        wb = Workbook()
        ws = wb.active
        ws.title = "奖惩记录"
        
        # 设置表头
        headers = ['日期*', '员工工号*', '类型*', '金额*', '工序编号', '原因']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)
            
        # 添加说明行
        ws.cell(row=2, column=1, value='2024-01-01')
        ws.cell(row=2, column=2, value='EMP001')
        ws.cell(row=2, column=3, value='bonus')  # 或 penalty
        ws.cell(row=2, column=4, value=100)
        ws.cell(row=2, column=5, value='P001')  # 可选
        ws.cell(row=2, column=6, value='优秀表现奖励')
        
        # 调整列宽
        for col in ws.columns:
            max_length = 0
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col[0].column_letter].width = max_length + 2
        
        return wb

    @staticmethod
    def create_task_template():
        """创建任务导入模板"""
        wb = Workbook()
        ws = wb.active
        ws.title = "任务分配"
        
        # 设置表头
        headers = ['员工工号*', '工序编号*', '数量*', '目标日期*', '备注']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)
            
        # 添加说明行
        ws.cell(row=2, column=1, value='EMP001')
        ws.cell(row=2, column=2, value='P001')
        ws.cell(row=2, column=3, value=100)
        ws.cell(row=2, column=4, value='2024-01-31')
        ws.cell(row=2, column=5, value='紧急任务')
        
        # 调整列宽
        for col in ws.columns:
            max_length = 0
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col[0].column_letter].width = max_length + 2
        
        return wb

    @staticmethod
    def parse_employee_data(file_path):
        """解析员工导入数据"""
        from openpyxl import load_workbook
        from datetime import datetime, date
        
        wb = load_workbook(file_path)
        ws = wb.active
        data = []
        
        for row_num, row in enumerate(ws.iter_rows(min_row=2), start=2):  # 跳过表头
            if not any(cell.value for cell in row):  # 跳过空行
                continue
                
            # 跳过说明行（从第4行开始的说明）
            if row_num >= 4 and row[0].value and str(row[0].value).startswith('说明'):
                continue
                
            try:
                # 处理入职时间
                hire_date_value = row[6].value if len(row) > 6 else None
                hire_date = None
                if hire_date_value:
                    if isinstance(hire_date_value, date):
                        hire_date = hire_date_value
                    elif isinstance(hire_date_value, str):
                        hire_date = datetime.strptime(hire_date_value.strip(), '%Y-%m-%d').date()
                
                # 处理离职时间
                termination_date_value = row[7].value if len(row) > 7 else None
                termination_date = None
                if termination_date_value:
                    if isinstance(termination_date_value, date):
                        termination_date = termination_date_value
                    elif isinstance(termination_date_value, str) and termination_date_value.strip():
                        termination_date = datetime.strptime(termination_date_value.strip(), '%Y-%m-%d').date()
                
                data.append({
                    'employee_id': str(row[0].value).strip(),
                    'name': str(row[1].value).strip(),
                    'position': str(row[2].value).strip(),
                    'department': str(row[3].value).strip(),
                    'base_salary': float(row[4].value),
                    'coefficient': float(row[5].value),
                    'hire_date': hire_date,
                    'termination_date': termination_date
                })
            except (ValueError, IndexError, TypeError) as e:
                # 记录解析错误，但继续处理其他行
                print(f"第{row_num}行数据解析失败: {e}")
                continue
        
        return data

    @staticmethod
    def parse_process_price_data(file_path):
        """解析工序价格导入数据"""
        from openpyxl import load_workbook
        wb = load_workbook(file_path)
        ws = wb.active
        data = []
        
        for row in ws.iter_rows(min_row=2):  # 跳过表头
            if not any(cell.value for cell in row):  # 跳过空行
                continue
            
            # 检查行中是否有足够的单元格
            if len(row) < 9:
                continue
            
            price_type = 'normal'
            included_processes = []
            
            # 获取价格类型
            if len(row) >= 9 and row[8].value:
                price_type = str(row[8].value).strip().lower()
                if price_type not in ['normal', 'subtotal']:
                    price_type = 'normal'
            
            # 获取包含工序
            if price_type == 'subtotal' and len(row) >= 10 and row[9].value:
                included_processes = [code.strip() for code in str(row[9].value).split(',') if code.strip()]
            
            data.append({
                'process_code': str(row[0].value).strip(),
                'process_name': str(row[1].value).strip(),
                'component': str(row[2].value).strip() if row[2].value else None,
                'drawing_no': str(row[3].value).strip() if row[3].value else None,
                'model_no': str(row[4].value).strip() if row[4].value else None,
                'price': float(row[5].value) if row[5].value else 0,
                'effective_date': row[6].value,
                'notes': str(row[7].value).strip() if row[7].value else None,
                'price_type': price_type,
                'included_processes': included_processes
            })
        
        return data

    @staticmethod
    def parse_production_record_data(file_path):
        """解析生产记录导入数据"""
        from openpyxl import load_workbook
        wb = load_workbook(file_path)
        ws = wb.active
        data = []
        
        for row in ws.iter_rows(min_row=2):  # 跳过表头
            if not any(cell.value for cell in row):  # 跳过空行
                continue
            data.append({
                'date': row[0].value,
                'employee_id': str(row[1].value).strip(),
                'process_code': str(row[2].value).strip(),
                'quantity': int(row[3].value)
            })
        
        return data

    @staticmethod
    def parse_bonus_penalty_data(file_path):
        """解析奖惩记录导入数据"""
        from openpyxl import load_workbook
        wb = load_workbook(file_path)
        ws = wb.active
        data = []
        
        for row in ws.iter_rows(min_row=2):  # 跳过表头
            if not any(cell.value for cell in row):  # 跳过空行
                continue
            data.append({
                'date': row[0].value,
                'employee_id': str(row[1].value).strip(),
                'type': str(row[2].value).strip(),
                'amount': float(row[3].value),
                'process_code': str(row[4].value).strip() if row[4].value else None,
                'reason': str(row[5].value).strip() if row[5].value else None
            })
        
        return data

    @staticmethod
    def parse_task_data(file_path):
        """解析任务导入数据"""
        from openpyxl import load_workbook
        wb = load_workbook(file_path)
        ws = wb.active
        data = []
        
        for row in ws.iter_rows(min_row=2):  # 跳过表头
            if not any(cell.value for cell in row):  # 跳过空行
                continue
            data.append({
                'employee_id': str(row[0].value).strip(),
                'process_code': str(row[1].value).strip(),
                'quantity': int(row[2].value),
                'target_date': row[3].value,
                'notes': str(row[4].value).strip() if row[4].value else None
            })
        
        return data

    @staticmethod
    def export_employees(employees):
        """导出员工信息"""
        wb = Workbook()
        ws = wb.active
        ws.title = "员工信息"

        # 设置表头
        headers = ['工号', '姓名', '职位', '部门', '基本工资', '系数', '入职时间', '离职时间', '状态', '是否管理员']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)

        # 写入数据
        for row, employee in enumerate(employees, 2):
            ws.cell(row=row, column=1, value=employee.employee_id)
            ws.cell(row=row, column=2, value=employee.name)
            ws.cell(row=row, column=3, value=employee.position)
            ws.cell(row=row, column=4, value=employee.department)
            ws.cell(row=row, column=5, value=employee.base_salary)
            ws.cell(row=row, column=6, value=employee.coefficient)
            ws.cell(row=row, column=7, value=employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else '')
            ws.cell(row=row, column=8, value=employee.termination_date.strftime('%Y-%m-%d') if employee.termination_date else '')
            ws.cell(row=row, column=9, value=employee.status)
            ws.cell(row=row, column=10, value='是' if employee.user and employee.user.role == 'admin' else '否')

        # 调整列宽
        for col in ws.columns:
            max_length = 0
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col[0].column_letter].width = max_length + 2

        return wb

    @staticmethod
    def export_process_prices(process_prices):
        """导出工序价格"""
        wb = Workbook()
        ws = wb.active
        ws.title = "工序价格"

        # 设置表头
        headers = ['工序编号', '工序名称', '部件', '图号', '型号', '单价', '生效日期', '备注', '价格类型', '包含工序']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)

        # 写入数据
        for row, process in enumerate(process_prices, 2):
            ws.cell(row=row, column=1, value=process.process_code)
            ws.cell(row=row, column=2, value=process.process_name)
            ws.cell(row=row, column=3, value=process.component)
            ws.cell(row=row, column=4, value=process.drawing_no)
            ws.cell(row=row, column=5, value=process.model_no)
            ws.cell(row=row, column=6, value=process.price)
            ws.cell(row=row, column=7, value=process.effective_date.strftime('%Y-%m-%d'))
            ws.cell(row=row, column=8, value=process.notes)
            ws.cell(row=row, column=9, value=process.price_type)
            
            # 如果是小计，添加包含的工序
            if process.price_type == 'subtotal':
                included_process_codes = []
                for group in ProcessPriceGroup.query.filter_by(subtotal_id=process.id).all():
                    included_process = ProcessPrice.query.get(group.process_id)
                    if included_process:
                        included_process_codes.append(included_process.process_code)
                ws.cell(row=row, column=10, value=','.join(included_process_codes))

        # 调整列宽
        for col in ws.columns:
            max_length = 0
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col[0].column_letter].width = max_length + 2

        return wb

    @staticmethod
    def export_production_records(records):
        """导出生产记录"""
        wb = Workbook()
        ws = wb.active
        ws.title = "生产记录"

        # 设置表头
        headers = ['日期', '员工工号', '员工姓名', '工序编号', '工序名称', '部件', '图号', '型号', '数量']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)

        # 写入数据
        for row, record in enumerate(records, 2):
            ws.cell(row=row, column=1, value=record.date.strftime('%Y-%m-%d'))
            ws.cell(row=row, column=2, value=record.employee.employee_id)
            ws.cell(row=row, column=3, value=record.employee.name)
            ws.cell(row=row, column=4, value=record.process.process_code)
            ws.cell(row=row, column=5, value=record.process.process_name)
            ws.cell(row=row, column=6, value=record.process.component)
            ws.cell(row=row, column=7, value=record.process.drawing_no)
            ws.cell(row=row, column=8, value=record.process.model_no)
            ws.cell(row=row, column=9, value=record.quantity)

        # 调整列宽
        for col in ws.columns:
            max_length = 0
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col[0].column_letter].width = max_length + 2

        return wb

    @staticmethod
    def export_bonus_penalties(records):
        """导出奖惩记录"""
        wb = Workbook()
        ws = wb.active
        ws.title = "奖惩记录"

        # 设置表头
        headers = ['日期', '员工工号', '员工姓名', '类型', '金额', '工序编号', '原因']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)

        # 写入数据
        for row, record in enumerate(records, 2):
            ws.cell(row=row, column=1, value=record.date.strftime('%Y-%m-%d'))
            ws.cell(row=row, column=2, value=record.employee.employee_id)
            ws.cell(row=row, column=3, value=record.employee.name)
            ws.cell(row=row, column=4, value='奖金' if record.type == 'bonus' else '罚款')
            ws.cell(row=row, column=5, value=record.amount)
            ws.cell(row=row, column=6, value=record.process.process_code if record.process else '')
            ws.cell(row=row, column=7, value=record.reason)

        # 调整列宽
        for col in ws.columns:
            max_length = 0
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col[0].column_letter].width = max_length + 2

        return wb

    @staticmethod
    def export_tasks(tasks):
        """导出任务记录"""
        wb = Workbook()
        ws = wb.active
        ws.title = "任务记录"

        # 设置表头
        headers = ['任务编号', '员工工号', '员工姓名', '工序编号', '工序名称', '数量', '目标日期', '状态', '分配日期', '完成日期', '备注']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)

        # 写入数据
        for row, task in enumerate(tasks, 2):
            ws.cell(row=row, column=1, value=task.id)
            ws.cell(row=row, column=2, value=task.employee.employee_id)
            ws.cell(row=row, column=3, value=task.employee.name)
            ws.cell(row=row, column=4, value=task.process.process_code)
            ws.cell(row=row, column=5, value=task.process.process_name)
            ws.cell(row=row, column=6, value=task.quantity)
            ws.cell(row=row, column=7, value=task.target_date.strftime('%Y-%m-%d'))
            ws.cell(row=row, column=8, value=task.status)
            ws.cell(row=row, column=9, value=task.assignment_date.strftime('%Y-%m-%d'))
            ws.cell(row=row, column=10, value=task.completion_date.strftime('%Y-%m-%d') if task.completion_date else '')
            ws.cell(row=row, column=11, value=task.notes)

        # 调整列宽
        for col in ws.columns:
            max_length = 0
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            ws.column_dimensions[col[0].column_letter].width = max_length + 2

        return wb

    @staticmethod
    def add_headers(wb, headers):
        """添加表头"""
        ws = wb.active
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            ExcelGenerator._apply_header_style(cell)
        return ws

    @staticmethod
    def add_row(ws, row_data, row_number=None):
        """添加数据行"""
        if row_number is None:
            row_number = ws.max_row + 1
        
        for col, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_number, column=col, value=value)
            ExcelGenerator._apply_cell_style(cell)

    @staticmethod
    def generate_response(wb, filename):
        """生成Excel响应"""
        from io import BytesIO
        from flask import send_file
        
        # 保存到内存
        excel_file = BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)
        
        # 返回文件
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        ) 