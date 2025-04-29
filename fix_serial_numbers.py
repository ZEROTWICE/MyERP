from app import create_app, db
from app.models import Employee, ProcessPrice, ProductionRecord, BonusPenalty, TaskAssignment, SerialNumber, RawMaterial, FinishedProduct
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

def fix_serial_numbers():
    app = create_app()
    with app.app_context():
        try:
            # 获取所有表中的最大序列号
            max_employee = db.session.query(db.func.max(Employee.global_sn)).scalar()
            max_process = db.session.query(db.func.max(ProcessPrice.global_sn)).scalar()
            max_production = db.session.query(db.func.max(ProductionRecord.global_sn)).scalar()
            max_bonus = db.session.query(db.func.max(BonusPenalty.global_sn)).scalar()
            max_task = db.session.query(db.func.max(TaskAssignment.global_sn)).scalar()
            max_raw_material = db.session.query(db.func.max(RawMaterial.global_sn)).scalar()
            max_finished_product = db.session.query(db.func.max(FinishedProduct.global_sn)).scalar()
            
            # 将所有序列号转换为整数进行比较
            max_numbers = []
            for x in [max_employee, max_process, max_production, max_bonus, max_task, max_raw_material, max_finished_product]:
                try:
                    max_numbers.append(int(x) if x else 0)
                except (ValueError, TypeError):
                    max_numbers.append(0)
            
            global_max = max(max_numbers)
            
            print(f"当前最大序列号: {global_max}")
            
            # 检查 serial_numbers 表是否存在记录
            serial = SerialNumber.query.first()
            if not serial:
                serial = SerialNumber(current_number=global_max)
                db.session.add(serial)
            else:
                serial.current_number = global_max
            
            db.session.commit()
            print("序列号已修复")
            
        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"数据库错误: {str(e)}")
        except Exception as e:
            print(f"发生错误: {str(e)}")

if __name__ == "__main__":
    fix_serial_numbers() 