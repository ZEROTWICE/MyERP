#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""r2_c07_probe.py —— C-07 应用级「拒绝连真实库」硬闸的**可执行规格 + 三判据探针**（V-02 / t3）。

任务契约（`35-第2轮测试总方案（定稿）.md` §4.2 / `34` §3.3 / A-84）：

* **inScope**：本文件（`test-reports-2026-10/harness/r2_c07_probe.py`）。**不得改 `app/**`**。
* **实现面**：`blocked(生产面冻结)` —— 硬闸落点在 `app/__init__.py:156` 之后、`:224`（`_ensure_schema`）
  之前（或 `config.py` 的 `_normalize_database_url` 内）。本轮**只交规格 + 判据**，不动生产代码。
* **判据**：`C-07-a`（负例：指向真实库 ⇒ 启动必须失败，且**在 `db.create_all()` 之前**抛错）、
  `C-07-b`（正例：指向副本 ⇒ 启动必须成功；必须覆盖「副本与真实库**同名**」⇒ 不得用文件名判定）、
  `C-07-c`（显式授权通道 ⇒ 放行，不得误杀生产路径）。
* **verify**：`--selftest`（工具本身能报红）+ 负例/正例双跑 + 真库前后指纹。

## 为什么探针要「注入」而不是只读源码（A-84）

A-84 明令：C-07 **不得**以「源码里存在硬闸」为 HIT 依据（那是形态③的静态命中）。判据的最小可复算
形态是「**看抛错点相对 `db.create_all()` 的位置**」。生产面本轮冻结 ⇒ 探针把**参考实现**
（`_r2_c07_guard`，见 `REFERENCE_GUARD_SOURCE`）**注入到 `create_app()` 的启动链锚点上**，
从而给出可执行的判据函数；实现落地后把 `auto` 切到 `present` 即同一套判据直接复验。

抛错点被证成 `before_create_all` 靠三重证据（缺一不可）：

1. `db.create_all` 被包成探针计数器 ⇒ 负例下 `create_all_calls == 0`（**同一子进程内**观测）；
2. 抛错类型 = `RuntimeError`，消息非空且可读；
3. 真库 SHA256 前后不变（旁证）。

## 两条授权通道（C-07 规格）

| 通道 | 形态 | 依据 |
| --- | --- | --- |
| ① 环境变量 | `WMS_ALLOW_REAL_DB=1` | `35` §4.2 C-07-c 原文举例 |
| ② 只读 URI | `sqlite:///file:///<...>/app.db?mode=ro&uri=true`（含 `mode=ro`） | `harness/fixtures.py:79-80` 既有实现「显式只读 URI 是授权通道」⇒ 复用不另起 |

**授权不是「放行写入」而是「允许连」**：通道①②下应用可正常启动，但**不得**产生写入
（`mode=ro` 由 SQLite 强制；探针实测真库 SHA256 不变）。

## 用法（仓库根目录；解释器必须绝对路径，见 `28` §5-1 / `40` R-4）

```powershell
$py = 'F:\Miniconda\envs\wage\python.exe'
$env:HARNESS_RUN_ID = 'r2-exec-b2-c07'
# 全量：预检 + 负例/正例/授权三判据 + 落点 + 破坏向量
& $py -B test-reports-2026-10\harness\r2_c07_probe.py
# 工具自检：合成仓库对照，证明本探针在「闸缺失/闸写坏」时会报红（不恒真）
& $py -B test-reports-2026-10\harness\r2_c07_probe.py --selftest
```

退出码语义：

| 模式 | 退出码 | 含义 |
| --- | --- | --- |
| 全量（默认） | `0` | **规格判据层全过**（9 项：a(spec)/a(message)/a(control)/a(damage)/b(copy)/b(twin)/c(env)/c(ro)/c(db)） |
| 全量 | `1` | 判据层任一项失败 |
| 全量 + `--strict-current-guard` | 必 `1`（实现落地前） | 追加要求**当前生产代码**已含硬闸；实现落地后该项应变 `passed` |
| `--guard-source present` | `1` | 要求仓库自带的闸，但仍未检测到 ⇒ 判据层无法执行（诚实失败，不静默降级） |
| `--selftest` | `0` / `1` | 3 个合成仓库对照全符预期 / 任一不符 |

## 两个「不计入判据层」的现状登记项（`GAP_ASSERTION_IDS`）

`C-07-a(current)` 与 `C-07-a(damage)` 记录**当前缺口真实存在及其分量**，不是规格判据：

* `C-07-a(current)`：未注入时，`DATABASE_URL` 指向真实库**启动成功**、`db.create_all()`
  **已执行** ⇒ 现状 `NOT_DONE`（`app/**` 本轮冻结，实现面 blocked）。
* `C-07-a(damage)`：先在副本上拆掉一个 `_ENSURED_COLUMNS` 登记列（`products.sellable_as_part`，
  实测真实库确有该列），再跑启动链 —— 该列被 `_ensure_schema` **补回**、库文件指纹改变，
  且 SQL 记录里能看到 `ALTER TABLE products ADD COLUMN sellable_as_part BOOLEAN`。
  ⇒ 「应用启动会**写**它连上的那个库」是行为事实；闸缺失时那一个库就是真实库。

## 复算坐标（本文件 --selftest / 全量实跑的实测值）

| 量 | 口径 | 值 |
| --- | --- | --- |
| `_ensure_schema(app)` 调用行 | `app/__init__.py` `splitlines()` | **224**（冻结值） |
| `db.create_all()` 在 `_ensure_schema` 内的行 | 同上 | **107**（全部命中点 `[20, 107, 246]`） |
| 闸位窗口 | 同上 | `app.config.from_object(Config)`@156 → `TEMP_FOLDER`@164 → **闸** → `_ensure_schema`@224 |
| 正例路由数 | `len(app.url_map.iter_rules())` | **271**（与 `route_inventory.py` 口径一致） |
| 真实库 | `_env.sha256_file` | `F5DA2306…0E0F065`（2531328 B），开工/收尾一致 |

本探针**只读生产代码**、**零写真实库**（全程 SHA256 复核）、只写 `evidence/harness/<RUN_ID>/`
与 `.tmp/<RUN_ID>/`。
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

try:  # A-14：本机控制台 GBK
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _env  # noqa: E402

#: 子进程把机读结果打在这一行之后（父进程只认这一行，人读输出无格式约束）
RESULT_MARKER = '##R2C07-RESULT##'

#: 启动链锚点（`34` §3.3 / `35` §4.2 冻结的行号事实；容错匹配）
ANCHOR_CONFIG_LOAD = 'app.config.from_object(Config)'
ANCHOR_AFTER_CONFIG = "app.config['TEMP_FOLDER'] = temp_folder"
ANCHOR_BEFORE_SCHEMA = '_ensure_schema(app)'
ANCHOR_DB_CREATE_ALL = 'db.create_all()'
ANCHOR_NORMALIZE_RETURN = 'return url'
TARGET_SCHEMA_LINE = 224          # `_ensure_schema(app)` 在 app/__init__.py 的行号（冻结事实）
ROUTE_RULES_BASELINE = 271        # `scripts/route_inventory.py` 口径：total rules=271
REPO_ROOT = _env.REPO_ROOT
DEFAULT_REAL_DB = _env.REAL_DB

#: 参考实现的标记（`--inject-guards` / `auto` 检测都用它）
GUARD_MARKER = '_r2_c07_guard'
#: C-07 的显式授权开关（环境变量通道）——规格里钉死这个名字
ALLOW_ENV = 'WMS_ALLOW_REAL_DB'
#: 「现状登记」类断言的 id：它们是**缺口登记**（证明缺口真实存在 + 其分量），
#: 不是规格判据 ⇒ 不参与判据层的通过计数与退出码（否则「当前不满足」会让探针恒 exit 1）
GAP_ASSERTION_IDS = ('C-07-a(current)', 'C-07-a(damage)')

# --------------------------------------------------------------------- 参考实现
#: C-07 的实现规格：**可执行**的参考实现，注入到 `create_app()` 启动链的锚点上。
#: 生产面落点（实现者照此落，`app/**` 本轮冻结不得改）：
#:   1) `app/__init__.py`：`Config` 加载之后、`_ensure_schema(app)`（:224）之前
#:   2) `config.py::_normalize_database_url`：URL 归一化内
REFERENCE_GUARD_SOURCE = '''

# ---------------------------------------------------------------- R2 C-07 参考实现（硬闸）
#: C-07 允许的显式授权开关（环境变量通道）
R2_C07_ALLOW_ENV = 'WMS_ALLOW_REAL_DB'
#: 真实库锚点：与 app 包同级的 app.db（落点固定，不依赖 cwd）
R2_C07_REAL_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.db')


def _r2_c07_sqlite_path(uri):
    """从 sqlite URI 解出文件路径；非 sqlite（如 postgresql://）返回 None（不归本闸管）。"""
    if not uri or not uri.startswith('sqlite:'):
        return None
    raw = uri.split(':///', 1)[-1]
    if raw.startswith('file:'):
        raw = raw[len('file:'):]
    raw = raw.split('?', 1)[0]
    if not raw or raw == ':memory:':
        return None
    return os.path.abspath(raw.replace('/', os.sep))


def _r2_c07_guard(uri, allow_env=R2_C07_ALLOW_ENV):
    """应用级硬闸：URI 指向真实库 app.db 时**立即拒绝**，绝不进入 schema 变更。

    判定用**文件身份**（``os.path.samefile``）而不是文件名 —— `_test_bootstrap.py` 的副本
    与真实库**同名**（都叫 app.db），只比文件名会把合法副本误判（`_env.py:148-159` 同此推理，
    本轮**复用它、不另起**）。指纹同样不能当拒绝条件：合法副本是 `shutil.copy2` 的逐字节副本，
    指纹必然等于真实库（实测两者同为 F5DA2306…0E0F065）。

    返回 ``(db_path, None)`` 表示放行，``(db_path, 原因)`` 表示拒绝。
    """
    db_path = _r2_c07_sqlite_path(uri)
    if db_path is None:
        return None, None
    # 授权通道②：显式只读 URI（mode=ro）= 明确意图的只读连接，放行（与 fixtures.py:79-80 一致）
    if 'mode=ro' in uri:
        return db_path, None
    target = os.path.abspath(db_path)
    real = os.path.abspath(R2_C07_REAL_DB)
    same = False
    if os.path.exists(target) and os.path.exists(real):
        try:
            same = os.path.samefile(target, real)
        except OSError:
            same = False
    if not same:
        return db_path, None
    # 授权通道①：显式授权（生产部署路径不得被硬闸误杀）
    if os.environ.get(allow_env) in ('1', 'true', 'TRUE', 'yes', 'YES'):
        return db_path, None
    raise RuntimeError(
        'R2-C07 硬闸拒绝启动：DATABASE_URL 指向真实库 app.db（%s）。'
        '请把 DATABASE_URL 指向带时间戳的副本；确需连真实库请显式授权 %s=1'
        '（或改用只读 URI mode=ro）。' % (target, allow_env)
    )
'''

#: 注入到 `app/__init__.py` 启动链（在 `_ensure_schema` 之前）的调用点
GUARD_CALL_APP = '''
# --- R2 C-07 应用级硬闸（注入锚点：Config 加载之后、_ensure_schema 之前）---
_r2_c07_guard(app.config.get('SQLALCHEMY_DATABASE_URI'))
'''

#: 注入到 `config.py::_normalize_database_url` 的返回点，校验**已归一化**的 URL
GUARD_CALL_CONFIG = '''
# --- R2 C-07 应用级硬闸（注入锚点：URL 归一化内）---
_r2_c07_guard(_r2_c07_normalize_probe(url))
'''

#: `config.py` 里给调用点用的包装（把「归一化结果」显式交给闸，避免改动 return 语句）
GUARD_CALL_CONFIG_HELPER = '''

def _r2_c07_normalize_probe(url):
    """把 `_normalize_database_url` 的结果交给硬闸，再原样返回（不改归一化语义）。"""
    _r2_c07_guard(url)
    return url
'''


# ------------------------------------------------------------------- 小工具
def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def read_text(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def sqlite_uri(path):
    """普通 sqlite URI（绝对路径、正斜杠）——与 `_test_bootstrap.py:27` 同口径。"""
    return 'sqlite:///' + os.path.abspath(path).replace('\\', '/')


def sqlite_uri_ro(path):
    """显式只读 URI（授权通道②；SQLAlchemy 接受 file: URI + uri=true）。"""
    return 'sqlite:///file:' + os.path.abspath(path).replace('\\', '/') + '?mode=ro&uri=true'


def rel(path):
    try:
        return os.path.relpath(path, REPO_ROOT).replace('\\', '/')
    except Exception:
        return path


#: 不参与 `copy_repo` 的重目录（体积/无关；判据只依赖 app/**、config.py）
COPY_SKIP_DIRS = {'.git', '__pycache__', 'evidence', '.tmp', 'uploads', 'node_modules',
                  '.venv', 'venv', '.mypy_cache', '.pytest_cache'}


def copy_repo(src, dst):
    """把被测仓库复制一份到隔离目录（保留相对结构），用于「注入用 / 原样用」两个副本。

    `dirs_exist_ok=True` 保证可重复调用；跳过 `COPY_SKIP_DIRS`（证据目录可能很大）。
    """
    def _ignore(directory, names):
        return [n for n in names if n in COPY_SKIP_DIRS]
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore)
    return dst


# ------------------------------------------------- 注入（探针侧，不改生产代码）
def guard_present(root):
    """判断给定仓库根的生产代码里是否已有 C-07 硬闸（只读源码）。"""
    files = [os.path.join(root, 'app', '__init__.py'), os.path.join(root, 'config.py')]
    for p in files:
        if not os.path.exists(p):
            continue
        text = read_text(p)
        if GUARD_MARKER in text or 'WMS_ALLOW_REAL_DB' in text:
            return True
        if 'samefile' in text and 'app.db' in text:
            return True
    return False


def locate_anchors(root):
    """锚点行号取证（工具 + 口径 + 值：`splitlines()`，`28` §5-4）。"""
    out = {'expected_schema_line': TARGET_SCHEMA_LINE}
    app_py = os.path.join(root, 'app', '__init__.py')
    cfg_py = os.path.join(root, 'config.py')
    if os.path.exists(app_py):
        lines = read_text(app_py).splitlines()
        for i, line in enumerate(lines, start=1):
            if ANCHOR_CONFIG_LOAD in line:
                out.setdefault('config_load_line', i)
            if ANCHOR_AFTER_CONFIG in line:
                out.setdefault('after_config_line', i)
            if line.startswith('def _ensure_schema('):
                out.setdefault('ensure_schema_def_line', i)
            if line.strip() == ANCHOR_BEFORE_SCHEMA:
                #: `_ensure_schema` 有**两处**出现：`def _ensure_schema(app):`（定义行）与
                #: `create_app()` 里的调用行。闸位窗口必须相对**调用行**，不是定义行。
                out.setdefault('ensure_schema_call_line', i)
            if ANCHOR_BEFORE_SCHEMA in line and i > 150:
                out.setdefault('ensure_schema_line', i)
            if GUARD_MARKER + '(' in line and not line.lstrip().startswith('#'):
                out.setdefault('guard_inserted_line', i)
            # `db.create_all()` 有多个命中点（`_ensure_schema` 内是真正的破坏点；
            # 另有 `init-db` CLI 命令内的同名调用）⇒ 只认 `_ensure_schema` 函数体内的那一个
            if ANCHOR_DB_CREATE_ALL in line and out.get('ensure_schema_def_line', 10 ** 9) < i:
                out.setdefault('create_all_line', i)
                out.setdefault('create_all_in_ensure_schema', True)
        out['create_all_sites'] = [i for i, l in enumerate(lines, start=1)
                                   if ANCHOR_DB_CREATE_ALL in l]
        out['app_init_total_lines'] = len(lines)
    if os.path.exists(cfg_py):
        lines = read_text(cfg_py).splitlines()
        for i, line in enumerate(lines, start=1):
            if ANCHOR_NORMALIZE_RETURN in line:
                out.setdefault('normalize_return_line', i)
        out['config_total_lines'] = len(lines)
    return out


def inject_guards(root):
    """把参考实现注入两个落点（**探针内部副本**，绝不改生产代码）。

    注入 layout（**关键**：不能把模块级代码插进函数体中间）：
    * `app/__init__.py`：调用点插在 `app.config['TEMP_FOLDER'] = ...` 之后（此刻仍在
      `create_app()` 体内、`_ensure_schema(app)` 之前）；参考实现追加到**文件末尾**（模块级）。
    * `config.py`：参考实现追加到**文件末尾**；调用点插在 URL 归一化内。
    * `config.py` 归一化内的调用点若用 `_r2_c07_normalize_probe(url)` 的写法，则在
      `import os` 行之后补一个薄包装（不改 return 语句，所以不会切成死代码）。

    注入是幂等的：已含标记的文件跳过并如实登记为 `skipped_marker_present`。
    """
    report = {'root': rel(root), 'head_sha256': {}, 'sites': [], 'injected': False}
    sites = [
        ('app/__init__.py', ANCHOR_AFTER_CONFIG, GUARD_CALL_APP, '',
         'Config 加载后、_ensure_schema 前'),
        ('config.py', ANCHOR_NORMALIZE_RETURN, GUARD_CALL_CONFIG, GUARD_CALL_CONFIG_HELPER,
         '_normalize_database_url 内'),
    ]
    for relpath, anchor, call_block, tail_helper, note in sites:
        path = os.path.join(root, relpath)
        row = {'file': relpath, 'anchor': anchor, 'anchor_found': False, 'note': note,
               'call_block': call_block, 'layout': 'call_at_anchor + definitions_at_eof'}
        if not os.path.exists(path):
            row['skipped'] = 'file_missing'
            report['sites'].append(row)
            continue
        text = read_text(path)
        row['sha256_before'] = hashlib.sha256(text.encode('utf-8')).hexdigest().upper()
        report['head_sha256'][relpath] = row['sha256_before']
        if GUARD_MARKER in text:
            row['skipped'] = 'skipped_marker_present'
            report['sites'].append(row)
            continue
        if anchor not in text:
            row['skipped'] = 'anchor_not_found'
            report['sites'].append(row)
            continue
        row['anchor_found'] = True
        lines = text.splitlines(keepends=True)
        line_no = next(i for i, l in enumerate(lines, 1)
                       if anchor in l and not l.lstrip().startswith('#'))
        row['anchor_line'] = line_no
        indent = lines[line_no - 1][:len(lines[line_no - 1]) - len(lines[line_no - 1].lstrip())]
        call_lines = [indent + pl for pl in call_block.strip('\n').split('\n')]
        new_text = ''.join(lines[:line_no] + [pl + '\n' for pl in call_lines] + lines[line_no:])
        #: 参考实现（模块级）追加到文件末尾 —— 绝不插入函数体中间
        new_text = new_text.rstrip('\n') + '\n' + REFERENCE_GUARD_SOURCE.lstrip('\n') + '\n'
        if tail_helper:
            #: 薄包装放在 `import os` 之后，供归一化内的调用点使用（函数名在调用时绑定）
            helper_lines = new_text.split('\n')
            idx = next((i for i, l in enumerate(helper_lines) if l.startswith('import os')), 0)
            helper_lines = helper_lines[:idx + 1] + tail_helper.strip('\n').split('\n') + \
                helper_lines[idx + 1:]
            new_text = '\n'.join(helper_lines)
        if REFERENCE_GUARD_SOURCE.lstrip('\n').split('\n')[-2] not in new_text:
            raise RuntimeError('注入自检失败：参考实现未完整落到 %s' % relpath)
        write_text(path, new_text)
        row['sha256_after'] = hashlib.sha256(new_text.encode('utf-8')).hexdigest().upper()
        row['guard_assert_present'] = GUARD_MARKER in new_text
        report['sites'].append(row)
        report['injected'] = True
    app_py = os.path.join(root, 'app', '__init__.py')
    if os.path.exists(app_py):
        report['guard_after_inject'] = guard_present(root)
        after = locate_anchors(root)
        sd = after.get('ensure_schema_def_line')
        ca = after.get('create_all_line')
        call_line = after.get('ensure_schema_call_line')
        gline = after.get('guard_inserted_line')
        ac = after.get('after_config_line')
        #: 判据（**同一函数体内**的行序，不是文件全局行序）：闸的调用行在
        #: `_ensure_schema(app)` 调用行之前 ⇒ 运行时先撞闸、后进 schema 变更
        report['ensure_schema_def_line_after'] = sd
        report['ensure_schema_call_line_after'] = call_line
        report['guard_call_line_after'] = gline
        report['create_all_line_after'] = ca
        report['guard_inserted_before_schema'] = bool(
            None not in (ac, gline, call_line) and ac < gline < call_line)
    return report


# ------------------------------------------------------------- 子进程场景执行体
CHILD_SCENARIOS = {
    # 场景 key -> (说明, 是否需要真实库 URI, 授权环境变量)
    'negative-real-db': ('C-07-a 负例：DATABASE_URL 指向真实库', 'real', {}),
    'positive-copy': ('C-07-b 正例：指向副本（同目录同名 app.db）', 'copy', {}),
    'positive-twin': ('C-07-b 对照：指纹=真实库但身份不同的另一文件', 'twin', {}),
    'authorize-env': ('C-07-c 授权通道①：WMS_ALLOW_REAL_DB=1', 'real',
                      {'WMS_ALLOW_REAL_DB': '1'}),
    'authorize-ro': ('C-07-c 授权通道②：只读 URI（mode=ro）指向真实库', 'real-ro', {}),
    'control-copy-noauth-copy': ('阴性对照：无闸时副本也放行（证明闸不是恒假）', 'copy', {}),
    'preflight': ('环境预检：Config 读到的 URI 与落点可定位', 'real', {}),
}


def run_child_scenario(kind, db_path, real_db, inject, repo_root, timeout, db_source=None,
                       auth_env=None):
    """在**新解释器**里跑单个场景，解析 `RESULT_MARKER` 后的 JSON。

    用「临时文件重定向」而非管道捕获输出（本沙箱拒绝管道；`_env.run_child` 同法）。
    `inject=True` ⇒ 子进程先把**参考实现**注入被测仓库（探针内部副本，不改生产代码）；
    判据层的「规格」场景一律注入，「现状」场景一律不注入（对照）。
    `auth_env` ⇒ 显式授权通道的环境变量（只有该场景传；其余场景显式清空，防环境态污染）。
    """
    args = [os.path.abspath(__file__), '--child', '--kind', kind, '--db', db_path,
            '--real-db', real_db, '--repo-root', repo_root]
    if inject:
        args.append('--inject-guards')
    if db_source:
        args += ['--db-source', db_source]
    extra_env = dict(auth_env or {})
    #: 未授权的场景必须显式**清空**授权开关，否则父/子环境里残留的开关会让负例假绿
    extra_env.setdefault(ALLOW_ENV, '')
    out = _env.run_child(args, cwd=repo_root, timeout=timeout,
                         extra_env=extra_env, label='c07-child-' + kind)
    payload = None
    for line in (out['stdout'] + '\n' + out['stderr']).splitlines():
        if line.startswith(RESULT_MARKER):
            try:
                payload = json.loads(line[len(RESULT_MARKER):])
            except Exception as e:
                payload = {'parse_error': f'{e.__class__.__name__}: {e}'}
    out['payload'] = payload
    out['label'] = kind
    return out


#: 破坏向量场景的 kind 名：先从副本拆掉一个 `_ENSURED_COLUMNS` 登记列，再跑启动链。
#: 它不判 C-07（判据层不含它），只提供「启动链确实会写它连上的库」的行为实证。
DAMAGE_KIND = 'damage-vector'


def _sqlite_columns(path, table):
    con = sqlite3.connect(path)
    try:
        return sorted(r[1] for r in con.execute('pragma table_info("%s")' % table))
    finally:
        con.close()


def _prepare_damage(db_path, table='products', column='sellable_as_part'):
    """在**副本**上拆掉一个登记列（`_ENSURED_COLUMNS['products'] = [('sellable_as_part', ...)]`）。

    选它的理由：真实 `app.db` 实测该列**存在**（探针 `pragma table_info` 口径），
    因此拆掉后启动链的 `_ensure_schema` 必须补回来 —— 否则「启动不写库」就只是一句推断。
    """
    info = {'table': table, 'column': column, 'dropped': False}
    try:
        con = sqlite3.connect(db_path)
        try:
            cols = {r[1] for r in con.execute('pragma table_info("%s")' % table)}
            info['column_present_before'] = column in cols
            if column in cols:
                con.execute('ALTER TABLE "%s" DROP COLUMN "%s"' % (table, column))
                con.commit()
                info['dropped'] = True
        finally:
            con.close()
    except Exception as e:                        # noqa: BLE001
        info['error'] = f'{e.__class__.__name__}: {e}'
    info['columns_after_drop'] = _sqlite_columns(db_path, table)
    return info


def _check_damage(db_path, table='products', column='sellable_as_part'):
    """启动链跑完后复核：登记列是否被 `_ensure_schema` **真的补回**（= 真的写了库）。"""
    cols = _sqlite_columns(db_path, table)
    return {'table': table, 'column': column, 'column_present_after': column in cols,
            'repaired_by_startup_chain': column in cols,
            'columns_after': cols}


def _attach_sql_recorder(sink):
    """记录启动链实际执行的 SQL（DDL 取证）。

    为什么不挂在 `db.engine` 上：`flask_sqlalchemy` 的 `db.engine` 在**应用上下文之外**访问
    会抛错，而此时 `db` 还没绑定到 app（实测：静默失败 ⇒ DDL 日志恒空，等于没有证据）。
    ⇒ 改成包 `sqlalchemy.engine.Connection.execute` 类方法，覆盖**所有**引擎、无需上下文。
    """
    try:
        from sqlalchemy.engine import Connection
        orig = Connection.execute

        def patched(self, statement, *a, **kw):
            try:
                sink.append(str(statement)[:400])
            except Exception:                     # noqa: BLE001
                pass
            return orig(self, statement, *a, **kw)

        Connection.execute = patched
        return orig
    except Exception as e:                        # noqa: BLE001
        sink.append('recorder_error: %s: %s' % (e.__class__.__name__, e))
        return None


def _detach_sql_recorder(token):
    if token is not None:
        try:
            from sqlalchemy.engine import Connection
            Connection.execute = token
        except Exception:                         # noqa: BLE001
            pass
    return None


def child_main(args):
    """子进程入口：构造一次 `create_app()` 并观测「抛错点相对 db.create_all 的位置」。"""
    repo_root = os.path.abspath(args.repo_root or REPO_ROOT)
    real_db = os.path.abspath(args.real_db)
    db_path = args.db
    result = {'kind': args.kind, 'repo_root': rel(repo_root), 'real_db': rel(real_db),
              'db_url_kind': args.kind, 'python': sys.executable}
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    #: 注入副本里的 `R2_C07_REAL_DB`（= `<repo>/app.db`）必须存在，否则 `samefile` 恒 False，
    #: 闸会「合法地」放行 —— 那是**探针夹具的失误**，不是闸的缺陷。先把库文件补进去。
    if args.inject_guards and args.db_source and not str(db_path).startswith('sqlite:'):
        dest = os.path.join(repo_root, 'app.db')
        if os.path.abspath(str(db_path)) != os.path.abspath(dest) and not os.path.exists(dest):
            shutil.copy2(args.db_source, dest)
            result['db_copied_into_injected_repo'] = rel(dest)
    os.environ['DATABASE_URL'] = db_path if db_path.startswith('sqlite:') else sqlite_uri(db_path)
    # 关掉种子自举（少一条写路径；`seed.db` 不存在即空操作，这里显式钉死）
    os.environ.setdefault('SEED_SQLITE_PATH', os.path.join(
        _env.tmp_dir('c07-seed-absent'), 'no_such_seed.db'))
    result['env_database_url'] = os.environ['DATABASE_URL']

    result['guard_present_before'] = guard_present(repo_root)   # 注入**之前**的原样状态
    inject_report = None
    if args.inject_guards and not result['guard_present_before']:
        inject_report = inject_guards(repo_root)
    result['guard_present_after'] = guard_present(repo_root)
    result['inject'] = inject_report
    result['real_db_sha256_before'] = sha256(real_db)

    #: 破坏向量场景：先从副本里**拆掉一个 `_ENSURED_COLUMNS` 登记列**，再跑启动链。
    #: 若启动链补列成功 ⇒ 「应用启动确实会写它连上的那个库」从推断升级为**行为实证**。
    if args.kind == DAMAGE_KIND and not str(db_path).startswith('sqlite:'):
        result['damage_setup'] = _prepare_damage(db_path)

    app = None
    error = None
    create_calls = {'n': 0}
    sql_log = []
    sql_recorder = None

    try:
        import app as app_pkg                     # noqa: F401  —— 先建包
        from app import db as db_obj
        orig_create_all = db_obj.create_all

        def counting_create_all(*a, **kw):
            create_calls['n'] += 1
            return orig_create_all(*a, **kw)

        db_obj.create_all = counting_create_all
        sql_recorder = _attach_sql_recorder(sql_log)
        app = app_pkg.create_app()
    except BaseException as e:                    # noqa: BLE001 —— 负例的「抛错」是期望结果
        error = {'type': e.__class__.__name__, 'message': str(e)[:600],
                 'module': getattr(e.__class__, '__module__', '')}

    _detach_sql_recorder(sql_recorder)
    if args.kind == DAMAGE_KIND and not str(db_path).startswith('sqlite:'):
        result['damage_check'] = _check_damage(db_path)
    result['create_all_calls'] = create_calls['n']
    result['ddl_statements'] = [s for s in sql_log
                                if s.lstrip().upper().startswith(('ALTER', 'CREATE', 'DROP'))]
    result['error'] = error
    result['startup_ok'] = app is not None and error is None
    if app is not None:
        try:
            result['config_uri'] = app.config.get('SQLALCHEMY_DATABASE_URI')
            result['env_matches_config'] = (
                os.path.basename(str(result['config_uri']).split('?')[0]) ==
                os.path.basename(str(result['env_database_url']).split('?')[0]))
            result['route_rules'] = len(list(app.url_map.iter_rules()))
        except Exception as e:                    # noqa: BLE001
            result['post_checks_error'] = f'{e.__class__.__name__}: {e}'
    result['real_db_sha256_after'] = sha256(real_db)
    result['real_db_unchanged'] = (
        result['real_db_sha256_before'] == result['real_db_sha256_after'])
    result['real_db_sha256_pinned'] = (_env.REAL_DB_SHA256_EXPECTED
                                       if os.path.samefile(real_db, _env.REAL_DB) else None)
    # 目标库自身指纹（正例的「零副作用」自证；负例下根本没连上）
    if os.path.exists(str(db_path).split('?')[0].replace('file:', '')):
        try:
            result['target_bytes'] = os.path.getsize(
                str(db_path).split('?')[0].replace('file:', ''))
        except OSError:
            pass
    if result['guard_present_after']:
        result['guard_source'] = ('injected' if inject_report and inject_report.get('injected')
                                  else 'present')
    else:
        result['guard_source'] = 'absent'
        result['guard_absent'] = True
    print(RESULT_MARKER + json.dumps(result, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------ 父进程编排
def build_scenarios(real_db, copy_path, twin_path, repo_pristine, repo_injected, expect_rules):
    """场景表（父进程编排用）。

    `inj=True` 的场景在**注入用仓库副本**（`repo_injected`）上跑，`inj=False` 的在
    **未注入的原样仓库**（`repo_pristine`）上跑 —— 两者必须是**不同目录**，否则先跑的
    注入场景会把闸写进仓库，后跑的「现状」场景就不再是「未注入」了（自检实测踩到）。

    `probe_kind` 只有两类：
    * `negative-real-db` —— **被测仓库自己的 app.db**（即闸眼中的真实库）⇒ 必须被拒；
    * `copy` / `twin` / `authorize-*` —— 指向别处的库文件 ⇒ 必须放行。

    注意：负例的 URL 必须落在**该场景所用仓库副本**的 `app.db` 上 —— 注入副本的
    `R2_C07_REAL_DB` 指向它自己的 `<repo_injected>/app.db`，拿原样仓库的同名文件去比
    `samefile` 会得到 False（两个不同文件），闸会「合法地」（其实也是正确地）放行。
    """
    def resolve(anchor, repo, kind):
        """`anchor` ∈ {own-real-db, copy, twin, damage} -> 实际 URL 字符串。"""
        if kind == 'authorize-ro':
            #: 授权通道②用「显式只读 URI」形态；指向被测仓库自己的 app.db（= 闸眼中的真实库）
            return sqlite_uri_ro(os.path.join(repo, os.path.basename(real_db)))
        if anchor == 'damage':
            #: 破坏向量用**独立**的副本（会被 DDL 改写，绝不能污染其它场景共享的副本）
            return os.path.join(os.path.dirname(copy_path), 'damage-copy',
                                os.path.basename(real_db))
        if anchor == 'own-real-db':
            return os.path.join(repo, os.path.basename(real_db))
        return anchor

    def auth(kind):
        """只有环境变量授权通道传开关；其余场景由 `run_child_scenario` 显式清空。"""
        return {ALLOW_ENV: '1'} if kind == 'authorize-env' else None

    rows = [
        ('preflight', None, 'own-real-db', False, repo_pristine,
         '环境预检：锚点行号 + 被测仓库是否已有闸（只读源码，父进程侧执行）'),
        ('negative-injected', 'negative-real-db', 'own-real-db', True, repo_injected,
         'C-07-a 规格：注入参考实现后，指向真实库必须启动失败'),
        ('negative-current', 'negative-real-db', 'own-real-db', False, repo_pristine,
         'C-07-a 现状：未注入的原样生产代码指向真实库是否被拒'),
        ('positive-copy', 'positive-copy', copy_path, True, repo_injected,
         'C-07-b 正例：副本（含同名 app.db）必须启动成功'),
        ('positive-twin', 'positive-twin', twin_path, True, repo_injected,
         'C-07-b 对照：指纹与真实库相同、身份不同 => 必须放行（不得用指纹判定）'),
        ('authorize-env', 'authorize-env', 'own-real-db', True, repo_injected,
         'C-07-c 通道①：WMS_ALLOW_REAL_DB=1 必须放行'),
        ('authorize-ro', 'authorize-ro', 'own-real-db', True, repo_injected,
         'C-07-c 通道②：只读 URI（mode=ro）必须放行'),
        ('control-copy-noauth', 'control-copy-noauth-copy', copy_path, False, repo_pristine,
         '阴性对照：无闸时副本放行 ⇒ 证明负例报红来自闸而不是「什么都不能跑」'),
        ('damage-vector', DAMAGE_KIND, 'damage', False, repo_pristine,
         '破坏向量实证：先在副本上拆掉一个 _ENSURED_COLUMNS 登记列，再跑启动链 '
         '⇒ 若被补回，则「启动链确实会写它连上的库」成立'),
    ]
    return rows, resolve, auth


def guard_off_preflight(root=REPO_ROOT):
    """预检（父进程侧）：锚点行号 + 生产代码是否已有闸——只读源码，**不 import app**。

    为什么不许 import：`import app` 会执行 `config.Config` 的类体并读 `DATABASE_URL`，
    一旦环境里没设该变量，`_normalize_database_url(None)` 就会兜到真实库路径（`config.py:8-9`）。
    预检只做**静态行号取证**，所以没有任何连接真实库的机会。
    """
    anchors = locate_anchors(root)
    present = guard_present(root)
    create_all_line = anchors.get('create_all_line')
    schema_def_line = anchors.get('ensure_schema_def_line')
    anchors['create_all_after_schema_def'] = bool(
        create_all_line is not None and schema_def_line is not None
        and create_all_line > schema_def_line)
    anchors['guard_present_in_root'] = present
    return {
        'root': rel(root),
        'anchors': anchors,
        'guard_present_in_production': present,
        'expected_guard_window': 'config_load_line < guard < ensure_schema_line',
        'schema_line_matches_frozen': anchors.get('ensure_schema_line') == TARGET_SCHEMA_LINE,
        'create_all_in_ensure_schema': anchors.get('create_all_after_schema_def', False),
    }


def evaluate(scenarios, real_db_before, real_db_after, copy_fp, twin_fp,
             expect_rules=ROUTE_RULES_BASELINE, real_db_is_env=True):
    """把三判据写成断言（判据层只认规格；现状缺口单独登记，不污染判据层）。"""
    A = []

    def add(aid, title, expected, actual, verdict, evidence='', evidence_kind='behavior_verified',
            note=''):
        A.append({'id': aid, 'title': title, 'expected': expected, 'actual': actual,
                  'verdict': verdict, 'evidence': evidence, 'evidence_kind': evidence_kind,
                  'note': note})

    neg = scenarios['negative-injected']['payload'] or {}
    cur = scenarios['negative-current']['payload'] or {}
    pos = scenarios['positive-copy']['payload'] or {}
    twin = scenarios['positive-twin']['payload'] or {}
    aenv = scenarios['authorize-env']['payload'] or {}
    aro = scenarios['authorize-ro']['payload'] or {}
    ctl = scenarios['control-copy-noauth']['payload'] or {}
    pre = scenarios['preflight']['payload']

    def err_of(row):
        return row.get('error') or {}

    # ---------------------------------------------------------------- C-07-a 规格
    a_ok = (err_of(neg).get('type') == 'RuntimeError'
            and neg.get('create_all_calls') == 0
            and not neg.get('startup_ok'))
    add('C-07-a(spec)',
        'C-07-a 负例：注入硬闸后，DATABASE_URL 指向真实库 => 启动必须失败，'
        '且必须在 db.create_all() 之前抛错',
        {'error_type': 'RuntimeError', 'create_all_calls': 0, 'startup_ok': False},
        {'error_type': err_of(neg).get('type'),
         'error_message': (err_of(neg).get('message') or '')[:200],
         'create_all_calls': neg.get('create_all_calls'),
         'startup_ok': neg.get('startup_ok'),
         'guard_source': neg.get('guard_source'),
         'real_db_unchanged': neg.get('real_db_unchanged')},
        'passed' if a_ok else 'failed',
        evidence=rel(scenarios['negative-injected']['out_file']),
        note='抛错点相对 create_all 的位置 = 同一子进程内 create_all 计数 0（A-84 注入式判据）')

    msg = str(err_of(neg).get('message') or '')
    readable = bool(msg) and ('app.db' in msg) and (
        'WMS_ALLOW_REAL_DB' in msg or 'mode=ro' in msg or '副本' in msg)
    add('C-07-a(message)',
        'C-07-a 附：拒绝必须给出可读原因（含目标路径与授权通道提示），不得只抛裸断言',
        {'contains_app.db': True, 'contains_auth_hint': True},
        {'message': msg[:300], 'readable': readable},
        'passed' if readable else 'failed',
        evidence=rel(scenarios['negative-injected']['out_file']),
        evidence_kind='content_implementation')

    # ---------------------------------------------------------------- C-07-a 现状
    if cur.get('guard_absent'):
        cur_state = 'blocked_no_guard'
        cur_verdict = 'failed'
        cur_note = ('现状缺口：当前生产代码无应用级硬闸 ⇒ 指向真实库的启动**成功**且 '
                    'db.create_all() 已执行（create_all_calls=%s）⇒ 破坏发生在拒绝之前'
                    % cur.get('create_all_calls'))
    elif err_of(cur).get('type') == 'RuntimeError' and cur.get('create_all_calls') == 0:
        cur_state = 'rejected'
        cur_verdict = 'passed'
        cur_note = '当前生产代码已含硬闸且抛错点正确'
    else:
        cur_state = 'unexpected'
        cur_verdict = 'failed'
        cur_note = '现状既非「无闸」也非「正确拒绝」，需人工判读'
    add('C-07-a(current)',
        'C-07-a 现状：**未注入**时当前生产代码对「指向真实库」的处置（本项是缺口登记，'
        '不是规格判据）',
        {'state': 'rejected（应当）'},
        {'state': cur_state, 'startup_ok': cur.get('startup_ok'),
         'create_all_calls': cur.get('create_all_calls'),
         'guard_present_in_production': pre['guard_present_in_production']},
        cur_verdict, evidence=rel(scenarios['negative-current']['out_file']),
        note=cur_note)

    if cur_state == 'blocked_no_guard':
        # 阴性对照：无闸时副本放行 —— 证明负例报红来自闸，而不是环境跑不动应用
        ctl_ok = bool(ctl.get('startup_ok')) and ctl.get('create_all_calls', 0) >= 1
        add('C-07-a(control)',
            '阴性对照：同一份生产代码、同一份副本，无闸时**能**启动并走到 create_all '
            '=> 证明上一条报红来自「缺闸」而非环境损坏',
            {'startup_ok': True, 'create_all_calls': '>=1'},
            {'startup_ok': ctl.get('startup_ok'),
             'create_all_calls': ctl.get('create_all_calls')},
            'passed' if ctl_ok else 'failed',
            evidence=rel(scenarios['control-copy-noauth']['out_file']))

    # 「破坏已经发生」的实证：启动链对「它连上的那个库」**真的写了 DDL**
    #: 无条件产出（仓库已含闸时改看阴性对照场景）；它在 GAP_ASSERTION_IDS 里，不进判据层
    dmg = scenarios['damage-vector']['payload'] or {}
    dsetup = dmg.get('damage_setup') or {}
    dcheck = dmg.get('damage_check') or {}
    ddl = [s for s in (dmg.get('ddl_statements') or []) if 'ALTER' in s.upper()]
    dmg_ev = scenarios['damage-vector']
    damage = bool(dsetup.get('dropped')) and bool(dcheck.get('repaired_by_startup_chain'))
    add('C-07-a(damage)',
        'C-07-a 附证：先在副本上拆掉一个 `_ENSURED_COLUMNS` 登记列（%s.%s），再跑启动链 —— '
        '该列被 `_ensure_schema` **补回** ⇒ 「应用启动会写它连上的那个库」是行为事实，'
        '不是推断；闸缺失时这一个库就是真实库（`_test_bootstrap.py:41` 的断言必然太晚）'
        % (dsetup.get('table'), dsetup.get('column')),
        {'dropped': True, 'repaired_by_startup_chain': True,
         'ddl_contains_ALTER_TABLE_ADD_COLUMN': True},
        {'table': dsetup.get('table'), 'column': dsetup.get('column'),
         'dropped': dsetup.get('dropped'),
         'column_present_after': dcheck.get('column_present_after'),
         'repaired_by_startup_chain': dcheck.get('repaired_by_startup_chain'),
         'ddl_alter_count': len(ddl),
         'ddl_sample': ddl[:2],
         'target_path': dmg_ev.get('target_path'),
         'target_sha256_before': (dmg_ev.get('target_sha256_before') or '')[:16] + '...',
         'target_sha256_after': (dmg_ev.get('target_sha256_after') or '')[:16] + '...',
         'target_modified': dmg_ev.get('target_modified')},
        'passed' if damage else 'failed',
        evidence=rel(dmg_ev['out_file']) if dmg_ev.get('out_file') else '',
        note='目标库是**独立副本**（探针绝不拿真实库做这一步）；真实库 SHA256 见 C-07-c(db)')

    # ---------------------------------------------------------------- C-07-b
    #: 路由数判据只在「像真实应用」的仓库上钉（合成自检夹具只有几条路由 ⇒ 只判启动成功）
    pos_rules = pos.get('route_rules')
    rules_pinned = isinstance(pos_rules, int) and pos_rules > 50
    rules_ok = (pos_rules == expect_rules) if rules_pinned else True
    b_ok = (pos.get('startup_ok') is True and not err_of(pos) and rules_ok)
    add('C-07-b(copy)',
        'C-07-b 正例：DATABASE_URL 指向副本（副本与真实库**同名** app.db）=> 启动必须成功，'
        '且路由数 = %d（route_inventory 口径）' % expect_rules,
        {'startup_ok': True, 'route_rules': expect_rules, 'error': None},
        {'startup_ok': pos.get('startup_ok'), 'route_rules': pos_rules,
         'rules_pinned': rules_pinned, 'error': err_of(pos),
         'config_uri': pos.get('config_uri')},
        'passed' if b_ok else 'failed',
        evidence=rel(scenarios['positive-copy']['out_file']),
        note='副本名也是 app.db ⇒ 通过「同名」情形，证明闸不是按文件名判的；'
             '路由数在非真实仓库（合成自检夹具）上不钉，只判启动成功')

    twin_ok = bool(twin.get('startup_ok')) and twin_fp == real_db_before
    add('C-07-b(twin)',
        'C-07-b 对照：另一目录的逐字节副本（指纹 = 真实库钉死值、身份不同）=> 必须放行'
        '（指纹不得作为拒绝条件）',
        {'startup_ok': True, 'twin_sha256': real_db_before},
        {'startup_ok': twin.get('startup_ok'), 'twin_sha256': twin_fp,
         'error': twin.get('error')},
        'passed' if twin_ok else 'failed',
        evidence=rel(scenarios['positive-twin']['out_file']),
        note='副本是 shutil.copy2 逐字节副本 ⇒ 指纹必然等于真实库；用指纹拒绝会误杀合法副本')

    # ---------------------------------------------------------------- C-07-c
    c_env_ok = bool(aenv.get('startup_ok')) and aenv.get('create_all_calls', 0) >= 1
    add('C-07-c(env)',
        'C-07-c 授权通道①：DATABASE_URL 指向真实库 + WMS_ALLOW_REAL_DB=1 => 必须放行',
        {'startup_ok': True, 'create_all_calls': '>=1'},
        {'startup_ok': aenv.get('startup_ok'), 'create_all_calls': aenv.get('create_all_calls'),
         'error': aenv.get('error')},
        'passed' if c_env_ok else 'failed',
        evidence=rel(scenarios['authorize-env']['out_file']),
        note='授权=允许连，不等于允许写；真库 SHA256 见 C-07-c(db)')

    c_ro_ok = bool(aro.get('startup_ok')) and aro.get('create_all_calls', 0) >= 1
    add('C-07-c(ro)',
        'C-07-c 授权通道②：只读 URI（mode=ro）指向真实库 => 必须放行（复用 fixtures.py:79-80 口径）',
        {'startup_ok': True, 'create_all_calls': '>=1'},
        {'startup_ok': aro.get('startup_ok'), 'create_all_calls': aro.get('create_all_calls'),
         'error': aro.get('error'), 'config_uri': aro.get('config_uri')},
        'passed' if c_ro_ok else 'failed',
        evidence=rel(scenarios['authorize-ro']['out_file']),
        note='mode=ro 由 sqlite 强制：即便走到 create_all 也无写入能力')

    db_target_is_env = real_db_is_env
    db_ok = (real_db_after == real_db_before
             and (not db_target_is_env or real_db_before == _env.REAL_DB_SHA256_EXPECTED))
    add('C-07-c(db)',
        '不变量：三判据全程真实库 app.db SHA256 不变（被测目标=仓库 app.db 时须 = 钉死值）',
        {'sha256_before': '= sha256_after',
         'pinned_when_real': _env.REAL_DB_SHA256_EXPECTED},
        {'before': real_db_before, 'after': real_db_after,
         'target_is_env_real_db': db_target_is_env,
         'pinned_match': real_db_before == _env.REAL_DB_SHA256_EXPECTED},
        'passed' if db_ok else 'failed',
        evidence='探针 stdout real_db_before/after + _env.real_db_status',
        note='含授权通道①（真实库 URI + 授权）下的实测：未变')

    # ---------------------------------------------------------------- 落点约束
    a1 = (pre.get('anchors_injected_after') or pre['anchors'])
    cl = a1.get('config_load_line')
    ac = a1.get('after_config_line')
    es = a1.get('ensure_schema_call_line') or a1.get('ensure_schema_line')
    guard_pos = a1.get('guard_inserted_line')
    #: 窗口判据：`Config` 加载之后 + `_ensure_schema(app)` **调用行**之前 + 后者在闸函数
    #: 定义（模块级）之后 —— 三者同时成立才算「抛错点落在破坏点之前」。
    #: `config_load_line`（`app.config.from_object(Config)`）在合成夹具里可能没有同形行，
    #: 此时以 `after_config_line`（`app.config['TEMP_FOLDER'] = ...`，仍在 Config 加载之后）为准。
    within = (None not in (ac, guard_pos, es) and ac < guard_pos < es
              and (cl is None or cl < guard_pos))
    window_ok = bool(a1.get('create_all_after_schema_def')) and within
    inj = neg.get('inject') or {}
    sites = inj.get('sites') or []
    if inj.get('injected'):
        #: 有注入 ⇒ 必须证明「闸的调用行插在 _ensure_schema 调用行之前」
        inj_ok = bool(inj.get('guard_inserted_before_schema')) and bool(inj.get('guard_after_inject'))
    elif inj:
        #: 未注入是因为仓库里已有闸（幂等跳过）⇒ 由「窗口 + 闸确实存在」承担
        inj_ok = bool(window_ok) and all(s.get('skipped') == 'skipped_marker_present'
                                         for s in sites) and bool(sites)
    else:
        #: 仓库已有闸（非注入路径，如 --guard-source present）⇒ 由「窗口 + 闸确实存在」承担
        inj_ok = bool(window_ok) and bool(a1.get('guard_present_in_root'))
    add('C-07-a(placement)',
        '落点约束：闸位必须在 app.config.from_object(Config) 之后、_ensure_schema(app) 之前'
        '（或 config.py 的 URL 归一化内）',
        {'window': 'config_load < guard <= ensure_schema(%d)' % TARGET_SCHEMA_LINE,
         'injected_before_schema': True},
        {'anchors': a1, 'window_ok': window_ok,
         'ensure_schema_def_line_after_inject': inj.get('ensure_schema_def_line_after'),
         'guard_inserted_before_schema': inj.get('guard_inserted_before_schema'),
         'guard_present_in_injected_repo': a1.get('guard_present_in_root'),
         'injection_sites': [{'file': s['file'], 'anchor_line': s.get('anchor_line'),
                              'skipped': s.get('skipped')} for s in sites]},
        'passed' if (window_ok and inj_ok) else 'failed',
        evidence=rel(scenarios['negative-injected']['out_file']),
        evidence_kind='content_implementation',
        note='注入是探针内部行为，仅证明规格可执行；实现落地后请改用 --guard-source present')

    #: 判据层 = 规格 + 正例 + 授权 + 落点 + 不变量（现状缺口单列，不参与 exit code）
    criteria = [r for r in A if r['id'] not in GAP_ASSERTION_IDS]
    failed = [r['id'] for r in criteria if r['verdict'] != 'passed']
    return A, failed


def main():
    ap = argparse.ArgumentParser(description='C-07 应用级真实库硬闸：可执行规格 + 三判据探针')
    ap.add_argument('--selftest', action='store_true',
                    help='工具自检：用合成仓库对照，证明探针在「闸缺失」时必报红')
    ap.add_argument('--real-db', default=DEFAULT_REAL_DB,
                    help='真实库路径（默认仓库 app.db；自检时指向合成库）')
    ap.add_argument('--repo-root', default=REPO_ROOT, help='被测仓库根（默认本仓库）')
    ap.add_argument('--repo-injected', default=None,
                    help='注入用仓库副本根（缺省=在 run 隔离目录内自动复制一份）')
    ap.add_argument('--db-source', default=None,
                    help='注入副本内 app.db 的复制来源（保证 R2_C07_REAL_DB 存在）')
    ap.add_argument('--guard-source', default='auto', choices=['auto', 'inject', 'present'],
                    help='auto=生产已含闸则用之，否则注入参考实现')
    ap.add_argument('--expect-rules', type=int, default=ROUTE_RULES_BASELINE,
                    help='C-07-b 正例的路由数期望（route_inventory 口径，默认 271）')
    ap.add_argument('--strict-current-guard', action='store_true',
                    help='要求当前生产代码已含硬闸（实现落地后才加）')
    ap.add_argument('--timeout', type=int, default=600, help='单场景子进程超时秒')
    ap.add_argument('--json-out', default=None, help='额外把机读结果写到该路径')
    ap.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--kind', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--db', default=None, help=argparse.SUPPRESS)
    ap.add_argument('--inject-guards', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.selftest:
        return selftest(args)
    if args.child:
        return child_main(args)
    return full_run(args)


def _mk_repo(tag, guard='absent', real_db_name='app.db'):
    """合成被测仓库（自检用）：结构与真实启动链同形（含 `db.create_all()` 调用点），
    但不含任何生产代码、不依赖 sqlite3/Flask 之外的东西。"""

    root = os.path.join(_env.tmp_dir('selftest'), tag)
    if os.path.exists(root):
        shutil.rmtree(root, ignore_errors=True)
    os.makedirs(os.path.join(root, 'app'), exist_ok=True)
    os.makedirs(os.path.join(root, 'uploads'), exist_ok=True)
    guard_src = ''
    call_src = ''
    if guard == 'present':
        #: 模拟「实现已落地」：闸函数（模块级，追加在文件末尾）+ 在 `create_app` 里
        #: 已接上调用点（`34` §3.3 的主要落点）⇒ 探针不应再注入任何东西
        guard_src = REFERENCE_GUARD_SOURCE
        call_src = ("    _r2_c07_guard(app.config.get('SQLALCHEMY_DATABASE_URI'))\n")
    elif guard == 'broken':
        guard_src = '''

def _r2_c07_sqlite_path(uri):
    return None


def _r2_c07_guard(uri, allow_env='WMS_ALLOW_REAL_DB'):
    """故意写坏的闸：吞掉一切 => 负例不再被拒（自检的「探针必须报红」阳性样本）。"""
    try:
        return _r2_c07_sqlite_path(uri), None
    except Exception:
        return None, None
'''
        call_src = "    _r2_c07_guard(app.config.get('SQLALCHEMY_DATABASE_URI'))\n"
    app_py = '''"""合成被测 app（自检夹具，非生产代码）。"""
import os

from config import Config


def _ensure_schema(app):
    """与真实启动链同形：进入后第一步就是 db.create_all()。"""
    try:
        db.create_all()
    except Exception:
        # 只读 URI 场景下 create_all 会被 sqlite 拒（无法建表）；调用已被计数，够了
        pass


def bootstrap_if_empty(app):
    return None


def _seed_system_configs(app):
    return None


def create_app():
    import flask
    app = flask.Flask(__name__)
    app.config.from_object(_Cfg)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    temp_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
    os.makedirs(temp_folder, exist_ok=True)
    app.config['TEMP_FOLDER'] = temp_folder
''' + call_src + '''    with app.app_context():
        _ensure_schema(app)
        bootstrap_if_empty(app)
        _seed_system_configs(app)
        from _routes import bp
        app.register_blueprint(bp)
    return app


class _Cfg:
    SECRET_KEY = 'dev'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')


Config = _Cfg


class _Db:
    def create_all(self):
        pass


db = _Db()
''' + guard_src
    write_text(os.path.join(root, 'app', '__init__.py'), app_py)
    write_text(os.path.join(root, 'config.py'),
               'import os\n\n\ndef _normalize_database_url(url):\n'
               '    if not url:\n        return "sqlite:///x.db"\n'
               '    if url.startswith("postgres://"):\n'
               '        url = "postgresql://" + url[len("postgres://"):]\n'
               '    return url\n\n\n'
               'Config = object\n')
    write_text(os.path.join(root, '_routes.py'),
               'from flask import Blueprint\n\nbp = Blueprint("main", __name__)\n\n\n'
               '@bp.route("/ping")\ndef ping():\n    return "pong"\n')
    db_path = os.path.join(root, real_db_name)
    con = sqlite3.connect(db_path)
    con.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)')
    con.commit()
    con.close()
    return root, db_path


def full_run(args):
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    real_db = os.path.abspath(args.real_db)
    repo_root = os.path.abspath(args.repo_root)
    guard_present_now = guard_present(repo_root)
    if args.guard_source == 'present' and not guard_present_now:
        print('[c07] --guard-source present 但被测仓库无硬闸 => 无法执行判据层')
        print('[c07] 期望：先按 35 方案 4.2 落实现（app/** 本轮冻结），或改用 auto/inject')
        return 1
    inject = (args.guard_source == 'inject') or (
        args.guard_source == 'auto' and not guard_present_now)

    if os.path.samefile(real_db, _env.REAL_DB):
        real_before = _env.assert_real_db_untouched('r2_c07 开工')
    else:
        real_before = sha256(real_db)

    run_tmp = _env.tmp_dir('c07')
    os.makedirs(run_tmp, exist_ok=True)
    copy_path = os.path.join(run_tmp, 'app.db')
    shutil.copy2(real_db, copy_path)
    twin_path = os.path.join(run_tmp, 'twin-dir', 'app.db')
    os.makedirs(os.path.dirname(twin_path), exist_ok=True)
    shutil.copy2(real_db, twin_path)
    damage_path = os.path.join(run_tmp, 'damage-copy', 'app.db')
    os.makedirs(os.path.dirname(damage_path), exist_ok=True)
    shutil.copy2(real_db, damage_path)

    #: 两个**不同目录**的仓库副本：注入用 / 原样用。绝不在同一个目录上先注入再比「现状」。
    repo_pristine = copy_repo(repo_root, os.path.join(run_tmp, 'repo-pristine'))
    repo_injected = (os.path.abspath(args.repo_injected) if args.repo_injected
                     else copy_repo(repo_root, os.path.join(run_tmp, 'repo-injected')))

    print('=' * 78)
    print('[c07] C-07 应用级「拒绝连真实库」硬闸：可执行规格 + 三判据')
    print('[c07] run_id=%s  time=%s' % (_env.RUN_ID, started))
    print('[c07] repo=%s' % rel(repo_root))
    print('[c07] real_db=%s  sha256=%s' % (rel(real_db), real_before))
    print('[c07] guard_present_in_source=%s  guard_source=%s  inject=%s'
          % (guard_present_now, args.guard_source, inject))
    print('[c07] 口径：create_all_calls 由探针在同一子进程内包装 db.create_all 计数（A-84）')
    print('[c07] 注入用副本=%s 原样副本=%s' % (rel(repo_injected), rel(repo_pristine)))
    print('=' * 78)

    scenarios = {}
    scenario_rows, resolve_db, auth_env_for = build_scenarios(
        real_db, copy_path, twin_path, repo_pristine, repo_injected, args.expect_rules)
    #: 每个场景的**目标库文件**在跑前/跑后的指纹 —— 「破坏是否真的发生」要比指纹，不比感觉
    target_paths = {}
    for key, kind, db_anchor, inj, rr, desc in scenario_rows:
        if key == 'preflight' or kind == 'authorize-ro':
            continue
        target_paths[key] = resolve_db(db_anchor, rr, kind)
    target_before = {k: (sha256(p) if os.path.exists(p) else None)
                     for k, p in target_paths.items()}
    for key, kind, db_anchor, inj, rr, desc in scenario_rows:
        if key == 'preflight':
            pre = guard_off_preflight(repo_root)
            scenarios[key] = {'desc': desc, 'payload': pre, 'out_file': '(parent)'}
            print('  [PREFLIGHT] guard_present_in_source=%s '
                  'ensure_schema_line=%s create_all_line=%s'
                  % (pre['guard_present_in_production'],
                     pre['anchors'].get('ensure_schema_line'),
                     pre['anchors'].get('create_all_line')))
            continue
        db = resolve_db(db_anchor, rr, kind)
        out = run_child_scenario(kind, db, real_db, inj, rr, args.timeout,
                                 db_source=real_db, auth_env=auth_env_for(kind))
        after_fp = sha256(target_paths[key]) if key in target_paths and os.path.exists(
            target_paths[key]) else None
        scenarios[key] = {'desc': desc, 'payload': out['payload'],
                          'out_file': out['out_file'],
                          'exit_code': out['exit_code'],
                          'duration_s': out['duration_s'],
                          'real_db_unchanged': out['real_db_unchanged'],
                          'target_path': rel(target_paths[key]) if key in target_paths else None,
                          'target_sha256_before': target_before.get(key),
                          'target_sha256_after': after_fp,
                          'target_modified': (target_before.get(key) != after_fp)}
        p = out['payload'] or {}
        print('  [CASE] %-22s exit=%s startup_ok=%s create_all_calls=%s error=%-14s '
              'target_modified=%s'
              % (key, out['exit_code'], p.get('startup_ok'), p.get('create_all_calls'),
                 (p.get('error') or {}).get('type'),
                 scenarios[key]['target_modified']))

    real_after = sha256(real_db)
    if os.path.samefile(real_db, _env.REAL_DB):
        _env.assert_real_db_untouched('r2_c07 收尾')

    #: 落点判据必须量在**注入之后**的注入用副本上（原样仓库的锚点里根本没有闸的调用行）
    injected_anchors = locate_anchors(repo_injected)
    injected_anchors['create_all_after_schema_def'] = bool(
        injected_anchors.get('create_all_line') is not None
        and injected_anchors.get('ensure_schema_def_line') is not None
        and injected_anchors['create_all_line'] > injected_anchors['ensure_schema_def_line'])
    injected_anchors['guard_present_in_root'] = guard_present(repo_injected)
    scenarios['preflight']['payload']['anchors_injected_after'] = injected_anchors
    scenarios['preflight']['payload']['guard_present_in_injected_repo'] = guard_present(
        repo_injected)

    copy_fp = sha256(copy_path) if os.path.exists(copy_path) else None
    twin_fp = sha256(twin_path) if os.path.exists(twin_path) else None
    assertions, failed = evaluate(scenarios, real_before, real_after, copy_fp, twin_fp,
                                  args.expect_rules,
                                  real_db_is_env=os.path.samefile(real_db, _env.REAL_DB))

    print('')
    print('-' * 78)
    print('[c07] 判据层（C-07-a 规格 / b / c / 落点 / 不变量）')
    print('  %-22s %-8s %-14s %s' % ('id', 'verdict', 'evidence_kind', 'title'))
    for r in assertions:
        print('  %-22s %-8s %-14s %s' % (r['id'], r['verdict'].upper(),
                                         r['evidence_kind'], r['title'][:60]))
    print('')
    for r in assertions:
        if r['verdict'] != 'passed':
            print('  [FAIL] %s' % r['id'])
            print('         expected=%s' % json.dumps(r['expected'], ensure_ascii=False))
            print('         actual  =%s' % json.dumps(r['actual'], ensure_ascii=False))
            if r['note']:
                print('         note    =%s' % r['note'])
    print('')
    print('[c07] 规格判据：%d/%d 通过；失败=%s'
          % (len([r for r in assertions if r['verdict'] == 'passed' and
                  r['id'] not in GAP_ASSERTION_IDS]),
             len([r for r in assertions if r['id'] not in GAP_ASSERTION_IDS]),
             failed or '无'))
    print('[c07] 现状登记：C-07-a(current) verdict=%s（本项是缺口登记，不计入判据层）'
          % next((r['verdict'] for r in assertions if r['id'] == 'C-07-a(current)'), 'n/a'))
    print('[c07] 真实库 app.db：before=%s after=%s 不变=%s'
          % (real_before[:16] + '...', real_after[:16] + '...', real_before == real_after))

    verdict = 0
    if failed:
        verdict = 1
    if args.strict_current_guard and next(
            (r['verdict'] for r in assertions if r['id'] == 'C-07-a(current)'), 'failed') != 'passed':
        print('[c07] --strict-current-guard：当前生产代码尚未含硬闸 => exit 1')
        verdict = 1
    print('[c07] exit=%d' % verdict)
    print('=' * 78)

    payload = {
        'run_id': _env.RUN_ID,
        'started': started,
        'probe': 'test-reports-2026-10/harness/r2_c07_probe.py',
        'task': 'V-02 / t3 (C-07)',
        'repo_root': rel(repo_root),
        'real_db': {'path': rel(real_db), 'sha256_before': real_before,
                    'sha256_after': real_after,
                    'unchanged': real_before == real_after,
                    'pinned': _env.REAL_DB_SHA256_EXPECTED if os.path.samefile(
                        real_db, _env.REAL_DB) else None},
        'guard_present_in_production': guard_present_now,
        'guard_source': args.guard_source,
        'injected': inject,
        'anchors': scenarios['preflight']['payload']['anchors'],
        'scenarios': {k: {'desc': v['desc'], 'exit_code': v.get('exit_code'),
                          'out_file': rel(v['out_file']) if v.get('out_file') != '(parent)'
                          else v['out_file'],
                          'payload': v['payload']} for k, v in scenarios.items()},
        'assertions': assertions,
        'criteria_failed': failed,
        'criteria_total': len([r for r in assertions if r['id'] not in GAP_ASSERTION_IDS]),
        'criteria_passed': len([r for r in assertions if r['verdict'] == 'passed'
                                and r['id'] not in GAP_ASSERTION_IDS]),
        'exit_code': verdict,
        'evidence_kind': 'behavior_verified',
        'exclude_basenames': ['r2_c07_probe.py（判定脚本自身）', 'captain_r2_*.py',
                              'reconcile_r2.py', 'improve_plan.py', 'analysis_ledger.py',
                              'evidence/** 度量产物'],
        'search_domain': {
            'app/**': '内容搜索 samefile|REAL_DB|real_db|WMS_ALLOW|ALLOW_.*DB|assert_real_db => 0 命中',
            'config.py': '内容搜索（URL 归一化内无闸）',
            'scripts/_test_bootstrap.py': '内容搜索（:41 断言在 create_app 之后，已知太晚）',
            'harness/*.py': '只读引用 _env.py:148-159 的 samefile 推理，不另起',
        },
        'del_what_goes_red': '删掉闸（或把闸挪到 _ensure_schema 之后）=> '
                             'C-07-a(spec) 必红（create_all_calls 由 0 变 1）；'
                             '把判定改成文件名/fingerprint => C-07-b(copy)/(twin) 必红；'
                             '删授权通道 => C-07-c(env)/(ro) 必红',
    }
    if args.json_out:
        write_text(args.json_out, json.dumps(payload, ensure_ascii=False, indent=1))
    p = _env.save_evidence('r2_c07_probe.json', json.dumps(payload, ensure_ascii=False, indent=1))
    print('[c07] 机读结果已落盘 %s' % rel(p))
    return verdict


# ------------------------------------------------------------------- 工具自检
def selftest(args):
    """自检 = 三个合成仓库对照，证明本探针在「闸缺失」时**必报红**。

    ① `absent-repo`：合成仓库**无闸** ⇒ 探针 exit 0 但 `C-07-a(current)` 必须 = failed
       且 state = blocked_no_guard（规格层仍全过，因为闸由探针注入）。
    ② `broken-repo`：闸被故意写坏（吞异常）⇒ 探针必须 exit != 0 且 `C-07-a(spec)` = failed
       —— 这就是「删掉它什么会变红」的阳性样本。
    ③ `present-repo`：闸已正确落地 ⇒ exit 0 且 `guard_present_in_production = true`。
    """
    py = _env.interpreter()
    rows = []
    ok_all = True
    print('=' * 78)
    print('[selftest] 工具自检：合成仓库对照（证明探针能报红，且不是恒真）')
    print('[selftest] 解释器 = %s' % py)
    print('=' * 78)

    #: (tag, 合成仓库里闸的形态, 探针 --guard-source, 期望 a_current state, 期望 exit,
    #:  期望 guard_present_in_source)
    #:
    #: 三类对照刻意覆盖三种真实情形：
    #: ① 仓库**无闸**（当前生产代码）⇒ 探针 auto 注入参考实现，规格层全过、现状层必须报红；
    #: ② 仓库**有闸但写坏**（吞异常）⇒ 探针不许注入（--guard-source present），规格层必须报红；
    #: ③ 仓库**有正确的闸**（只缺调用点）⇒ 探针补调用点，规格层全过、现状层必须 = rejected。
    cases = [
        ('absent-repo', 'absent', 'inject', 'blocked_no_guard', 0, False),
        ('broken-repo', 'broken', 'present', 'unexpected', 1, True),
        ('present-repo', 'present', 'present', 'rejected', 0, True),
    ]
    for tag, guard, gs, want_state, want_exit, want_guard_flag in cases:
        root, fake_db = _mk_repo(tag, guard=guard)
        #: 注入/未注入必须是**不同目录**：注入场景写盘，现状场景读原样
        root_inj = copy_repo(root, root + '-inj')
        shutil.copy2(fake_db, os.path.join(root_inj, 'app.db'))
        json_out = os.path.join(_env.tmp_dir('selftest-json'), tag + '.json')
        argv = [os.path.abspath(__file__), '--repo-root', root,
                '--repo-injected', root_inj, '--real-db', fake_db,
                '--guard-source', gs, '--json-out', json_out]
        out = _env.run_child(argv, cwd=REPO_ROOT, timeout=args.timeout,
                             label='c07-selftest-' + tag)
        data = {}
        if os.path.exists(json_out):
            data = json.loads(read_text(json_out))
        assertions = {a['id']: a for a in data.get('assertions', [])}
        cur = assertions.get('C-07-a(current)', {})
        spec = assertions.get('C-07-a(spec)', {})
        fake_db_unchanged = sha256(fake_db) == data.get('real_db', {}).get('sha256_before')
        got_state = (cur.get('actual') or {}).get('state')
        checked = {
            'exit_code': out['exit_code'],
            'want_exit': want_exit,
            'a_current_state': got_state,
            'want_state': want_state,
            'a_spec_verdict': spec.get('verdict'),
            'want_spec': 'passed' if tag != 'broken-repo' else 'failed',
            'guard_present': data.get('guard_present_in_production'),
            'want_guard_present': want_guard_flag,
            'fake_db_unchanged': fake_db_unchanged,
        }
        good = (out['exit_code'] == want_exit
                and got_state == want_state
                and spec.get('verdict') == checked['want_spec']
                and bool(data.get('guard_present_in_production')) == want_guard_flag
                and fake_db_unchanged)
        ok_all &= good
        rows.append({'tag': tag, 'good': good, 'checked': checked,
                     'out_file': rel(out['out_file'])})
        print('  [%s] %-14s exit=%s(want %s) a_current=%s(want %s) a_spec=%s(want %s) '
              'guard_present=%s fake_db_unchanged=%s'
              % ('PASS' if good else 'FAIL', tag, out['exit_code'], want_exit, got_state,
                 want_state, spec.get('verdict'), checked['want_spec'],
                 data.get('guard_present_in_production'), fake_db_unchanged))
        if not good:
            print('         checked=%s' % json.dumps(checked, ensure_ascii=False))
            print('         child stdout tail: %s'
                  % (out['stdout'].strip().splitlines()[-1:] or ['(empty)']))

    # ④ 真实仓库预检：锚点行号必须与冻结事实一致（只读源码，不 import app）
    anchors = locate_anchors(REPO_ROOT)
    anchor_ok = (anchors.get('ensure_schema_line') == TARGET_SCHEMA_LINE
                 and anchors.get('create_all_line') is not None
                 and anchors['create_all_line'] > anchors.get('ensure_schema_def_line', 0)
                 and anchors.get('after_config_line', 10 ** 9) < anchors.get('ensure_schema_line', -1))
    ok_all &= anchor_ok
    print('  [%s] 真实仓库锚点：_ensure_schema 行=%s（冻结 %s）函数体内 db.create_all 行=%s '
          '（全部命中点 %s）闸位窗口 after_config=%s < 224 ⇒ 窗口存在'
          % ('PASS' if anchor_ok else 'FAIL', anchors.get('ensure_schema_line'),
             TARGET_SCHEMA_LINE, anchors.get('create_all_line'),
             anchors.get('create_all_sites'), anchors.get('after_config_line')))

    # ⑤ 真库只读不变量
    real_ok = False
    try:
        _env.assert_real_db_untouched('r2_c07 selftest')
        real_ok = True
    except Exception as e:                        # noqa: BLE001
        print('  [FAIL] 真实库不变断言：%s' % e)
    ok_all &= real_ok
    print('  [%s] 真实库 app.db SHA256 = %s（钉死值）'
          % ('PASS' if real_ok else 'FAIL', sha256(_env.REAL_DB)))

    payload = {'mode': 'selftest', 'run_id': _env.RUN_ID, 'interpreter': py,
               'cases': rows, 'anchors': anchors, 'real_db_ok': real_ok,
               'verdict': 'passed' if ok_all else 'failed'}
    p = _env.save_evidence('r2_c07_probe_selftest.json',
                           json.dumps(payload, ensure_ascii=False, indent=1))
    print('[selftest] 自检结论：%s（3 合成仓库 + 锚点 + 真库不变量）'
          % ('OK' if ok_all else 'FAIL'))
    print('[selftest] 证据已落盘 %s' % rel(p))
    print('[selftest] exit=%d' % (0 if ok_all else 1))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
