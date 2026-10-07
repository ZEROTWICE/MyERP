# -*- coding: utf-8 -*-
"""t8 最终测试报告的只读复算器（Final Recount）。

定位（A-40 合规）
-----------------
本脚本**不重跑任何会产生 evidence 的上游脚本**（run_gates / measure_coverage /
negative_matrix / api_matrix / write_suite / uat_chains / analysis_ledger /
improve_plan 一律不调用），**不 import 应用**（无 `create_app()`、无 `flask db`），
**不打开真实库**（`app.db` 只做 SHA256/字节/mtime 指纹，不建 sqlite 连接）。

只做两件事：
  A. 对「阶段一 + 阶段二」全部交付物逐文件复算 bytes / splitlines() 行数 / 非空行数 / SHA256，
     并与各任务自带的 artifact_hashes.json 逐项比对（MATCH / MISMATCH / MISSING）。
  B. 从既有**机读证据**（只读 JSON）里机械抽取本轮报告要引用的每一个聚合值，
     与报告/各文档自述值逐条对照（expected vs actual）。

用法（仓库根目录）：
  F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/final_recount.py            # 预检（写 recount-pre.*）
  F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/final_recount.py --finalize  # 定稿（写 artifact_hashes.json + recount-final.*）

落点：test-reports-2026-10/evidence/final/（本任务新建目录，不覆盖任何既有文件）
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.dirname(HERE)                      # test-reports-2026-10
ROOT = os.path.dirname(REPORTS)                      # repo root
OUTDIR = os.path.join(REPORTS, "evidence", "final")
PY_EXE = r"F:\Miniconda\envs\wage\python.exe"

REAL_DB = os.path.join(ROOT, "app.db")
REAL_DB_PINNED = "F5DA2306BC31CBAB098AAD3774016D320A9B9AA3546F93418196AE9900E0F065"

# ---- 交付物清单（相对仓库根；POSIX 风格 key） -------------------------------
STAGE2 = [
    "test-reports-2026-10/00-编号登记册与权威说明.md",
    "test-reports-2026-10/00b-裁定与纪律增补.md",
    "test-reports-2026-10/01-阶段一产出冻结清单.md",
    "test-reports-2026-10/01-阶段一产出冻结清单.manifest.json",
    "test-reports-2026-10/02-测试脚手架与自动化说明.md",
    "test-reports-2026-10/03-测试资产可信度与盲区评估.md",
    "test-reports-2026-10/03b-测试资产评估补遗.md",
    "test-reports-2026-10/04-API实测结果.md",
    "test-reports-2026-10/05-端到端验收实测.md",
    "test-reports-2026-10/06-测试结果分析与缺陷分级.md",
    "test-reports-2026-10/07-测试与工程改进报告.md",
    "test-reports-2026-10/08-最终测试报告.md",
]
STAGE1_DOCS = os.path.join("docs", "test-reports", "2026-10")
SNAPSHOT = os.path.join("test-reports-2026-10", "phase1-snapshot")
HARNESS_DIR = os.path.join("test-reports-2026-10", "harness")
EVIDENCE_DIR = os.path.join("test-reports-2026-10", "evidence")

SUPERSEDED = [
    "02-业务验收标准与端到端判据.md",
    "02-测试工具链能力评估与差距矩阵.md",
    "03-验证目标与风险登记.md",
]

EVIDENCE_SUBDIRS = ["harness", "api", "uat", "analysis", "improve", "final"]

# ---- 机读证据（只读） -------------------------------------------------------
J = lambda *p: os.path.join(*p)
MACHINE = {
    "gates": J(EVIDENCE_DIR, "harness", "gates.json"),
    "negative_matrix": J(EVIDENCE_DIR, "harness", "negative_matrix.json"),
    "coverage": J(EVIDENCE_DIR, "harness", "coverage.json"),
    "api_matrix": J(EVIDENCE_DIR, "api", "api_matrix.json"),
    "write_suite": J(EVIDENCE_DIR, "api", "write_suite.json"),
    "verify_t4": J(EVIDENCE_DIR, "api", "verify_t4.json"),
    "uat_chains": J(EVIDENCE_DIR, "uat", "uat_chains.json"),
    "assertion_ledger": J(EVIDENCE_DIR, "analysis", "assertion_ledger.json"),
    "coverage_verdict": J(EVIDENCE_DIR, "analysis", "coverage_verdict.json"),
    "real_db_recount": J(EVIDENCE_DIR, "analysis", "real_db_recount.json"),
    "source_assertions": J(EVIDENCE_DIR, "analysis", "source_assertions.json"),
    "fix_plan": J(EVIDENCE_DIR, "improve", "fix_plan.json"),
    "improve_plan": J(EVIDENCE_DIR, "improve", "improve_plan.json"),
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(abspath):
    """bytes / splitlines() 行数 / 非空行数 / SHA256（A-23 行数口径）。"""
    if not os.path.isfile(abspath):
        return {"exists": False}
    raw = open(abspath, "rb").read()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return {
        "exists": True,
        "bytes": len(raw),
        "total_lines": len(lines),
        "nonempty_lines": sum(1 for ln in lines if ln.strip()),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def collect_artifacts():
    out = {}
    for rel in STAGE2:
        out[rel] = fingerprint(os.path.join(ROOT, rel.replace("/", os.sep)))
    # 阶段一 8 份 + 3 份作废残留
    if os.path.isdir(os.path.join(ROOT, STAGE1_DOCS)):
        for name in sorted(os.listdir(os.path.join(ROOT, STAGE1_DOCS))):
            if name.endswith(".md"):
                rel = (STAGE1_DOCS + "/" + name).replace(os.sep, "/")
                out[rel] = fingerprint(os.path.join(ROOT, STAGE1_DOCS, name))
    # 快照
    snap_abs = os.path.join(ROOT, SNAPSHOT)
    if os.path.isdir(snap_abs):
        for dirpath, _dirs, files in os.walk(snap_abs):
            for name in sorted(files):
                ap = os.path.join(dirpath, name)
                rel = os.path.relpath(ap, ROOT).replace(os.sep, "/")
                out[rel] = fingerprint(ap)
    # harness 脚本
    h_abs = os.path.join(ROOT, HARNESS_DIR)
    if os.path.isdir(h_abs):
        for name in sorted(os.listdir(h_abs)):
            ap = os.path.join(h_abs, name)
            if os.path.isfile(ap):
                rel = (HARNESS_DIR + "/" + name).replace(os.sep, "/")
                out[rel] = fingerprint(ap)
    # evidence 全量（含本轮 final）
    e_abs = os.path.join(ROOT, EVIDENCE_DIR)
    if os.path.isdir(e_abs):
        for dirpath, _dirs, files in os.walk(e_abs):
            for name in sorted(files):
                ap = os.path.join(dirpath, name)
                rel = os.path.relpath(ap, ROOT).replace(os.sep, "/")
                if rel.endswith("evidence/final/artifact_hashes.json"):
                    continue  # 自身索引不入索引
                out[rel] = fingerprint(ap)
    return out


def evidence_dir_stats():
    stats = {}
    for sub in EVIDENCE_SUBDIRS:
        d = os.path.join(ROOT, EVIDENCE_DIR, sub)
        if not os.path.isdir(d):
            stats[sub] = {"exists": False}
            continue
        files = [os.path.join(d, n) for n in os.listdir(d) if os.path.isfile(os.path.join(d, n))]
        stats[sub] = {"exists": True, "files": len(files), "bytes": sum(os.path.getsize(p) for p in files)}
    return stats


def cross_check_self_indexes(artifacts):
    """与各任务自带的 artifact_hashes.json 逐项比对（只读）。"""
    results = []
    idx_specs = [
        ("test-reports-2026-10/evidence/analysis/artifact_hashes.json", "artifacts", "dict"),
        ("test-reports-2026-10/evidence/improve/artifact_hashes.json", "artifacts", "list"),
        ("test-reports-2026-10/evidence/uat/artifact_hashes.json", "files", "dict"),
    ]
    for rel_idx, key, shape in idx_specs:
        ap = os.path.join(ROOT, rel_idx.replace("/", os.sep))
        entry = {"index": rel_idx, "exists": os.path.isfile(ap)}
        if not entry["exists"]:
            entry["verdict"] = "INDEX_MISSING"
            results.append(entry)
            continue
        data = json.load(open(ap, encoding="utf-8"))
        claims = []
        if shape == "dict":
            for name, meta in (data.get(key) or {}).items():
                if isinstance(meta, dict):
                    claims.append((name, meta))
        else:
            for meta in (data.get(key) or []):
                if isinstance(meta, dict) and meta.get("path"):
                    claims.append((os.path.relpath(meta["path"], ROOT).replace(os.sep, "/"), meta))
        match = mismatch = missing = 0
        detail = []
        for name, meta in claims:
            cand = name if name in artifacts else None
            if cand is None:
                # 允许以文件名 / 相对路径的多种写法匹配
                for k in artifacts:
                    if k.endswith("/" + name) or k == name or os.path.basename(k) == name:
                        cand = k
                        break
            if cand is None or not artifacts[cand].get("exists"):
                missing += 1
                detail.append({"file": name, "verdict": "MISSING"})
                continue
            act = artifacts[cand]
            c_sha = (meta.get("sha256") or "")[:16].upper()
            c_bytes = meta.get("bytes")
            ok = (act["sha256"][:16].upper() == c_sha) and (c_bytes in (None, act["bytes"]))
            if ok:
                match += 1
            else:
                mismatch += 1
            detail.append({
                "file": name, "verdict": "MATCH" if ok else "MISMATCH",
                "claimed_bytes": c_bytes, "actual_bytes": act["bytes"],
                "claimed_sha16": c_sha, "actual_sha16": act["sha256"][:16].upper(),
                "claimed_lines": meta.get("total_lines") or meta.get("lines"),
                "actual_lines": act["total_lines"],
            })
        entry.update({"claims": len(claims), "match": match, "mismatch": mismatch,
                      "missing": missing, "detail": detail})
        entry["verdict"] = "ALL_MATCH" if (mismatch == 0 and missing == 0) else "DIFF"
        results.append(entry)
    return results


def dig(data, path, default=None):
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def machine_claims(artifacts=None):
    """从既有只读机读证据机械抽取本报告要引用的聚合值 + 期望值对照。

    claim.kind:
      verify  = 必须逐字相等（不等 = 报告会被证伪）
      note    = 有意标注的口径/漂移（不等是预期事实，单列 findings）
    """
    artifacts = artifacts or {}
    out = {"sources": {}, "claims": [], "missing": []}

    def add(what, expected, actual, src, kind="verify"):
        out["claims"].append({"what": what, "expected": expected, "actual": actual,
                              "src": src, "kind": kind})

    def load(key):
        p = MACHINE[key]
        if not os.path.isfile(p):
            out["missing"].append(p)
            return None
        d = json.load(open(p, encoding="utf-8"))
        out["sources"][key] = {"path": p.replace(os.sep, "/"), "bytes": os.path.getsize(p)}
        return d

    g = load("gates")
    if g:
        s = g.get("summary", {})
        el = g.get("expected_lock", {})
        sens = g.get("sensitivity", {})
        for k, v in (("total", 6), ("pass", 5), ("fail", 0), ("probe_only", 1), ("probe_unexpected", 0)):
            add("门禁 summary." + k, v, s.get(k), "gates.json.summary")
        for k, v in (("injections_all_nonzero", True), ("baselines_all_zero", True)):
            add("门禁敏感性 " + k, v, sens.get(k), "gates.json.sensitivity")
        for k, v in (("templates_files", "87"), ("capabilities_declared", "44"),
                     ("capabilities_used_templates", "40"), ("capabilities_used_routes", "44"),
                     ("landing_endpoints", "5"), ("migration_head_count", "1"),
                     ("migration_revisions", "35"), ("properties_files", "23"),
                     ("model_classes", "74"), ("routes_total_rules", "271"),
                     ("routes_get_no_arg", "104"), ("routes_get_with_arg", "56"),
                     ("routes_non_get", "110")):
            a = el.get(k)
            add("expected_lock." + k, v, str(a) if a is not None else None, "gates.json.expected_lock")
        add("run_id（t2 文档自述 t2-final-20261006 vs 制品实际值）", "t2-repro-20261006", g.get("run_id"),
            "gates.json.run_id", kind="note")
    nm = load("negative_matrix")
    if nm:
        s = nm.get("summary", {})
        for k, v in (("total", 28), ("passed", 27), ("failed", 1), ("blocked", 0)):
            add("阴性矩阵 " + k, v, s.get(k), "negative_matrix.json.summary")
        add("阴性矩阵 run_id（t2 自述 t2-final vs 实际）", "t3-repro-20261006", nm.get("run_id"),
            "negative_matrix.json.run_id", kind="note")
    ws = load("write_suite")
    if ws:
        for k, v in (("probe_count", 54), ("passed", 51), ("failed", 3)):
            add("写断言 " + k, v, ws.get(k), "write_suite.json")
        add("写断言真实库未变", True, ws.get("real_db_unchanged"), "write_suite.json")
    vt = load("verify_t4")
    if vt:
        add("t4 独立复核 passed/total", "44/44", "%s/%s" % (vt.get("passed"), vt.get("total")), "verify_t4.json")
    uc = load("uat_chains")
    if uc:
        s = uc.get("summary", {})
        for k, v in (("total", 40), ("passed", 34), ("failed", 6), ("blocked", 0)):
            add("端到端 " + k, v, s.get(k), "uat_chains.json.summary")
        add("端到端 run_id", "t5-uat-final", s.get("run_id"), "uat_chains.json.summary")
    al = load("assertion_ledger")
    if al:
        t = al.get("totals", {})
        for k, v in (("total", 144), ("passed", 128), ("failed", 10), ("blocked", 0)):
            add("断言账本 totals." + k, v, t.get(k), "assertion_ledger.json.totals")
        per = al.get("by_suite", {})
        sub = sum(per.get(x, {}).get("total", 0) for x in ("negative_matrix", "write_suite", "uat"))
        add("逐条断言小计（28+54+40）", 122, sub, "assertion_ledger.json.by_suite")
        add("api 违规合计", 71, al.get("api_violations_total"), "assertion_ledger.json")
    cv = load("coverage_verdict")
    if cv:
        for key, exp in (("method_level_non_get_recount", 155), ("literal_covered_recount", 6),
                         ("covered_any_recount", 14), ("dynamic_only", 8),
                         ("non_get_without_any_hit", 141), ("rules_non_get", 153),
                         ("uncovered_writable", 101), ("method_level_get", 161)):
            add("覆盖度 " + key, exp, cv.get(key), "coverage_verdict.json")
        add("literal ⊂ any", True, cv.get("literal_is_subset_of_any"), "coverage_verdict.json")
        cs = cv.get("csrf", {})
        add("CSRF 本档案 probed / enforced_or_exempt / not_enforced",
            "155/155/0", "%s/%s/%s" % (cs.get("probed"), cs.get("enforced_or_exempt"), cs.get("not_enforced")),
            "coverage_verdict.json.csrf")
        add("CSRF 正例（本档案内联取 token 结果 vs verify_t4 独立正例）",
            "verify_t4 成功（token HTTP 200 / 正例 302 / 阴性 400）",
            str(cv.get("csrf_positive_control"))[:40], "coverage_verdict.json.csrf_positive_control", kind="note")
    rd = load("real_db_recount")
    if rd:
        for key, exp in (("unchanged", True), ("tables_total", 75), ("tables_without_alembic", 74),
                         ("rows_total", 6713), ("rows_business", 6712), ("zero_row_tables", 49),
                         ("batch_items_total", 23), ("batch_items_null_quality", 23),
                         ("batch_items_pending_quality", 0), ("finished_product_rows", 2),
                         ("finished_product_null_stock_kind", 2), ("rows_material_allocations", 0)):
            add("真实库 " + key, exp, rd.get(key), "real_db_recount.json")
        add("真实库 SHA256", REAL_DB_PINNED, (rd.get("sha256") or "").upper(), "real_db_recount.json")
    sa = load("source_assertions")
    if sa:
        a = sa.get("assertions", [])
        passed = sum(1 for x in a if str(x.get("verdict", "")).lower() in ("pass", "passed", "match", "ok", "true"))
        add("源码断言总数", 23, len(a), "source_assertions.json")
        add("源码断言通过数", 22, passed, "source_assertions.json")
    fp = load("fix_plan")
    if fp:
        add("改进待办条数", 38, len(fp.get("items", [])), "fix_plan.json.items")
        add("改进波次数", 8, len(fp.get("waves", [])), "fix_plan.json.waves")
        add("门禁判据条数", 14, len(fp.get("gates", [])), "fix_plan.json.gates")
    ip = load("improve_plan")
    if ip:
        c = ip.get("counts", [])
        if isinstance(c, dict):
            c = [{"label": k, "count": v} for k, v in c.items()]
        names = ("check_templates", "check_properties", "check_migration_heads",
                 "check_db_bootstrap", "route_inventory", "negative_matrix",
                 "smoke_test", "functional_test", "pytest")
        jk_sum = sum(int(x.get("count") or 0) for x in c if str(x.get("pattern", "")) in names)
        add("Jenkinsfile 对 9 个门禁/测试名的调用次数合计", 0, jk_sum,
            "improve_plan.json.counts（逐条 pattern × count）")
        add("Jenkinsfile py_compile 次数", 2,
            next((int(x.get("count") or 0) for x in c if x.get("pattern") == "py_compile"), None),
            "improve_plan.json.counts")
        add("GitHub workflow 步骤数", 4,
            next((int(x.get("count") or 0) for x in c if "步骤" in str(x.get("label", ""))), None),
            "improve_plan.json.counts")
        add("GitHub workflow 测试动作", 0,
            next((int(x.get("count") or 0) for x in c if "测试动作" in str(x.get("label", ""))), None),
            "improve_plan.json.counts")
        for key, exp, label in (("http404_swallowed", 17, "swallowed_count"),
                                ("get_json_without_silent", 39, "count"),
                                ("undefined_model_refs", 2, None),
                                ("data_bracket_subscript", 206, None)):
            v = ip.get(key)
            if isinstance(v, list):
                n = len(v)
            elif isinstance(v, dict):
                n = v.get(label) if label else None
            else:
                n = v
            add("t7 实测 " + key, exp, n, "improve_plan.json." + key)
        d = ip.get("derived", {})
        if isinstance(d, dict):
            for key, exp in (("no_hit_method_level_ge", 141), ("uncovered_writable_rules_len", 101),
                             ("non_get_method_level", 155), ("literal_covered", 6), ("covered_any", 14)):
                add("t7 派生 " + key, exp, d.get(key), "improve_plan.json.derived")
    am = MACHINE["api_matrix"]
    if os.path.isfile(am):
        d = json.load(open(am, encoding="utf-8"))
        out["sources"]["api_matrix"] = {"path": am.replace(os.sep, "/"), "bytes": os.path.getsize(am)}
        add("api_matrix 违规合计", 71, d.get("violations_total"), "api_matrix.json.violations_total")
        cov = d.get("coverage", {})
        add("t4 执行覆盖（业务非 GET 方法级 probed/total）",
            "152/152", "%s/%s" % (cov.get("methods_probed_non_get"), cov.get("total_non_get")),
            "api_matrix.json.coverage")
        add("t4 业务分母（规则/方法级/非 GET 方法级）", "266/308/152",
            "%s/%s/%s" % (d.get("denominators", {}).get("rules_total"),
                          d.get("denominators", {}).get("method_level_total"),
                          d.get("denominators", {}).get("method_level_non_get")),
            "api_matrix.json.denominators")
        rows = (d.get("matrix_f_csrf") or {}).get("rows", [])
        blk = sum(1 for r in rows if r.get("csrf_blocked"))
        exm = sum(1 for r in rows if r.get("exempt"))
        nen = sum(1 for r in rows if (not r.get("csrf_blocked")) and (not r.get("exempt")))
        add("CSRF 逐行复算（探针 155 / 拦截 / 豁免 / 未拦）", "155/133/22/0",
            "%s/%s/%s/%s" % (len(rows), blk, exm, nen), "api_matrix.json.matrix_f_csrf.rows")
        add("CSRF 违规数", 0, (lambda v: len(v) if isinstance(v, list) else v)(
            (d.get("matrix_f_csrf") or {}).get("violations")),
            "api_matrix.json.matrix_f_csrf.violations")
    if vt:
        pos = [c for c in vt.get("checks", []) if "正例" in str(c.get("name", ""))]
        add("t4 独立复核 CSRF 正例判据通过数", len(pos),
            sum(1 for c in pos if c.get("ok")), "verify_t4.json.checks（正例）")
    # t6 自索引 vs 现场（append-only 漂移检测）
    ap_analysis = os.path.join(ROOT, "test-reports-2026-10", "evidence", "analysis", "artifact_hashes.json")
    if os.path.isfile(ap_analysis):
        d6 = json.load(open(ap_analysis, encoding="utf-8")).get("artifacts", {})
        for name, cur in (("00b-裁定与纪律增补.md", artifacts.get("test-reports-2026-10/00b-裁定与纪律增补.md")),
                          ("00-编号登记册与权威说明.md", artifacts.get("test-reports-2026-10/00-编号登记册与权威说明.md"))):
            old = d6.get(name) or {}
            if cur and cur.get("exists") and old.get("bytes"):
                same = (old.get("bytes") == cur["bytes"])
                o_lines = old.get("total_lines") or old.get("lines")
                if o_lines:
                    exp = "%s B / %s 行" % (old.get("bytes"), o_lines)
                    act = "%s B / %s 行" % (cur["bytes"], cur["total_lines"])
                else:  # t6 该条未登记行数 ⇒ 只比字节
                    exp = "%s B" % old.get("bytes")
                    act = "%s B" % cur["bytes"]
                add("t6 索引登记的 %s（append-only 漂移检测）" % name, exp, act,
                    "analysis/artifact_hashes.json vs 现场", kind=("verify" if same else "note"))
    # 报告级自述 vs 复算（本任务）
    st = evidence_dir_stats()
    add("evidence/harness 文件数（t2 自述 17）", 16, st.get("harness", {}).get("files"), "os.listdir")
    add("evidence/harness 字节和（t2 自述 314482）", 314482, st.get("harness", {}).get("bytes"), "os.path.getsize")
    add("evidence/harness/artifact_hashes.json 存在（T-08）", False,
        os.path.isfile(os.path.join(ROOT, EVIDENCE_DIR, "harness", "artifact_hashes.json")), "os.path.isfile")
    add("evidence 子目录数（harness/api/uat/analysis/improve/final）", 6,
        sum(1 for s in st.values() if s.get("exists")), "os.path.isdir")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true", help="写 artifact_hashes.json（定稿口径）")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()
    run_id = args.run_id or ("t8-final-20261006" if args.finalize else "t8-pre-20261006")

    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(OUTDIR, exist_ok=True)

    print("=== t8 只读复算（final_recount.py） ===")
    print("run_id =", run_id)
    print("interpreter =", sys.executable, "| 期望", PY_EXE)
    print("repo_root =", ROOT)
    print("本脚本不 import 应用 / 不建 sqlite 连接 / 不重跑任何上游证据脚本（A-40）")

    # 1) 真实库指纹（不打开）
    db_before = {"sha256": sha256_of(REAL_DB), "bytes": os.path.getsize(REAL_DB),
                 "mtime": datetime.fromtimestamp(os.path.getmtime(REAL_DB)).strftime("%Y-%m-%d %H:%M:%S")}
    db_before["pinned"] = REAL_DB_PINNED
    db_before["unchanged"] = (db_before["sha256"].upper() == REAL_DB_PINNED.upper())
    print("\n[1] 真实库指纹 app.db:", db_before["sha256"][:24] + "...", "bytes", db_before["bytes"],
          "pinned_match", db_before["unchanged"])

    # 2) 制品指纹
    artifacts = collect_artifacts()
    print("[2] 制品指纹数（含阶段一/快照/harness/evidence，排除自身索引）:", len(artifacts))
    missing_docs = [k for k in STAGE2 if not artifacts.get(k, {}).get("exists")]
    print("    阶段二权威件缺失:", missing_docs if missing_docs else "无")

    # 3) 证据目录
    stats = evidence_dir_stats()
    print("[3] evidence 子目录:", json.dumps(stats, ensure_ascii=False))
    print("    evidence/harness/artifact_hashes.json 存在 =",
          os.path.isfile(os.path.join(ROOT, EVIDENCE_DIR, "harness", "artifact_hashes.json")))

    # 4) 自带索引对拍
    xc = cross_check_self_indexes(artifacts)
    print("[4] 自带索引对拍:")
    for e in xc:
        print("    -", e["index"], "|", e.get("verdict"), "| claims", e.get("claims"),
              "match", e.get("match"), "mismatch", e.get("mismatch"), "missing", e.get("missing"))

    # 5) 机读聚合值
    mc = machine_claims(artifacts)
    notes = [c for c in mc["claims"] if c["kind"] == "note"]
    bad = [c for c in mc["claims"] if c["kind"] == "verify" and c["expected"] != c["actual"]]
    print("[5] 机读聚合值对照: 共", len(mc["claims"]), "条；verify 不一致", len(bad), "条；note（有意标注/漂移）", len(notes), "条")
    for c in bad:
        print("    ! ", c["what"], "| expected", repr(c["expected"]), "| actual", repr(c["actual"]), "|", c["src"])
    for c in notes:
        print("    ~ ", c["what"], "|", repr(c["expected"]), "->", repr(c["actual"]))

    db_after = {"sha256": sha256_of(REAL_DB), "bytes": os.path.getsize(REAL_DB)}
    db_same = (db_after["sha256"].upper() == db_before["sha256"].upper() == REAL_DB_PINNED.upper())
    print("[6] 真实库复算后 SHA256 未变 =", db_same)

    payload = {
        "run_id": run_id, "generated_by": "harness/final_recount.py (t8)",
        "started": started, "finished": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "interpreter": sys.executable, "repo_root": ROOT,
        "read_only_declaration": "未 import 应用 / 未建 sqlite 连接 / 未重跑任何上游证据脚本（A-40）",
        "real_db": {"before": db_before, "after": db_after,
                    "sha256_unchanged": db_same},
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "stage2_missing": missing_docs,
        "evidence_dirs": stats,
        "harness_artifact_hashes_exists": os.path.isfile(
            os.path.join(ROOT, EVIDENCE_DIR, "harness", "artifact_hashes.json")),
        "self_index_cross_check": xc,
        "machine_claims": mc["claims"],
        "machine_claims_mismatch": bad,
        "machine_claims_notes": notes,
        "machine_sources": mc["sources"],
        "machine_missing": mc["missing"],
    }

    tag = "final" if args.finalize else "pre"
    jpath = os.path.join(OUTDIR, "recount-%s.json" % tag)
    tpath = os.path.join(OUTDIR, "recount-%s.out.txt" % tag)
    with open(jpath, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    # 控制台原文（A-14：父进程强制 UTF-8）
    print("[7] 已写:", jpath.replace(os.sep, "/"))

    if args.finalize:
        # 定稿：recount-final.* 已在上一步落盘 ⇒ 重新采集制品，把这两个文件也纳入基线
        # （避免重演 T-11「制品写在指纹采集之后 ⇒ 无法自证」的缺陷形态）
        artifacts = collect_artifacts()
        idx = {
            "run_id": run_id, "generated_at": payload["finished"],
            "producer": "t8 高级项目经理 / harness/final_recount.py --finalize",
            "scope": "阶段一 + 阶段二全部交付物与证据的防篡改基线（附录 A 口径：bytes / Python splitlines() 行数 / 非空 / SHA256）",
            "self_excluded": "本文件 evidence/final/artifact_hashes.json 自身不列入（写入自身哈希会自相矛盾）",
            "regeneration_note": "若本文件已存在，--finalize 会重新生成（它是本任务自产的可再生索引）；"
                                 "生成时先落 recount-final.* 再重采制品，故基线内每个制品（除本索引自身）均有可复算指纹",
            "real_db_sha256": db_after["sha256"],
            "artifact_count": len(artifacts),
            "stage2_authoritative": {k: artifacts[k] for k in STAGE2 if k in artifacts},
            "artifacts": artifacts,
            "evidence_dirs": evidence_dir_stats(),
            "self_index_cross_check": xc,
            "t8_recount": {"recount_json": jpath.replace(os.sep, "/"),
                           "claims": len(mc["claims"]), "claims_mismatch": len(bad),
                           "claims_notes": len(notes)},
        }
        ipath = os.path.join(OUTDIR, "artifact_hashes.json")
        with open(ipath, "w", encoding="utf-8") as fh:
            json.dump(idx, fh, ensure_ascii=False, indent=2)
        print("[8] 已写:", ipath.replace(os.sep, "/"), "| 基线制品数", len(artifacts))

    with open(tpath, "w", encoding="utf-8") as fh:
        fh.write("t8 final_recount run_id=%s\n" % run_id)
        fh.write("机器聚合值：%d 条，verify 不一致 %d 条，note %d 条\n" % (len(mc["claims"]), len(bad), len(notes)))
        for c in mc["claims"]:
            ok = c["expected"] == c["actual"] or c["kind"] == "note"
            fh.write("%-6s | %-8s | %s | expected=%r actual=%r | %s\n" % (
                "OK" if ok else "DIFF", c["kind"], c["what"], c["expected"], c["actual"], c["src"]))
        fh.write("\n自带索引对拍：\n")
        for e in xc:
            fh.write("- %s | %s | match=%s mismatch=%s missing=%s\n" % (
                e["index"], e.get("verdict"), e.get("match"), e.get("mismatch"), e.get("missing")))
        fh.write("\n真实库 before=%s\nafter=%s\nunchanged=%s\n" % (
            db_before["sha256"], db_after["sha256"], payload["real_db"]["sha256_unchanged"]))
    print("[9] 已写:", tpath.replace(os.sep, "/"))
    return 0 if db_before["unchanged"] else 1


if __name__ == "__main__":
    sys.exit(main())
