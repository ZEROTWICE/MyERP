"""单列回归检查：/products/import 表单层契约（阶段C 在册项 O9）。

背景：`ProductImportForm.file` 原为 `MultipleFileField`（`data` 是 list）且缺 `update_existing`
字段，而路由 `app/main/routes.py:import_products` 把 `form.file.data` 当 FileStorage 用
（读 `.filename`）、并读 `form.update_existing.data` ⇒ 真实表单 POST 恒走外层 except
（`B17-登记.md:187` 在案）。本脚本断言修后行为，并把旧形态装回去做阴性对照，证明本检查对缺陷敏感。

跑法（仓库根）：/opt/wage-venv/bin/python -B test-reports-2026-10/harness/check_products_import_form.py
"""
import io
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from _test_bootstrap import make_app, ensure_role_users, login_as  # noqa: E402
from openpyxl import Workbook  # noqa: E402

H = ['产品编码', '产品名称', '图号', '型号', '规格', '单位', '类别', '版本', '状态', '编码规则', '备注']
results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(f'{"PASS" if cond else "FAIL"}  {name}  {detail}')


def build_xlsx(code, name):
    wb = Workbook()
    ws = wb.active
    ws.title = '产品信息'   # parse_product_data 只认这个 sheet 名（默认 'Sheet' ⇒ 0 行 0 错）
    ws.append(H)
    ws.append([code, name, 'D-01', 'M-01', 'S1', '件', '测试', '1.0', 'active', '', ''])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def post(client, code, name, update_existing):
    return client.post('/products/import',
                       data={'file': (build_xlsx(code, name), 'e.xlsx'),
                             'update_existing': update_existing},
                       content_type='multipart/form-data')


app, db_path = make_app(fresh=True)
ensure_role_users(app)
client = app.test_client()
login_as(client, '_t_admin')

from app import db  # noqa: E402
import app.main.routes as R  # noqa: E402
from app.models import Product  # noqa: E402

TEMP = app.config['TEMP_FOLDER']

# ---------- A：合法单文件 ⇒ 入库 ----------
resp = post(client, 'E-O9-A', 'O9 产品A', '')
body = resp.get_json(silent=True) or {}
check('A.status_200', resp.status_code == 200, f'status={resp.status_code}')
check('A.success_true', body.get('success') is True, f'body={str(body)[:200]}')
check('A.imported_1', body.get('imported_count') == 1, f'imported={body.get("imported_count")}')
with app.app_context():
    rows = Product.query.filter_by(product_code='E-O9-A').count()
check('A.row_in_db', rows == 1, f'rows={rows}')

# ---------- B：已存在编码 + update_existing='1' ⇒ 更新分支（修前此处 AttributeError） ----------
resp = post(client, 'E-O9-A', 'O9 产品A改', '1')
body = resp.get_json(silent=True) or {}
check('B.success_true', body.get('success') is True, f'body={str(body)[:200]}')
check('B.updated_1', body.get('updated_count') == 1, f'updated={body.get("updated_count")}')
with app.app_context():
    p = Product.query.filter_by(product_code='E-O9-A').first()
    check('B.name_updated', p is not None and p.product_name == 'O9 产品A改',
          f'name={getattr(p, "product_name", None)!r}')

# ---------- C：临时目录无 mkdtemp 残留 ----------
check('C.no_temp_leftover', sorted(os.listdir(TEMP)) == [], f'entries={sorted(os.listdir(TEMP))}')

# ---------- D：未选文件 ⇒ 友好失败（不 500） ----------
resp = client.post('/products/import', data={'update_existing': ''},
                   content_type='multipart/form-data')
body = resp.get_json(silent=True) or {}
check('D.no_file_handled', resp.status_code == 200 and body.get('success') is False,
      f'status={resp.status_code} body={str(body)[:120]}')
check('D.message_ok', ('表单验证失败' in (body.get('message') or ''))
      or ('请选择有效的Excel文件' in (body.get('message') or '')),
      f'msg={body.get("message")!r}')

# ---------- E：阴性对照（旧形态必须失败） ----------
from wtforms import MultipleFileField  # noqa: E402
from wtforms.validators import DataRequired  # noqa: E402


class _LegacyProductImportForm(R.ProductImportForm):
    """修前形态：MultipleFileField（data 是 list）+ 无 update_existing 字段。"""

    file = MultipleFileField('Excel文件', validators=[DataRequired('请选择文件')])
    update_existing = None


_orig = R.ProductImportForm
R.ProductImportForm = _LegacyProductImportForm
try:
    resp = post(client, 'E-O9-NEG', 'O9 阴性', '')
    body = resp.get_json(silent=True) or {}
    check('E.legacy_form_fails', body.get('success') is not True,
          f'status={resp.status_code} body={str(body)[:160]}')
finally:
    R.ProductImportForm = _orig

fails = [n for n, ok in results if not ok]
print(f'\nTOTAL={len(results)} PASS={len(results) - len(fails)} FAIL={len(fails)}')
for n in fails:
    print('FAILED:', n)
print('RESULT: ' + ('OK' if not fails else 'FAIL'))
sys.exit(1 if fails else 0)
