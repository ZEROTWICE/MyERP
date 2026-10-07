"""t9 回归前的证据归档与复跑后完整性校验（captain 预置，针对 A-58）。

目的：t9 必须复跑 uat_chains / write_suite / api_matrix / measure_coverage，
而这 4 个脚本会**原地覆盖** evidence/**。本工具提供两阶段防护：

  阶段 1（preflight）：把 evidence/** 全量归档到 evidence/_phaseB-prefreeze/<stamp>/，
                       并写出 manifest（路径 + 字节 + SHA256）。归档本身不删除、不改写原件。
  阶段 2（verify）    ：与 manifest 比对，报告 modified / deleted / added，
                       任一 modified/deleted 即 exit 1。

用法（仓库根）：
  python -B test-reports-2026-10/harness/regression_preflight.py preflight
  python -B test-reports-2026-10/harness/regression_preflight.py verify
只读原件；仅写归档目录与 manifest。
"""
import hashlib
import io
import json
import os
import shutil
import sys
import time

BASE = os.path.join("test-reports-2026-10", "evidence")
ARCHIVE_ROOT = os.path.join(BASE, "_phaseB-prefreeze")
MANIFEST_NAME = "preflight-manifest.json"


def sha256_file(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest().upper()


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "_phaseB-prefreeze"]
        for f in filenames:
            yield os.path.relpath(os.path.join(dirpath, f), BASE).replace("\\", "/")


def preflight():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(ARCHIVE_ROOT, stamp)
    os.makedirs(dest, exist_ok=True)
    files = {}
    n = 0
    for rel in iter_files(BASE):
        src = os.path.join(BASE, rel)
        dst = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        files[rel] = {"bytes": os.path.getsize(src), "sha256": sha256_file(src)}
        n += 1
    man = os.path.join(dest, MANIFEST_NAME)
    with open(man, "w", encoding="utf-8") as fh:
        json.dump({"stamp": stamp, "file_count": n, "files": files}, fh, ensure_ascii=False, indent=1)
    # 同时写一个「最新归档」指针，便于 verify 默认取它
    with open(os.path.join(ARCHIVE_ROOT, "LATEST.txt"), "w", encoding="utf-8") as fh:
        fh.write(stamp + "\n")
    print("[preflight] 归档 %d 个文件 -> %s" % (n, dest))
    print("[preflight] manifest -> %s" % man)
    return 0


def latest_manifest():
    ptr = os.path.join(ARCHIVE_ROOT, "LATEST.txt")
    if not os.path.isfile(ptr):
        return None
    stamp = open(ptr, encoding="utf-8").read().strip()
    man = os.path.join(ARCHIVE_ROOT, stamp, MANIFEST_NAME)
    return man if os.path.isfile(man) else None


def verify():
    man = latest_manifest()
    if not man:
        print("NO MANIFEST：请先跑 preflight")
        return 2
    doc = json.load(open(man, encoding="utf-8"))
    old = doc["files"]
    buf = io.StringIO()
    modified, deleted = [], []
    for rel, meta in old.items():
        p = os.path.join(BASE, rel)
        if not os.path.isfile(p):
            deleted.append(rel)
            continue
        if os.path.getsize(p) != meta["bytes"] or sha256_file(p) != meta["sha256"].upper():
            modified.append(rel)
    now = set(iter_files(BASE))
    added = sorted(now - set(old))
    print("[verify] 基线 %s（%d 文件）" % (doc["stamp"], doc["file_count"]))
    print("[verify] modified=%d deleted=%d added=%d" % (len(modified), len(deleted), len(added)))
    for r in modified:
        print("   M %s" % r)
    for r in deleted:
        print("   D %s" % r)
    for r in added[:20]:
        print("   A %s" % r)
    if len(added) > 20:
        print("   ... 另有 %d 个新增" % (len(added) - 20))
    verdict = "OK" if (not modified and not deleted) else "VIOLATION"
    print("[verify] 判定 = %s" % verdict)
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if cmd == "preflight":
        sys.exit(preflight())
    if cmd == "verify":
        sys.exit(verify())
    print(__doc__)
    sys.exit(2)
