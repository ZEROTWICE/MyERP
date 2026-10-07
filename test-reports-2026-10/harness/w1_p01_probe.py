"""w1_p01_probe.py — P-01（blocker）与 TL-01（`check_model_refs`）的对抗验证探针。

## 为什么不直接信「改了一行就应该好」
P-01 的失效形态是「**同一文件里只有两个函数坏**」（同模块另有 ≥10 处函数内导入先例），
所以本探针不靠人读 diff，而是做**同一套请求探针跑两棵树**的 A/B：

| 树 | 来源 | 期望 |
| --- | --- | --- |
| `<repo>/app` | 当前工作树（已补导入） | 两端点 **非 5xx**、`use` 后 `quantity` 真的减少、不存在 id 返 **404** |
| `.tmp/<RUN_ID>/prefix/app` | `git show HEAD:app/main/routes.py`（**修复前**逐字节） | 两端点 **500**、`quantity` **未变**；`use` 的未捕获 `NameError` 由 Flask 记进 stderr |

两棵树**只差 routes.py 一个文件**，请求脚本、夹具、判据完全同一份 ⇒ 差异只能由那一行导入解释。

## 判据（机械可判）
| id | 判据 |
| --- | --- |
| P-01-a1 | 修后：`POST /consumables/<id>/use`（合法 JSON，量 1）=> **200** 且库字段 `quantity 10.0 -> 9.0` |
| P-01-a2 | 修后：`DELETE /consumables/<id>` => **200** 且该行确实被删除 |
| P-01-a3 | 修后：超量领用（9999 > 库存）=> **400**（业务校验，非 5xx） |
| P-01-b | 修后：不存在的 id => `use` / `delete` **均 404**（不是 500） |
| P-01-r1 | 修前（prefix 树）：`use` 与 `delete` **均 500**；`delete` 正文含 `not defined`；子进程 stderr 含 `NameError: name 'Consumable' is not defined` |
| P-01-r2 | 修前（prefix 树）：`quantity` **未变**（10.0 -> 10.0），且行未被删 |
| TL-01-a | `check_model_refs.py --root app` => 修前 **2 处**（`routes.py:10891`/`:10943`）、修后 **0 处**（exit 1 -> 0） |
| TL-01-b | 合成注入树（1 个同类 `NameError`）=> 门禁报红（exit 1，命中 1 处） |
| TL-01-c | `--selftest` => 2 阳性 + 11 阴性 = **13/13** |

## 只读约束
- 真实库 `app.db` **只做 SHA256**（前后各一次 + `_env.assert_real_db_untouched`），一切请求跑在
  `shutil.copy2` 出来的副本上；副本与真实库**不是同一个文件**（`samefile=False`，证据里记）。
- 不改 `app/**`（prefix 树是 `.tmp` 下的副本）、不改 `scripts/**`、不改 `harness/**`。
- 证据落盘一律走 `_env.save_evidence`（E-01：分 run 目录 + 写入守卫 + 台账），**绝不原地覆盖**。

## 用法（仓库根目录；A-40：复跑必须换 `HARNESS_RUN_ID`）
    $env:HARNESS_RUN_ID='w1-p01-t6-final'
    python -B test-reports-2026-10/harness/w1_p01_probe.py --scenario all
    python -B test-reports-2026-10/harness/w1_p01_probe.py --scenario gate     # 只跑门禁三组
    python -B test-reports-2026-10/harness/w1_p01_probe.py --scenario request  # 只跑请求 A/B
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
sys.path.insert(0, HERE)

from _env import (  # noqa: E402
    REAL_DB, RUN_ID, assert_real_db_untouched, ensure_dir, interpreter, run_child, run_python,
    save_evidence, sha256_file, tmp_dir,
)

GATE_SCRIPT = os.path.join(SCRIPTS_DIR, 'check_model_refs.py')
ROUTES_REL = os.path.join('app', 'main', 'routes.py')
APP_DIR = os.path.join(REPO_ROOT, 'app')
PREFIX_TREE = os.path.join(tmp_dir('prefix'))
LINE6_TREE = os.path.join(tmp_dir('line6'))
INJECT_TREE = os.path.join(tmp_dir('inject'))

#: 本任务唯一的生产代码改动（`app/main/routes.py:6` 行尾追加）
MY_IMPORT_SUFFIX = ', Consumable, ConsumableCategory'

#: 请求探针（同一份源码跑两棵树；@PLACEHOLDER@ 由 orchestrator 替换）
REQUEST_SOURCE = r'''
import json
import os
import sys
import traceback
from datetime import datetime

TREE = '@TREE@'
DB_COPY = '@DB_COPY@'
TAG = '@TAG@'
out = {'tag': TAG, 'tree': TREE or '<repo worktree>', 'db_copy': DB_COPY}

if TREE:
    sys.path.insert(0, TREE)
os.environ['DATABASE_URL'] = 'sqlite:///' + DB_COPY.replace('\\', '/')

try:
    from app import create_app, db
    from app.models import Consumable, ConsumableCategory, User
    import app.main.routes as R
    out['routes_module_file'] = R.__file__
    out['module_has_Consumable'] = hasattr(R, 'Consumable')
    out['module_has_ConsumableCategory'] = hasattr(R, 'ConsumableCategory')

    application = create_app()
    application.config['WTF_CSRF_ENABLED'] = False
    application.config['TESTING'] = True
    application.config['DEBUG'] = False
    application.config['PROPAGATE_EXCEPTIONS'] = False
    out['db_uri'] = application.config['SQLALCHEMY_DATABASE_URI']

    with application.app_context():
        u = User.query.filter_by(username='_t_admin').first()
        if u is None:
            u = User(username='_t_admin', role='admin')
            db.session.add(u)
        u.role = 'admin'
        u.set_password('test_pw_123')
        cat = ConsumableCategory.query.first()
        if cat is None:
            cat = ConsumableCategory(name='_p01_cat', code='_P01C', is_active=True)
            db.session.add(cat)
            db.session.flush()
        row = Consumable(supplier='_p01_supplier', category_id=cat.id, supplier_number='_P01S',
                         specification='_p01_spec', quantity=10.0, unit='pcs', unit_price=1.0,
                         status='in_stock', storage_date=datetime.now())
        db.session.add(row)
        db.session.commit()
        out['consumable_id'] = row.id
        out['qty_initial'] = float(row.quantity)

    client = application.test_client()
    login = client.post('/auth/login', data={'username': '_t_admin', 'password': 'test_pw_123'})
    out['login_status'] = login.status_code

    def call(name, method, path, **kw):
        """返回 dict：status / body_head；异常也如实记录（修前 use 端点会抛 NameError）。"""
        try:
            resp = getattr(client, method)(path, **kw)
            body = resp.get_data(as_text=True)
            return {'probe': name, 'method': method.upper(), 'path': path,
                    'status': resp.status_code, 'body_head': body[:240].replace('\n', ' | '),
                    'raised': None}
        except Exception as exc:
            return {'probe': name, 'method': method.upper(), 'path': path, 'status': None,
                    'body_head': '', 'raised': '%s: %s' % (type(exc).__name__, exc)}

    cid = out['consumable_id']
    out['P01a1_use_existing'] = call('P01a1-use-existing', 'post',
                                     '/consumables/%d/use' % cid, json={'usage_quantity': 1})
    with application.app_context():
        db.session.expire_all()
        row = Consumable.query.get(cid)
        out['qty_after_use'] = float(row.quantity) if row else None
    out['P01a3_use_over_stock'] = call('P01a3-use-over-stock', 'post',
                                       '/consumables/%d/use' % cid, json={'usage_quantity': 9999})
    out['P01b_use_missing'] = call('P01b-use-missing-id', 'post',
                                   '/consumables/900000001/use', json={'usage_quantity': 1})
    out['P01b_delete_missing'] = call('P01b-delete-missing-id', 'delete',
                                      '/consumables/900000002')
    out['P01a2_delete_existing'] = call('P01a2-delete-existing', 'delete',
                                        '/consumables/%d' % cid)
    with application.app_context():
        db.session.expire_all()
        out['row_after_delete'] = Consumable.query.get(cid) is not None
    out['OK'] = True
except Exception as exc:
    out['OK'] = False
    out['EXCEPTION'] = '%s: %s' % (type(exc).__name__, exc)
    out['TRACEBACK_TAIL'] = traceback.format_exc()[-1500:]
print('__RESULT__' + json.dumps(out, ensure_ascii=True, default=str))
'''


def log(lines, text=''):
    print(text)
    lines.append(text)


def json_line(obj):
    """控制台行一律 ASCII 安全（A-14/A-60）：JSON 用 ensure_ascii=True。"""
    return json.dumps(obj, ensure_ascii=True, sort_keys=True)


def _git_to_file(args, dest):
    ensure_dir(os.path.dirname(dest))
    with open(dest, 'wb') as fh:
        proc = subprocess.run(args, cwd=REPO_ROOT, stdout=fh, stderr=subprocess.DEVNULL)
    return proc.returncode


def git_head_rev():
    dest = os.path.join(tmp_dir('prefix'), 'head-rev.txt')
    _git_to_file(['git', 'rev-parse', 'HEAD'], dest)
    with open(dest, encoding='utf-8', errors='replace') as fh:
        return fh.read().strip()


def worktree_state():
    """记录取证时刻的工作树状态（本仓是多人并发写入的活体，A/B 必须写清当时状态）。"""
    dest = os.path.join(tmp_dir(), 'git-status.txt')
    _git_to_file(['git', 'status', '--porcelain'], dest)
    with open(dest, encoding='utf-8', errors='replace') as fh:
        rows = [ln for ln in fh.read().splitlines() if ln.strip()]
    return {
        'git_head_rev': git_head_rev(),
        'git_status_porcelain': rows,
        'app_main_routes_sha256': sha256_file(os.path.join(REPO_ROOT, ROUTES_REL)),
        'app_main_quality_sha256': sha256_file(os.path.join(REPO_ROOT, 'app', 'main', 'quality.py')),
        'app_init_sha256': sha256_file(os.path.join(REPO_ROOT, 'app', '__init__.py')),
    }


def build_prefix_tree(lines):
    """`.tmp/<RUN_ID>/prefix/app` = 当前 app/ 的副本，但 routes.py 换成 git HEAD（修复前逐字节）。"""
    if os.path.isdir(PREFIX_TREE):
        shutil.rmtree(PREFIX_TREE)
    ensure_dir(PREFIX_TREE)
    shutil.copytree(APP_DIR, os.path.join(PREFIX_TREE, 'app'),
                    ignore=shutil.ignore_patterns('__pycache__'))
    head_routes = os.path.join(PREFIX_TREE, 'git-head-routes.py')
    rc = _git_to_file(['git', 'show', 'HEAD:' + ROUTES_REL.replace('\\', '/')], head_routes)
    shutil.copyfile(head_routes, os.path.join(PREFIX_TREE, 'app', 'main', 'routes.py'))
    worktree_routes = os.path.join(REPO_ROOT, ROUTES_REL)
    info = {
        'git_head_rev': git_head_rev(),
        'git_show_exit': rc,
        'head_routes_bytes': os.path.getsize(head_routes),
        'head_routes_sha256': sha256_file(head_routes),
        'worktree_routes_bytes': os.path.getsize(worktree_routes),
        'worktree_routes_sha256': sha256_file(worktree_routes),
        'prefix_tree': os.path.relpath(PREFIX_TREE, REPO_ROOT).replace('\\', '/'),
        'prefix_routes_sha256': sha256_file(os.path.join(PREFIX_TREE, 'app', 'main', 'routes.py')),
        'line6_head': None,
        'line6_worktree': None,
    }
    with open(head_routes, encoding='utf-8', errors='replace') as fh:
        info['line6_head'] = fh.read().splitlines()[5].strip()[-70:]
    with open(worktree_routes, encoding='utf-8', errors='replace') as fh:
        info['line6_worktree'] = fh.read().splitlines()[5].strip()[-70:]
    log(lines, '[prefix] git show exit=%s rev=%s bytes=%d sha256=%s'
        % (info['git_show_exit'], info['git_head_rev'][:12], info['head_routes_bytes'],
           info['head_routes_sha256']))
    log(lines, '[prefix] head  line6 tail = ...%s' % info['line6_head'])
    log(lines, '[prefix] worktree line6 tail = ...%s (sha256=%s)'
        % (info['line6_worktree'], info['worktree_routes_sha256']))
    return info


def build_line6_tree(lines):
    """`.tmp/<RUN_ID>/line6/app` = **当前工作树** app/ 的副本，只把这一行导入改回去。

    为什么需要它：本仓是多人并发写入的活体（W2/W3 同时在改 `app/**`）。git HEAD 树能复现
    「原始缺陷」，但无法隔离「本任务这一行」；把当前工作树**只回退这一行**（其余字节全同），
    才能把差异唯一归因到本任务的导入补丁。
    """
    if os.path.isdir(LINE6_TREE):
        shutil.rmtree(LINE6_TREE)
    ensure_dir(LINE6_TREE)
    shutil.copytree(APP_DIR, os.path.join(LINE6_TREE, 'app'),
                    ignore=shutil.ignore_patterns('__pycache__'))
    worktree_routes = os.path.join(REPO_ROOT, ROUTES_REL)
    target = os.path.join(LINE6_TREE, 'app', 'main', 'routes.py')
    suffix = MY_IMPORT_SUFFIX.encode('utf-8')
    with open(worktree_routes, 'rb') as fh:
        raw = fh.read()
    parts = raw.split(b'\n')
    if not parts[5].endswith(suffix):
        raise RuntimeError('工作树 routes.py:6 不含本任务的导入后缀，单行 A/B 无法构造：%r'
                           % parts[5][-80:])
    reverted = list(parts)
    reverted[5] = parts[5][:-len(suffix)]
    with open(target, 'wb') as fh:
        fh.write(b'\n'.join(reverted))
    with open(target, 'rb') as fh:
        patched = fh.read()
    a = raw.split(b'\n')
    b = patched.split(b'\n')
    only_line6 = (len(a) == len(b)
                  and all(x == y for i, (x, y) in enumerate(zip(a, b)) if i != 5))
    info = {
        'line6_tree': os.path.relpath(LINE6_TREE, REPO_ROOT).replace('\\', '/'),
        'worktree_routes_sha256': sha256_file(worktree_routes),
        'line6_routes_sha256': sha256_file(target),
        'bytes_removed': len(raw) - len(patched),
        'reverted_lines_total': len(b),
        'only_line6_differs': bool(only_line6),
        'line6_worktree_tail': parts[5].decode('utf-8', 'replace')[-70:],
        'line6_reverted_tail': b[5].decode('utf-8', 'replace')[-70:],
    }
    log(lines, '[line6] tree=%s only_line6_differs=%s bytes_removed=%d'
        % (info['line6_tree'], info['only_line6_differs'], info['bytes_removed']))
    log(lines, '[line6] worktree tail = ...%s' % info['line6_worktree_tail'])
    log(lines, '[line6] reverted tail = ...%s' % info['line6_reverted_tail'])
    return info


def build_inject_tree(lines):
    """合成注入树：1 个同类 `NameError`（大写名 `Widget` 未绑定）=> 门禁必须报红。"""
    root = os.path.join(INJECT_TREE, 'app')
    if os.path.isdir(INJECT_TREE):
        shutil.rmtree(INJECT_TREE)
    ensure_dir(os.path.join(root, 'main'))
    src = ('"""synthetic injection tree (probe only, never written into the repo app/)."""\n'
           '\n\n'
           'def injected_missing_name(oid):\n'
           '    return Widget.query.get_or_404(oid)\n')
    path = os.path.join(root, 'main', 'injected_missing_name.py')
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(src)
    log(lines, '[inject] synthetic tree = %s (1 file, >=1 violation expected)'
        % os.path.relpath(root, REPO_ROOT).replace('\\', '/'))
    return {'inject_root': os.path.relpath(root, REPO_ROOT).replace('\\', '/'),
            'inject_file': os.path.relpath(path, REPO_ROOT).replace('\\', '/'),
            'inject_file_sha256': sha256_file(path)}


def run_gate(root, label, extra=()):
    """跑 `scripts/check_model_refs.py`，返回 dict（含**真实退出码**）。"""
    args = [GATE_SCRIPT, '--root', root, '--json'] + list(extra)
    res = run_child(args, cwd=REPO_ROOT, timeout=600, label=label)
    parsed = None
    for line in res['stdout'].splitlines():
        if line.startswith('__JSON__'):
            try:
                parsed = json.loads(line[len('__JSON__'):])
            except ValueError:
                parsed = None
    return {'label': label, 'root': os.path.relpath(root, REPO_ROOT).replace('\\', '/'),
            'exit_code': res['exit_code'], 'stdout': res['stdout'], 'stderr': res['stderr'],
            'parsed': parsed, 'real_db_unchanged': res['real_db_unchanged']}


def run_request(tree, tag, lines):
    """在副本库上跑请求探针（同一份源码；tree 为空串即当前工作树、非空则是**含 app 包的目录**）。"""
    dest = os.path.join(tmp_dir('db'), 'app_%s_%s.db' % (tag, RUN_ID))
    ensure_dir(os.path.dirname(dest))
    shutil.copy2(REAL_DB, dest)
    same_file = os.path.samefile(dest, REAL_DB)
    # 路径一律用正斜杠注入：反斜杠在 Python 字符串字面量里会被当转义（`\a` -> BEL，
    # 第 1 轮 `w1-p01-t6-final` 就是这样把副本路径写坏的 —— 那轮判据如实报红并留档）。
    source = (REQUEST_SOURCE.replace('@TREE@', tree.replace('\\', '/'))
                            .replace('@DB_COPY@', dest.replace('\\', '/'))
                            .replace('@TAG@', tag))
    res = run_python(source, cwd=REPO_ROOT, timeout=1800, label='request-' + tag)
    payload = None
    for line in res['stdout'].splitlines():
        if line.startswith('__RESULT__'):
            try:
                payload = json.loads(line[len('__RESULT__'):])
            except ValueError:
                payload = None
    info = {'tag': tag, 'tree': tree or '<repo worktree>', 'db_copy': dest,
            'db_copy_sha256': sha256_file(dest), 'copy_samefile_as_real': same_file,
            'exit_code': res['exit_code'], 'payload': payload,
            'real_db_unchanged': res['real_db_unchanged'],
            'child_stdout_tail': res['stdout'][-1200:], 'child_stderr_tail': res['stderr'][-2500:]}
    log(lines, '[request:%s] tree=%s db_copy_samefile_real=%s child_exit=%s'
        % (tag, tree or '<repo>', same_file, res['exit_code']))
    return info


# ------------------------------------------------------------------ 判据
def _under(path, root):
    if not path:
        return False
    return os.path.normcase(os.path.abspath(path)).startswith(
        os.path.normcase(os.path.abspath(root)) + os.sep)


def judge_fixed(req):
    p = req['payload'] or {}
    use = p.get('P01a1_use_existing') or {}
    dele = p.get('P01a2_delete_existing') or {}
    over = p.get('P01a3_use_over_stock') or {}
    miss_use = p.get('P01b_use_missing') or {}
    miss_del = p.get('P01b_delete_missing') or {}
    q0, q1 = p.get('qty_initial'), p.get('qty_after_use')
    return [
        ('(probe self-check) worktree app/ imported and module HAS Consumable/ConsumableCategory',
         _under(p.get('routes_module_file'), APP_DIR) and p.get('module_has_Consumable') is True
         and p.get('module_has_ConsumableCategory') is True,
         'routes_module_file=%s has_Consumable=%s has_ConsumableCategory=%s'
         % (p.get('routes_module_file'), p.get('module_has_Consumable'),
            p.get('module_has_ConsumableCategory'))),
        ('P-01-a1 POST use existing -> 200 and quantity 10.0 -> 9.0',
         use.get('status') == 200 and q0 == 10.0 and q1 == 9.0,
         'status=%s raised=%s qty %s -> %s body=%s'
         % (use.get('status'), use.get('raised'), q0, q1, (use.get('body_head') or '')[:120])),
        ('P-01-a2 DELETE existing -> 200 and row gone',
         dele.get('status') == 200 and p.get('row_after_delete') is False,
         'status=%s raised=%s row_after_delete=%s body=%s'
         % (dele.get('status'), dele.get('raised'), p.get('row_after_delete'),
            (dele.get('body_head') or '')[:120])),
        ('P-01-a3 over-stock (9999 > 10) -> 400 business check, not 5xx',
         over.get('status') == 400,
         'status=%s body=%s' % (over.get('status'), (over.get('body_head') or '')[:120])),
        ('P-01-b use missing id -> 404',
         miss_use.get('status') == 404,
         'status=%s body=%s' % (miss_use.get('status'), (miss_use.get('body_head') or '')[:120])),
        ('P-01-b delete missing id -> 404',
         miss_del.get('status') == 404,
         'status=%s body=%s' % (miss_del.get('status'), (miss_del.get('body_head') or '')[:120])),
        ('no NameError text in any fixed-tree response body',
         all('not defined' not in (x.get('body_head') or '')
             for x in (use, dele, over, miss_use, miss_del)),
         'five bodies checked'),
    ]


def judge_prefix_like(req, tree_root, label, allow_masked_body=False):
    """修前行为判据（同一套源码跑两棵「缺这一行」的树：git HEAD 树 / 当前树回退一行）。

    ``allow_masked_body``：并发写入者（W2/W3）给 `delete_consumable` 加了统一错误脱敏后，
    500 正文不再回显异常文案（根因仍由 `current_app.logger.error` 记进 stderr，由另一条判据断言）
    ⇒ 对「当前工作树」这一侧只要求 **500 + 根因在 stderr**；对冻结的 git HEAD 树仍要求正文原样。
    """
    p = req['payload'] or {}
    use = p.get('P01a1_use_existing') or {}
    dele = p.get('P01a2_delete_existing') or {}
    miss_use = p.get('P01b_use_missing') or {}
    q0, q1 = p.get('qty_initial'), p.get('qty_after_use')
    stderr = req.get('child_stderr_tail') or ''
    name_error = "NameError: name 'Consumable' is not defined"
    return [
        ('(probe self-check) %s tree really imported: routes module under that tree and it has '
         'NO module-level Consumable' % label,
         _under(p.get('routes_module_file'), tree_root)
         and p.get('module_has_Consumable') is False,
         'routes_module_file=%s has_Consumable=%s'
         % (p.get('routes_module_file'), p.get('module_has_Consumable'))),
        ('P-01-r1 %s: POST use existing -> 500 (or NameError raised)' % label,
         use.get('status') == 500 or (use.get('raised') or '').startswith('NameError')
         or (use.get('raised') or '').endswith("name 'Consumable' is not defined"),
         'status=%s raised=%s body=%s' % (use.get('status'), use.get('raised'),
                                          (use.get('body_head') or '')[:120])),
        ('P-01-r1 %s: DELETE existing -> 500 (root cause in body%s)'
         % (label, ', or masked with root cause logged' if allow_masked_body else ''),
         dele.get('status') == 500
         and ('not defined' in (dele.get('body_head') or '') or allow_masked_body),
         'status=%s body=%s' % (dele.get('status'), (dele.get('body_head') or '')[:160])),
        ('P-01-r1 %s: child stderr contains the root cause NameError' % label,
         name_error in stderr,
         'stderr_has_name_error=%s' % (name_error in stderr)),
        ('P-01-r2 %s: quantity unchanged 10.0 -> 10.0' % label,
         q0 == 10.0 and q1 == 10.0, 'qty %s -> %s' % (q0, q1)),
        ('P-01-r2 %s: missing id also fails (500 / raised, name lookup first)' % label,
         miss_use.get('status') == 500 or bool(miss_use.get('raised')),
         'status=%s raised=%s' % (miss_use.get('status'), miss_use.get('raised'))),
        ('P-01-r2 %s: row NOT deleted (row_after_delete=True)' % label,
         p.get('row_after_delete') is True, 'row_after_delete=%s' % p.get('row_after_delete')),
    ]


def judge_prefix(req):
    return judge_prefix_like(req, PREFIX_TREE, '(pre-fix tree = git HEAD routes.py)')


def judge_line6(req):
    return judge_prefix_like(req, LINE6_TREE,
                             '(current worktree with ONLY line 6 reverted)',
                             allow_masked_body=True)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

    ap = argparse.ArgumentParser(description='P-01 + TL-01 A/B probe (read-only on app.db)')
    ap.add_argument('--scenario', default='all', choices=('all', 'gate', 'request'))
    args = ap.parse_args(argv)

    lines = []
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    log(lines, '=' * 78)
    log(lines, '[w1_p01_probe] RUN_ID=%s scenario=%s started=%s' % (RUN_ID, args.scenario, started))
    log(lines, '[w1_p01_probe] repo=%s' % REPO_ROOT)
    log(lines, '[w1_p01_probe] interpreter=%s' % interpreter())
    real_before = sha256_file(REAL_DB)
    log(lines, '[real-db] sha256 before = %s' % real_before)
    log(lines, '=' * 78)

    out = {'run_id': RUN_ID, 'scenario': args.scenario, 'started': started,
           'repo_root': REPO_ROOT, 'real_db_sha256_before': real_before}
    out['worktree'] = worktree_state()
    log(lines, '[worktree] git HEAD = %s' % out['worktree']['git_head_rev'])
    log(lines, '[worktree] routes.py sha256 = %s' % out['worktree']['app_main_routes_sha256'])
    log(lines, '[worktree] git status --porcelain (%d rows, concurrent writers may appear):'
        % len(out['worktree']['git_status_porcelain']))
    for row in out['worktree']['git_status_porcelain']:
        log(lines, '    %s' % row)

    # ------------------------------------------------ 1. 门禁三组
    if args.scenario in ('all', 'gate'):
        out['prefix'] = build_prefix_tree(lines)
        out['line6'] = build_line6_tree(lines)
        out['inject'] = build_inject_tree(lines)

        gate_prefix = run_gate(os.path.join(PREFIX_TREE, 'app'), 'gate-prefix')
        gate_line6 = run_gate(os.path.join(LINE6_TREE, 'app'), 'gate-line6')
        gate_fixed = run_gate(APP_DIR, 'gate-fixed')
        gate_inject = run_gate(os.path.join(INJECT_TREE, 'app'), 'gate-inject')
        gate_selftest = run_child([GATE_SCRIPT, '--selftest'], cwd=REPO_ROOT, timeout=600,
                                  label='gate-selftest')
        out['gate'] = {'prefix': gate_prefix, 'line6': gate_line6, 'fixed': gate_fixed,
                       'inject': gate_inject,
                       'selftest': {'exit_code': gate_selftest['exit_code'],
                                    'stdout': gate_selftest['stdout']}}
        out['inject']['declared_expectation'] = '>=1 violation (gate must go red)'

        n_pre = (gate_prefix['parsed'] or {}).get('violation_count')
        n_l6 = (gate_line6['parsed'] or {}).get('violation_count')
        n_post = (gate_fixed['parsed'] or {}).get('violation_count')
        n_inj = (gate_inject['parsed'] or {}).get('violation_count')
        pre_lines = sorted(v['line'] for v in (gate_prefix['parsed'] or {}).get('violations', []))
        l6_funcs = sorted(v['func'] for v in (gate_line6['parsed'] or {}).get('violations', []))
        st_ok = gate_selftest['exit_code'] == 0 and '13/13' in gate_selftest['stdout']
        gate_criteria = [
            ('TL-01-a pre-fix gate (git HEAD routes.py) -> exit 1 with exactly 2 hits',
             gate_prefix['exit_code'] == 1 and n_pre == 2,
             'exit=%s violations=%s' % (gate_prefix['exit_code'], n_pre)),
            ('TL-01-a pre-fix hits are routes.py:10891 and :10943',
             pre_lines == [10891, 10943], 'lines=%s' % pre_lines),
            ('TL-01-a (current worktree, only line 6 reverted) gate -> exit 1 with exactly 2 hits '
             'in delete_consumable/use_consumable',
             gate_line6['exit_code'] == 1 and n_l6 == 2
             and l6_funcs == ['delete_consumable', 'use_consumable'],
             'exit=%s violations=%s funcs=%s lines=%s'
             % (gate_line6['exit_code'], n_l6, l6_funcs,
                sorted(v['line'] for v in (gate_line6['parsed'] or {}).get('violations', [])))),
            ('TL-01-a after fix gate -> exit 0 with 0 hits',
             gate_fixed['exit_code'] == 0 and n_post == 0,
             'exit=%s violations=%s' % (gate_fixed['exit_code'], n_post)),
            ('TL-01-b synthetic injection tree -> exit 1 with >=1 hit (gate goes red)',
             gate_inject['exit_code'] == 1 and (n_inj or 0) >= 1,
             'exit=%s violations=%s' % (gate_inject['exit_code'], n_inj)),
            ('TL-01-c --selftest -> exit 0 and 13/13',
             st_ok, 'exit=%s' % gate_selftest['exit_code']),
        ]
        out['gate_criteria'] = [{'criterion': c, 'passed': bool(ok), 'evidence': e}
                                for c, ok, e in gate_criteria]
        log(lines, '')
        log(lines, '--- TL-01 gate criteria ---')
        for c, ok, e in gate_criteria:
            log(lines, '  [%s] %s' % ('PASS' if ok else 'FAIL', c))
            log(lines, '         %s' % e)
        for tag, res, n in (('prefix', gate_prefix, n_pre), ('line6', gate_line6, n_l6),
                            ('fixed', gate_fixed, n_post), ('inject', gate_inject, n_inj)):
            log(lines, '')
            log(lines, '[gate:%s] exit=%s violations=%s' % (tag, res['exit_code'], n))
            log(lines, res['stdout'].rstrip())
        log(lines, '')
        log(lines, '[gate:selftest] exit=%s' % gate_selftest['exit_code'])
        log(lines, gate_selftest['stdout'].rstrip())

    # ------------------------------------------------ 2. 请求 A/B
    if args.scenario in ('all', 'request'):
        if 'prefix' not in out:
            out['prefix'] = build_prefix_tree(lines)
        if 'line6' not in out:
            out['line6'] = build_line6_tree(lines)
        req_prefix = run_request(PREFIX_TREE, 'prefix', lines)
        req_line6 = run_request(LINE6_TREE, 'line6', lines)
        req_fixed = run_request('', 'fixed', lines)
        out['request'] = {'prefix': req_prefix, 'line6': req_line6, 'fixed': req_fixed}
        crit_prefix = judge_prefix(req_prefix)
        crit_line6 = judge_line6(req_line6)
        crit_fixed = judge_fixed(req_fixed)
        out['request_criteria'] = {
            'prefix_pre_fix': [{'criterion': c, 'passed': bool(ok), 'evidence': e}
                               for c, ok, e in crit_prefix],
            'line6_revert_pre_fix': [{'criterion': c, 'passed': bool(ok), 'evidence': e}
                                     for c, ok, e in crit_line6],
            'fixed_after': [{'criterion': c, 'passed': bool(ok), 'evidence': e}
                            for c, ok, e in crit_fixed],
        }
        log(lines, '')
        log(lines, '--- P-01 request criteria (pre-fix tree = git HEAD routes.py) ---')
        for c, ok, e in crit_prefix:
            log(lines, '  [%s] %s' % ('PASS' if ok else 'FAIL', c))
            log(lines, '         %s' % e)
        log(lines, '')
        log(lines, '--- P-01 request criteria (current worktree, ONLY line 6 reverted) ---')
        for c, ok, e in crit_line6:
            log(lines, '  [%s] %s' % ('PASS' if ok else 'FAIL', c))
            log(lines, '         %s' % e)
        log(lines, '')
        log(lines, '--- P-01 request criteria (after-fix tree = current worktree) ---')
        for c, ok, e in crit_fixed:
            log(lines, '  [%s] %s' % ('PASS' if ok else 'FAIL', c))
            log(lines, '         %s' % e)
        log(lines, '')
        log(lines, '[request:prefix] payload=%s' % json_line(req_prefix['payload'] or {}))
        log(lines, '')
        log(lines, '[request:line6]  payload=%s' % json_line(req_line6['payload'] or {}))
        log(lines, '')
        log(lines, '[request:fixed]  payload=%s' % json_line(req_fixed['payload'] or {}))

    # ------------------------------------------------ 3. 收尾
    log(lines, '')
    real_after = assert_real_db_untouched('w1_p01_probe 收尾')
    log(lines, '[real-db] sha256 after  = %s (unchanged=%s)'
        % (real_after, real_after == real_before))
    out['real_db_sha256_after'] = real_after
    out['real_db_unchanged'] = real_after == real_before

    all_criteria = list(out.get('gate_criteria', []))
    for group in ('prefix_pre_fix', 'line6_revert_pre_fix', 'fixed_after'):
        all_criteria += out.get('request_criteria', {}).get(group, [])
    failed = [c['criterion'] for c in all_criteria if not c['passed']]
    verdict = 'PASS' if not failed else 'FAIL'
    log(lines, '')
    log(lines, '[verdict] criteria=%d failed=%d => %s'
        % (len(all_criteria), len(failed), verdict))
    for c in failed:
        log(lines, '  FAILED: %s' % c)
    out['verdict'] = verdict
    out['failed_criteria'] = failed
    out['criteria_total'] = len(all_criteria)

    # ------------------------------------------------ 4. 证据落盘（E-01 守卫）
    transcript = '\n'.join(lines) + '\n'
    saved = []
    if args.scenario in ('all', 'gate'):
        saved.append(save_evidence('w1-p01-gate-prefix.json',
                                   json.dumps(out['gate']['prefix'], ensure_ascii=False,
                                              indent=1, default=str)))
        saved.append(save_evidence('w1-p01-gate-line6-revert.json',
                                   json.dumps(out['gate']['line6'], ensure_ascii=False,
                                              indent=1, default=str)))
        saved.append(save_evidence('w1-p01-gate-fixed.json',
                                   json.dumps(out['gate']['fixed'], ensure_ascii=False,
                                              indent=1, default=str)))
        saved.append(save_evidence('w1-p01-gate-inject.json',
                                   json.dumps(out['gate']['inject'], ensure_ascii=False,
                                              indent=1, default=str)))
        saved.append(save_evidence('w1-p01-gate-selftest.txt', out['gate']['selftest']['stdout']))
        saved.append(save_evidence('w1-p01-prefix-provenance.json',
                                   json.dumps({'prefix_tree': out.get('prefix'),
                                               'line6_tree': out.get('line6'),
                                               'inject_tree': out.get('inject'),
                                               'routes_rel': ROUTES_REL,
                                               'note': 'prefix tree = app/ copy + git HEAD '
                                                       'routes.py; line6 tree = current app/ copy '
                                                       'with ONLY line 6 reverted'},
                                              ensure_ascii=False, indent=1, default=str)))
    if args.scenario in ('all', 'request'):
        saved.append(save_evidence('w1-p01-request-prefix.json',
                                   json.dumps(out['request']['prefix'], ensure_ascii=False,
                                              indent=1, default=str)))
        saved.append(save_evidence('w1-p01-request-line6-revert.json',
                                   json.dumps(out['request']['line6'], ensure_ascii=False,
                                              indent=1, default=str)))
        saved.append(save_evidence('w1-p01-request-fixed.json',
                                   json.dumps(out['request']['fixed'], ensure_ascii=False,
                                              indent=1, default=str)))
        saved.append(save_evidence('w1-p01-request-criteria.json',
                                   json.dumps(out['request_criteria'], ensure_ascii=False,
                                              indent=1, default=str)))
    saved.append(save_evidence('w1-p01-criteria.json',
                               json.dumps({k: v for k, v in out.items()
                                           if k in ('run_id', 'scenario', 'repo_root', 'prefix',
                                                    'line6', 'inject', 'gate_criteria',
                                                    'request_criteria', 'verdict', 'criteria_total',
                                                    'failed_criteria', 'real_db_sha256_before',
                                                    'real_db_sha256_after', 'real_db_unchanged')},
                                          ensure_ascii=False, indent=1, default=str)))
    saved.append(save_evidence('w1-p01-transcript.txt', transcript))
    log(lines, '')
    for path in saved:
        log(lines, '[evidence] -> %s' % os.path.relpath(path, REPO_ROOT).replace('\\', '/'))
    log(lines, '[verdict] %s' % verdict)

    print(transcript)
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
