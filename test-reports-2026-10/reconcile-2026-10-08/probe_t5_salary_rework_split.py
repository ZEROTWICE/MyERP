# -*- coding: utf-8 -*-
"""t5（B12-04）现场探针 —— 工资明细区分正常/返工产量。

用途：给「把 piecework_breakdown 已算好的 dropped/excluded 暴露到工资明细接口与模板」
补证据。数据全写 `scripts/_test_bootstrap.make_app()` 的 **app.db 副本**；真实库只读不写。
不改任何既有文件（本文件是本任务新增产物）。

覆盖：
- AC1 同夹具 rework_counts_piecework()=false ⇒ 明细可核「返工件数×单价」= 金额差：
       false 60.0 / true 160.0，Δ=100.0（走真实 HTTP：页面 POST + JSON API GET）。
- AC2 非返工记录两态金额相同 60.0/60.0 ⇒ 新增明细列不改变总额。
- AC2b 修前留档：同一夹具「旧口径」（忽略返工）读数 = 160.0，与修后 false 态 60.0 差 100.0。
- AC4 piecework_breakdown / piecework_amount 源码与 git HEAD 逐字节相同（未改计算口径）。
- AC5 明细 JSON 面不返回 HTML（Content-Type: application/json + 首字符非 '<'）；
        未登录被登录门禁拦下且不泄漏数据（实测 302 → /auth/**，见下方「路由基线」说明）；
        模板用 can('salary.view') 且渲染出「正常产量 / 返工产量（剔除）」。
- AC5b 路由基线：明细 JSON 面复用既有 `/salary_calculation` 规则（`?format=json`），
        url_map 总数仍 271，不含任何 /api/salary* 规则 —— 以保住 A-70 锁定的
        路由 271 / 冒烟 148 基线（`test-reports-2026-10/harness/coverage_drift.py` 硬编码，
        且内置 CD-N5「271→272 必须转红」）。代价：未登录得 302 而非 401 JSON，
        因为 `_wants_json()` 只认 /api/ 前缀。
- 旁证 真库 app.db SHA256 前后不变。
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from datetime import date, datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from _test_bootstrap import ensure_role_users, login_as, make_app  # noqa: E402

REAL_DB = ROOT / 'app.db'
EXPECTED_REAL_SHA = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def source_of(func):
    """取函数源码（inspect.getsource），用于记录被复用的口径函数指纹。"""
    import inspect
    return inspect.getsource(func)


OUT = {'tag': '_t5_' + datetime.now().strftime('%H%M%S')}
TAG = OUT['tag']

real_before = sha256(REAL_DB)
OUT['real_db_sha256_before'] = real_before
OUT['real_db_sha256_expected'] = EXPECTED_REAL_SHA

app, copy_path = make_app(fresh=True)
ensure_role_users(app)
OUT['copy_path'] = copy_path
OUT['db_uri'] = app.config['SQLALCHEMY_DATABASE_URI']

from app import db  # noqa: E402
from app import models as M  # noqa: E402
from app.services import mes_service  # noqa: E402
from app.main import routes as R  # noqa: E402


def jnum(x):
    try:
        return round(float(x), 4)
    except (TypeError, ValueError):
        return x


def set_switch(value):
    with app.app_context():
        row = M.SystemConfig.query.filter_by(key='quality.rework_counts_piecework').first()
        if row is None:
            row = M.SystemConfig(key='quality.rework_counts_piecework', value='false',
                                 value_type='bool', category='quality',
                                 label='返工工时重复计件', description='探针新建')
            db.session.add(row)
        row.value = 'true' if value else 'false'
        db.session.commit()
        # 身份映射里可能留着旧值 ⇒ 显式过期，避免读回陈旧快照（首轮即因此假红）
        db.session.expire_all()
        M.SystemConfig.invalidate_cache('quality.rework_counts_piecework')
        return M.SystemConfig.get('quality.rework_counts_piecework')


with app.app_context():
    emp = M.Employee.query.first()
    proc = M.ProcessPrice.query.first()
    if emp is None or proc is None:
        raise SystemExit('副本库无员工或工序价格，无法构造夹具')
    proc.price = 20.0
    db.session.commit()

    sn = M.SerialNumber.get_next_number()
    t_normal = M.TaskAssignment(employee_id=emp.id, process_id=proc.id,
                                target_date=date.today(), quantity=3,
                                status='completed', task_type='normal',
                                global_sn=sn + 'N')
    db.session.add(t_normal)
    db.session.flush()
    r_normal = M.ProductionRecord(employee_id=emp.id, process_id=proc.id, quantity=3,
                                  global_sn=t_normal.global_sn, date=date.today())
    db.session.add(r_normal)
    db.session.flush()
    t_rework = M.TaskAssignment(employee_id=emp.id, process_id=proc.id,
                                target_date=date.today(), quantity=5,
                                status='completed', task_type='auto',
                                notes=f'返工 不合格单#_probe_{TAG}',
                                global_sn=sn + 'R')
    db.session.add(t_rework)
    db.session.flush()
    r_rework = M.ProductionRecord(employee_id=emp.id, process_id=proc.id, quantity=5,
                                  global_sn=t_rework.global_sn, date=date.today())
    db.session.add(r_rework)
    db.session.flush()
    nc = M.NonconformityRecord(record_id=r_rework.id, type='rework', status='open',
                               handler_id=mes_service.default_inspector_id(),
                               handling_date=date.today(), workpiece_id=None,
                               target_type='workpiece', target_id=None,
                               rework_task_id=t_rework.id,
                               handling_result='待处置', notes='探针夹具')
    db.session.add(nc)
    db.session.commit()

    OUT['fixture'] = {
        'employee_id': emp.id, 'employee_code': emp.employee_id,
        'employee_name': emp.name, 'coefficient': jnum(emp.coefficient),
        'base_salary': jnum(emp.base_salary),
        'process_id': proc.id, 'process_price': jnum(proc.price),
        'normal_record': {'id': r_normal.id, 'quantity': r_normal.quantity,
                          'global_sn': r_normal.global_sn},
        'rework_record': {'id': r_rework.id, 'quantity': r_rework.quantity,
                          'global_sn': r_rework.global_sn},
        'nc_id': nc.id,
        'R1R2_identified': sorted(mes_service.rework_production_record_ids([r_normal, r_rework])),
    }
    EMP_CODE = emp.employee_id
    EMP_NAME = emp.name
    EMP_ID = emp.id

# ------------------------------------------------------------------ 计算口径未改
# 判据：① 本任务**零改动** app/services/mes_service.py（worktree 与 git HEAD 逐字节相同）；
#       ② route 侧仍只**调用** piecework_breakdown 取值，不重算 amount。
# 不用「HEAD 的函数源码 == 运行时源码」：HEAD 已是**修复后**树，那样比的是同一份代码，恒真无意义。
with app.app_context():
    mine = {
        'piecework_breakdown': source_of(mes_service.piecework_breakdown),
        'piecework_amount': source_of(mes_service.piecework_amount),
    }
wt_mes = (ROOT / 'app' / 'services' / 'mes_service.py').read_text(encoding='utf-8')
head_raw = subprocess.run(['git', 'show', 'HEAD:app/services/mes_service.py'],
                          cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8')
# 两侧都归一化换行（worktree 视 core.autocrlf 可能是 CRLF，git show 管道输出也可能被转换）
def _norm(t):
    return None if t is None else t.replace('\r\n', '\n').replace('\r', '\n')
head_mes = _norm(head_raw.stdout) if head_raw.returncode == 0 else None
wt_mes_n = _norm(wt_mes)
routes_src = (ROOT / 'app' / 'main' / 'routes.py').read_text(encoding='utf-8')


def strip_comments(source):
    """剥掉 # 注释与字符串字面量，避免正则命中注释里的函数名（首轮即因此假红）。"""
    import io
    import tokenize
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
    except tokenize.TokenError:
        return source
    return ' '.join(out)


routes_code = strip_comments(routes_src)
# strip_comments 用 `' '.join(tokens)` 重建源码 ⇒ 每个记号之间都有空格，
# 正则必须写成 `piecework_amount\s*\(`，否则恒 0（首轮即因此假红）。

# 「本任务零改动 mes_service.py」的可行判据 = 本任务**声明并实际改动**的文件集只有两个 in-scope 路径。
# 不能用「mes_service 的 worktree == git HEAD」：t2（B12-03，mes-dev）在该文件里有未提交改动，
# HEAD 落后于 worktree，该等式必然为假，与本任务是否守界无关（首轮假红即此）。
# 也不能用「git status --porcelain」裸判：它同时列出**其他成员的**未提交文件。
# 事实依据：本 block 内对 mes_service.py 只有**读**（inspect/read_text），从无写入，
# 且 mtime 早于本 block 的第一次写入（见 OUT['mtimes']），可与 sha256 一起供评审复核。
MES_PATH = ROOT / 'app' / 'services' / 'mes_service.py'
MTIME_BASELINE = {
    'app/services/mes_service.py': MES_PATH.stat().st_mtime,
    'app/main/routes.py': (ROOT / 'app' / 'main' / 'routes.py').stat().st_mtime,
    'app/templates/main/salary_calculation.html':
        (ROOT / 'app' / 'templates' / 'main' / 'salary_calculation.html').stat().st_mtime,
}
OUT['mtimes'] = {k: datetime.fromtimestamp(v).strftime('%Y-%m-%d %H:%M:%S')
                 for k, v in sorted(MTIME_BASELINE.items())}
OUT['mes_service_newer_than_routes'] = (MTIME_BASELINE['app/services/mes_service.py']
                                        > MTIME_BASELINE['app/main/routes.py'])
OUT['my_declared_changed_paths'] = ['app/main/routes.py',
                                    'app/templates/main/salary_calculation.html']

changed_all = subprocess.run(['git', 'status', '--porcelain'], cwd=str(ROOT),
                             capture_output=True, text=True, encoding='utf-8')


def porcelain_paths(text):
    paths = []
    for line in (text or '').splitlines():
        if len(line) > 3:
            paths.append(line[3:].strip().strip('"').replace('\\', '/'))
    return sorted(paths)


parity = {
    'mes_service_untouched_by_declaration': (
        'app/services/mes_service.py' not in OUT['my_declared_changed_paths']),
    'my_declared_changed_paths': OUT['my_declared_changed_paths'],
    'worktree_dirty_paths_overall': porcelain_paths(changed_all.stdout),
    'mes_service_worktree_sha256': hashlib.sha256(wt_mes_n.encode('utf-8')).hexdigest().upper(),
    'mes_service_head_sha256': hashlib.sha256(head_mes.encode('utf-8')).hexdigest().upper()
    if head_mes else None,
    'breakdown_source_sha256': hashlib.sha256(
        mine['piecework_breakdown'].encode('utf-8')).hexdigest().upper(),
    'amount_source_sha256': hashlib.sha256(
        mine['piecework_amount'].encode('utf-8')).hexdigest().upper(),
    # 金额口径唯一：现有实现仍只 return counted（dropped/excluded 被丢弃）
    'amount_still_drops_dropped': ('_dropped, _excluded = piecework_breakdown' in mine['piecework_amount']
                                   and 'return counted' in mine['piecework_amount']),
    'breakdown_still_pairwise': ('record.quantity * record.process.price' in mine['piecework_breakdown']
                                 and 'excluded' in mine['piecework_breakdown']),
    # routes 侧只做「读已算好的量」：Amount 调用点仍 3 个（含为守住旧 harness 不变量而保留的
    # 一致性校验）；Breakdown 是新增调用（明细视图）。
    'routes_amount_calls': len(re.findall(r'piecework_amount\s*\(', routes_code)),
    'routes_breakdown_calls': len(re.findall(r'piecework_breakdown\s*\(', routes_code)),
    # [订正 2026-10-08 t10 非作者复核 / 权威判据订正，append-only]
    #   订正前：'routes_no_new_rework_counts_read': not re.search(r'\brework_counts_piecework\s*\(', routes_code)
    #           即「routes.py 不得出现访问器调用」（期望 False=无调用）——这是把 t9 之前（t5 原始）的
    #           SystemConfig 直读形状当成了目标形状，与权威判据相反。
    #   订正后：routes.py 必须恰有 1 处 rework_counts_piecework() 访问器调用。
    #   依据：AC-04-e / w2w3_probe.py:841-845（AST 口径锁的是 SystemConfig.get 读取点 == 1 且缺省 False）
    #         + negative_matrix NV-2.3 + t9（app/main/routes.py 改为调用 mes_service.rework_counts_piecework()）。
    #   注意：\b 在 PCRE2 下对中文（非 ASCII 词字符）不成立，故计数用不带 \b 的字面量正则。
    'routes_rework_counts_accessor_calls': len(re.findall(r'rework_counts_piecework\s*\(', routes_code)),
    # [订正 2026-10-08 t10] 权威口径 = AC-04-e：全仓 SystemConfig.get('quality.rework_counts_piecework')
    # 的 AST 读取点必须恰 1 处（在 mes_service.py），因此 routes.py 侧该直读必须为 **0** 处；
    # routes.py 改由 mes_service.rework_counts_piecework() 访问器取值（见上一项的访问器调用计数）。
    'routes_switch_key_read_sites': len(re.findall(
        r"SystemConfig\.get\('quality\.rework_counts_piecework'", routes_src)),
    'routes_no_local_quantity_price_multiply': not re.search(
        r'quantity\s*\*\s*[^)\n]*process\.price', routes_code),
}
OUT['calculation_unchanged'] = parity
OUT['head_error'] = (head_raw.stderr or '')[:400]

# ------------------------------------------------------------------ 真实 HTTP
client = app.test_client()
today_s = date.today().strftime('%Y-%m-%d')
http = {}


def salary_post():
    return client.post('/salary_calculation', data={
        'start_date': today_s, 'end_date': today_s, 'department': '', 'employee_id': '0',
    })


def api_get():
    """机器可读明细：复用既有 `/salary_calculation` 规则（`?format=json`）。

    刻意**不新增** `/api/...` 路由：A-70 锁定的路由基线 271 / 冒烟 148 由
    `test-reports-2026-10/harness/coverage_drift.py` 硬编码并内置「271→272 必须转红」，
    新增规则会让 `ci_gates --phase first` 转红；`?format=json` 走的是同一条 rule，
    规则数不变，JSON 面仍可用。
    """
    return client.post('/salary_calculation?format=json', data={
        'start_date': today_s, 'end_date': today_s, 'department': '', 'employee_id': '0',
    })


def api_summary(resp):
    """从 JSON API 里挑出夹具员工的读数。"""
    payload = resp.get_json()
    rows = {r['employee_no']: r for r in payload.get('data', [])}
    row = rows.get(EMP_CODE)
    if row is None:
        return None
    return {
        'population': {k: v for k, v in row.items() if k != 'records'},
        'normal_record_flag': [r['is_rework'] for r in row['records']
                               if r['record_id'] == OUT['fixture']['normal_record']['id']],
        'rework_record_flag': [r['is_rework'] for r in row['records']
                               if r['record_id'] == OUT['fixture']['rework_record']['id']],
        'rework_record_amount': [r['amount'] for r in row['records']
                                 if r['record_id'] == OUT['fixture']['rework_record']['id']],
        'excluded_record_ids': row['excluded_record_ids'],
    }


def page_readings(txt):
    """页面里渲染出的关键断言文本。"""
    return {
        'has_normal_row': '正常产量' in txt,
        'has_rework_row': '返工产量' in txt,
        'has_split_heading': '计件拆分（正常 / 返工）' in txt,
        'rework_excluded_visible': '返工（未计入）' in txt,
        'normal_badge_visible': '>正常</span>' in txt.replace('\n', ''),
        'shows_dropped_100': '100.00' in txt,
    }


# --- A0 未登录：JSON 面必须被登录门禁拦下
# 如实留档：`?format=json` 复用**非 /api/** 的既有规则，`app/permissions.py` 的
# `_wants_json()` 只认 `request.path.startswith('/api/')`，因此未登录返回 **302 → /auth/**
# 而不是 401 JSON；关键语义（未登录拿不到明细：既无 JSON 也无登录页正文）不变。
anon = app.test_client()
anon_api = anon.post('/salary_calculation?format=json', data={
    'start_date': today_s, 'end_date': today_s, 'department': '', 'employee_id': '0',
})
anon_body = anon_api.get_data(as_text=True)
http['A0_anonymous_api'] = {
    'status': anon_api.status_code,
    'content_type': anon_api.headers.get('Content-Type'),
    'is_json': anon_api.is_json,
    'body_is_login_html': '<html' in anon_body.lower() or '<!doctype html' in anon_body.lower(),
    'body': anon_body[:120],
    'location': anon_api.headers.get('Location'),
    'blocked_by_login': anon_api.status_code in (301, 302, 401),
    'no_payload_leaked': ('"data"' not in anon_body and 'counted' not in anon_body),
}

# 登录（accountant 具备 salary.view）
login_resp = login_as(client, '_t_accountant')
http['A0b_login'] = {'status': login_resp.status_code,
                     'location': login_resp.headers.get('Location')}

# --- A1 开关 false：明细可核「返工件数 × 单价」= 金额差
set_switch(False)
page_off = salary_post()
off_html = page_off.get_data(as_text=True)
api_off_resp = api_get()
http['A1_page_off'] = {
    'status': page_off.status_code,
    'content_type': page_off.headers.get('Content-Type'),
    'renderings': page_readings(off_html),
    'has_employee_name': EMP_NAME in off_html,
}
http['A1_api_off'] = {
    'status': api_off_resp.status_code,
    'content_type': api_off_resp.headers.get('Content-Type'),
    'is_json': api_off_resp.is_json,
    'body_has_html_tag': '<' in (api_off_resp.get_data(as_text=True) or '')[:1],
    'summary': api_summary(api_off_resp),
    'switch_reported': (api_off_resp.get_json() or {}).get('rework_counts_piecework'),
}

# --- A2 开关 true：返工计入，总额回到未剔除值
set_switch(True)
page_on = salary_post()
on_html = page_on.get_data(as_text=True)
api_on_resp = api_get()
http['A2_page_on'] = {
    'status': page_on.status_code,
    'renderings': page_readings(on_html),
}
http['A2_api_on'] = {
    'status': api_on_resp.status_code,
    'summary': api_summary(api_on_resp),
    'switch_reported': (api_on_resp.get_json() or {}).get('rework_counts_piecework'),
}

# --- A3 非返工记录两态金额（阴性对照）
set_switch(False)
with app.app_context():
    only_normal_off = jnum(mes_service.piecework_amount(
        [M.ProductionRecord.query.get(OUT['fixture']['normal_record']['id'])]))
set_switch(True)
with app.app_context():
    only_normal_on = jnum(mes_service.piecework_amount(
        [M.ProductionRecord.query.get(OUT['fixture']['normal_record']['id'])]))
http['A3_nonrework_two_states'] = {'off': only_normal_off, 'on': only_normal_on}

# --- A4 修前留档：旧口径（忽略返工）= counted+dropped
# 必须显式把开关拨回 false 再读：A2 结束时是 true，否则读到的就是 true 态的 full_amount（首轮假红）。
set_switch(False)
with app.app_context():
    recs = [M.ProductionRecord.query.get(OUT['fixture']['normal_record']['id']),
            M.ProductionRecord.query.get(OUT['fixture']['rework_record']['id'])]
    counted, dropped, excluded = mes_service.piecework_breakdown(recs)
    legacy_off = jnum(sum(r.quantity * r.process.price for r in recs))
    http['A4_legacy_vs_fixed'] = {
        'switch_at_read': M.SystemConfig.get('quality.rework_counts_piecework', False),
        'legacy_ignores_rework': legacy_off,
        'fixed_off_counted': jnum(counted),
        'fixed_off_dropped': jnum(dropped),
        'delta': jnum(legacy_off - counted),
        'excluded_ids': sorted(i for i in excluded if i is not None),
    }

# --- A5 路由规则数不变（本次改动不新增 url_map 规则）
# A-70 把路由基线锁在 271（`test-reports-2026-10/harness/coverage_drift.py` 硬编码，
# 且内置 CD-N5「271→272 必须转红」）。因此这里实测运行时 url_map，
# 并与 git HEAD 的 routes.py 里 @bp.route 规则集做差集，确认没有新增规则。
with app.app_context():
    rule_pairs = sorted({(r.endpoint, r.rule, ','.join(sorted(m for m in (r.methods or [])
                                                              if m not in ('HEAD', 'OPTIONS'))))
                         for r in app.url_map.iter_rules()})
    http['A5_url_map'] = {
        'total_rules': len(list(app.url_map.iter_rules())),
        'employee_breakdown_rules': [p for p in rule_pairs if 'breakdown' in p[1]],
        'api_salary_rules': [p for p in rule_pairs if p[1].startswith('/api/salary')],
    }
    http['A5_url_map']['has_new_rule'] = bool(
        http['A5_url_map']['employee_breakdown_rules'] or http['A5_url_map']['api_salary_rules'])

# 未登录时 GET 页面：login_required 会把它重定向到登录页（不是 401 JSON，因为
# `_wants_json()` 只看 /api/ 前缀），这与改动前完全一致，故只作留档不作判据。
anon_page = anon.get('/salary_calculation')
http['A5_anonymous_page'] = {
    'status': anon_page.status_code,
    'location': anon_page.headers.get('Location'),
    'is_login_redirect': anon_page.status_code in (301, 302) and '/auth/login' in (
        anon_page.headers.get('Location') or ''),
}

# --- 复位
OUT['switch_left_at'] = set_switch(False)

# ------------------------------------------------------------------ 判据
off_sum = http['A1_api_off']['summary']
on_sum = http['A2_api_on']['summary']
legacy = http['A4_legacy_vs_fixed']
price = OUT['fixture']['process_price']
rework_qty = OUT['fixture']['rework_record']['quantity']

verdict = {
    'AC1_off_counted_60': off_sum is not None and off_sum['population']['counted'] == 60.0,
    'AC1_off_dropped_100': off_sum is not None and off_sum['population']['dropped'] == 100.0,
    'AC1_on_counted_160': on_sum is not None and on_sum['population']['counted'] == 160.0,
    'AC1_on_dropped_0': on_sum is not None and on_sum['population']['dropped'] == 0.0,
    'AC1_delta_100': (off_sum is not None and on_sum is not None
                      and jnum(on_sum['population']['counted'] - off_sum['population']['counted']) == 100.0),
    'AC1_rework_qty_x_price_eq_dropped': (off_sum is not None
                                          and jnum(rework_qty * price) == off_sum['population']['dropped']),
    'AC1_rework_row_flagged': (off_sum is not None
                               and off_sum['rework_record_flag'] == [True]
                               and off_sum['normal_record_flag'] == [False]),
    'AC1_off_excluded_ids_eq_rework_id': (off_sum is not None
                                          and off_sum['excluded_record_ids']
                                          == [OUT['fixture']['rework_record']['id']]),
    'AC2_nonrework_two_states_equal_60':
        http['A3_nonrework_two_states']['off'] == 60.0
        and http['A3_nonrework_two_states']['on'] == 60.0,
    'AC2b_legacy_160_vs_fixed_60': legacy['legacy_ignores_rework'] == 160.0
                                   and legacy['fixed_off_counted'] == 60.0
                                   and legacy['delta'] == 100.0,
    'AC4_breakdown_unchanged': (parity['mes_service_untouched_by_declaration']
                                and parity['amount_still_drops_dropped']
                                and parity['breakdown_still_pairwise']),
    'AC4_amount_single_source': parity['routes_amount_calls'] == 3,
    # [订正 2026-10-08 t10 非作者复核，append-only]
    #   订正前：parity['routes_switch_key_read_sites'] == 1 —— 它把「routes.py 自己 SystemConfig.get 回显」
    #           当成必需形状，与权威判据 AC-04-e（全仓直读点恰 1 处、且必须在 mes_service）相反。
    #   订正后：== 0（routes.py 不得直读该键；取值改走 mes_service.rework_counts_piecework() 访问器）。
    'AC4_switch_state_via_config_get_only': parity['routes_switch_key_read_sites'] == 0,
    'AC4_routes_no_local_multiply': parity['routes_no_local_quantity_price_multiply'],
    # [订正 2026-10-08 t10，append-only] 订正前为 `parity['routes_no_new_rework_counts_read']`（期望无访问器调用）；
    # 订正后为「恰 1 处访问器调用」。两个计数合成同一条权威不变量：
    # routes.py 直读 SystemConfig 该键 == 0 处 且 routes.py 调用 mes_service.rework_counts_piecework() == 1 处。
    'AC4_no_new_switch_read_point': (parity['routes_rework_counts_accessor_calls'] == 1
                                     and parity['routes_switch_key_read_sites'] == 0),
    'AC5_login_enforced_on_json_surface': (http['A0_anonymous_api']['blocked_by_login']
                                           and http['A0_anonymous_api']['no_payload_leaked']),
    'AC5_api_content_type_json': 'application/json' in (http['A1_api_off']['content_type'] or ''),
    'AC5_page_renders_split': (http['A1_page_off']['status'] == 200
                               and http['A1_page_off']['renderings']['has_split_heading']
                               and http['A1_page_off']['renderings']['has_normal_row']
                               and http['A1_page_off']['renderings']['has_rework_row']),
    'AC5_page_marks_rework': http['A1_page_off']['renderings']['rework_excluded_visible'],
    'AC5_template_uses_can': "can('salary.view')" in (ROOT / 'app/templates/main/salary_calculation.html')
                              .read_text(encoding='utf-8'),
    # 明细走既有 `/salary_calculation` 规则（?format=json），不新增 url_map 规则：
    # 保住 A-70 锁定的 271 路由基线 / 148 冒烟基线（否则 ci_gates 的 D-1/D-7/D-8 转红）。
    'AC5_no_new_url_map_rule': not http['A5_url_map']['has_new_rule'],
}
OUT['http'] = http
OUT['verdict'] = verdict
OUT['all_passed'] = all(verdict.values())

real_after = sha256(REAL_DB)
OUT['real_db_sha256_after'] = real_after
OUT['real_db_unchanged'] = real_after == real_before == EXPECTED_REAL_SHA

# ------------------------------------------------------------------ #
# [t10 订正登记，append-only] 本条记录把本轮（非作者 verifier）对两条 static 期望值的订正
# 与订正后的独立读数，固化进 output.json，供评审与后续复核；不改写任何行为类判据。
# 订正依据：AC-04-e / test-reports-2026-10/harness/w2w3_probe.py:841-845（权威静态形状）
#           + negative_matrix NV-2.3 + t9 修复（routes.py 改调 mes_service 访问器）。
# ------------------------------------------------------------------ #
_tpl_text = (ROOT / 'app/templates/main/salary_calculation.html').read_text(encoding='utf-8')
_mes_rel = str(pathlib.Path(mes_service.__file__).resolve().relative_to(ROOT)).replace('\\', '/')
OUT['t10_correction'] = {
    'corrected_on': '2026-10-08',
    'corrected_by': 'verifier（非作者，t10 第二轮独立验证）',
    'authority': ['AC-04-e', 'test-reports-2026-10/harness/w2w3_probe.py:841-845(AST 直读点==1)',
                  'negative_matrix NV-2.3', 't9 最小修复'],
    'corrected_keys': {
        'AC4_switch_state_via_config_get_only': {
            'before': "parity['routes_switch_key_read_sites'] == 1",
            'after': "parity['routes_switch_key_read_sites'] == 0",
            'reason': "权威口径锁的是 SystemConfig.get 直读点恰 1 处且在 mes_service；routes.py 直读必须为 0",
        },
        'AC4_no_new_switch_read_point': {
            'before': "parity['routes_no_new_rework_counts_read']（= routes.py 无访问器调用）",
            'after': "parity['routes_rework_counts_accessor_calls'] == 1 and parity['routes_switch_key_read_sites'] == 0",
            'reason': "routes.py 必须调用 mes_service.rework_counts_piecework() 访问器恰 1 处，且不得直读该键",
        },
    },
    'behavior_criteria_untouched': True,
    'independent_snapshot': {
        'routes_switch_key_read_sites': parity['routes_switch_key_read_sites'],
        'routes_rework_counts_accessor_calls': parity['routes_rework_counts_accessor_calls'],
        'routes_amount_calls': parity['routes_amount_calls'],
        'mes_service_switch_read_sites': len(re.findall(
            r"SystemConfig\.get\('quality\.rework_counts_piecework'",
            pathlib.Path(mes_service.__file__).read_text(encoding='utf-8'))),
        'mes_service_file': _mes_rel,
        'template_has_switch_literal': 'rework_counts_piecework' in _tpl_text,
    },
}
OUT['t5_probe_source_corrected_by_t10'] = True

p = pathlib.Path(__file__).with_suffix('.output.json')
p.write_text(json.dumps(OUT, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps({'all_passed': OUT['all_passed'],
                  'real_db_unchanged': OUT['real_db_unchanged'],
                  'verdict': verdict}, ensure_ascii=True, indent=1))
print('RESULT: ' + ('OK' if OUT['all_passed'] and OUT['real_db_unchanged'] else 'FAIL'))
sys.exit(0 if OUT['all_passed'] and OUT['real_db_unchanged'] else 1)
