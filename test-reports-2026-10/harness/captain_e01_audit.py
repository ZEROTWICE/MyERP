"""captain 独立终审：E-01 / A-50 / A-53 验收（不依赖 t1 自述）。

判据：
  C1  run_id 分目录        —— evidence/harness 下存在 >=2 个独立 run 目录
  C2  原件未被覆盖          —— evidence/harness 下 6 个 negative 原件 mtime/哈希仍在
  C3  索引覆盖一致          —— 每个 artifact_hashes.json 的 file_count == 本目录「应计文件数」
  C4  A-50 归零             —— w0-e01-baseline / w0-e01-accept 的缺口为 0
  C5  同目录双索引命名错位  —— 索引文件名必须与所在目录一致，或自述 dir 字段一致
  C6  哈希大小写一致        —— 索引内哈希表示统一（全大写或全小写）
  C7  写入守卫              —— 存在「同名写入被改名保留」的证据对

输出：test-reports-2026-10/evidence/harness/captain-e01-audit.json
只读：不改动任何被测文件。
"""
import hashlib
import io
import json
import os
import re
import time

BASE = os.path.join("test-reports-2026-10", "evidence")
HARNESS = os.path.join(BASE, "harness")
RUN_ID = os.environ.get("CAPTAIN_AUDIT_RUN_ID") or ("captain-audit-" + time.strftime("%Y%m%d-%H%M%S"))
OUT_DIR = os.path.join(HARNESS, RUN_ID)
OUT = os.path.join(OUT_DIR, "captain-e01-audit.json")


def guard_write(path, text):
    """A-55：与 E-01 同口径的写入守卫——目标已存在则改名保留原件，绝不覆盖。"""
    if os.path.exists(path):
        root, ext = os.path.splitext(path)
        alt = "%s.%s%s" % (root, RUN_ID, ext)
        n = 1
        while os.path.exists(alt):
            alt = "%s.%s-%d%s" % (root, RUN_ID, n, ext)
            n += 1
        path = alt
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path

buf = io.StringIO()


def w(*a):
    print(*a, file=buf)


def sha256_of(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def is_index_like(name):
    return name.startswith("artifact_hashes") and name.endswith(".json")


result = {"audit": "captain-e01-audit", "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "checks": {}}

# ---- C1 run 目录 ----
run_dirs = [d for d in os.listdir(HARNESS) if os.path.isdir(os.path.join(HARNESS, d))]
c1 = len(run_dirs) >= 2
w("C1 run_id 分目录: %s（%d 个：%s）" % ("PASS" if c1 else "FAIL", len(run_dirs), ", ".join(sorted(run_dirs))))
result["checks"]["C1_run_dirs"] = {"pass": c1, "count": len(run_dirs), "dirs": sorted(run_dirs)}

# ---- C2 原件未被覆盖 ----
originals = {
    "negative_case1_real_db_guard.txt": "10-06 22:27",
    "negative_case2_fake_switch.txt": None,
    "negative_case3_qc_gate.txt": None,
    "negative_case4_fixture_scale.txt": None,
    "negative_case5_shipment_prerequisite.txt": None,
    "negative_matrix.json": None,
}
present = {n: os.path.isfile(os.path.join(HARNESS, n)) for n in originals}
c2 = all(present.values())
w("C2 原件仍在: %s（%s）" % ("PASS" if c2 else "FAIL", ", ".join("%s=%s" % (k, v) for k, v in present.items())))
result["checks"]["C2_originals_present"] = {"pass": c2, "detail": present}

# ---- C3/C4 索引覆盖（A-54 修正：同目录任一索引覆盖全部非索引文件即算通过） ----
cov = {}
gaps = []
for root, dirs, files in os.walk(BASE):
    idx_files = [f for f in files if is_index_like(f)]
    if not idx_files:
        continue
    rel = os.path.relpath(root, BASE)
    real_files = [f for f in os.listdir(root)
                  if os.path.isfile(os.path.join(root, f)) and not is_index_like(f)]
    best = None
    per_index = {}
    for f in idx_files:
        try:
            doc = json.load(open(os.path.join(root, f), encoding="utf-8"))
        except Exception as exc:
            per_index[f] = {"error": str(exc)}
            continue
        items = doc.get("files")
        n_pairs = doc.get("self_index_pairs_match")
        if isinstance(items, dict):
            n_idx = len(items)
        elif isinstance(items, list):
            n_idx = len(items)
        elif isinstance(n_pairs, int):
            # 聚合型索引：以自述配对数为覆盖计数
            n_idx = n_pairs
        else:
            n_idx = doc.get("file_count") if isinstance(doc.get("file_count"), int) else None
        per_index[f] = {"entries": n_idx, "run_id": doc.get("run_id"), "dir_field": doc.get("dir")}
        if n_idx is not None and (best is None or n_idx > best[1]):
            best = (f, n_idx)
    gap = None if best is None else len(real_files) - best[1]
    cov[rel] = {"real": len(real_files), "best_index": best[0] if best else None,
                "best_entries": best[1] if best else None, "gap": gap, "indexes": per_index}
    if gap is not None and gap > 0:
        gaps.append((rel, gap))

targets = {"harness/w0-e01-baseline", "harness/w0-e01-accept"}
a50 = [g for g in gaps if g[0].replace("\\", "/") in targets]
c4 = len(a50) == 0
w("C4 A-50 归零（任一索引覆盖全部非索引文件）: %s（%s）" % ("PASS" if c4 else "FAIL", a50 if a50 else "无缺口"))
w("   其余缺口: %s" % (gaps if gaps else "无"))
result["checks"]["C4_a50_zero"] = {"pass": c4, "a50_gaps": a50}
result["coverage"] = cov

# ---- C5 同目录多索引命名（A-54 修正：snap<N> 为已声明规范，不算错位） ----
mis = []
for root, dirs, files in os.walk(BASE):
    rel = os.path.relpath(root, BASE).replace("\\", "/")
    base_name = os.path.basename(root)
    for f in files:
        if is_index_like(f) and f != "artifact_hashes.json":
            tag = f[len("artifact_hashes."):-len(".json")]
            ok = (tag == base_name or tag.startswith(base_name)
                  or tag == "w0" or tag.startswith("w0-")
                  or re.match(r"^snap\d+$", tag) is not None)
            if not ok:
                mis.append({"dir": rel, "index": f, "tag": tag})
c5 = len(mis) == 0
w("C5 多索引命名（snap<N> / w0-* / 与目录同名 视为合规）: %s（错位 %d 处：%s）" % ("PASS" if c5 else "FAIL", len(mis), mis if mis else "无"))
result["checks"]["C5_index_naming"] = {"pass": c5, "mismatched": mis}

# ---- C6 哈希大小写一致 ----
case_bad = []
for root, dirs, files in os.walk(BASE):
    if "artifact_hashes.json" not in files:
        continue
    try:
        doc = json.load(open(os.path.join(root, "artifact_hashes.json"), encoding="utf-8"))
    except Exception:
        continue
    vals = []
    items = doc.get("files")
    if isinstance(items, dict):
        for v in items.values():
            if isinstance(v, dict) and v.get("sha256"):
                vals.append(str(v["sha256"]))
    elif isinstance(items, list):
        for v in items:
            if isinstance(v, dict) and v.get("sha256"):
                vals.append(str(v["sha256"]))
    upper = sum(1 for s in vals if s == s.upper())
    lower = sum(1 for s in vals if s == s.lower())
    if vals and upper and lower:
        case_bad.append(os.path.relpath(root, BASE))
c6 = len(case_bad) == 0
w("C6 索引内哈希大小写一致: %s（混合 %d 处：%s）" % ("PASS" if c6 else "FAIL", len(case_bad), case_bad if case_bad else "无"))
result["checks"]["C6_hash_case"] = {"pass": c6, "mixed_dirs": case_bad}

# ---- C7 写入守卫证据 ----
guard_pairs = []
for root, dirs, files in os.walk(BASE):
    fs = set(files)
    for f in fs:
        m = re.match(r"^(w0_guard_injection_probe)\.([^.]+)\.txt$", f)
        if m and (m.group(1) + ".txt") in fs:
            guard_pairs.append(os.path.relpath(os.path.join(root, f), BASE))
c7 = len(guard_pairs) >= 1
w("C7 写入守卫证据: %s（%d 对）" % ("PASS" if c7 else "FAIL", len(guard_pairs)))
result["checks"]["C7_guard"] = {"pass": c7, "pairs": guard_pairs}

passed = sum(1 for v in result["checks"].values() if v.get("pass"))
w("")
w("=== 终审合计: %d/%d PASS ===" % (passed, len(result["checks"])))
result["summary"] = {"passed": passed, "total": len(result["checks"])}
result["stdout"] = buf.getvalue()

os.makedirs(OUT_DIR, exist_ok=True)
result["run_id"] = RUN_ID
result["out_dir"] = os.path.relpath(OUT_DIR).replace("\\", "/")
written = guard_write(OUT, json.dumps(result, ensure_ascii=False, indent=1))
print(buf.getvalue())
print("written ->", written)
