"""权限矩阵检查。

对每个 GET 路由，比较各角色的实际可访问性与 permissions.py 的登记：
- ALL_ROLES_PASS：所有登录角色都能访问（含 user），提示可能缺校验
- ANON_PASS：未登录也能拿到内容，属于严重问题
并列出路由源码上实际挂的校验方式（require_capability / 手写 role 判断 / 无）。

**退出码语义（E-03 分类：原「伪门禁型」→ 已补失败出口）**

本脚本 stdout **携带判据语义**（`匿名可访问（应为 0）`），因此退出码必须与之同源（A-30）：
`anon_open == 0` ⇒ **exit 0**；`anon_open` 非空 ⇒ **exit 1**（并打印 `[FAIL] 匿名可访问视图 N 个（应为 0）`）。

**落盘与退出码解耦（E-03：原「写盘污染型」）**：矩阵 JSON 默认写
`test-reports-2026-10/.tmp/<RUN_ID>/_permission_matrix.json`（**不再写仓库根**，历史缺陷 T-07/A-11：
写仓库根 JSON 被拒时「断言全绿也 exit 1」= 狼来了）。`--out PATH` 可指定落点，`--no-dump` 完全跳过；
**写盘失败只打印 `[WARN]`，绝不改变退出码**。退出码纯由判据决定。

用法（仓库根目录）：

    python -B scripts/permission_matrix.py                # 默认落 .tmp/<RUN_ID>/
    python -B scripts/permission_matrix.py --no-dump      # 不落盘（CI 推荐）
    python -B scripts/permission_matrix.py --out /tmp/x.json

**C-06 四模块权限断言面（V-07 新增，复用本脚本口径、不新起并行工具）**

`35` §4 的 `C-06` 行把靶心收窄为「**权限断言面**」（可达性命中面已在库）：`equipment` /
`purchase_orders` / `shipments` / `stock` 四个模块**各 ≥1 allow + ≥1 deny**；注入「移除
`@require_capability`」⇒ 对应 deny 断言**必须转红**；这四个模块的 **5xx = 0**。
本脚本用**同一个 `classify()` 口径**（'权限不足' 文案 / 401 / 403 ⇒ DENY）与**同一批 actor client**
跑 `MODULE_FACE`，因此不存在「同端点两个分母」。能力→允许角色取自 `app.permissions.roles_for`
（与产品同一事实来源）。

* `--out-modules PATH`：额外落盘四模块面矩阵（默认不写；`--no-dump` 不影响它）。
* `--inject-module NAME`：**副本进程内**把该模块面端点的 `@require_capability` 剥掉
  （保留 `@login_required`）⇒ 对应 deny 断言必须转红（`strip_capability()`；**不改生产代码**）。
* 退出码：`anon_open == 0` **且** 四模块面全绿 ⇒ `exit 0`；任一不满足 ⇒ `exit 1`。

**B17-13：四模块写端点面（方法参数化，仍在同一工具内）**

页面面按设计只扫 GET ⇒ 四模块**写端点**的 deny 断言原是余项。现在 `classify()` 增 `method`/`data`
参数（默认 GET ⇒ 既有调用与判据逐字不变），写端点按**能力**从 `url_map` 派生（不手抄路径表），
逐写端点跑「≥1 allow + ≥1 deny + 无 5xx/EXC」，并与 `MODULE_FACE[*]['write_expect']` 台账对拍
（数目上下漂移都红）。`--inject-write-module NAME` = 剥掉该模块首个写端点的 `@require_capability`
⇒ 写面 deny 必须转红。

**B17-04：内联 role ≤ 白名单（双向断言）**

`INLINE_ROLE_WHITELIST` 登记 `app/` 下所有 `current_user.role` / `_require_roles(` 用法（AST 口径，
带行号 + 该行源码 anchor；模板面按行正则）。**比对键 = (文件, anchor 文本) 的出现次数**（t16 修 F1）：
源码出现次数 > 台账次数 ⇒ `extra` 红；台账次数 > 源码次数 ⇒ `stale` 红；文本与次数都不变、仅行号漂移
只 `[WARN]`。**同文本重复行**（复制一处已登记的判断）也会被计数抓住 —— 旧口径只比 anchor 键存在性，
多出来的那次只落 `drift` ⇒ 17 条扫描配 16 条白名单仍报绿。判据与实现见 `check_inline_roles()`。内联
role 判断必须走 `can()` / `@require_capability`，白名单是「存量台账」而非「可增长名单」。
"""
import argparse
import ast
import json
import os
import re
import sys
import time
import pathlib

from _test_bootstrap import make_app, ensure_role_users, login_as, seed_fixtures, ROLES

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS = ROOT / 'test-reports-2026-10'
DUMP_NAME = '_permission_matrix.json'
ROUTE_FILES = ('app/main/routes.py', 'app/main/quality.py', 'app/main/production_center.py')

#: ---- C-06（V-07）：四模块权限断言面（口径 = 本脚本 classify，不新起工具）----
#: `urls` 是该模块**页面面**的具名入口（含被通用 GET 扫因为带参而跳过的 `/stock/<kind>`）；
#: `capability` 取自路由源码上的 `@require_capability`；允许角色由 `app.permissions.roles_for` 派生。
MODULE_FACE = (
    {'module': 'equipment', 'capability': 'equipment.manage',
     'urls': ('/equipment', '/work_centers', '/heat_lots', '/workpieces'),
     'inject_endpoint': 'main.manage_equipment', 'write_expect': 9,
     'deny_sample': ('hr', 'accountant', 'inspector', 'sales', 'user')},
    {'module': 'purchase_orders', 'capability': 'purchase.manage',
     'urls': ('/purchase_orders', '/suppliers', '/purchase_requisitions'),
     'inject_endpoint': 'main.manage_purchase_orders', 'write_expect': 8,
     'deny_sample': ('hr', 'accountant', 'inspector', 'sales', 'user')},
    {'module': 'shipments', 'capability': 'shipment.manage',
     'urls': ('/shipments',),
     'inject_endpoint': 'main.manage_shipments', 'write_expect': 4,
     'deny_sample': ('hr', 'accountant', 'inspector', 'user')},
    {'module': 'stock', 'capability': 'inventory.view',
     'urls': ('/stock/fg', '/stock/raw'),
     'inject_endpoint': 'main.stock_by_kind', 'write_expect': 0,
     'deny_sample': ('hr', 'accountant', 'inspector', 'sales', 'user')},
)
MODULES_DUMP_NAME = '_permission_matrix_modules.json'

#: ---- B17-13：四模块**写端点**面（方法参数化，复用本脚本 classify 口径）----
#: `guard_of_view()` 默认只扫 `ROUTE_FILES`，而四模块的写视图在上面这四个模块文件里 ⇒ 另扫一遍
#: （**默认调用点不动**，既有 stdout 因此逐字不变）。
WRITE_ROUTE_FILES = ('app/main/equipment.py', 'app/main/purchase.py',
                     'app/main/shipping.py', 'app/main/stock.py')
#: 少数写端点在「空表单」下会早退（先查单据字段）⇒ 给最小字段让请求真正走到**守卫之后**的业务分支；
#: 取不到 id 就空表单发并 `[WARN]`（不伪造红）。`MODULE_FACE[*]['write_expect']` 是写端点台账。
WRITE_PAYLOADS = (('/shipments/create', 'sales_order_id', 'SalesOrder'),)

#: ---- B17-04：内联 role ≤ 白名单（**双向**断言；台账 = 15 Python + 1 模板）----
#: 口径 = **AST**（`ast.Attribute(attr='role')` 属性访问 + `_require_roles(` 调用）⇒ docstring/注释
#: 天然不计，且能扫到 `f'... role={current_user.role}'` 这类**无比较运算符**的用法（行正则扫不到）；
#: 模板面按行正则 `current_user\.role`（先把 Jinja `{# … #}` 注释按等行数替换掉）。
#: 判据（**计入退出码**；比对键 = (文件, anchor 文本) 的**出现次数**，见 `check_inline_roles`）：
#:   * 源码出现次数 > 台账次数 ⇒ `extra`（绕过 CAPABILITIES 新写内联 role 判断，含**同文本重复行**）⇒ 红；
#:   * 台账次数 > 源码次数 ⇒ `stale`（那几行已删/已改写；同一文本登记多次时少一次也抓得住）⇒ 红 —— 双向；
#:   * 文本与次数都不变、仅行号不一致 ⇒ 只 `[WARN] 行号漂移`（并发编辑下防 blocking 步假红）。
#: 每条 = `(相对路径, 行号, anchor)`；anchor = 该行去空白后的源码文本（行号可漂，文本改了要登记）；
#: 行号只用于定位与漂移提示，判据本身不依赖行号（并发插行不会把 blocking 步判红）。
INLINE_ROLE_WHITELIST = (
    ('app/main/quality.py', 47, "if current_user.role == 'inspector':"),
    ('app/main/quality.py', 84, "if current_user.role == 'inspector':"),
    ('app/main/quality.py', 107, "if current_user.role == 'inspector' and task.inspector_id != current_user.id:"),
    ('app/main/quality.py', 124, "if current_user.role == 'inspector' and record.inspector_id != current_user.id:"),
    ('app/main/quality.py', 534, "if current_user.role == 'inspector':"),
    ('app/main/quality.py', 854, "if current_user.role == 'inspector' and task.inspector_id != current_user.id:"),
    ('app/main/quality.py', 944, "if current_user.role == 'inspector' and record.inspector_id != current_user.id:"),
    ('app/main/quality.py', 1263, "if current_user.role == 'inspector':"),
    ('app/main/quality.py', 1324, "if current_user.role == 'inspector' and record.inspector_id != current_user.id:"),
    ('app/main/quality.py', 1418, "if current_user.role == 'inspector' and record.inspector_id != current_user.id:"),
    ('app/main/routes.py', 426, "if current_user.role in ('admin', 'manager'):"),
    ('app/main/routes.py', 430, 'endpoint = ROLE_LANDING_ENDPOINTS.get(current_user.role)'),
    ('app/main/routes.py', 441, "f'user_dashboard accessed by user {current_user.id} ({current_user.username}) role={current_user.role}'"),
    ('app/main/routes.py', 746, "if current_user.role == 'admin':"),
    ('app/main/routes.py', 6530, "if current_user.role not in ['admin', 'hr']:"),
    ('app/templates/main/quality/task_detail.html', 13, "{% if task.status == 'pending' and (current_user.role in ['admin', 'manager'] or (current_user.role == 'inspector' and task.inspector_id == current_user.id)) %} {# B16-08 契约豁免：此为「角色+对象归属」复合条件，can() 只表达纯角色能力、无法表达归属 ⇒ 保留内联角色判断 #}"),
)



def run_id():
    """落盘标识：优先 HARNESS_RUN_ID，否则时间戳。"""
    return os.environ.get('HARNESS_RUN_ID') or time.strftime('run-%Y%m%d-%H%M%S')


def default_out():
    """.tmp/<RUN_ID>/ 下的落点（绝对路径，与 cwd 无关 —— 不再是 cwd 相对的 `../`）。"""
    return str(REPORTS / '.tmp' / run_id() / DUMP_NAME)


def modules_out(path):
    """`--out-modules` 的落点解析（**绝对路径、cwd 无关**，且绝不落到任何根目录）。

    * 绝对路径 ⇒ 原样；
    * 带目录的相对路径 ⇒ 相对 `REPORTS`（`test-reports-2026-10/`）解析；
    * **裸文件名** ⇒ 落到 `REPORTS/.tmp/<RUN_ID>/`（与 `default_out()` 同目录）。

    ⚠ 两个踩过的坑（t8 实测）：① 经 `scripts/_sandbox_compat.py` 运行时 cwd 是 `scripts/`，
    直接把相对路径交给 `open()` 会落到 `scripts/test-reports-2026-10/.tmp/...`；
    ② 裸文件名若按 `REPORTS` 直接解析会落到报告根目录。⇒ 统一解析成绝对路径。
    """
    if not path:
        return None
    p = pathlib.Path(path)
    if p.is_absolute():
        return str(p)
    if p.parent == pathlib.Path('.'):
        return str(REPORTS / '.tmp' / run_id() / p.name)
    return str(REPORTS / p)


def a14_reconfigure():
    """A-14：本机控制台是 GBK；只放宽 errors，避免编码问题被误读成「崩溃 exit 1」。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass


def dump_matrix(matrix, out_path):
    """落盘（**与退出码解耦**）：失败返回 (False, 警告串)，调用方不得据此改退出码。"""
    try:
        directory = os.path.dirname(os.path.abspath(out_path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(matrix, f, ensure_ascii=False, indent=1)
        return True, f'完整矩阵已写入 {out_path}'
    except OSError as e:
        return False, (f'[WARN] 落盘失败（不影响退出码）: {e.__class__.__name__}: {e}')


def guard_of_view(files=ROUTE_FILES):
    """扫源码，得出每个视图函数用了哪种权限校验。`files` 默认与历史一致（既有 stdout 不变）。"""
    guards = {}
    for rel in files:
        text = (ROOT / rel).read_text(encoding='utf-8')
        lines = text.splitlines()
        for i, line in enumerate(lines):
            m = re.match(r'^def (\w+)\(', line)
            if not m:
                continue
            func = m.group(1)
            # 往上收集装饰器
            decos = []
            j = i - 1
            while j >= 0 and (lines[j].startswith('@') or lines[j].strip() == ''):
                if lines[j].startswith('@'):
                    decos.append(lines[j].strip())
                j -= 1
            # 往下看函数体前 25 行有没有手写 role 判断
            body = '\n'.join(lines[i:i + 25])
            kinds = []
            for d in decos:
                if 'require_capability' in d:
                    kinds.append('capability' + d[d.index('('):] if '(' in d else 'capability')
                elif 'require_roles' in d or 'admin_required' in d:
                    kinds.append(d)
            if re.search(r'current_user\.role\s+(not\s+)?in|_require_roles\(|current_user\.role\s*[!=]=', body):
                kinds.append('inline_role_check')
            if not any('login_required' in d for d in decos):
                kinds.append('NO_LOGIN_REQUIRED')
            guards[func] = kinds or ['NONE']
    return guards


def _jinja_comment_pad(text):
    """把 Jinja `{# … #}` 注释换成等行数的空行（**保住行号**，模板面判据才能带行号）。"""
    return re.sub(r'\{#.*?#\}', lambda m: '\n' * m.group(0).count('\n'), text, flags=re.S)


def _is_current_user_role(node):
    """`current_user.role`（**当前登录用户**的取用）；`User.role`/`employee.user.role` 这类
    查询过滤、赋值、展示不算内联授权判断（它们不经 `current_user`，混进来只会制造噪声）。"""
    return (isinstance(node, ast.Attribute) and node.attr == 'role'
            and isinstance(node.value, ast.Name) and node.value.id == 'current_user')


def scan_inline_roles():
    """扫描内联 role 用法 ⇒ `(相对路径, 行号, anchor)` 排序去重列表（B17-04 的事实来源）。

    Python 面走 **AST**（`current_user.role` / `_require_roles(` 调用）：docstring/注释天然不计，
    且能扫到 `f'... role={current_user.role}'` 这种**无比较运算符**的用法（行正则扫不到）；
    模板面走行正则 `current_user\\.role`。anchor = 该行去空白后的源码文本。"""
    found = set()
    for path in sorted((ROOT / 'app').rglob('*.py')):
        if '__pycache__' in path.parts:
            continue
        rel = str(path.relative_to(ROOT)).replace(os.sep, '/')
        lines = path.read_text(encoding='utf-8').splitlines()
        for node in ast.walk(ast.parse('\n'.join(lines))):
            hit = _is_current_user_role(node) or (
                isinstance(node, ast.Call) and getattr(node.func, 'id', None) == '_require_roles')
            if hit:
                found.add((rel, node.lineno, lines[node.lineno - 1].strip()))
    for path in sorted((ROOT / 'app' / 'templates').rglob('*.html')):
        rel = str(path.relative_to(ROOT)).replace(os.sep, '/')
        raw = path.read_text(encoding='utf-8').splitlines()
        for i, line in enumerate(_jinja_comment_pad('\n'.join(raw)).splitlines(), 1):
            if re.search(r'current_user\.role', line):
                found.add((rel, i, raw[i - 1].strip()))
    return sorted(found)


def _by_anchor(entries):
    """`(file, anchor) -> [行号…]`（升序）⇒ **比对键 = (文件, anchor 文本)，判据看出现次数**。

    行号随 `extra`/`stale` 一并给出（定位用），但判据本身不靠行号：见 `check_inline_roles()`。"""
    out = {}
    for rel, lineno, anchor in entries:
        out.setdefault((rel, anchor), []).append(lineno)
    return {k: sorted(v) for k, v in out.items()}


def check_inline_roles(whitelist=INLINE_ROLE_WHITELIST):
    """双向比对：返回 `(scanned, extra, stale, drift)`；extra/stale ⇒ 红，drift ⇒ 仅 `[WARN]`。

    **方案（t16 修 F1）**：比对按 **(file, anchor 文本) 的出现次数计数式**成立，不是「anchor 是否
    出现过」——同一行文本在源码里多出现一次（复制粘贴一处已登记的内联判断）必须判 `extra`；台账里
    同一 anchor 登记 N 次而源码只剩 N-1 次则判 `stale`。旧口径只比 anchor 键存在性 ⇒ 多出来的那次
    只落 `drift`、exit 0（**单向漏斗**：17 条扫描配 16 条白名单仍打印「双向无漏斗」）。
    仍满足「**带行号**」：`extra`/`stale` 第 3 项 = **多出来的那些行号**（计数用），face 打印时对该
    anchor 同时给出「源码行号」与「台账行号」两个列表 —— 行号随编辑整体平移，「哪一行是新加的」不可
    判定，故不假装精确，但**所有相关行号可见**；`drift` 给「文本相同、次数相同、仅位置不同」的两组行号。"""
    scanned = scan_inline_roles()
    scan_d, ledger_d = _by_anchor(scanned), _by_anchor(whitelist)
    extra, stale = [], []
    for key, src in sorted(scan_d.items()):          # 源码次数 > 台账次数 ⇒ 多出的算 extra
        surplus = src[len(ledger_d.get(key, [])):]
        if surplus:
            extra.append((key[0], key[1], surplus))
    for key, led in sorted(ledger_d.items()):        # 台账次数 > 源码次数 ⇒ 少掉的算 stale
        surplus = led[len(scan_d.get(key, [])):]
        if surplus:
            stale.append((key[0], key[1], surplus))
    drift = [(f, a, ledger_d[(f, a)], scan_d[(f, a)]) for (f, a) in sorted(scan_d)
             if (f, a) in ledger_d and len(ledger_d[(f, a)]) == len(scan_d[(f, a)])
             and ledger_d[(f, a)] != scan_d[(f, a)]]
    return scanned, extra, stale, drift


def _occ(entries):
    """`extra`/`stale` 的**出现次数**合计（同文本多出 2 次 ⇒ 2 处，不是 1 个键）。"""
    return sum(len(lines_) for _rel, _anchor, lines_ in entries)


def print_inline_role_face(scanned, extra, stale, drift):
    """打印 B17-04 face（失败时顺带给出可直接登记的台账行）。

    「无漏斗」这类断言只在上面的 `[OK  ]` 分支出现 —— 那时 extra/stale 均为空（按出现次数逐一相等），
    不会出现「17 条 == 16 条」这种自相矛盾的绿。"""
    ok = not (extra or stale)
    scan_d, ledger_d = _by_anchor(scanned), _by_anchor(INLINE_ROLE_WHITELIST)
    print('\n=== B17-04 内联 role ≤ 白名单（双向：扫描⊄白名单 或 白名单⊄扫描 ⇒ 均红）===')
    print(f"  [{'OK  ' if ok else 'FAIL'}] 扫描={len(scanned)} 白名单={len(INLINE_ROLE_WHITELIST)}"
          f' 新增未登记={_occ(extra)} 处（{len(extra)} 个文本键）'
          f' stale={_occ(stale)} 处（{len(stale)} 个）'
          f' 行号漂移={len(drift)}（漂移仅 WARN）')
    for rel, anchor, lines_ in extra:
        src, led = scan_d[(rel, anchor)], ledger_d.get((rel, anchor), [])
        where = (f'源码 {len(src)} 次 > 台账 {len(led)} 次，多出 {len(lines_)} 次；源码行号 {src}'
                 + (f' vs 台账行号 {led}' if led else '（台账无此文本）'))
        print(f'        新增未登记: {rel}  {where}  {anchor}')
    for rel, anchor, lines_ in stale:
        led, src = ledger_d[(rel, anchor)], scan_d.get((rel, anchor), [])
        where = (f'台账 {len(led)} 次 > 源码 {len(src)} 次，少掉 {len(lines_)} 次；台账行号 {led}'
                 + (f' vs 源码行号 {src}' if src else '（源码已无此文本）'))
        print(f'        stale: {rel}  {where}  {anchor}')
    for rel, anchor, wl, src in drift:
        print(f'        [WARN] 行号漂移 {rel}: 白名单{wl} != 源码{src}  {anchor}')
    if not ok:
        print('        --- 现场逐条台账（可直接粘进 INLINE_ROLE_WHITELIST）---')
        for rel, lineno, anchor in scanned:
            print(f'        ({rel!r}, {lineno}, {anchor!r}),')


def content_ok(resp_code, final_code):
    return final_code == 200 and resp_code == 200


def classify(client, url, method='GET', data=None):
    """**单一判定口径**（C-06 复用，不另起第二套）：`'权限不足'` 文案 / 401 / 403 ⇒ `DENY`；
    登录页特征 ⇒ `LOGIN`；200 且非以上 ⇒ `OK`；其余 ⇒ `HTTP<code>`；抛异常 ⇒ `EXC:<类型>`。

    B17-13：`method`/`data` 默认 `'GET'`/`None` ⇒ **既有 GET 调用与判据逐字不变**；写端点面传
    `method='POST'` 复用同一条判定（`HTTP404` = 守卫已放行、只是 dummy id 下资源缺失 ⇒ 正常放行）。"""
    try:
        if method == 'GET':
            r = client.get(url, follow_redirects=True)
        else:
            r = client.open(url, method=method, data=data or {}, follow_redirects=True)
    except Exception as e:
        return f'EXC:{e.__class__.__name__}'
    try:
        body = r.get_data(as_text=True)
    except UnicodeDecodeError:
        body = ''  # 二进制下载（导出文件）
    denied = ('权限不足' in body) or r.status_code in (401, 403)
    login_page = 'name="username"' in body and '登录' in body
    if r.status_code == 200 and not denied and not login_page:
        return 'OK'
    if denied:
        return 'DENY'
    if login_page:
        return 'LOGIN'
    return f'HTTP{r.status_code}'


def strip_capability(app, endpoint):
    """**副本进程内**移除某端点的 `@require_capability`（C-06 注入回放；不改生产代码）。

    装饰器链：`@login_required`（最外）→ `@require_capability` → 视图函数 ⇒ 取最内层视图函数后
    用 `login_required` 重包：**能力面被移除、登录面保留**（匿名判定因此不受污染，注入是靶向的）。
    返回注入记录（`None` = 端点不存在）。"""
    from flask_login import login_required
    view = app.view_functions.get(endpoint)
    if view is None:
        return None
    inner, layers = view, 0
    while hasattr(inner, '__wrapped__') and layers < 8:
        inner = inner.__wrapped__
        layers += 1
    app.view_functions[endpoint] = login_required(inner)
    return {'endpoint': endpoint, 'stripped_layers': layers,
            'inner': getattr(inner, '__name__', '?')}


def run_module_face(clients, roles_for):
    """四模块 allow + deny 断言（**复用 `classify()` 的同一口径与同一批 client**）。

    判据分两层（缺一不可）：
    * **逐入口（可被注入证伪的那一层）**：每个 face URL 上 ① `capability` 允许的角色**至少一个**
      `OK`（allow 面）② `deny_sample` 中**至少一个**未授权角色 `DENY`（deny 面）③ 无 5xx。
      ⇒ 「移除某端点的 `@require_capability`」必然让**该入口**的 deny 面塌掉 ⇒ 对应断言转红。
      （模块级只看「≥1」会**掩盖**同模块其它入口仍在拒绝，注入因此不红 —— 实测踩过，见 t8 证据。）
    * **模块级**：`35` §4 C-06 的口径 = 该模块 ≥1 allow + ≥1 deny + 5xx=0。
    返回 `(逐 URL 矩阵, 逐模块结论)`。"""
    rows, summary = {}, []
    for spec in MODULE_FACE:
        cap_roles = tuple(roles_for(spec['capability']))
        table = {url: {actor: classify(c, url) for actor, c in clients.items()}
                 for url in spec['urls']}
        rows[spec['module']] = table
        per_url = []
        for url in spec['urls']:
            row = table[url]
            allow = [r for r in cap_roles if row[r] == 'OK']
            deny = [r for r in spec['deny_sample'] if row[r] == 'DENY']
            five = sorted({v for v in row.values() if v.startswith('HTTP5')})
            problems = []
            if not allow:
                problems.append('allow 面为 0（%s 无任何允许角色可访问）' % url)
            if not deny:
                problems.append('deny 面为 0（%s 未拒绝任何样本角色）' % url)
            if five:
                problems.append('%s 出现 5xx: %s' % (url, ','.join(five)))
            per_url.append({'url': url, 'allow': allow, 'deny': deny, 'fivexx': five,
                            'problems': problems, 'ok': not problems})
        allow_any = [r for r in cap_roles if any(table[u][r] == 'OK' for u in spec['urls'])]
        deny_any = [r for r in spec['deny_sample']
                    if any(table[u][r] == 'DENY' for u in spec['urls'])]
        five_all = sorted({v for u in spec['urls'] for v in table[u].values()
                           if v.startswith('HTTP5')})
        problems = ['%s: %s' % (e['url'], '; '.join(e['problems']))
                    for e in per_url if not e['ok']]
        if len(allow_any) != len(cap_roles):
            problems.append('模块级 allow 角色缺失: %s'
                            % ','.join(r for r in cap_roles if r not in allow_any))
        if not deny_any:
            problems.append('模块级 deny ≥1 不成立（样本角色全未命中）')
        if five_all:
            problems.append('模块级 5xx 非空: %s' % ','.join(five_all))
        summary.append({'module': spec['module'], 'capability': spec['capability'],
                        'cap_roles': list(cap_roles), 'allow_ok': allow_any,
                        'deny_sample': list(spec['deny_sample']), 'deny_ok': deny_any,
                        'fivexx': five_all, 'urls': list(spec['urls']), 'per_url': per_url,
                        'inject_endpoint': spec['inject_endpoint'],
                        'problems': problems, 'ok': not problems})
    return rows, summary


def write_endpoints(app, guards, capability):
    """**派生**该能力面的写端点（不手抄路径表）：`url_map` 里有写方法 + 该视图函数挂了该能力。

    返回 `[(rule_str, endpoint, method)]`（只取写方法 ⇒ 与页面面不重号）。"""
    out = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint in ('static', 'bootstrap.static') or rule.endpoint.startswith('auth.'):
            continue
        methods = sorted(rule.methods - {'GET', 'HEAD', 'OPTIONS'})
        if not methods:
            continue
        kinds = guards.get(rule.endpoint.rsplit('.', 1)[-1], [])
        if any(f"'{capability}'" in k for k in kinds):
            out.append((str(rule), rule.endpoint, methods[0]))
    return sorted(out)


def write_payload(rule_str, ids):
    """`WRITE_PAYLOADS` 登记的写端点给最小字段；取不到 id ⇒ 空表单 + `[WARN]`（**不伪造红**）。"""
    for path, field, model in WRITE_PAYLOADS:
        if rule_str == path:
            value = (ids.get(model) or (None, None))[1]
            if value is None:
                print(f'[WARN] {path} 缺 {field}（副本库无 {model} 行）⇒ 空表单发送')
                return {}
            return {field: str(value)}
    return {}


def run_write_face(found_by_module, clients, roles_for, ids):
    """四模块**写端点** deny 面（B17-13，方法参数化；同一 `classify()` 口径、同一批 client）。

    逐端点（与页面面同构 ⇒ 可被注入证伪）：① 允许角色**至少一个**通过守卫（`OK`/`HTTP404`）
    ② `deny_sample` **至少一个** `DENY` ③ 无 5xx/EXC。模块级：写端点数 == `write_expect` 台账
    （**上下漂移都红** ⇒ 防「删端点/去装饰器 ⇒ face 静默缩小」）+ 全部 cap 角色 ≥1 allow
    + ≥1 deny + 5xx=0。返回 `(逐端点矩阵, 逐模块结论)`。

    `found_by_module` 由调用方在**注入之前**用 `write_endpoints()` 派生（注入会摘掉能力 ⇒ 不能现算）。"""
    rows, summary = {}, []
    for spec in MODULE_FACE:
        cap_roles = tuple(roles_for(spec['capability']))
        found = found_by_module.get(spec['module'], [])
        table, per_ep = {}, []
        for rule_str, endpoint, method in found:
            url = re.sub(r'<[^<>]+>', '1', rule_str)
            data = write_payload(rule_str, ids)
            row = {actor: classify(c, url, method=method, data=data)
                   for actor, c in clients.items()}
            table[f'{method} {rule_str} [{endpoint}]'] = row
            allow = [r for r in cap_roles
                     if row[r] not in ('DENY', 'LOGIN') and not row[r].startswith(('HTTP5', 'EXC'))]
            deny = [r for r in spec['deny_sample'] if row[r] == 'DENY']
            bad = sorted({v for v in row.values() if v.startswith(('HTTP5', 'EXC'))})
            problems = []
            if not allow:
                problems.append('allow 面为 0（%s 无任何允许角色通过守卫）' % rule_str)
            if not deny:
                problems.append('deny 面为 0（%s 未拒绝任何样本角色）' % rule_str)
            if bad:
                problems.append('%s 出现 5xx/EXC: %s' % (rule_str, ','.join(bad)))
            per_ep.append({'rule': rule_str, 'endpoint': endpoint, 'method': method, 'url': url,
                           'allow': allow, 'deny': deny, 'bad': bad,
                           'problems': problems, 'ok': not problems})
        rows[spec['module']] = table
        allow_any = [r for r in cap_roles if any(r in e['allow'] for e in per_ep)]
        deny_any = [r for r in spec['deny_sample'] if any(r in e['deny'] for e in per_ep)]
        bad_all = sorted({v for e in per_ep for v in e['bad']})
        problems = ['%s: %s' % (e['rule'], '; '.join(e['problems'])) for e in per_ep if not e['ok']]
        if len(found) != spec['write_expect']:
            problems.append('写端点数漂移: 现场 %d != 台账 %d（上下都算漂移 ⇒ 同步台账）'
                            % (len(found), spec['write_expect']))
        if len(allow_any) != len(cap_roles) and per_ep:
            problems.append('模块级 allow 角色缺失: %s'
                            % ','.join(r for r in cap_roles if r not in allow_any))
        if not deny_any and per_ep:
            problems.append('模块级 deny ≥1 不成立（样本角色全未命中）')
        if bad_all:
            problems.append('模块级 5xx/EXC 非空: %s' % ','.join(bad_all))
        summary.append({'module': spec['module'], 'capability': spec['capability'],
                        'cap_roles': list(cap_roles), 'expect_writes': spec['write_expect'],
                        'found_writes': len(found), 'allow_ok': allow_any,
                        'deny_sample': list(spec['deny_sample']), 'deny_ok': deny_any,
                        'bad': bad_all, 'per_endpoint': per_ep,
                        'problems': problems, 'ok': not problems})
    return rows, summary


def print_write_face(write_face, injection, inject_write_module):
    """打印 B17-13 写端点面。"""
    print('\n=== C-06 四模块**写端点**面（方法参数化，复用本脚本 classify 口径：逐端点 allow+deny）===')
    for m in write_face:
        print(f"  [{'OK  ' if m['ok'] else 'FAIL'}] {m['module']:<16}"
              f"cap={m['capability']:<20} 写端点={m['found_writes']}/{m['expect_writes']}"
              f"  allow≥1={','.join(m['allow_ok']) or '-'}"
              f"  deny≥1={','.join(m['deny_ok']) or '-'}  5xx/EXC={m['bad'] or '无'}")
        for e in m['per_endpoint']:
            print(f"        [{'OK  ' if e['ok'] else 'FAIL'}] {e['method']} {e['rule']:<44}"
                  f"allow={','.join(e['allow']) or '-'}  deny={','.join(e['deny']) or '-'}"
                  f"  5xx/EXC={e['bad'] or '无'}")
        if not m['per_endpoint']:
            print('        （该能力面无写端点，台账 write_expect=0 ⇒ 只声明「无写端点」）')
        for p in m['problems']:
            print(f'        - {p}')
    if injection is not None:
        target = next((m for m in write_face if m['module'] == inject_write_module), {})
        print(f'[INJECT] 期望 = 该模块写面 deny 断言转红 ⇒ 实际 deny_ok='
              f'{target.get("deny_ok")}  module_ok={target.get("ok")}')
        print(f'[INJECT] 靶向性 = 其它三模块写面仍全绿: '
              f'{[m["module"] for m in write_face if m["module"] != inject_write_module and m["ok"]]}')


def run(out_path=None, dump=True, out_modules=None, inject_module=None, inject_write_module=None):
    a14_reconfigure()
    app, _ = make_app()
    users, password = ensure_role_users(app)
    seed_fixtures(app)
    guards = guard_of_view()
    # B17-13：写端点面另扫四个模块文件（`guards` 保持默认扫描面 ⇒ 既有 stdout 逐字不变）
    wguards = guard_of_view(files=ROUTE_FILES + WRITE_ROUTE_FILES)
    from app.permissions import roles_for   # C-06：能力→角色取**产品同一事实来源**

    from smoke_test import first_ids, resolve_url, SKIP
    ids = first_ids(app)

    targets = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static' or 'GET' not in rule.methods or str(rule) in SKIP:
            continue
        if rule.endpoint.startswith('auth.') or rule.endpoint == 'bootstrap.static':
            continue
        if rule.arguments:
            url, _why = resolve_url(rule, ids)
            if url is None:
                continue
        else:
            url = str(rule)
        targets.append((str(rule), url, rule.endpoint))

    matrix = {}
    clients = {}
    for role in ROLES:
        c = app.test_client()
        login_as(c, users[role], password)
        clients[role] = c
    clients['anonymous'] = app.test_client()

    # B17-13：写端点清单必须在**任何注入之前**派生（`strip_capability()` 会就地改 app）
    write_found = {spec['module']: write_endpoints(app, wguards, spec['capability'])
                   for spec in MODULE_FACE}

    for rule_str, url, endpoint in sorted(targets):
        row = {}
        for actor, c in clients.items():
            row[actor] = classify(c, url)
        matrix[f'{rule_str} [{endpoint}]'] = row

    print('=== 匿名可访问（应为 0，登录页/静态资源除外）===')
    anon_open = [k for k, v in matrix.items() if v['anonymous'] == 'OK']
    for k in anon_open:
        func = k.split('[')[-1].rstrip(']').split('.')[-1]
        print(f'  {k}  guards={guards.get(func)}')
    if not anon_open:
        print('  无')

    print('\n=== 所有登录角色（含 user/accountant/sales）均可访问 ===')
    for k, v in matrix.items():
        if v['anonymous'] == 'OK':
            continue
        if all(v[r] == 'OK' for r in ROLES):
            func = k.split('[')[-1].rstrip(']').split('.')[-1]
            print(f'  {k}  guards={guards.get(func)}')

    print('\n=== 源码上完全没有权限校验的视图（仅 login_required 或更少）===')
    endpoints_tested = {k.split('[')[-1].rstrip(']').split('.')[-1] for k in matrix}
    for func in sorted(endpoints_tested):
        g = guards.get(func, ['UNKNOWN'])
        if g == ['NONE'] or 'NO_LOGIN_REQUIRED' in g:
            print(f'  {func}: {g}')

    # ---- C-06（V-07）：四模块权限断言面（allow + deny + 5xx=0）----
    injection = None
    if inject_module:
        spec = next((s for s in MODULE_FACE if s['module'] == inject_module), None)
        if spec is None:
            print(f'\n[FAIL] --inject-module 未知模块: {inject_module}'
                  f'（可选 {[s["module"] for s in MODULE_FACE]}）')
            return 2
        injection = strip_capability(app, spec['inject_endpoint'])
        print(f'\n[INJECT] 副本进程内移除 @require_capability：module={inject_module} '
              f'endpoint={spec["inject_endpoint"]} stripped_layers='
              f'{None if injection is None else injection["stripped_layers"]} '
              f'inner={None if injection is None else injection["inner"]}'
              f'（login_required 保留 ⇒ 匿名判定不受污染）')
    face_rows, face = run_module_face(clients, roles_for)
    face_failures = [m['module'] for m in face if not m['ok']]
    print('\n=== C-06 四模块权限断言面（复用本脚本口径：逐入口 allow+deny，模块级 ≥1≥1，5xx=0）===')
    for m in face:
        print(f"  [{'OK  ' if m['ok'] else 'FAIL'}] {m['module']:<16}"
              f"cap={m['capability']:<20} allow≥1={','.join(m['allow_ok']) or '-'}"
              f"  deny≥1={','.join(m['deny_ok']) or '-'}  入口={len(m['urls'])}"
              f"  5xx={m['fivexx'] or '无'}")
        for e in m['per_url']:
            print(f"        [{'OK  ' if e['ok'] else 'FAIL'}] {e['url']:<32}"
                  f"allow={','.join(e['allow']) or '-'}  deny={','.join(e['deny']) or '-'}"
                  f"  5xx={e['fivexx'] or '无'}")
        for p in m['problems']:
            print(f'        - {p}')
    if injection is not None:
        target = next((m for m in face if m['module'] == inject_module), {})
        print(f'[INJECT] 期望 = 该模块 deny 断言转红 ⇒ 实际 deny_ok='
              f'{target.get("deny_ok")}  module_ok={target.get("ok")}')
        print(f'[INJECT] 靶向性 = 其它三模块仍全绿: '
              f'{[m["module"] for m in face if m["module"] != inject_module and m["ok"]]}')

    # ---- B17-13：四模块**写端点** deny 面（方法参数化；与页面面同一 classify 口径）----
    write_injection = None
    if inject_write_module:
        eps = list(write_found.get(inject_write_module, []))
        if not eps:
            print(f'\n[FAIL] --inject-write-module 未知模块或该面无写端点: {inject_write_module}'
                  f'（有写端点的模块 {[s["module"] for s in MODULE_FACE if write_found.get(s["module"])]}）')
            return 2
        target_ep = eps[0][1]                       # 该模块首个写端点（派生顺序确定）
        write_injection = strip_capability(app, target_ep)
        print(f'\n[INJECT] 副本进程内移除**写端点**的 @require_capability：'
              f'module={inject_write_module} endpoint={target_ep} stripped_layers='
              f'{None if write_injection is None else write_injection["stripped_layers"]} '
              f'inner={None if write_injection is None else write_injection["inner"]}'
              f'（login_required 保留 ⇒ 匿名判定不受污染）')
    write_rows, write_face = run_write_face(write_found, clients, roles_for, ids)
    write_failures = [m['module'] for m in write_face if not m['ok']]
    print_write_face(write_face, write_injection, inject_write_module)

    # ---- B17-04：内联 role ≤ 白名单（双向断言，纯静态、不发请求）----
    ir_scanned, ir_extra, ir_stale, ir_drift = check_inline_roles()
    print_inline_role_face(ir_scanned, ir_extra, ir_stale, ir_drift)
    ir_extra_occ, ir_stale_occ = _occ(ir_extra), _occ(ir_stale)
    ir_failed = bool(ir_extra or ir_stale)

    # ---- E-03：落盘与退出码解耦（写盘失败绝不改变判据）----
    if dump:
        _ok, note = dump_matrix(matrix, out_path or default_out())
        print('\n' + note)
    else:
        print('\n[--no-dump] 已跳过落盘（退出码只反映判据）')
    if out_modules:
        face_doc = {'run_id': run_id(), 'capability_source': 'app.permissions.roles_for',
                    'criterion': 'C-06：各模块 ≥1 allow + ≥1 deny + 5xx=0（复用本脚本 classify 口径）',
                    'injected': injection, 'summary': face, 'rows': face_rows,
                    'write_criterion': 'C-06 写端点面（B17-13）：逐写端点 ≥1 allow + ≥1 deny + 5xx/EXC=0，'
                                       '写端点数 == write_expect 台账（上下漂移都红）',
                    'write_injected': write_injection, 'write_summary': write_face,
                    'write_rows': write_rows,
                    'inline_role_criterion': 'B17-04：扫描集 == 白名单（按 (file, anchor 文本) 出现次数'
                                             '双向比对，含同文本重复行；白名单 stale 亦红）',
                    'inline_role_scanned': ir_scanned, 'inline_role_drift': ir_drift}
        m_ok, m_note = dump_matrix(face_doc, out_modules)
        print(m_note if m_ok else m_note)      # 与主落盘同口径：失败只 [WARN]，不改退出码

    # ---- E-03：失败出口（原为无条件 return 0 的伪门禁；判据语义与退出码同源）----
    # C-06（V-07）：四模块权限面失败同样计入退出码 ⇒ ci_gates 的 permission_matrix 步骤
    # **永久**执法 C-06（allow + deny + 5xx=0），而不只是在实测里跑一次。
    # B17-04/B17-13：内联 role 白名单（双向）与写端点 deny 面同样计入退出码。
    code = 1 if (anon_open or face_failures or write_failures or ir_failed) else 0
    if anon_open:
        print(f'[FAIL] 匿名可访问视图 {len(anon_open)} 个（应为 0）')
    else:
        print('[OK] 匿名可访问 = 0')
    if face_failures:
        print(f'[FAIL] C-06 四模块权限面失败：{",".join(face_failures)}')
    else:
        print('[OK] C-06 四模块权限面 = 全绿（4 模块 allow + deny + 5xx=0）')
    if write_failures:
        print(f'[FAIL] C-06 四模块**写端点**面失败：{",".join(write_failures)}')
    else:
        print('[OK] C-06 四模块写端点面 = 全绿（%d 写端点：逐端点 ≥1 allow + ≥1 deny，5xx/EXC=0）'
              % sum(m['found_writes'] for m in write_face))
    if ir_failed:
        print(f'[FAIL] 内联 role 白名单断言失败：新增未登记 {ir_extra_occ} 处 / stale {ir_stale_occ} 处'
              f'（扫描 {len(ir_scanned)} 条，白名单 {len(INLINE_ROLE_WHITELIST)} 条；'
              '按 (file, 文本) 出现次数双向比对）')
    else:
        print(f'[OK] 内联 role ≤ 白名单 = 全绿（扫描 {len(ir_scanned)} 条 == 白名单 '
              f'{len(INLINE_ROLE_WHITELIST)} 条，按 (file, 文本) 出现次数逐一相等、双向无漏斗；'
              f'行号漂移 {len(ir_drift)} 处仅 WARN）')
    print('[e03] exit_code_semantics=' + json.dumps({
        'script': 'scripts/permission_matrix.py',
        'class': '有判据语义（原伪门禁，E-03 已补失败出口；V-07 增补 C-06 四模块面；'
                 'B17-04/13 增补内联 role 白名单与写端点面；t16 白名单按出现次数双向比对）',
        'rule': 'anon_open == 0 且 C-06 四模块面（页面面 + 写端点面）全绿 且 内联 role ≤ 白名单（双向）'
                ' -> exit 0; 任一不满足 -> exit 1',
        'inputs': {'anon_open': len(anon_open), 'routes_tested': len(matrix),
                   'c06_modules_failed': face_failures, 'c06_injected': inject_module,
                   'c06_write_modules_failed': write_failures,
                   'c06_write_injected': inject_write_module,
                   'inline_role_scanned': len(ir_scanned), 'inline_role_extra': ir_extra_occ,
                   'inline_role_stale': ir_stale_occ,
                   'inline_role_extra_keys': len(ir_extra), 'inline_role_stale_keys': len(ir_stale)},
        'dump': ('skipped' if not dump else str(out_path or default_out())),
        'modules_dump': str(out_modules) if out_modules else 'skipped',
        'code': code,
    }, ensure_ascii=False))
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='权限矩阵检查（E-03：判据驱动退出码；落盘与退出码解耦；'
                    'V-07：C-06 四模块 allow/deny 断言面）')
    ap.add_argument('--out', default=None,
                    help=f'矩阵 JSON 落点（默认 {REPORTS}/.tmp/<RUN_ID>/{DUMP_NAME}）')
    ap.add_argument('--no-dump', action='store_true', help='完全不落盘（退出码只反映判据）')
    ap.add_argument('--out-modules', default=None,
                    help='额外落盘 C-06 四模块面矩阵（默认不写；裸文件名 ⇒ '
                         f'test-reports-2026-10/.tmp/<RUN_ID>/{MODULES_DUMP_NAME}，'
                         '带目录的相对路径 ⇒ 相对 test-reports-2026-10/ 解析）')
    ap.add_argument('--inject-module', default=None,
                    help='注入回放：副本进程内移除该模块面端点的 @require_capability '
                         '⇒ 对应 deny 断言必须转红（不改生产代码）')
    ap.add_argument('--inject-write-module', default=None,
                    help='注入回放（B17-13）：副本进程内移除该模块**首个写端点**的 '
                         '@require_capability ⇒ 写面 deny 断言必须转红（不改生产代码）')
    args = ap.parse_args(argv)
    return run(out_path=args.out, dump=not args.no_dump,
               out_modules=modules_out(args.out_modules), inject_module=args.inject_module,
               inject_write_module=args.inject_write_module)


if __name__ == '__main__':
    sys.exit(main())
