"""harness 环境层：绝对路径、编码、副本目录、子进程（沙箱安全）。

设计约束（来自 `00` 登记册 §4 与 `00b` 增补纪律 12–14、`08` §4.2 铁律 E-1…E-7）：

* **绝对路径解释器**：PATH 上的 ``python`` 无 Flask（A-7）⇒ 一切子进程用 ``PY_EXE``。
* **不建 0o700 目录**：``tempfile.mkdtemp()`` 默认 0o700，本沙箱下写入被拒且目录**永久不可删**
  （E-4 / GAP-7）⇒ 副本与中间产物一律落 ``test-reports-2026-10/.tmp/<run_id>/``（``os.makedirs``）。
* **不用管道**：本沙箱下 ``subprocess`` 管道（`subprocess.PIPE`）被拒 —— 这也是
  ``scripts/_sandbox_compat.py`` 存在的理由。本层捕获子进程输出走「临时文件重定向 + 读回」，
  与 `_sandbox_compat._run` 同法，但**不依赖 shim**。
* **编码（A-14）**：父按 ``utf-8`` 解码、子进程强制 ``PYTHONIOENCODING=utf-8``；
  若仍出现替换字符，``evidence_level`` 必须标为「原文可能乱码」。
* **真实库零改动**：``app.db`` 期望 SHA256 在此**硬钉**；每次 ``run_child`` 前后自动复核。
* **证据只追加（E-01，修复 D-5/T-01/T-08/A-36）**：落盘一律进 ``EVIDENCE_ROOT/<RUN_ID>/``，
  且写入前过 ``guard_write``——目标已存在时**改名保留**（``<name>.<run_id>.<ext>``）而**绝不覆盖**。
  每次落盘追加一行到 ``evidence_journal.jsonl``（可审计谁在何时写了什么、是否触发改名）。
  历史平铺原件（``EVIDENCE_ROOT`` 直接子文件，t2/t3 产出）**只读引用**，不得再写入。
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

# ------------------------------------------------------------------ 绝对路径
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HARNESS_DIR)
REPO_ROOT = os.path.dirname(REPORTS_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'scripts')
PY_EXE = r'F:\Miniconda\envs\wage\python.exe'
PY_FALLBACK = sys.executable

# ------------------------------------------------------------------ 证据落点（E-01）
RUN_ID = os.environ.get('HARNESS_RUN_ID') or time.strftime('run-%Y%m%d-%H%M%S')
#: 稳定根目录：历史（t2/t3/t4/t5）平铺制品所在，**只读引用**，新写入不得落在这一层
EVIDENCE_ROOT = os.path.join(REPORTS_ROOT, 'evidence', 'harness')
#: 本次 run 的落点：``evidence/harness/<RUN_ID>/``（E-01 的核心改动，防复跑静默覆盖）
EVIDENCE_DIR = os.path.join(EVIDENCE_ROOT, RUN_ID)
HARNESS_EVIDENCE_DIR = EVIDENCE_DIR
#: 历史平铺目录（与 EVIDENCE_DIR 同义的历史命名，语义不同：这一层是只读的）
EVIDENCE_DIR_LEGACY = EVIDENCE_ROOT
#: 落盘审计流水（只追加；同 run 内每写一个文件追加一行）
EVIDENCE_JOURNAL_NAME = 'evidence_journal.jsonl'

REAL_DB = os.path.join(REPO_ROOT, 'app.db')
#: ── A-70「有意更新三步」历史 + **B14-R1 回退**（ALLOY-IMPORT-02 / 2026-10-09）────────────────
#: 【历史留痕 · 生效期望已回退】ALLOY-IMPORT-02（「合金钢辙叉计件工价标准 + 48页表格 BOM」正式
#:   写入真实库：工价 +3534 / 小计关系 +3507 / 旧工价 −3486 / 旧小计关系 −2906 / 产品 +1080 /
#:   BOM 明细 +1728 / 审计 +3）曾按 A-70 三步把本行由「导入前锚点」`F5DA2306…0F065`（2531328 B）
#:   改写为导入后锚点 `4EB632A48F1C7E8A13BCE8F6263D587A1958D01CC84E37A0D4359E1506DDFA43`
#:   （3035136 B）。**该重基线已被 B14-R1（2026-10-09，用户裁定「回退真库锚点重基线、保留合金钢
#:   功能代码」）回退**：真实库由 captain 还原为 2531328 B / `F5DA2306…0F065` /
#:   mtime `2026-09-18 12:50:55`；导入态字节另存 `app.db.evidence-ALLOY-IMPORT-02-20261009_004539`
#:   （3035136 B / `4EB632A4…FA43`）；上述导入后锚点自此**只作注释里的历史记录**，不作生效期望。
#: 同批一并回退的三处（同一触发项，四者必须同改，否则 `t6_ledger_check.py:183` 的交叉断言或门禁必红）：
#:   `run_gates.py` 的 `EXPECTED['bootstrap_copied_rows']`、`ci_gates.py` 的 `check_db_bootstrap`
#:   期望串、`t6_ledger_check.py` 的 `PINNED_DB_SHA`。逐处前值/新值/依据/命令见 append-only 登记件
#:   `test-reports-2026-10/B14-R1-锚点回退登记.md`。
#: 判据（阴性对照）：把本行写成导入后锚点 `4EB632A4…`（干净库现状）⇒ `assert_real_db_untouched()`
#:   现场必抛 `RuntimeError: 真实库 app.db 已偏离钉死哈希`（B14-R1 已实测，见登记件 §阴性对照）。
#: 冻结历史件（`harness/final_recount.py`、`harness/analysis_ledger.py`、`harness/reconcile_r2.py`、
#:   `reconcile-2026-10-08/*`、带日期 markdown 报告、`r2_v14_ledgerbook.py` 等）一律**不动** ——
#:   它们本就钉在导入前的干净口径上，无需随本次回退改动。
#: ────────────────────────────────────────────────────────────────────────────────────────
REAL_DB_SHA256_EXPECTED = 'F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065'

_encode_fix = "import sys;sys.stdout.reconfigure(encoding='utf-8',errors='replace');sys.stderr.reconfigure(encoding='utf-8',errors='replace')\n"

for _d in (SCRIPTS_DIR, HARNESS_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

TMP_ROOT = os.path.join(REPORTS_ROOT, '.tmp', RUN_ID)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def evidence_dir(subdir=None, run_id=None):
    """解析证据落点目录（E-01）。

    * ``evidence_dir()``              -> ``evidence/harness/<RUN_ID>/``（默认：本次 run 目录）
    * ``evidence_dir(subdir='uat')``  -> ``evidence/harness/uat/``（显式域目录，仍不在平铺层）
    * ``evidence_dir(run_id='x')``    -> ``evidence/harness/x/``

    任何情形都**不含**平铺层 ``evidence/harness/`` 本身 ⇒ 历史原件不可能被新写入命中。
    """
    rid = run_id or RUN_ID
    base = EVIDENCE_ROOT if subdir is None else os.path.join(EVIDENCE_ROOT, str(subdir))
    if subdir is None:
        base = os.path.join(base, rid)
    return ensure_dir(base)


def guard_write(path, run_id=None):
    """写前守卫（E-01，样板同 ``improve_plan.py:guard_write``）：**绝不覆盖**既有文件。

    目标不存在 ⇒ 原样返回 ``(path, False)``；目标已存在 ⇒ 返回改名后的
    ``<base>.<run_id><ext>``（必要时再加 ``.n``），原文件**一字不动**。
    """
    if not os.path.exists(path):
        return path, False
    rid = run_id or RUN_ID
    base, ext = os.path.splitext(path)
    alt = f'{base}.{rid}{ext}'
    n = 1
    while os.path.exists(alt):
        alt = f'{base}.{rid}.{n}{ext}'
        n += 1
    return alt, True


def _append_journal(directory, requested, written, renamed, text, run_id=None):
    """落盘审计：一行一条 JSON（只追加）。"""
    row = {
        'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
        'run_id': run_id or RUN_ID,
        'requested': requested,
        'written': os.path.basename(written),
        'renamed_by_guard': bool(renamed),
        'bytes': len(text.encode('utf-8')),
        'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest().upper(),
    }
    with open(os.path.join(directory, EVIDENCE_JOURNAL_NAME), 'a', encoding='utf-8',
              newline='\n') as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    return row


def tmp_dir(*parts):
    return ensure_dir(os.path.join(TMP_ROOT, *parts))


def db_copy(tag, dest_dir=None):
    """把真实库复制一份到本 run 的隔离目录，返回副本绝对路径（绝不改动真实库）。"""
    import shutil
    dest_dir = dest_dir or tmp_dir('db')
    ensure_dir(dest_dir)
    dest = os.path.join(dest_dir, f'app_{tag}_{RUN_ID}.db')
    shutil.copy2(REAL_DB, dest)
    return dest


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def real_db_status():
    """真实库指纹：文件名（SHA256 / 字节 / mtime）。"""
    st = os.stat(REAL_DB)
    return {
        'path': os.path.relpath(REAL_DB, REPO_ROOT).replace('\\', '/'),
        'sha256': sha256_file(REAL_DB),
        'bytes': st.st_size,
        'mtime_ns': st.st_mtime_ns,
    }


def real_db_is_target(uri, target_path):
    """独立隔离闸的**纯函数**实现（可对任意输入验收，便于阳性/阴性对照）。

    返回 ``(is_real_db, reasons)``。

    判据：``os.path.samefile(target_path, REAL_DB)`` 成立 ⇒ **就是真实库** ⇒ 必须拒。
    （URI 里出现 ``app.db`` 只是旁证：副本与真实库同名，**不能**只凭文件名判定。）

    为什么不用指纹做拒绝判据：``_test_bootstrap`` 的副本是 ``shutil.copy2`` 的**逐字节副本**，
    指纹必然等于真实库（实测两者同为 ``F5DA2306…0E0F065``）；用指纹拒绝会把合法副本一并拒掉。
    指纹只作为取证/旁证（``assert_isolated_fingerprint``）。
    """
    reasons = []
    same = False
    try:
        same = os.path.samefile(target_path, REAL_DB)
    except OSError as e:
        reasons.append(f'samefile 探测失败: {e.__class__.__name__}')
    if same:
        reasons.append('目标文件与真实库 app.db 是同一个文件（samefile=True）⇒ 拒')
    else:
        reasons.append('目标文件不是真实库（samefile=False）⇒ 放行')
    if 'app.db' not in uri:
        reasons.append('URI 未命中 app.db（旁证，不参与判定）')
    return (same, reasons)


def real_db_guard_report(uri, target_path):
    """把 ``real_db_is_target`` 包成可读报告（便于 JSON 落盘与逐条对照）。"""
    is_real, reasons = real_db_is_target(uri, target_path)
    return {'rejected': is_real, 'is_real_db': is_real, 'reasons': reasons,
            'uri': uri, 'target': target_path, 'real_db': REAL_DB,
            'target_sha256': sha256_file(target_path) if os.path.exists(target_path) else None,
            'pinned_sha256': REAL_DB_SHA256_EXPECTED}


def assert_real_db_untouched(context=''):
    """真实库零改动闸：偏离钉死哈希即抛异常（绝不宽容）。"""
    actual = sha256_file(REAL_DB)
    if actual != REAL_DB_SHA256_EXPECTED:
        raise RuntimeError(
            f'真实库 app.db 已偏离钉死哈希（{context}）：\n'
            f'  期望 {REAL_DB_SHA256_EXPECTED}\n  实测 {actual}')
    return actual


def interpreter():
    return PY_EXE if os.path.exists(PY_EXE) else PY_FALLBACK


# -------------------------------------------------------------- 子进程（无管道）
def run_child(args, cwd=REPO_ROOT, timeout=1800, extra_env=None, label=''):
    """跑一个子进程并捕获输出 —— 不用管道，全程走临时文件重定向。

    返回 dict：``argv`` / ``cwd`` / ``exit_code`` / ``stdout`` / ``stderr`` /
    ``evidence_level`` / ``duration_s`` / ``real_db_sha256_before|after``。
    """
    ensure_dir(EVIDENCE_DIR)
    stamp = re.sub(r'[^0-9A-Za-z_.-]', '_', label) or 'child'
    out_path = os.path.join(TMP_ROOT, 'child', f'{stamp}.out')
    err_path = os.path.join(TMP_ROOT, 'child', f'{stamp}.err')
    ensure_dir(os.path.dirname(out_path))
    real_argv = [interpreter(), '-B'] + list(args)
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env['PYTHONPATH'] = os.pathsep.join(
        [HARNESS_DIR, SCRIPTS_DIR, REPO_ROOT]
        + ([env['PYTHONPATH']] if env.get('PYTHONPATH') else []))
    env['HARNESS_RUN_ID'] = RUN_ID
    if extra_env:
        env.update(extra_env)

    before = sha256_file(REAL_DB)
    started = time.time()
    rc = None
    err = ''
    with open(out_path, 'w', encoding='utf-8', errors='replace') as fo, \
            open(err_path, 'w', encoding='utf-8', errors='replace') as fe:
        try:
            proc = subprocess.run(real_argv, cwd=cwd, env=env, stdout=fo, stderr=fe, timeout=timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc = -9
            err = f'TIMEOUT after {timeout}s'
        except Exception as e:  # 环境层失败也要留痕，不能静默
            rc = -1
            err = f'{e.__class__.__name__}: {e}'
    duration = time.time() - started
    with open(out_path, encoding='utf-8', errors='replace') as fh:
        out = fh.read()
    with open(err_path, encoding='utf-8', errors='replace') as fh:
        err_txt = fh.read()
    after = sha256_file(REAL_DB)

    combined = out + err_txt
    garbled = combined.count('\ufffd')
    level = '原文可信' if garbled == 0 else f'原文可能乱码（U+FFFD x{garbled}）'
    return {
        'argv': real_argv,
        'argv_display': ' '.join('"%s"' % a if ' ' in a else a for a in real_argv),
        'cwd': cwd,
        'exit_code': rc,
        'stdout': out,
        'stderr': err_txt + (('\n--- runner note: ' + err) if err else ''),
        'evidence_level': level,
        'duration_s': round(duration, 2),
        'out_file': out_path,
        'err_file': err_path,
        'real_db_sha256_before': before,
        'real_db_sha256_after': after,
        'real_db_unchanged': before == after == REAL_DB_SHA256_EXPECTED,
    }


def run_python(source, cwd=REPO_ROOT, timeout=900, extra_env=None, label='inline'):
    """把一段 Python 源码写进本 run 的隔离目录后执行（避免 -c 的引号地狱）。"""
    path = os.path.join(tmp_dir('inline'), f'{label}.py')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(_encode_fix)
        fh.write(source)
    return run_child([path], cwd=cwd, timeout=timeout, extra_env=extra_env, label=label)


def save_evidence(filename, text, subdir=None, run_id=None, guard=True, journal=True):
    """把文本证据落盘到 ``evidence/harness/<RUN_ID>/``（E-01：只追加）。

    返回**实际写入路径**（发生改名时是改名后的路径，不是请求路径）。

    * ``subdir``：显式域目录（相对 ``EVIDENCE_ROOT``）；缺省即本 run 目录。
    * ``guard``：默认开——目标已存在则改名保留（``<name>.<run_id><ext>``），绝不覆盖。
    * ``journal``：默认开——向同目录 ``evidence_journal.jsonl`` 追加一行审计记录。
    """
    directory = evidence_dir(subdir=subdir, run_id=run_id)
    requested = os.path.join(directory, filename)
    path = requested
    renamed = False
    if guard:
        path, renamed = guard_write(requested, run_id=run_id)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    if journal:
        _append_journal(directory, requested, path, renamed, text, run_id=run_id)
    return path


def assert_isolated_fingerprint(uri, target_path):
    """加固闸（第二道判据）：目标库文件**指纹**等于真实库钉死哈希时，必须拒绝写入。

    为什么不能只比路径：副本与真实库**同名**（都叫 ``app.db``），只比文件名会把副本误判；
    而只比路径又防不住「有人把真实库复制到别的目录再指向它」。⇒ 路径 + 指纹双判据。
    """
    reasons = []
    if 'app.db' not in uri:
        reasons.append('URI 未命中 app.db')
    exists = os.path.exists(target_path)
    if not exists:
        reasons.append(f'目标文件不存在: {target_path}')
        actual = None
    else:
        actual = sha256_file(target_path)
        if actual == REAL_DB_SHA256_EXPECTED:
            reasons.append('目标文件指纹等于真实库钉死哈希 ⇒ 疑似真实库（或它的整库副本）')
    return {'rejected': bool(reasons), 'reasons': reasons,
            'target_sha256': actual, 'pinned': REAL_DB_SHA256_EXPECTED,
            'exists': exists}


def line_count(path):
    """行数口径：Python ``splitlines()``（A-23 裁定），同时给非空行数。"""
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    lines = text.splitlines()
    return {'total_lines': len(lines), 'nonempty_lines': sum(1 for l in lines if l.strip())}
