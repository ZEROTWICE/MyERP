# -*- coding: utf-8 -*-
"""probe_arch_docs.py —— W1/t2 只读探针：批次9（B9-01…B9-16）文档漂移 + AGENTS.md 门禁表 + 构建层。

纪律：
* **只读**——只 `open(..., encoding='utf-8')` 读生产文档，不写任何生产文件；
* 唯一输出走 stdout（JSON），落盘由调用方决定；
* 不 import app / 不触碰任何数据库。

用法（仓库根目录）：
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/reconcile-2026-10-08/probe_arch_docs.py
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if not os.path.isfile(os.path.join(ROOT, 'AGENTS.md')):
    # 从脚本位置回推：<repo>/test-reports-2026-10/reconcile-2026-10-08/probe_x.py
    ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

DOCS = os.path.join(ROOT, 'docs')
REPORTS = os.path.join(ROOT, 'test-reports-2026-10')


def read(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.isfile(p):
        return None
    with io.open(p, encoding='utf-8') as fh:
        return fh.read()


def lines_of(rel):
    t = read(rel)
    return t.splitlines() if t is not None else []


def find_lines(rel, pattern):
    """返回 [(lineno, line)] 命中（1-based）。"""
    out = []
    for i, ln in enumerate(lines_of(rel), start=1):
        if re.search(pattern, ln):
            out.append((i, ln.strip()))
    return out


def probe():
    r = {}

    # ---------- B9-01 / B9-02：继续开发准备报告 旧数字是否已订正 ----------
    target = 'docs/继续开发准备报告.md'
    r['B9-01_B9-02_file_exists'] = os.path.isfile(os.path.join(ROOT, target))
    for tag, pat in [
        ('261_view', r'261\s*个?\s*视图|261\s*视图'),
        ('102_inline', r'102\s*(处|个)?\s*(inline|内联)'),
        ('194_route', r'194\s*(个)?\s*路由'),
        ('2_head', r'2\s*个?\s*head|两个\s*head'),
        ('31_template_77_role', r'31\s*个?\s*模板|77\s*处'),
    ]:
        r['B9-01_' + tag] = [(n, s[:120]) for n, s in find_lines(target, pat)]

    # ---------- B9-02：模板 role 行号是否订正为 :340 ----------
    r['B9-02_tasks_337_remains'] = [(n, s[:120]) for n, s in
                                    find_lines(target, r'tasks\.html[`\'"]?:?337|tasks\.html:337')]
    r['B9-02_tasks_340_present'] = [(n, s[:120]) for n, s in
                                    find_lines(target, r'tasks\.html[`\'"]?:?340|tasks\.html:340')]

    # ---------- B9-06：继续开发准备报告 的 ❓ 标注 ----------
    r['B9-06_question_mark_lines'] = [(n, s[:150]) for n, s in
                                      find_lines(target, r'❓')]
    r['B9-06_yijue_present'] = [(n, s[:150]) for n, s in
                                find_lines(target, r'已决')]

    # ---------- B9-03：app/main 模块清单是否补/删 sales_routes ----------
    for f in ['docs/开发进度与交接.md', 'docs/交付说明-P0P1.md',
              'docs/业务流程现状与缺口.md', target]:
        r['B9-03_sales_routes@' + f] = [(n, s[:130]) for n, s in
                                        find_lines(f, r'sales_routes')]

    # ---------- B9-07：HEAD 指针 148d8a5 / f60a54d ----------
    for f in ['docs/开发进度与交接.md', target]:
        r['B9-07_148d8a5@' + f] = [(n, s[:130]) for n, s in find_lines(f, r'148d8a5')]
        r['B9-07_f60a54d@' + f] = [(n, s[:130]) for n, s in find_lines(f, r'f60a54d')]

    # ---------- B9-07/B9-12：_ENSURED_COLUMNS 数字 ----------
    for f in ['docs/开发进度与交接.md', target, 'docs/交付说明-P0P1.md']:
        r['B9-12_ensured@' + f] = [(n, s[:140]) for n, s in
                                   find_lines(f, r'_ENSURED_COLUMNS')]

    # ---------- B9-11：5 个 head 措辞 ----------
    for f in ['docs/开发进度与交接.md', target]:
        r['B9-11_five_head@' + f] = [(n, s[:140]) for n, s in
                                     find_lines(f, r'5\s*个?\s*head|五个\s*head')]

    # ---------- B9-15：质检结论是否降级为「部分实现」 ----------
    for f in ['docs/业务流程现状与缺口.md', 'docs/开发进度与交接.md']:
        r['B9-15_partial@' + f] = [(n, s[:150]) for n, s in
                                   find_lines(f, r'部分实现')]
        r['B9-15_full_qc@' + f] = [(n, s[:150]) for n, s in
                                   find_lines(f, r'质检门禁与不合格处置')]

    # ---------- B9-10：75/5/15 三量纲 ----------
    for f in ['docs/测试报告-2026-08-11.md']:
        r['B9-10_dims@' + f] = [(n, s[:140]) for n, s in
                                find_lines(f, r'75|无校验')][:12]

    # ---------- B9-13：routes.py 行数口径 ----------
    for f in [target, 'docs/开发进度与交接.md']:
        r['B9-13_route_lines@' + f] = [(n, s[:140]) for n, s in
                                       find_lines(f, r'1212[67]')]

    # ---------- AGENTS.md：门禁表期望值 + 表述 ----------
    agents = 'AGENTS.md'
    for tag, pat in [
        ('templates_expect', r'87 templates'),
        ('properties_expect', r'23 个文件，模型类 74 个|74 模型类'),
        ('modelrefs_expect', r'violations 0'),
        ('route_expect', r'total rules=271'),
        ('heads_expect', r"HEADS=\['p1nonctarget'\]"),
        ('one_route_module_claim', r'只有\s*`?routes\.py`?\s*一个路由模块'),
        ('eight_modules_claim', r'8 个含\s*`?@bp\.route`?\s*的模块'),
        ('import_must_persist_48', r'仅上传解析必须落盘'),
        ('import_must_persist_282', r'Excel 导入（\*\*必须落盘'),
        ('check_is_archived_policy', r'check_is_archived_policy'),
        ('check_notification_triggers', r'check_notification_triggers'),
        ('check_model_refs_gate', r'check_model_refs'),
        ('check_http_contract_gate', r'check_http_contract'),
        ('w4_http_contract', r'w4_http_contract'),
        ('fourteen_steps', r'14 步'),
    ]:
        r['AGENTS_' + tag] = [(n, s[:150]) for n, s in find_lines(agents, pat)]

    # AGENTS.md:79-81 到底是什么
    al = lines_of(agents)
    r['AGENTS_79_81'] = [(i, al[i - 1].strip()[:120]) for i in (79, 80, 81) if len(al) >= i]
    r['AGENTS_48_50'] = [(i, al[i - 1].strip()[:120]) for i in (48, 49, 50) if len(al) >= i]
    r['AGENTS_282'] = [(282, al[281].strip()[:150])] if len(al) >= 282 else []
    r['AGENTS_total_lines'] = len(al)

    # ---------- 构建层：Jenkinsfile / docker-deploy.yml ----------
    jl = lines_of('Jenkinsfile')
    r['JENKINS_error_active'] = [(i, ln.strip()[:120]) for i, ln in enumerate(jl, 1)
                                 if re.match(r'\s*error\(', ln)]
    r['JENKINS_error_commented'] = [(i, ln.strip()[:120]) for i, ln in enumerate(jl, 1)
                                    if re.match(r'\s*//\s*error\(', ln)]
    r['JENKINS_echo_blocking_list'] = [(i, ln.strip()[:200]) for i, ln in enumerate(jl, 1)
                                       if 'blocking:' in ln and 'echo' in ln]
    r['JENKINS_mentions_new_gates'] = {
        'check_model_refs': [(i, ) for i, ln in enumerate(jl, 1) if 'check_model_refs' in ln],
        'check_http_contract': [(i, ) for i, ln in enumerate(jl, 1) if 'check_http_contract' in ln],
        'evidence_hash': [(i, ) for i, ln in enumerate(jl, 1) if 'evidence_hash' in ln],
    }

    gh = lines_of('.github/workflows/docker-deploy.yml')
    r['GH_continue_on_error'] = [(i, ln.strip()) for i, ln in enumerate(gh, 1)
                                 if 'continue-on-error' in ln]
    r['GH_needs_gate'] = [(i, ln.strip()) for i, ln in enumerate(gh, 1)
                          if re.search(r'needs:\s*gate', ln)]

    # ---------- 门禁脚本是否落地 ----------
    for s in ['scripts/check_db_url_guard.py', 'scripts/check_notification_triggers.py',
              'scripts/check_is_archived_policy.py', 'requirements.lock',
              'test-reports-2026-10/harness/ci_lint.py',
              'test-reports-2026-10/harness/r2_c07_probe.py']:
        p = os.path.join(ROOT, s.replace('/', os.sep))
        r['exists::' + s] = os.path.isfile(p)

    # ---------- 仓库卫生 ----------
    def walkstat(rel):
        base = os.path.join(ROOT, rel)
        if not os.path.isdir(base):
            return {'exists': False}
        n = 0
        b = 0
        for dp, _dn, fn in os.walk(base):
            for f in fn:
                try:
                    b += os.path.getsize(os.path.join(dp, f))
                    n += 1
                except OSError:
                    pass
        return {'exists': True, 'files': n, 'bytes': b}

    r['hygiene_evidence'] = walkstat('test-reports-2026-10/evidence')
    r['hygiene_tmp'] = walkstat('test-reports-2026-10/.tmp')
    r['hygiene_repo_root_tmp_v15'] = sorted(
        f for f in os.listdir(ROOT) if f.startswith('.tmp_v15_'))

    # .gitignore 覆盖
    gi = lines_of('.gitignore')
    r['gitignore_uploads_temp'] = [(i, ln) for i, ln in enumerate(gi, 1)
                                   if 'uploads/temp' in ln]
    r['gitignore_dot_tmp'] = [(i, ln) for i, ln in enumerate(gi, 1)
                              if '/test-reports-2026-10/.tmp/' in ln or ln.strip() == '.tmp/']
    r['gitignore_evidence'] = [(i, ln) for i, ln in enumerate(gi, 1)
                               if 'evidence' in ln]
    r['gitignore_lines'] = len(gi)

    return r


def main():
    out = probe()
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
