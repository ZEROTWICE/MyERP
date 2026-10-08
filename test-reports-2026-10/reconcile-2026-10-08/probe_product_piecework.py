# -*- coding: utf-8 -*-
"""t6（产品经理）现场复核探针 —— 只读源码 + 只写 app.db **副本**。

用途：为 recon-product.md 的 Q-2（返工默认不计件）补一条**产品口径**证据：
DEC-2 §2.5 要求 S1/S2/S3/S4 四个计件计算点**同口径**。既有探针
`probe_backend_field.py` 的 G 组只覆盖 **S1（共享函数本身）** 的 false/true 差分，
未覆盖 **S2（`Employee.total_salary`）/ S3（员工详情当日）/ S4（员工详情当月）**。
本探针补这三处，并断言：开关关 ⇒ 返工记录被剔除；开关开 ⇒ 计入；非返工记录两态不变。

纪律：
1. 数据全写 `scripts/_test_bootstrap.make_app()` 的 **app.db 副本**；真实库只读不写；
2. 不修改任何既有文件；本文件是本任务的新增产物；
3. 不跑 request 型脚本、不改仓库 `uploads/`。
"""
import json
import pathlib
import sys
from datetime import date, datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from _test_bootstrap import ensure_role_users, login_as, make_app  # noqa: E402

app, copy_path = make_app(fresh=True)
ensure_role_users(app)

from app import db  # noqa: E402
from app import models as M  # noqa: E402
from app.services import mes_service  # noqa: E402

OUT = {'copy_path': copy_path, 'tag': '_t6_' + datetime.now().strftime('%H%M%S')}
TAG = OUT['tag']


def jnum(x):
    try:
        return round(float(x), 4)
    except (TypeError, ValueError):
        return x


def set_switch(value):
    """写 `quality.rework_counts_piecework`（仅副本库）并读回。"""
    row = M.SystemConfig.query.filter_by(key='quality.rework_counts_piecework').first()
    if row is None:
        row = M.SystemConfig(key='quality.rework_counts_piecework', value='false',
                             value_type='bool', category='quality',
                             label='返工工时重复计件', description='探针新建')
        db.session.add(row)
    row.value = 'true' if value else 'false'
    db.session.commit()
    M.SystemConfig.invalidate_cache('quality.rework_counts_piecework')
    return M.SystemConfig.get('quality.rework_counts_piecework')


with app.app_context():
    # ---------------------------------------------------------- 夹具
    emp = M.Employee.query.first()
    if emp is None:
        raise SystemExit('副本库无员工，无法构造计件夹具')
    proc = M.ProcessPrice.query.first()
    if proc is None:
        raise SystemExit('副本库无工序价格，无法构造计件夹具')
    proc.price = 20.0
    db.session.commit()

    sn = M.SerialNumber.get_next_number()
    # 正常任务（非返工）
    t_normal = M.TaskAssignment(employee_id=emp.id, process_id=proc.id,
                                target_date=date(2026, 10, 8), quantity=3,
                                status='completed', task_type='normal',
                                global_sn=sn + 'N')
    db.session.add(t_normal)
    db.session.flush()
    r_normal = M.ProductionRecord(employee_id=emp.id, process_id=proc.id, quantity=3,
                                  global_sn=t_normal.global_sn, date=date(2026, 10, 8))
    db.session.add(r_normal)
    db.session.flush()
    # 返工任务（notes 前缀 + NC.rework_task_id 双给，验证「R1 主判据」而非 notes 单判）
    t_rework = M.TaskAssignment(employee_id=emp.id, process_id=proc.id,
                                target_date=date(2026, 10, 8), quantity=5,
                                status='completed', task_type='auto',
                                notes=f'返工 不合格单#_probe_{TAG}',
                                global_sn=sn + 'R')
    db.session.add(t_rework)
    db.session.flush()
    r_rework = M.ProductionRecord(employee_id=emp.id, process_id=proc.id, quantity=5,
                                  global_sn=t_rework.global_sn, date=date(2026, 10, 8))
    db.session.add(r_rework)
    db.session.flush()
    # `record_id` / `handler_id` / `handling_date` 在模型层非空 ⇒ 显式给足
    handler_id = mes_service.default_inspector_id()
    nc = M.NonconformityRecord(record_id=None, type='rework', status='open',
                               handler_id=handler_id, handling_date=date.today(),
                               workpiece_id=None, target_type='workpiece', target_id=None,
                               rework_task_id=t_rework.id,
                               handling_result='待处置', notes='探针夹具')
    nc.record_id = r_rework.id
    db.session.add(nc)
    db.session.commit()

    OUT['fixture'] = {
        'employee_id': emp.id, 'employee_code': emp.employee_id,
        'coefficient': jnum(emp.coefficient), 'base_salary': jnum(emp.base_salary),
        'process_id': proc.id, 'process_price': jnum(proc.price),
        'normal_record': {'id': r_normal.id, 'quantity': r_normal.quantity,
                          'global_sn': r_normal.global_sn},
        'rework_record': {'id': r_rework.id, 'quantity': r_rework.quantity,
                          'global_sn': r_rework.global_sn},
        'rework_task': {'id': t_rework.id, 'notes': t_rework.notes},
        'nc_id': nc.id,
        'R1R2_identified': sorted(mes_service.rework_production_record_ids(
            [r_normal, r_rework])),
        'R3_hint_only': mes_service.rework_hint(t_rework),
    }

    # --------------------------------------------------- S2: Employee.total_salary
    def s2_salary():
        db.session.expire_all()
        e = M.Employee.query.get(emp.id)
        return jnum(e.total_salary)

    # ------------------------------------------- S3/S4: 员工详情「当日/当月工资」
    def s3_s4():
        """复算 routes.py:398-412 的两条式子（同式同源，只读共享函数）。"""
        from app.services.mes_service import piecework_amount
        today = date.today()
        month_start = date(today.year, today.month, 1)
        daily = M.ProductionRecord.query.filter_by(employee_id=emp.id, date=today).all()
        monthly = M.ProductionRecord.query.filter(
            M.ProductionRecord.employee_id == emp.id,
            M.ProductionRecord.date >= month_start).all()
        return jnum(piecework_amount(daily) * emp.coefficient), \
            jnum(piecework_amount(monthly) * emp.coefficient)

    # 基线：让两条记录都落在「今天」以便 S3 能取到（复制日期）
    r_normal.date = date.today()
    r_rework.date = date.today()
    db.session.commit()

    res = {}
    snapshots = []

    def snapshot(switch):
        sw = set_switch(switch)
        s1 = jnum(mes_service.piecework_amount([r_normal, r_rework]))
        s2 = s2_salary()
        s3, s4 = s3_s4()
        snap = {'switch_readback': sw, 'S1_shared_amount': s1, 'S2_total_salary': s2,
                'S3_daily': s3, 'S4_monthly': s4}
        snapshots.append(snap)
        return snap

    off = snapshot(False)
    on = snapshot(True)
    res['off'] = off
    res['on'] = on

    # 非返工记录的贡献两态必须相等（阴性对照 AC-27）
    off_nonrework = jnum(mes_service.piecework_amount([r_normal]))
    set_switch(True)
    on_nonrework = jnum(mes_service.piecework_amount([r_normal]))

    OUT['criteria'] = {
        'expected_nonrework': jnum(r_normal.quantity * proc.price),
        'expected_rework': jnum(r_rework.quantity * proc.price),
        'readings': res,
        'nonrework_off': off_nonrework,
        'nonrework_on': on_nonrework,
    }
    # 判据（含阴性对照）
    OUT['verdict'] = {
        'switch_readback_off': off['switch_readback'] is False,
        'switch_readback_on': on['switch_readback'] is True,
        'S1_delta_ne_0': off['S1_shared_amount'] != on['S1_shared_amount'],
        'S2_delta_ne_0': off['S2_total_salary'] != on['S2_total_salary'],
        'S3_delta_ne_0': off['S3_daily'] != on['S3_daily'],
        'S4_delta_ne_0': off['S4_monthly'] != on['S4_monthly'],
        'nonrework_unchanged': off_nonrework == on_nonrework,
    }

# 复位开关为默认 false（仅副本库，仍显式确认）
with app.app_context():
    OUT['switch_left_at'] = set_switch(False)

p = pathlib.Path(__file__).with_suffix('.output.json')
p.write_text(json.dumps(OUT, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps(OUT, ensure_ascii=False, indent=1))
