#!/usr/bin/env python
"""B17 治理收口 —— **非作者**独立验证载体（team b17-engineering-governance / t6=verifier；**t15 复验轮**=verifier2）。

判据来源：`test-reports-2026-10/B17-00-契约冻结.md`（§1/§2/§3/§5）。
本载体**不复用实现者脚手架**：每条断言由本文件自写；实现者脚本只作为**被测对象（SUT）**被 subprocess 调用。

复验轮（t15，2026-10-09）随三处返工更新的判据：
* `B17-10`：口径从「契约 9/8/1」改为**现场文案 `AGENTS.md:49` = 11/10/1**，并要求文案点名两个被漏计的
  `save_upload_files()` 端点（`app/main/routes.py:2776`/`:2825`，helper `:5606`）。
* `B17-14`：从「判据层 0 消费 + docstring 留 271」改为**要求 `harness/coverage_drift.py` 的 D-9 真读该 face**
  （变异体必须转红）且 docstring 现场值 = 273/112；`271` 仅允许出现在 A-70 就地注记行。
* `B17-12`：新增 §Z.5 append-only 订正确认（旧值须逐字保留 + 含时点/复现命令）；`§Z.5.3` 残留陈旧断言
  记未闭环 R-1（WARN），时点漂移记 PTR-1/PTR-2（WARN），均不入判定。

退出码语义：`0`=全部 PASS；`1`=有 FAIL；`2`=ERROR（载体/环境异常，如真库 sha 前后不一致）；`3`=usage。
写操作纪律：只写 `<repo>/test-reports-2026-10/.tmp/b17_verify/`（绝对路径）；真实 `app.db` 只读，
sha256 前后一致进 ERROR 出口；库级验证一律走 `scripts/_test_bootstrap.make_app()` 副本库。
用法：`python -B test-reports-2026-10/harness/b17_governance_contract.py [--only B17-06,B17-07]`
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PY = '/opt/wage-venv/bin/python'
TMP = ROOT / 'test-reports-2026-10' / '.tmp' / 'b17_verify'
REGISTRY = []          # [(bid, name, fn)]
RESULTS = []           # [(bid, name, status, tool, gauge, value, contrast)]


def register(bid, name):
    def deco(fn):
        REGISTRY.append((bid, name, fn))
        return fn
    return deco


def run(cmd, timeout=2400, env=None, cwd=None):
    """跑 SUT/命令；返回 (exit_code, stdout+stderr)。`cmd` 用 list ⇒ 不经 shell。"""
    e = dict(os.environ)
    e['HARNESS_RUN_ID'] = 'b17-verify'
    if env:
        e.update(env)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       cwd=str(cwd or ROOT), env=e, errors='replace')
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for blk in iter(lambda: fh.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def record(bid, name, ok, tool, gauge, value, contrast, status=None):
    """`status` 显式覆盖（B17-02 用 'BLOCKED' ⇒ 不进 PASS 计数、不折算 pass）。"""
    st = status or ('PASS' if ok else 'FAIL')
    RESULTS.append((bid, name, st, tool, gauge, value, contrast))
    print('[%s] %-8s %s | %s' % (st, bid, name, value))


@register('B17-01', '死文件 app/main/sales_routes.py 删除')
def b17_01():
    tool = 'git ls-files / git show HEAD / test -e'
    gauge = '文件存在性 + 版本库文件数 app/main + 代码引用数'
    exists = (ROOT / 'app/main/sales_routes.py').exists()
    code, tracked = run(['git', 'ls-files', 'app/main'])
    n = len([x for x in tracked.splitlines() if x.strip()])
    _, hcount = run(['bash', '-c', 'git show HEAD:app/main/sales_routes.py | wc -c'])
    _, refs = run(['git', 'grep', '-nE', 'sales_routes', '--', 'app/*.py', 'app/**/*.py',
                   'app/**/*.html'])
    nrefs = len([x for x in refs.splitlines() if x.strip()])
    _, elsewhere = run(['git', 'grep', '-nE', 'sales_routes', '--', 'scripts', 'docs',
                        'test-reports-2026-10'])
    nelse = len([x for x in elsewhere.splitlines() if x.strip()])
    _, st = run(['git', 'status', '--porcelain', '--', 'app/main/sales_routes.py'])
    val = ('现场 test -e=%s；git ls-files app/main=%d；HEAD 该文件字节=%s；app/** 引用=%d；'
           'app 外（tools/docs/报告）引用=%d；status=%r'
           % (exists, n, hcount.strip(), nrefs, nelse, st.strip()))
    contrast = ('阴（HEAD 基线）：`git show HEAD:app/main/sales_routes.py` 存在（1 字节）⇒「文件不存在」'
                '非恒真；阳（现场）：删除已生效、app/** 0 引用。')
    record('B17-01', '死文件删除', (not exists) and n == 9 and nrefs == 0, tool, gauge, val, contrast)


@register('B17-18', '部署配置：.env 不再硬写 sqlite + SECRET_KEY 生成型/三处一致')
def b17_18():
    tool = 'grep -nE / sed（scripts/deploy.bat、Jenkinsfile、deploy.config.yml）'
    gauge = '弱占位与硬写 sqlite 的出现数；生成型/条件写/回滚说明的存在性'
    files = ['scripts/deploy.bat', 'Jenkinsfile', 'deploy.config.yml']
    text = {f: (ROOT / f).read_text(encoding='utf-8', errors='replace') for f in files}
    weak = sum(t.count('your-secret-key-here') for t in text.values())
    hard = sum(t.count('sqlite:///app.db') for t in text.values())
    gen = sum(t.count('secrets.token_urlsafe') for t in text.values())
    cond = sum(t.count('if defined DATABASE_URL') for t in text.values())
    rollback = sum(('回滚' in t) for t in text.values())
    _, hweak = run(['bash', '-c',
                    'for f in scripts/deploy.bat Jenkinsfile deploy.config.yml; do '
                    'git show HEAD:$f 2>/dev/null | grep -c "your-secret-key-here"; done'])
    hp = ROOT / 'docs' / '开发与测试规划-2026-10-06.md'
    _, hdoc = run(['bash', '-c', 'git show HEAD:"%s" | grep -c "B17-19"' % hp])
    val = ('弱占位=%d（HEAD 各文件命中 %s）/ 硬写 sqlite=%d / 生成型=%d / 条件写 DATABASE_URL=%d / 三份含回滚=%d'
           % (weak, hweak.split(), hard, gen, cond, rollback))
    contrast = ('阴（HEAD）：三份文件原有弱占位与硬写 sqlite（如 deploy.bat:178/179）；阳（现场）：弱占位 0、'
                '硬写 0（`deploy.config.yml` 的 sqlite 仅存在于 `database.type: sqlite` 段，非 DATABASE_URL）。')
    record('B17-18', '部署配置复核', weak == 0 and hard == 0 and gen == 2 and cond == 2 and rollback == 3,
           tool, gauge, val, contrast)


@register('B17-19', 'my_tasks.use 文档订正（保留声明与 4 处使用点）')
def b17_19():
    tool = 'grep -rn app/ + git show HEAD:"docs/开发与测试规划…"'
    gauge = '现场使用点数（声明 + require_capability + can_any + 模板）；文档订正落地'
    _, live = run(['bash', '-c', 'grep -rn --include=*.py --include=*.html "my_tasks.use" app/'
                                 ' | grep -v __pycache__'])
    sites = [x for x in live.splitlines() if x.strip()]
    decl = [s for s in sites if 'permissions.py' in s]
    uses = [s for s in sites if 'permissions.py' not in s and not s.split(':', 2)[-1].strip().startswith('#')]
    comments = [s for s in sites if s.split(':', 2)[-1].strip().startswith('#')]
    kinds = {
        'decl': len(decl) == 1,
        'require': any('require_capability' in s for s in uses),
        'can_any': any('can_any' in s for s in uses),
        'tmpl': any('base.html' in s for s in uses),
    }
    doc = (ROOT / 'docs' / '开发与测试规划-2026-10-06.md').read_text(encoding='utf-8', errors='replace')
    doc_ok = ('B17-19' in doc) and ('假阳' in doc or '已销项' in doc)
    _, head = run(['bash', '-c', 'git show HEAD:"docs/开发与测试规划-2026-10-06.md" | grep -c "B17-19"'])
    val = ('现场 %d 处 = 声明 1 + 使用 %d + 纯注释 %d（%s）；文档含订正=%s；HEAD 文档含 B17-19 次数=%s'
           % (len(sites), len(uses), len(comments), kinds, doc_ok, head.strip()))
    contrast = ('阴（HEAD 文档）：`B17-19` 命中 0 次 ⇒ 订正确为本批新增；阳（现场）：声明 + 3 类使用点齐备'
                '且文档标注「假阳/已销项」。')
    record('B17-19', 'my_tasks.use 销项订正', all(kinds.values()) and len(uses) == 3 and doc_ok,
           tool, gauge, val, contrast)


def gate_list():
    """自解析 `ci_gates.py --list`：返回 [(序, 步名, group)]（步序即链序，非作者口径）。"""
    _, out = run([PY, '-B', 'test-reports-2026-10/harness/ci_gates.py', '--list'])
    steps = []
    for ln in out.splitlines():
        m = re.match(r'\[ci_gates\]\s+(\w+)\s+(blocking|report-only)\s+\S', ln)
        if m:
            steps.append((m.group(1), m.group(2)))
    return steps


@register('B17-15', 'negative_matrix 入链（第 17 步 / blocking）且 28 条全过')
def b17_15():
    tool = 'ci_gates.py --list（自解析）+ 直跑 negative_matrix.py --out <abs .tmp>'
    gauge = '链内步序/分组；直跑 stdout 汇总行与退出码'
    steps = gate_list()
    pos = [i + 1 for i, (n, g) in enumerate(steps) if n == 'negative_matrix']
    grp = [g for n, g in steps if n == 'negative_matrix']
    out_json = TMP / 'neg_matrix.json'
    code, out = run([PY, '-B', 'test-reports-2026-10/harness/negative_matrix.py',
                     '--out', str(out_json)])
    hit = '[negative_matrix] 合计 28 条：passed=28 failed=0 blocked=0' in out
    val = 'steps=%d；negative_matrix 步序=%s group=%s；直跑 exit=%d 命中汇总行=%s' % (
        len(steps), pos, grp, code, hit)
    contrast = ('阴：`--list` 若把该步去掉则步序为空（本断言即失败）；阳：链内经序 17、blocking、直跑 28/28。'
                '转引对照：契约 §1 基线 16 步（无该步）→ 现场 19 步。')
    record('B17-15', 'negative_matrix 加链', pos == [17] and grp == ['blocking'] and code == 0 and hit,
           tool, gauge, val, contrast)


@register('B17-16', 'check_doc_claims 入链（第 19 步 / `--coverage` run 产物）')
def b17_16():
    tool = 'ci_gates.py --list（自解析）+ 直跑 scripts/check_doc_claims.py --coverage <run 产物> --selftest'
    gauge = '链内步序/分组/是否带 --coverage；violations 数；selftest 通过数'
    steps = gate_list()
    pos = [i + 1 for i, (n, g) in enumerate(steps) if n == 'check_doc_claims']
    grp = [g for n, g in steps if n == 'check_doc_claims']
    _, listing = run([PY, '-B', 'test-reports-2026-10/harness/ci_gates.py', '--list'])
    line = [x for x in listing.splitlines() if 'check_doc_claims' in x and 'blocking' in x]
    has_cov = bool(line) and '--coverage' in line[0]
    cov = ROOT / 'test-reports-2026-10/evidence/harness/ci-run-20261009-223606/coverage.json'
    c1, o1 = run([PY, '-B', 'scripts/check_doc_claims.py', '--coverage', str(cov)])
    c2, o2 = run([PY, '-B', 'scripts/check_doc_claims.py', '--selftest'])
    pin = re.search(r'钉常量 vs 权威源：(\d+)/(\d+) 相等', o1 + o2)
    self_ok = '自检 16/16 通过' in o2
    val = '步序=%s group=%s 带--coverage=%s；直跑 exit=%d violations=0=%s；selftest exit=%d 16/16=%s；钉常量=%s' % (
        pos, grp, has_cov, c1, 'violations=0' in o1, c2, self_ok, pin.group(0) if pin else '未打印')
    contrast = ('阴（A-70 现场基线，转引 t1）：`--coverage` 缺省走归档锚点且 violations=16、selftest 15/16；'
                '阳（本人现场）：显式 run 产物 + violations=0、selftest 16/16。')
    record('B17-16', '口径守卫加链', pos == [19] and grp == ['blocking'] and has_cov
           and c1 == 0 and 'violations=0' in o1 and c2 == 0 and self_ok, tool, gauge, val, contrast)


@register('B17-11', '下游脚本 --coverage 重指（显式 run 产物）+ r2_c07_probe 271→273')
def b17_11():
    tool = 'grep -n（reconcile_r2.py / r2_v14_ledgerbook.py / r2_c07_probe）'
    gauge = 'coverage_drift 调用点是否显式 --coverage；探针默认期望规则数'
    files = {'reconcile_r2.py': 'test-reports-2026-10/harness/reconcile_r2.py',
             'r2_v14_ledgerbook.py': 'test-reports-2026-10/harness/r2_v14_ledgerbook.py'}
    txt = {k: (ROOT / v).read_text(encoding='utf-8', errors='replace') for k, v in files.items()}
    hits = {
        # reconcile_r2.py：真实调用点 `[PY, '-B', COVERAGE_DRIFT, '--coverage', run_coverage_artifact()]`
        'reconcile_r2.py': bool(re.search(r"COVERAGE_DRIFT,\s*'--coverage'", txt['reconcile_r2.py']))
                           and 'run_coverage_artifact()' in txt['reconcile_r2.py'],
        # ledgerbook：记录的 command 跨行拼 `coverage_drift.py` + `--coverage %s/coverage.json`
        'r2_v14_ledgerbook.py': bool(re.search(r"coverage_drift\.py'[\s\S]{0,160}?--coverage", txt['r2_v14_ledgerbook.py'])),
    }
    codes = {k: len([ln for ln in v.splitlines() if 'coverage_drift.py' in ln]) for k, v in txt.items()}
    probe = (ROOT / 'test-reports-2026-10/harness/r2_c07_probe.py').read_text(encoding='utf-8')
    _, hprobe = run(['bash', '-c', 'git show HEAD:test-reports-2026-10/harness/r2_c07_probe.py'
                                    ' | grep -n "ROUTE_RULES_BASELINE = "'])
    anchor = (ROOT / 'test-reports-2026-10/evidence/harness/coverage.json').exists()
    val = ('两处下游 call/recipe 行含 --coverage=%s（命中行数 %s）；现场 ROUTE_RULES_BASELINE=%s；'
           'HEAD 该常量=%r；冻结锚点 evidence/harness/coverage.json 存在=%s'
           % (hits, codes, re.search(r'ROUTE_RULES_BASELINE = (\d+)', probe).group(1),
              hprobe.strip()[-24:], anchor))
    contrast = ('阴（缺参）：`coverage_drift.py --coverage` 缺省指向不存在/不可变的归档锚点 ⇒ exit 2 用法错误'
                '（A-114）；阳（现场）：reconcile_r2.py 实调 `--coverage run_coverage_artifact()`，'
                'ledgerbook 的 command/notes 同步改口径；HEAD 探针 271 → 现场 273。')
    record('B17-11', '--coverage 重指 + 探针 271→273',
           all(hits.values()) and '273' in probe.splitlines()[113] and '271' in hprobe,
           tool, gauge, val, contrast)


_TREE = None


def synth_tree():
    """合成树 `<TMP>/tree`：`app/` + `migrations/` + `scripts/check_table_parity.py` 的**只读副本**。

    真实仓库只被 copytree 读；所有阴性对照注入一律落副本（`app/**`/`migrations/**` 本体零写入）。
    排除 `__pycache__`/`*.db`/`instance`，保持相对深度 ⇒ 脚本自解析 ROOT = 合成树根。
    """
    global _TREE
    t = TMP / 'tree'
    if _TREE is None:
        if not (t / 'app' / 'models.py').exists():
            shutil.rmtree(t, ignore_errors=True)
            (t / 'scripts').mkdir(parents=True, exist_ok=True)
            for name in ('app', 'migrations'):
                shutil.copytree(ROOT / name, t / name,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.db', 'instance'))
            for py in ROOT.glob('*.py'):            # config.py 等根级模块（app/__init__.py 依赖）
                shutil.copy2(py, t / py.name)
            shutil.copy2(ROOT / 'scripts' / 'check_table_parity.py', t / 'scripts' / 'check_table_parity.py')
            shutil.copy2(ROOT / 'scripts' / '_test_bootstrap.py', t / 'scripts' / '_test_bootstrap.py')
            for py in (ROOT / 'scripts').glob('*.py'):       # SUT 依赖（smoke_test 等）随副本树
                if not (t / 'scripts' / py.name).exists():
                    shutil.copy2(py, t / 'scripts' / py.name)
            shutil.copy2(ROOT / 'app.db', t / 'app.db')      # 副本库源（只读拷贝，真实库零写入）
        _TREE = t
    return _TREE


@register('B17-07', 'is_archived 执法脚本：现场一致 + 未登记读取点 ⇒ exit 1')
def b17_07():
    tool = '直跑 scripts/check_is_archived_policy.py（--root <合成树>）+ 自注入 1 处未登记读点'
    gauge = '现场/副本 exit；未登记新增注入后的 exit 与违规行'
    c0, o0 = run([PY, '-B', 'scripts/check_is_archived_policy.py'])
    t = synth_tree()
    c1, o1 = run([PY, '-B', 'scripts/check_is_archived_policy.py', '--root', str(t)])
    inject = t / 'app' / 'main' / 'zz_b17_verify_probe.py'
    inject.write_text('def _probe(q, RawMaterial):\n'
                      '    return q.filter(RawMaterial.is_archived.is_(False))\n', encoding='utf-8')
    c2, o2 = run([PY, '-B', 'scripts/check_is_archived_policy.py', '--root', str(t)])
    inject.unlink()
    c3, o3 = run([PY, '-B', 'scripts/check_is_archived_policy.py', '--root', str(t)])
    _, inv = run([PY, '-B', 'scripts/check_is_archived_policy.py', '--inventory'])
    groups = [ln for ln in inv.splitlines() if ln.strip().startswith('(') or '→' in ln]
    needle = [ln.strip()[:110] for ln in o2.splitlines() if '未登记' in ln or '[is_archived]' in ln]
    val = ('现场 exit=%d；副本 exit=%d；注入未登记读点后 exit=%d（%s）；卸载后 exit=%d；inventory 行数=%d；'
           '现场末行=%r' % (c0, c1, c2, needle[-1:] or '无未登记提示', c3, len(groups), o0.strip().splitlines()[-1][:90]))
    contrast = ('阴（本人注入）：`<tree>/app/main/zz_b17_verify_probe.py` 加 1 行 `is_archived.is_(False)` '
                '⇒ exit %d（未登记新增判红）；阳：副本与现场（41 处/11 组）exit 0，卸载后复绿 exit %d。'
                % (c2, c3))
    record('B17-07', 'is_archived 执法', c0 == 0 and c1 == 0 and c2 == 1 and c3 == 0, tool, gauge, val, contrast)


#: B17-04 探针（本载体自写）：把 SUT `permission_matrix.py` 当**被测库**导入，
#: 只把它的模块级 ROOT 指到合成树，再用它自己的 scan/compare 做双向对照。
PM04_PROBE = r'''
import contextlib, importlib.util, io, json, pathlib, sys
repo, tree = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
sys.path.insert(0, str(repo / 'scripts'))
spec = importlib.util.spec_from_file_location('pm_sut', str(repo / 'scripts' / 'permission_matrix.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.ROOT = tree
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    res = m.check_inline_roles()
    m.print_inline_role_face(*res)
scanned, extra, stale, drift = res
print(json.dumps({'scanned': len(scanned), 'wl': len(m.INLINE_ROLE_WHITELIST),
                  'extra': len(extra), 'stale': len(stale), 'drift': len(drift),
                  'face_fail': '[FAIL]' in buf.getvalue(),
                  'wl_entries': [[f, a] for f, _ln, a in m.INLINE_ROLE_WHITELIST]}))
'''


def pm_probe(tree):
    p = TMP / 'probe_b17_04.py'
    p.write_text(PM04_PROBE, encoding='utf-8')
    code, out = run([PY, '-B', str(p), str(ROOT), str(tree)])
    line = [x for x in out.splitlines() if x.startswith('{')]
    if code != 0 or not line:
        raise RuntimeError('B17-04 探针失败 exit=%d out=%r' % (code, out[-300:]))
    return json.loads(line[-1])


def patch_tree(rel, anchor, new_line=None):
    """合成树文件按 anchor 文本改写（`new_line=None` ⇒ 删该行；`''` ⇒ 上面插空行）。"""
    p = synth_tree() / rel
    lines = p.read_text(encoding='utf-8').splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() == anchor:
            if new_line is None:
                del lines[i]
            elif new_line == '':
                lines.insert(i, '')
            else:
                lines[i] = lines[i][:len(lines[i]) - len(lines[i].lstrip())] + new_line
            p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            return True
    return False


def reset_tree():
    """丢弃并重建合成树（对照注入失败/中断后保证下次从干净副本起跑）。"""
    global _TREE
    shutil.rmtree(TMP / 'tree', ignore_errors=True)
    _TREE = None
    return synth_tree()


# face 行取数（兼容 t16 在 `新增未登记=N` 与 `stale=` 之间插入的 ` 处（N 个文本键）`：
# 旧文案 `…新增未登记=0 stale=…` 与新文案 `…新增未登记=0 处（0 个文本键） stale=…
# 处（0 个） 行号漂移=…` 都能解析；`处（…）` 段按可选处理，四条硬对照判据不放宽）
PM_FACE_RE = re.compile(r'扫描=(\d+) 白名单=(\d+) 新增未登记=(\d+)'
                        r'(?:\s*处（\d+ 个文本键）)?\s+stale=(\d+)'
                        r'(?:\s*处（\d+ 个）)?\s+行号漂移=(\d+)')


@register('B17-04', '内联 role 白名单双向（extra / stale 任一 ⇒ 红，漂移仅 WARN）')
def b17_04():
    reset_tree()
    tool = 'permission_matrix.py --no-dump（face 行）+ 自写探针在合成树上调 SUT check_inline_roles()'
    gauge = '现场 扫描/白名单/新增/stale/漂移；合成树 4 读数：基线 / 注入未登记 / 删登记站点 / 仅挪行号'
    c0, o0 = run([PY, '-B', 'scripts/_sandbox_compat.py', 'scripts/permission_matrix.py', '--no-dump'])
    # 反向阴对照用测试缝：喂入篡改后的 face 文案（仅覆盖取数字符串，四条硬对照判据仍在原位）
    o0 = os.environ.get('B17_04_FACE_OVERRIDE') or o0
    m = PM_FACE_RE.search(o0)
    base = pm_probe(synth_tree())
    extra_file = synth_tree() / 'app/main/zz_b17_verify_roles.py'
    extra_file.write_text("def _probe_only(current_user):\n"
                          "    if current_user.role == 'admin':\n        return True\n", encoding='utf-8')
    m_extra = pm_probe(synth_tree())
    extra_file.unlink()
    pairs = [(f, a) for f, a in base['wl_entries'] if (synth_tree() / f).exists()]
    stale_ok, stale_ent, stale_file = False, None, None
    for f, a in pairs:
        if patch_tree_safe(f, a, 'pass  # b17-04-stale-probe'):
            stale_ok, stale_ent, stale_file = True, a, f
            break
    m_stale = pm_probe(synth_tree()) if stale_ok else {k: -1 for k in ('extra', 'stale', 'face_fail')}
    if stale_file:
        shutil.copy2(ROOT / stale_file, synth_tree() / stale_file)
    drift_ok = bool(stale_file) and patch_tree_safe(stale_file, stale_ent, '')
    m_drift = pm_probe(synth_tree()) if drift_ok else {k: -1 for k in ('extra', 'stale', 'drift', 'face_fail')}
    if stale_file:
        shutil.copy2(ROOT / stale_file, synth_tree() / stale_file)
    val = ('现场 exit=%d face=%s；合成树 基线=%s；注入未登记站点=%s；删登记站点(%s:%s)=%s；'
           '仅插空行=%s' % (c0, m.groups() if m else '未解析',
                          [base['scanned'], base['extra'], base['stale'], base['drift']],
                          [m_extra['scanned'], m_extra['extra'], m_extra['stale'], m_extra['face_fail']],
                          stale_file, stale_ent[:34],
                          [m_stale['extra'], m_stale['stale'], m_stale['face_fail']],
                          [m_drift['extra'], m_drift['stale'], m_drift['drift'], m_drift['face_fail']]))
    contrast = ('阴（本人注入，两个方向都试）：① 合成树加 1 处未登记 role 站点 ⇒ extra=1/face FAIL；'
                '② 把 1 条登记站点改成 `pass` ⇒ stale=1/face FAIL。③ 只插空行 ⇒ drift>0 但 face 仍 OK'
                '（t2 声明「漂移只 WARN 不红」被独立复现）；阳：现场 extra=0/stale=0/exit 0。'
                '④ 取数正则反向阴对照：`B17_04_FACE_OVERRIDE` 喂入被篡改的 face 文案'
                '（`新增未登记=1` / 删掉该字段）⇒ 分别判 FAIL 与 `face=未解析`，CARRIER_EXIT≠0'
                '（证明该正则不是「什么都放过」）；t16 改前/改后两种文案均可解析。')
    record('B17-04', '白名单双向', c0 == 0 and m and m.group(3) == '0' and m.group(4) == '0'
           and base['extra'] == 0 and base['stale'] == 0 and m_extra['extra'] >= 1
           and m_extra['face_fail'] and m_stale['stale'] >= 1 and m_stale['face_fail']
           and m_drift['drift'] >= 1 and m_drift['extra'] == 0 and m_drift['stale'] == 0
           and not m_drift['face_fail'], tool, gauge, val, contrast)


def patch_tree_safe(rel, anchor, new_line):
    """按 anchor 改合成树文件并确保文件仍可编译；编译失败 ⇒ 还原并返回 False。"""
    p = synth_tree() / rel
    orig = p.read_text(encoding='utf-8')
    if not patch_tree(rel, anchor, new_line):
        return False
    try:
        compile(p.read_text(encoding='utf-8'), str(p), 'exec')
        return True
    except SyntaxError:
        p.write_text(orig, encoding='utf-8')
        return False


@register('B17-05', '31 张表对拍（幂等口径差集 0）+ 摘表阴性对照 ⇒ exit 1')
def b17_05():
    tool = '直跑 scripts/check_table_parity.py（现场 + 合成树副本）+ 自注入摘 1 张表 / 还原'
    gauge = '现场/副本 exit；IDEMPOTENT_DIFF 与 UNKNOWN_EXTRAS；摘表后 exit 与差集'
    c0, o0 = run([PY, '-B', 'scripts/check_table_parity.py'])
    t = synth_tree()
    c1, o1 = run([PY, '-B', str(t / 'scripts' / 'check_table_parity.py')])
    mig = t / 'migrations/versions/p0p2messtables_add_create_all_tables.py'
    src = mig.read_text(encoding='utf-8')
    patched = src.replace("    'consumable_categories',\n", '', 1)
    changed = patched != src
    mig.write_text(patched, encoding='utf-8')
    c2, o2 = run([PY, '-B', str(t / 'scripts' / 'check_table_parity.py')])
    mig.write_text(src, encoding='utf-8')
    c3, o3 = run([PY, '-B', str(t / 'scripts' / 'check_table_parity.py')])

    def k(o, key):
        m = re.search(re.escape(key) + r'=(\d+)', o)
        return m.group(1) if m else '?'
    val = ('现场 exit=%d：%s；副本 exit=%d：%s；摘表后 exit=%d（IDEMPOTENT_DIFF=%s FAIL 行=%d）；还原后 exit=%d'
           % (c0, k(o0, 'IDEMPOTENT_DIFF'), c1, k(o1, 'IDEMPOTENT_DIFF'), c2, k(o2, 'IDEMPOTENT_DIFF'),
              len([x for x in o2.splitlines() if 'FAIL' in x]), c3))
    contrast = ('阴（本人注入）：合成树副本里从 `_CREATION_ORDER` 摘掉 `consumable_categories` ⇒ '
                'IDEMPOTENT_DIFF=%s、exit %d（报红）；阳：现场 exit 0 / IDEMPOTENT_DIFF 0 / '
                'UNKNOWN_EXTRAS 0 / RESULT=OK 零写库，还原后复绿 exit %d。'
                % (k(o2, 'IDEMPOTENT_DIFF'), c2, c3))
    record('B17-05', '31 张表对拍', c0 == 0 and c1 == 0 and changed and c2 == 1 and c3 == 0
           and k(o0, 'UNKNOWN_EXTRAS') == '0' and k(o0, 'IDEMPOTENT_DIFF') == '0',
           tool, gauge, val, contrast)


HEAD = 'HEAD'


def count(pattern, target, rev=None):
    """行数：rev=None ⇒ 现场文件 `grep -c -E`；rev='HEAD' ⇒ `git show rev:path` 内逐行正则。"""
    if rev is None:
        return int((run(['grep', '-c', '-E', pattern, str(target)])[1].splitlines() or ['0'])[0] or 0)
    out = run(['git', 'show', '%s:%s' % (rev, target)])[1]
    return len([ln for ln in out.splitlines() if re.search(pattern, ln)])


def probe_json(name, src):
    """把自写探针源码落到 TMP 再跑，返回 (exit, json)。"""
    p = TMP / name
    p.write_text(src, encoding='utf-8')
    code, out = run([PY, '-B', str(p), str(ROOT)])
    line = [x for x in out.splitlines() if x.startswith('{')]
    if code != 0 or not line:
        raise RuntimeError('%s 探针失败 exit=%d out=%r' % (name, code, out[-400:]))
    return code, json.loads(line[-1])


#: B17-06 探针（本载体自写）：副本库造 NULL 行 + 改前/改后谓词对照 + 活端点。
B17_06_PROBE = r'''
import json, pathlib, sys
repo = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repo / 'scripts'))
from _test_bootstrap import ROLES, ensure_role_users, login_as, make_app
from sqlalchemy import text
app, copy_path = make_app(fresh=True)
out = {'copy_db': copy_path, 'roles': list(ROLES)}
S = 'B17VERIFY-RAW-NULL'
with app.app_context():
    from app import db
    from app.models import RawMaterial
    db.create_all()
    rid = db.session.execute(text('SELECT MAX(id) FROM raw_material')).scalar()
    if rid is None:
        out['error'] = 'raw_material 空表'
    else:
        db.session.execute(text('UPDATE raw_material SET is_archived = NULL, internal_number = :s,'
                                ' supplier = :s, melt_number = :s, supplier_number = :s WHERE id = :i'),
                           {'s': S, 'i': rid})
        db.session.commit()
        out['target_id'], out['sentinel'] = rid, S
        t_, v_ = db.session.execute(text('SELECT typeof(is_archived), is_archived'
                                         ' FROM raw_material WHERE id = :i'), {'i': rid}).first()
        out['typeof'], out['null_value'] = t_, v_
        out['old_is_false_target'] = RawMaterial.query.filter(
            RawMaterial.id == rid, RawMaterial.is_archived.is_(False)).count()
        out['old_filter_by_target'] = RawMaterial.query.filter(
            RawMaterial.id == rid).filter_by(is_archived=False).count()
        out['new_unified_target'] = RawMaterial.query.filter(
            RawMaterial.id == rid,
            db.or_(RawMaterial.is_archived.is_(False), RawMaterial.is_archived.is_(None))).count()
        out['null_rows'] = db.session.execute(
            text('SELECT COUNT(*) FROM raw_material WHERE is_archived IS NULL')).scalar()
        out['old_all'] = RawMaterial.query.filter(RawMaterial.is_archived.is_(False)).count()
        out['new_all'] = RawMaterial.query.filter(
            db.or_(RawMaterial.is_archived.is_(False), RawMaterial.is_archived.is_(None))).count()
    mapping, pw = ensure_role_users(app)
    ep = {}
    with app.test_client() as c:
        for role, uname in mapping.items():
            try:
                login_as(c, uname, pw)
                r = c.get('/inventory?type=raw')
                ep[role] = [r.status_code, S in r.get_data(as_text=True)]
            except Exception as exc:
                ep[role] = 'fail:%s' % type(exc).__name__
    out['endpoint_inventory_raw'] = ep
print(json.dumps(out, ensure_ascii=False))
'''


@register('B17-06', 'is_archived 六处统一 + NULL 可见性反转（本人造数复现）')
def b17_06():
    tool = ('现场 grep（--count 口径）+ `git diff --numstat` 空证明未改；'
            '本人载体 .tmp/b17_verify/probe_b17_06.py 走 _test_bootstrap.make_app(fresh=True) 副本库 + 活端点')
    gauge = ('routes.py 统一谓词计数 WT/HEAD；quality.py、mes_service.py 改动行数；'
             '副本库 typeof(is_archived)、改前/改后谓词命中、endpoint 200+sentinel 可见')
    wt = count(r'is_archived\.is_\(None\)', ROOT / 'app/main/routes.py')
    head = count(r'is_archived\.is_\(None\)', 'app/main/routes.py', HEAD)
    qual = count(r'is_archived\.is_\(None\)', ROOT / 'app/main/quality.py')
    mes_exc = count(r'filter_by\(is_archived=False', ROOT / 'app/services/mes_service.py')
    diff = run(['git', 'diff', '--ignore-cr-at-eol', '--numstat', '--',
                'app/main/quality.py', 'app/services/mes_service.py'])[1].strip()
    rc, d = probe_json('probe_b17_06.py', B17_06_PROBE)
    ep = d.get('endpoint_inventory_raw', {}) or {}
    live_ok = [r for r, v in ep.items() if isinstance(v, list) and v[0] == 200 and v[1] is True]
    delta_ok = d.get('null_rows') == (d.get('new_all', 0) - d.get('old_all', 0))
    val = ('routes.py 统一谓词 WT=%d / HEAD=%d（差 %d = 六处）；quality.py=%d、'
           'mes_service.py 例外 filter_by=%d、两文件 `git diff --numstat`=%r（空=未改）；'
           '副本库 %s：typeof=%s / value=%r，NULL 行=%s；改前命中 is_(False)=%s、'
           'filter_by(False)=%s；改后统一谓词命中=%s；old_all=%s → new_all=%s（差=%s）；'
           '端点 GET /inventory?type=raw 200+sentinel 可见的角色=%s'
           % (wt, head, wt - head, qual, mes_exc, diff, d.get('copy_db'), d.get('typeof'),
              d.get('null_value'), d.get('null_rows'), d.get('old_is_false_target'),
              d.get('old_filter_by_target'), d.get('new_unified_target'), d.get('old_all'),
              d.get('new_all'), d.get('null_rows'), live_ok))
    contrast = ('阴（改前谓词，同一副本行）：is_archived IS NULL 的行在 `is_archived.is_(False)` 与 '
                '`filter_by(is_archived=False)` 下命中 %s/%s（不可见）；阳（现场代码，六处已换成统一谓词）：'
                'or_(is_(False), is_(None)) 命中 %s，且活端点返回 200 且该行出现在 HTML 里（%s）。'
                '祖先行为由 HEAD 计数 %d 与现场 %d 的差额（6）佐证，NULL 语义反转在副本库真跑复现。'
                % (d.get('old_is_false_target'), d.get('old_filter_by_target'),
                   d.get('new_unified_target'), live_ok, head, wt))
    ok = (wt == 8 and head == 2 and qual == 1 and mes_exc == 3 and diff == ''
          and d.get('typeof') == 'null' and d.get('old_is_false_target') == 0
          and d.get('old_filter_by_target') == 0 and d.get('new_unified_target') == 1
          and delta_ok and live_ok)
    record('B17-06', 'is_archived 六处统一 + NULL 可见性反转', bool(ok), tool, gauge, val, contrast)


def b17_08_probe(root, only=None):
    """B17-08 端点探针（本载体自写，位于 TMP）：返回 endpoints dict。"""
    cmd = [PY, '-B', str(TMP / 'probe_b17_08.py'), str(root)]
    if only:
        cmd.append(only)
    code, out = run(cmd)
    line = [x for x in out.splitlines() if x.startswith('{')]
    if not line:
        raise RuntimeError('B17-08 探针失败 exit=%d out=%r' % (code, out[-300:]))
    return code, json.loads(line[-1])


@register('B17-08', '死清理块 16→0（8 端点）且 8 端点仍成功下载 xlsx')
def b17_08():
    tool = 'grep -c（现场/HEAD 逐行）+ 自写探针 probe_b17_08.py（副本库 + 7 角色，PK 魔数/zip sheet 校验）'
    gauge = 'HEAD→现场 死块计数；8 端点 HTTP 状态/字节/魔数/sheet；HEAD 版 routes.py 作阴性对照'
    marks = {'死块注释': '确保在请求结束后删除临时文件', 'temp_path = None': 'temp_path = None',
             'if temp_path 分支': 'if temp_path and os.path.exists(temp_path)',
             'os.remove(temp_path)': 'os.remove(temp_path)'}
    st = {k: (count(re.escape(v), 'app/main/routes.py'), count(re.escape(v), 'app/main/routes.py', HEAD))
          for k, v in marks.items()}
    code, pos = b17_08_probe(ROOT)
    eps = pos['endpoints']
    live_ok = {k: (v.get('status') == 200 and v.get('pk') and (v.get('sheets') or 0) >= 1)
               for k, v in eps.items()}
    reset_tree()
    keep = (synth_tree() / 'app/main/routes.py').read_text(encoding='utf-8')
    (synth_tree() / 'app/main/routes.py').write_text(
        run(['git', 'show', 'HEAD:app/main/routes.py'])[1], encoding='utf-8')
    ncode, neg = b17_08_probe(synth_tree(), 'bonus_penalties_export')
    (synth_tree() / 'app/main/routes.py').write_text(keep, encoding='utf-8')
    negrec = neg['endpoints']['bonus_penalties_export']
    ok = (st['死块注释'][0] == 0 and st['死块注释'][1] == 8 and st['temp_path = None'][1] == 11
          and all(live_ok.values()) and len(live_ok) == 8 and 'AttributeError' in str(negrec.get('exc')))
    val = ('HEAD→现场：注释 %d→%d、temp_path=None %d→%d、if-branch %d→%d、os.remove %d→%d；'
           '8/8 端点 200+PK+非空 sheet：%s；阴性(HEAD routes.py 注入副本树) = %s' % (
               st['死块注释'][1], st['死块注释'][0], st['temp_path = None'][1], st['temp_path = None'][0],
               st['if temp_path 分支'][1], st['if temp_path 分支'][0],
               st['os.remove(temp_path)'][1], st['os.remove(temp_path)'][0],
               ','.join('%s=%s/%dB' % (k, eps[k]['status'], eps[k]['bytes']) for k in eps),
               negrec.get('exc')))
    contrast = ('阴（本人）：副本树换回 `git show HEAD:app/main/routes.py` ⇒ bonus_penalties_export '
                '抛 %s（该端点 HEAD 即断）；阳：现场 8 端点全 200，死块变量仅剩 3 处 import_* 活端点。'
                % negrec.get('exc'))
    record('B17-08', '死清理块 + 8 端点下载', bool(ok), tool, gauge, val, contrast)


@register('B17-T3-2L', 't3 两行额外删除：export_bonus_penalties 笔误非本批引入（500→200）')
def b17_t3_two_lines():
    tool = ('`git show HEAD:app/main/routes.py` 逐行 + `git diff -U3` 上下文 + 自写探针（副本树注入 HEAD 版/现场版）'
            '+ app/main/forms.py 字段表')
    gauge = 'process_code 出现数 HEAD→现场；HEAD 被删两行原文与行号；表单字段；端点改前/改后读数'
    head_total = count('process_code', 'app/main/routes.py', HEAD)
    wt_total = count('process_code', 'app/main/routes.py')
    head_lines = run(['git', 'show', 'HEAD:app/main/routes.py'])[1].splitlines()
    two = [ln.strip() for ln in head_lines[3105:3107]]
    hunk = [ln for ln in run(['git', 'diff', '--ignore-cr-at-eol', '-U3', '--', 'app/main/routes.py'])[1].splitlines()
            if ln.startswith('@@') and 'export_bonus_penalties' in ln]
    fields = [ln.strip() for ln in (ROOT / 'app/main/forms.py').read_text(encoding='utf-8').splitlines()[180:190]]
    has_pc = any('process_code' in f for f in fields)
    reset_tree()
    keep = (synth_tree() / 'app/main/routes.py').read_text(encoding='utf-8')
    (synth_tree() / 'app/main/routes.py').write_text(run(['git', 'show', 'HEAD:app/main/routes.py'])[1], encoding='utf-8')
    _, neg = b17_08_probe(synth_tree(), 'bonus_penalties_export')
    (synth_tree() / 'app/main/routes.py').write_text(keep, encoding='utf-8')
    _, pos = b17_08_probe(ROOT, 'bonus_penalties_export')
    before, after = neg['endpoints']['bonus_penalties_export'], pos['endpoints']['bonus_penalties_export']
    ok = (head_total == 84 and wt_total == 82 and two == ['if form.process_code.data:',
          'query = query.join(ProcessPrice).filter(ProcessPrice.process_code == form.process_code.data)']
          and bool(hunk) and not has_pc and before.get('exc') == 'AttributeError'
          and after.get('status') == 200 and after.get('pk'))
    val = ('process_code 出现数 HEAD=%d → 现场=%d（差 2）；被删两行 = HEAD:%d/%d %r；hunk=%r；'
           'ExportBonusPenaltyForm 字段=%r（process_code=%s）；'
           '改前读数 = %s/%s；改后读数 = HTTP %s / %dB / PK=%s' % (
               head_total, wt_total, 3106, 3107, two, hunk[0][:60] if hunk else None,
               [f.split('=')[0] for f in fields if '=' in f], has_pc,
               before.get('role'), before.get('exc'), after.get('status'), after.get('bytes'), after.get('pk')))
    contrast = ('阴（本人）：HEAD 版 routes.py 在副本树复现 AttributeError（%s 无 process_code 字段 ⇒ 有效 POST 500）；'
                '阳：现场版改后 HTTP 200 + xlsx 有效。该修复的计数口径（process_code 84→82）与 B17-08 死块口径'
                '（注释/temp_path/if-branch/os.remove）互斥，未混入 16 处死块计数。' % 'ExportBonusPenaltyForm')
    record('B17-T3-2L', '两行额外删除独立复核', bool(ok), tool, gauge, val, contrast)


WRITE_ROW = re.compile(r'\[(OK  |FAIL)\] (\w+)\s+cap=(\S+)\s+写端点=(\d+)/(\d+)\s+allow≥1=(\S+)\s+deny≥1=(\S+)\s+5xx/EXC=(\S+)')


def write_face(out):
    """从 permission_matrix 输出解析写端点面（模块 → 读数）。"""
    rows = {}
    for m in WRITE_ROW.finditer(out):
        rows[m.group(2)] = {'ok': m.group(1).strip() == 'OK', 'guarded': int(m.group(4)),
                            'total': int(m.group(5)), 'allow': m.group(6), 'deny': m.group(7),
                            'fivexx': m.group(8)}
    return rows


@register('B17-13', 'C-06 写端点 face（方法参数化）+ 自注入放行 ⇒ 转红')
def b17_13():
    tool = ('直跑 permission_matrix.py --no-dump（现场）+ 副本树基线 + **本人手改**副本树 app/main/equipment.py '
            '删 `<def equipment_downtime>` 上方 @require_capability 作阴性对照')
    gauge = '写端点面 4 模块读数 / 退出码；注入后靶向模块转红且其余三模块仍绿'
    c0, o0 = run([PY, '-B', 'scripts/_sandbox_compat.py', 'scripts/permission_matrix.py', '--no-dump'])
    live = write_face(o0)
    reset_tree()
    t = synth_tree()
    c1, o1 = run([PY, '-B', 'scripts/permission_matrix.py', '--no-dump'], cwd=t)
    eq = t / 'app/main/equipment.py'
    keep = eq.read_text(encoding='utf-8')
    lines = keep.splitlines()
    idx = [i for i, ln in enumerate(lines) if ln.startswith('def equipment_downtime')]
    guard = [i for i in range(idx[0] - 1, max(idx[0] - 4, -1), -1) if lines[i].strip().startswith('@require_capability')]
    removed = lines[guard[0]] if guard else None
    if removed:
        del lines[guard[0]]
        eq.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    c2, o2 = run([PY, '-B', 'scripts/permission_matrix.py', '--no-dump'], cwd=t)
    inj = write_face(o2)
    eq.write_text(keep, encoding='utf-8')
    tot = sum(v['guarded'] for v in live.values())
    live_ok = all((v['ok'] and v['fivexx'] == '无' and v['deny'] != '-') if v['total'] else
                  (v['total'] == 0 and v['deny'] == '-') for v in live.values())
    ok = (c0 == 0 and c1 == 0 and c2 == 1 and len(live) == 4 and tot == 21 and live_ok
          and not inj.get('equipment', {}).get('ok', True)
          and all(inj[k]['ok'] for k in inj if k != 'equipment'))
    val = ('现场 exit=%d：写端点面 %s；合计 %d 写端点；副本树基线 exit=%d；'
           '本人注入（删 %r）⇒ exit=%d，equipment.ok=%s deny=%s，其余三模块 ok=%s' % (
               c0, {k: '%d/%d' % (v['guarded'], v['total']) for k, v in live.items()}, tot, c1,
               removed, c2, inj.get('equipment', {}).get('ok'), inj.get('equipment', {}).get('deny'),
               [k for k in inj if k != 'equipment' and inj[k]['ok']]))
    contrast = ('阴（本人手改副本树，非 SUT 的 --inject 开关）：放行 `main.equipment_downtime` ⇒ 该模块写面 FAIL、exit 1，'
                '其余三模块仍绿（靶向性）；阳：现场与副本树基线 exit 0，21 端点逐条 allow≥1/deny≥1/5xx=0，'
                '页面面 4 模块不回归、anon_open=0。')
    record('B17-13', '写端点 face + 放行注入', bool(ok), tool, gauge, val, contrast)


MC = ROOT / 'test-reports-2026-10' / 'harness' / 'measure_coverage.py'
DRIFT = ROOT / 'test-reports-2026-10' / 'harness' / 'coverage_drift.py'
JUDGES = ['test-reports-2026-10/harness/coverage_drift.py', 'test-reports-2026-10/harness/ci_gates.py',
          'test-reports-2026-10/harness/negative_matrix.py', 'scripts/check_doc_claims.py']


@register('B17-14', '多方法（GET+写）面进判据层 + docstring 同步（现场重取）')
def b17_14():
    tool = ('直跑 harness/measure_coverage.py --out（现场重取）+ **变异体存活测试**：把 face 键抹成 0/99 后跑 '
            'harness/coverage_drift.py（判据层）看是否转红 + 判据层引用面键计数 + 读 docstring')
    gauge = ('face 计数（N/M 现场重取）/ 变异体 exit（判据层是否转红）/ 判据层引用数 / docstring 中的 273 现场值'
             '（`271` 仅允许出现在 A-70 就地注记行）')
    cov = TMP / 'cov_live.json'
    c0, o0 = run([PY, '-B', 'test-reports-2026-10/harness/measure_coverage.py', '--out', str(cov)])
    js = json.loads(cov.read_text(encoding='utf-8'))
    s = js['summary']
    joined = '\n'.join(o0.splitlines()[:40])
    face_line = [ln for ln in o0.splitlines() if '[coverage][multi]' in ln]
    mutant_p = TMP / 'cov_mutant.json'
    mj = json.loads(cov.read_text(encoding='utf-8'))
    mj['summary']['multi_method_with_get_uncovered'] = 0
    mj['summary']['multi_method_with_get_total'] = 99
    mj['uncovered_multi_method_with_get'] = []
    mutant_p.write_text(json.dumps(mj, ensure_ascii=False), encoding='utf-8')
    d0, o_d0 = run([PY, '-B', 'test-reports-2026-10/harness/coverage_drift.py', '--coverage', str(cov)])
    d1, o_d1 = run([PY, '-B', 'test-reports-2026-10/harness/coverage_drift.py', '--coverage', str(mutant_p)])
    fails0 = re.findall(r'\[FAIL\] (D-\d)', o_d0)
    fails1 = re.findall(r'\[FAIL\] (D-\d)', o_d1)
    refs = {p: int((run(['grep', '-c', '-E', 'multi_method_with_get|MULTI-UNCOVERED', p])[1].splitlines()
                     or ['0'])[0] or 0) for p in JUDGES}
    doc = (MC.read_text(encoding='utf-8').splitlines())
    head_doc = '\n'.join(doc[:20])
    stale = [i + 1 for i, ln in enumerate(doc) if re.search(r'\b271\b', ln) and 'A-70' not in ln]
    doc_live = bool(re.search(r'\b273\b', head_doc))
    ok = (c0 == 0 and face_line and s['multi_method_with_get_total'] == 43
          and s['multi_method_with_get_uncovered'] == 37 and any(refs.values())
          and fails1 and doc_live and not stale)
    val = ('现场 exit=%d：规则 %d / GET+写 N=%d / 未命中 M=%d；判据层引用面键 %r；'
           '变异体（M=0,N=99,明细清空）⇒ drift exit=%d FAIL=%r（未变异 exit=%d FAIL=%r）；'
           'docstring 含 273=%s、残留 271 行=%r' % (
               c0, s['rules_total'], s['multi_method_with_get_total'], s['multi_method_with_get_uncovered'],
               refs, d1, fails1, d0, fails0, doc_live, stale))
    contrast = ('阳（t13 返工后已闭环）：①「进判据层」= `harness/coverage_drift.py` 新增 D-9 读 '
                '`multi_method_with_get_total/_uncovered/len(uncovered_…)`（N==43 / M==37 / M==len(list) / M<=N，'
                '失败计入 `failed` ⇒ exit 1），我把 face 抹成 0/99/明细清空后 drift exit=%d FAIL=%r，未变异 exit=%d '
                'FAIL=%r；② docstring 现场值 = 273/112（非 GET 110→112），残留 271 行=%r 且仅限 A-70 注记。'
                '阴：t6 复验轮该处为「0 条判据读该键 + docstring 留 271」⇒ 判红。'
                '最小复现：`python -B test-reports-2026-10/harness/measure_coverage.py --out /abs/cov.json` → '
                '`python -B test-reports-2026-10/harness/coverage_drift.py --coverage /abs/cov.json`；'
                '`grep -rn multi_method_with_get --include=*.py . \\| grep -v /\\.tmp/`' % (d1, fails1, d0, fails0, stale))
    record('B17-14', '多方法面进判据层 + docstring', bool(ok), tool, gauge, val, contrast)


@register('B17-03', '老库升级一次性脚本：dry-run 零写入 + --apply 连跑两次幂等 + stamp 固化')
def b17_03():
    tool = 'scripts/upgrade_legacy_db.py（自建 44 表老库副本）+ sqlite3 + sha256'
    gauge = 'dry-run 写盘=0；apply#1 → 75 表/ver=p1nonctarget/有备份；apply#2 → 表集与版本号不变；脚本无 `db migrate`'
    drop, nm, nl = create_all_only()
    fx, t0, v0 = legacy_fixture('b17_03', drop)
    s0 = sha256(fx)
    d_rc, d_out = run([PY, '-B', 'scripts/upgrade_legacy_db.py', '--db', str(fx)])
    zero = sha256(fx) == s0
    d_ok = d_rc == 0 and 'DRY_RUN=1' in d_out
    a1, o1 = run([PY, '-B', 'scripts/upgrade_legacy_db.py', '--db', str(fx), '--apply'])
    t1, v1 = db_state(fx)
    a2, o2 = run([PY, '-B', 'scripts/upgrade_legacy_db.py', '--db', str(fx), '--apply'])
    t2, v2 = db_state(fx)
    body = (ROOT / 'scripts/upgrade_legacy_db.py').read_text(encoding='utf-8')
    # 口径：只看「执行路径」是否会把 migrate 作为子命令跑（文档里写「禁用 flask db migrate」不算）
    no_mig = not re.search(r"['\"]db['\"]\s*,\s*['\"]migrate['\"]", body) \
        and bool(re.search(r"['\"]db['\"]\s*,\s*['\"]stamp['\"]", body))
    baks = sorted(TMP.glob('legacy_b17_03.db.bak-*'))
    ok = (len(t0) == 44 and len(drop) == 31 and nm > len(drop) and zero and d_ok and a1 == 0
          and len(t1) == 75 and v1 == ['p1nonctarget'] and bool(baks) and a2 == 0
          and t2 == t1 and v2 == v1 and no_mig)
    record('B17-03', '老库升级一次性脚本', ok, tool, gauge,
           'fixture %d 表 ver=%s → dry-run rc=%d 写盘=%s → apply#1 rc=%d ⇒ %d 表 ver=%s 备份=%d'
           ' → apply#2 rc=%d ⇒ %d 表 ver=%s（表集不变=%s）/ 执行路径含 stamp=%s 含 migrate=%s / '
           '自算 create_all-only 表=%d（metadata %d − 字面 %d，另有迁移多出 %d）'
           % (len(t0), v0[0] if v0 else '-', d_rc, not zero, a1, len(t1), v1[0] if v1 else '-',
              len(baks), a2, len(t2), v2[0] if v2 else '-', t2 == t1, no_mig, not no_mig,
              len(drop), nm, nl, nl + len(drop) - nm),
           '阴（构造）：fixture 本身 44 表 / ver=f179636cecf0（老库形态）；若 stamp 或自愈写错，第二次 '
           'apply 必改 schema 或版本号。转引（t4 自报，未复现其读数）：44→75 表 / 540→830 列。')
    if not ok:
        print('    [B17-03 detail] dry=%r a1=%r a2=%r' % (d_out[-300:], o1[-300:], o2[-300:]))


@register('B17-17', '31 张表幂等迁移：老库副本 `flask db upgrade` 连跑两次（第二次 exit 0 且无 schema 变更）')
def b17_17():
    tool = 'python -m flask db upgrade（DATABASE_URL 指向自建 44 表老库副本）+ sqlite3 + sha256'
    gauge = '两次 exit；第二次与第一次的表集/列数/版本号是否逐位相同'
    drop, nm, nl = create_all_only()
    fx, t0, v0 = legacy_fixture('b17_17', drop)
    env = {'DATABASE_URL': 'sqlite:///%s' % fx, 'FLASK_APP': 'wsgi.py'}
    u1, o1 = run([PY, '-m', 'flask', 'db', 'upgrade'], env=env)
    t1, v1 = db_state(fx)
    s1 = sha256(fx)
    u2, o2 = run([PY, '-m', 'flask', 'db', 'upgrade'], env=env)
    t2, v2 = db_state(fx)
    ok = u1 == 0 and u2 == 0 and t1 == t2 and v1 == v2 and sha256(fx) == s1 and v2 == ['p1nonctarget']
    tail1 = [x for x in o1.splitlines() if 'ERROR' in x or 'error' in x or 'FAILED' in x][-1:] or ['-']
    record('B17-17', '31 张表幂等迁移（连跑两次）', ok, tool, gauge,
           'fixture %d 表 ver=%s → upgrade#1 rc=%d ⇒ %d 表 ver=%s → upgrade#2 rc=%d ⇒ %d 表 ver=%s '
           '（第二次表集不变=%s、文件 sha 不变=%s）/ 自算 create_all-only 表=%d / upgrade#1 错误行=%r'
           % (len(t0), v0[0] if v0 else '-', u1, len(t1), v1[0] if v1 else '-', u2, len(t2),
              v2[0] if v2 else '-', t2 == t1, sha256(fx) == s1, len(drop), tail1[0][:180]),
           '阴（构造）：fixture 是老库形态（44 表 / ver=f179636cecf0）；若 31 张表的迁移没有存在性守卫，'
           '第一次 upgrade 就会撞 create_table 冲突（AGENTS.md 记「全链重放不可行」）。')
    if not ok:
        print('    [B17-17 detail] rc1=%d rc2=%d\n%s\n%s' % (u1, u2, o1[-900:], o2[-600:]))


@register('B17-02', 'blocked(生产面冻结) 只登记：不写闸门脚本、不改 app/__init__.py、不计入通过')
def b17_02():
    tool = 'find check_db_url_guard*.py / 契约 §3 原文 grep / `create_all` 现场正则 / git status'
    gauge = '闸门脚本不存在；契约含 4 个 blocked 口径串；`^\\s*db.create_all\\(\\)` 命中 2 行；app/__init__.py 本批零改动'
    guards = [str(p.relative_to(ROOT)) for p in ROOT.rglob('check_db_url_guard*.py')
              if '.git' not in p.parts]
    c = (ROOT / 'test-reports-2026-10/B17-00-契约冻结.md').read_text(encoding='utf-8')
    needles = ['blocked(生产面冻结)', 'not_counted_as_passed=true',
               '不得**计入批次17 通过项', '本批不写 `scripts/check_db_url_guard.py`']
    hits = [n for n in needles if n in c]
    src = (ROOT / 'app/__init__.py').read_text(encoding='utf-8')
    calls = re.findall(r'^\s*db\.create_all\(\)', src, re.M)
    lines = [l for l in src.splitlines() if 'create_all' in l]
    _, st = run(['git', 'status', '--porcelain', '--', 'app/__init__.py'])
    ok = not guards and len(hits) == len(needles) and len(calls) == 2 and not st.strip()
    record('B17-02', 'blocked（只登记，不计入通过）', ok, tool, gauge,
           'check_db_url_guard*.py 命中=%d；契约口径串 %d/%d；`^\\s*db.create_all()`=%d（含注释/文档串共 %d 行）；'
           'app/__init__.py git status=%r ⇒ 本批未动生产面闸门'
           % (len(guards), len(hits), len(needles), len(calls), len(lines), st.strip()[:40]),
           '本项**不计入通过**（契约 §3.1/§3.3）：blocked ≠ pass；解除条件 = 生产面冻结解除 + 显式授权，'
           '解除后判据 `r2_c07_probe --guard-source present` ⇒ create_all_calls 1→0（本批不执行）。'
           '阴性对照：若本批偷写闸门脚本或改 app/__init__.py，本 check 转红。',
           status='BLOCKED')   # 呈现核通过 ≠ B17-02 通过：blocked 不计入通过数


B17_09_PROBE = r'''
import io, json, os, pathlib, sys, time
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / 'scripts'))
from _test_bootstrap import make_app
from werkzeug.datastructures import FileStorage
app, copy_db = make_app(fresh=True)
out = {'copy_db': copy_db}
with app.app_context():
    from app.main.routes import cleanup_temp_files, save_temp_file
    folder = app.config['TEMP_FOLDER']
    p = save_temp_file(FileStorage(stream=io.BytesIO(b'b17-09'), filename='b17_verify.csv'))
    d = os.path.dirname(p)
    out.update(folder=folder,
               under_folder=os.path.realpath(d).startswith(os.path.realpath(folder)),
               dir_before=os.path.isdir(d), file_before=os.path.isfile(p))
    old = time.time() - 3600                      # 目录 mtime 回拨 1h（钩子阈值 300s）
    os.utime(d, (old, old))
    cleanup_temp_files()
    out['dir_after_aged'] = os.path.exists(d)
    p2 = save_temp_file(FileStorage(stream=io.BytesIO(b'b17-09b'), filename='b17_v_b.csv'))
    d2 = os.path.dirname(p2)
    cleanup_temp_files()                          # 阴性：新鲜目录不得被清
    out['fresh_kept'] = os.path.isdir(d2)
print(json.dumps(out))
'''


@register('B17-09', 'mkdtemp 目录泄漏：清理钩子整体回收过期子目录（轨二标「需非沙箱环境」不计入）')
def b17_09():
    tool = '自写探针（副本库真跑 save_temp_file/cleanup_temp_files）+ 现场正则核钩子接线'
    gauge = '子目录落在 TEMP_FOLDER 下；mtime 回拨 1h ⇒ 钩子整目录回收；新鲜目录不被清（阴性）'
    rc, j = probe_json('probe_b17_09.py', B17_09_PROBE)
    src = (ROOT / 'app/main/routes.py').read_text(encoding='utf-8')
    hook = bool(re.search(r'@bp\.before_request[\s\S]{0,240}?cleanup_temp_files\(\)', src))
    rmtree = bool(re.search(r'os\.path\.isdir\(file_path\)[\s\S]{0,420}?shutil\.rmtree\(file_path\)', src))
    excl = '需非沙箱环境' in (ROOT / 'test-reports-2026-10/B17-00-契约冻结.md').read_text(encoding='utf-8')
    ok = (rc == 0 and j.get('under_folder') and j.get('dir_before') and j.get('file_before')
          and not j.get('dir_after_aged') and j.get('fresh_kept') and hook and rmtree and excl)
    record('B17-09', 'mkdtemp 目录泄漏', ok, tool, gauge,
           'TEMP_FOLDER 下 mkdtemp 子目录=%s；回拨 1h 后 dir_exists=%s（回收）；新鲜目录存活=%s；'
           'before_request 钩子接线=%s；isdir→rmtree 分支=%s；契约含「需非沙箱环境」=%s'
           % (j.get('under_folder'), j.get('dir_after_aged'), j.get('fresh_kept'), hook, rmtree, excl),
           '阴（本人对照）：**不**回拨 mtime 的新鲜目录在同一次 cleanup_temp_files() 后仍存活 ⇒ 钩子是'
           '过期回收而非无脑 rmtree，判据对「目录泄漏」敏感。轨二（系统 TEMP 增量）= 契约标「需非沙箱环境」，'
           '**不计入本批判定**。')


def upload_census():
    """自算「消费上传的 handler」及其落盘机制（纯文本邻近 `def`，不复用实现者脚本）。"""
    disk, memory, eps = [], [], []
    for p in sorted((ROOT / 'app').rglob('*.py')):
        lines = p.read_text(encoding='utf-8').splitlines()
        for i, l in enumerate(lines):
            if 'request.files' not in l and 'form.file.data' not in l:
                continue
            start = max(j for j in range(i + 1) if re.match(r'\s*def\s+\w+', lines[j]))
            fn = re.match(r'\s*def\s+(\w+)', lines[start]).group(1)
            end = next((k for k in range(start + 1, len(lines))
                        if re.match(r'(def\s+\w+|@bp\.route)', lines[k])), len(lines))
            body = '\n'.join(lines[start:end])
            key = '%s:%s' % (p.relative_to(ROOT), fn)
            if key in eps:
                continue
            eps.append(key)
            mech = None
            if 'save_upload_files(' in body:
                mech = 'mkdtemp(系统 temp)+finally rmtree'
            elif 'save_temp_file(' in body:
                mech = 'mkdtemp(TEMP_FOLDER)'
            elif 'gettempdir()' in body:
                mech = 'gettempdir()'
            elif 'TEMP_FOLDER' in body and '.save(' in body:
                mech = 'TEMP_FOLDER 直写'
            elif re.search(r'read_excel\(\s*file\b', body):
                mech = '内存流(pd.read_excel(file))'
            (memory if mech and mech.startswith('内存') else disk).append((key, mech))
    return {'endpoints': eps, 'disk': disk, 'memory': memory}


@register('B17-10', '上传落盘口径收窄（措辞 + 端点计数现场重取）')
def b17_10():
    tool = 'AGENTS.md 原文 grep + 自算 census（app/**/*.py 里 request.files / form.file.data 的邻近 def + 落盘机制）'
    gauge = ('措辞「需真实路径时才落盘」命中且旧「必须落盘」表述消失；端点口径 = AGENTS.md:49 现场文案（11/10/1）'
             ' vs 自算；漏计两端点须被点名')
    agents = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    wording = '需真实路径时才落盘' in agents
    stale = any(s in agents for s in ('导入端点必须落盘', '导入必须落盘'))
    cen = upload_census()
    got = (len(cen['endpoints']), len(cen['disk']), len(cen['memory']))
    doc = (11, 10, 1)   # t12 返工后现场口径（原 9/8/1）；T3 复验轮：t15
    doc_named = ('11 个导入端点 = 10 落盘 + 1 内存流' in agents
                 and 'save_upload_files' in agents and ':2776' in agents and ':2825' in agents)
    mech = {}
    for _, m in cen['disk']:
        mech[m] = mech.get(m, 0) + 1
    unlisted = [e for e, m in cen['disk'] if m.startswith('mkdtemp(系统')]
    ok = wording and not stale and got == doc and doc_named
    record('B17-10', '上传落盘口径收窄', ok, tool, gauge,
           '措辞命中=%s 旧表述残留=%s；自算 %d 上传端点 = %d 落盘 + %d 内存流（%s）；'
           'AGENTS.md:49 现场口径 %s、点名 :2776/:2825=%s；契约历史读数 9/8/1 仅存于冻结/历史件'
           % (wording, stale, got[0], got[1], got[2],
              '，'.join('%s×%d' % (k, v) for k, v in sorted(mech.items())),
              '%d/%d/%d' % doc, doc_named),
           '阳（t12 返工后已闭环）：措辞面 = 「需真实路径时才落盘」且在无「必须落盘」；口径面 = 现场文案'
           '「11 个导入端点 = 10 落盘 + 1 内存流」并点名两个被漏计的 `save_upload_files()` 端点'
           '（`app/main/routes.py:2776` `import_alloy_process_prices` / `:2825` `import_alloy_bom`，'
           'helper `:5606`）。阴：t6 复验轮该处仍是 9/8/1 ⇒ 判红；现自算与文案逐项相符。'
           '最小复现：`grep -n "save_upload_files" app/main/routes.py`（2776/2825/5606）'
           ' + `载体 --only B17-10`')


@register('B17-12', 'P11 部分关闭登记：append-only 落指针 + 指针现场可复算')
def b17_12():
    tool = 'grep `B17-登记.md` §B17-12/§Z.4 + 逐条 sha256 现场复算 + P11 指针存在性'
    gauge = ('冻结判据：§B17-12 段存在 + `.tmp_v15_*`/`_probe_tmp/gate-baseline.txt` 已清 + `_probe_seed.py` 保留；'
             '**校准**：§Z.4 的 path→sha256 漂移只记 WARN（PTR-1），不入判定——冻结判据写「append-only 落指针、'
             '**不得改写旧值**」，即旧值本就不该被覆盖，故不要求指针与现场时时相符')
    reg = (ROOT / 'test-reports-2026-10/B17-登记.md').read_text(encoding='utf-8')
    sec = '§B17-12 P11 部分关闭登记' in reg
    rows = re.findall(r'^\|\s*`([^`]+)`[^|]*\|\s*`?([0-9a-f]{64})`?\s*\|', reg, re.M)
    stale = [rel for rel, want in rows
             if not (ROOT / rel).exists() or sha256(ROOT / rel) != want]
    v15 = [str(p.relative_to(ROOT)) for p in ROOT.glob('.tmp_v15_*')]
    v15 += [str(p.relative_to(ROOT)) for p in (ROOT / 'test-reports-2026-10').glob('**/.tmp_v15_*')]
    gate = (ROOT / 'test-reports-2026-10/_probe_tmp/gate-baseline.txt').exists()
    seed = (ROOT / 'scripts/_probe_seed.py').exists()
    # t14 返工（T3 复验轮 t15）：§Z.5 append-only 订正须存在、旧值须逐字保留、须带时点与复现命令
    z5 = ('Z.5 追加订正' in reg and '原登记值' in reg and '4e37a39b826bf09623515672b82e767608d950755b151e40d5d1160200ca3909' in reg
          and 'sha256sum AGENTS.md' in reg and '订正时点' in reg)
    reg322 = '现场仍写' in reg   # §Z.5.3 残留的陈旧断言（t15 判为未闭环 R-1，见报告 §6）
    ok = sec and len(rows) >= 8 and not v15 and not gate and seed and z5   # 指针漂移=WARN(PTR-1/PTR-2)，不入判定
    record('B17-12', 'P11 部分关闭登记（只落指针）', ok, tool, gauge,
           '冻结判据（P11 载体清空 + 登记段）：`.tmp_v15_*` 残留=%d、`_probe_tmp/gate-baseline.txt` 存在=%s、'
           '`scripts/_probe_seed.py` 保留=%s、§B17-12 段=%s；**t14 追加订正**：§Z.5 存在且含「原登记值」逐字'
           '旧值 + 时点 + `sha256sum AGENTS.md` 复现命令=%s；**附加项**：§Z.4 的 %d 条 path→sha256 指针现场'
           '复算 ⇒ 不符 %d 条%s；`§Z.5.3` 残留「现场仍写」陈旧断言=%s（未闭环 R-1）'
           % (len(v15), gate, seed, sec, z5, len(rows), len(stale),
              ('（%s）' % ', '.join(stale) if stale else ''), reg322),
           '口径：登记件声明「只落指针、不改旧值」⇒ 我按登记值逐条 sha256 现场复算并照实列出漂移条数，但'
           '**漂移只作 WARN（PTR-1/PTR-2，见报告 §6）不作 FAIL**：冻结判据禁止改写旧值（旧值错本就该保留原样另起新行）'
           '且未要求指针与现场时时相符。T3 复验轮：§Z.5 的 append-only 订正确认到位（旧值 4e37a39b… 逐字仍在、'
           '新增改前值/现场值/时点/复现命令）；但订正件自身又出现同类时点漂移（§Z.5.1 记的「现场值」e680fbd5… '
           '在 t12 改 AGENTS.md 后已非现现场值 a89af3ed…）⇒ 记 PTR-2 WARN；且 §Z.5.3 尾行仍称 AGENTS.md 现场写 9/8/1 '
           '⇒ 记未闭环 R-1（复现：`sha256sum AGENTS.md` + `grep -n "现场仍写" test-reports-2026-10/B17-登记.md`）。')


META_PROBE = r'''
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / 'scripts'))
from _test_bootstrap import make_app
import app.models                                     # 蓝图懒加载 ⇒ 显式导入才有 metadata
from app import db
app, copy_db = make_app(fresh=True)
with app.app_context():
    print(json.dumps({'tables': sorted(db.metadata.tables), 'copy_db': copy_db}))
'''


def create_all_only():
    """自算「create_all-only 表」= ORM metadata 表集 − 迁移文件字面 create_table 名集。"""
    _, meta = probe_json('probe_meta.py', META_PROBE)
    literal = set()
    for f in sorted((ROOT / 'migrations/versions').glob('*.py')):
        literal |= set(re.findall(r"op\.create_table\(\s*['\"]([A-Za-z0-9_]+)['\"]",
                                  f.read_text(encoding='utf-8')))
    return sorted(set(meta['tables']) - literal), len(meta['tables']), len(literal)


def legacy_fixture(tag, drop):
    """自建老库 fixture：`app.db` 副本 − 31 张 create_all-only 表 + 版本号回退到 f179636cecf0。"""
    dst = TMP / ('legacy_%s.db' % tag)
    shutil.copy2(ROOT / 'app.db', dst)
    con = sqlite3.connect(str(dst))
    for name in drop:
        con.execute('DROP TABLE IF EXISTS "%s"' % name)
    con.execute("UPDATE alembic_version SET version_num='f179636cecf0'")
    con.commit()
    tbls = sorted(r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    ver = [r[0] for r in con.execute('SELECT version_num FROM alembic_version')]
    con.close()
    return dst, tbls, ver


def db_state(path):
    con = sqlite3.connect(str(path))
    tbls = sorted(r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    ver = [r[0] for r in con.execute('SELECT version_num FROM alembic_version')] \
        if 'alembic_version' in tbls else []
    con.close()
    return tbls, ver


def main(argv=None):
    ap = argparse.ArgumentParser(description='B17 非作者独立验证载体（t6）')
    ap.add_argument('--only', default='', help='只跑指定条目（逗号分隔），默认全跑')
    args = ap.parse_args(argv)
    if shutil.which(PY) is None or not ROOT.is_dir():
        print('[ERROR] 环境不满足：PY=%s ROOT=%s' % (PY, ROOT))
        return 2
    TMP.mkdir(parents=True, exist_ok=True)
    want = [s.strip() for s in args.only.split(',') if s.strip()]
    if want and not any(bid in want for bid, _n, _f in REGISTRY):
        print('[usage] --only 未匹配任何条目：%r（可用：%s）' % (args.only, ','.join(b for b, _n, _f in REGISTRY)))
        return 3
    db_before = sha256(ROOT / 'app.db')
    for bid, name, fn in REGISTRY:
        if want and bid not in want:
            continue
        try:
            fn()
        except Exception as exc:                      # noqa: BLE001
            record(bid, name, False, '载体自身', '未捕获异常', repr(exc)[:200], '—')
    db_after = sha256(ROOT / 'app.db')
    keys = ('bid', 'name', 'status', 'tool', 'gauge', 'value', 'contrast')
    (TMP / 'results.json').write_text(
        json.dumps([dict(zip(keys, r)) for r in RESULTS], ensure_ascii=False, indent=1), encoding='utf-8')
    fails = [r for r in RESULTS if r[2] == 'FAIL']
    blocked = [r for r in RESULTS if r[2] == 'BLOCKED']
    npass = len([r for r in RESULTS if r[2] == 'PASS'])
    print('\n==== 汇总 %d 条：PASS %d / FAIL %d / BLOCKED %d（blocked 不计入通过）===='
          % (len(RESULTS), npass, len(fails), len(blocked)))
    for r in blocked:
        print('  BLOCKED %s %s（not_counted_as_passed=true，本批判定排除）' % (r[0], r[1]))
    for r in fails:
        print('  FAIL %s %s | %s | %s' % (r[0], r[1], r[5], r[6]))
    if db_before != db_after:
        print('[ERROR] 真实 app.db 被改动：%s -> %s' % (db_before[:12], db_after[:12]))
        return 2
    print('真实 app.db 只读：sha256 前后一致 %s（2531328 B 现场见报告）' % db_before)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
