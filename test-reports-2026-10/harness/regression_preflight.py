"""t9 回归前的证据归档与复跑后完整性校验（captain 预置，针对 A-58）。

目的：t9 必须复跑 uat_chains / write_suite / api_matrix / measure_coverage，
而这 4 个脚本会**原地覆盖** evidence/**。本工具提供两阶段防护：

  阶段 1（preflight）：把 evidence/** 全量归档到 evidence/_phaseB-prefreeze/<stamp>/，
                       并写出 manifest（路径 + 字节 + SHA256）。归档本身不删除、不改写原件。
  阶段 2（verify）    ：与 manifest 比对，报告 modified / deleted / added，
                       任一 modified/deleted 即 exit 1（白名单内见下）。

**有意复跑白名单（N-5 / B18-08）**：`verify --whitelist <文件>` 把「本来就该被复跑改写」
的产物列为 `expected_modified`，它们不再计入 verdict ⇒ verify 的 exit 可直接读。
白名单只接受**精确相对路径**（相对 ``evidence/``，一行一条，`#` 注释）——**通配一律拒绝**
（40- §8-C-2：归档排除与白名单不得成为两套并存机制；`_phaseB-prefreeze/**` 由 ``iter_files``
在复制阶段整体排除，不进 manifest）。**不给默认白名单**：不传参 = 与旧行为完全一致。

用法（仓库根）：
  python -B test-reports-2026-10/harness/regression_preflight.py preflight
  python -B test-reports-2026-10/harness/regression_preflight.py verify
  python -B test-reports-2026-10/harness/regression_preflight.py verify --whitelist <白名单文件>
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


def load_whitelist(path):
    """读「有意复跑白名单」：**精确相对路径**一行一条，``#`` 注释、空行忽略。

    含通配符（``*`` / ``?`` / ``[``）的行**一律拒绝**（usage error）：白名单是逐文件登记，
    不许退化成「通配一开、整类放行」的第二套机制（40- §8-C-2）。
    """
    if not path:
        return set()
    if not os.path.isfile(path):
        print("[verify] 白名单文件不存在：%s" % path)
        return None
    out = set()
    for lineno, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if any(ch in line for ch in "*?["):
            print("[verify] 白名单第 %d 行含通配符（本工具只接受精确路径）：%s" % (lineno, line))
            return None
        out.add(line.replace("\\", "/").lstrip("./"))
    return out


def latest_manifest():
    ptr = os.path.join(ARCHIVE_ROOT, "LATEST.txt")
    if not os.path.isfile(ptr):
        return None
    stamp = open(ptr, encoding="utf-8").read().strip()
    man = os.path.join(ARCHIVE_ROOT, stamp, MANIFEST_NAME)
    return man if os.path.isfile(man) else None


def verify(whitelist=None):
    man = latest_manifest()
    if not man:
        print("NO MANIFEST：请先跑 preflight")
        return 2
    whitelist = whitelist or set()
    doc = json.load(open(man, encoding="utf-8"))
    old = doc["files"]
    buf = io.StringIO()
    modified, deleted, expected = [], [], []
    for rel, meta in old.items():
        p = os.path.join(BASE, rel)
        if not os.path.isfile(p):
            deleted.append(rel)
            continue
        if os.path.getsize(p) != meta["bytes"] or sha256_file(p) != meta["sha256"].upper():
            (expected if rel in whitelist else modified).append(rel)
    now = set(iter_files(BASE))
    added = sorted(now - set(old))
    print("[verify] 基线 %s（%d 文件）" % (doc["stamp"], doc["file_count"]))
    print("[verify] modified=%d（白名单内 %d）deleted=%d added=%d"
          % (len(modified), len(expected), len(deleted), len(added)))
    print("[verify] 白名单 = %s" % ("（未提供：判定与旧行为一致）" if not whitelist
                                    else "%d 条精确路径" % len(whitelist)))
    for r in expected:
        print("   W %s（白名单：有意复跑改写，不计入判定）" % r)
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
    argv = sys.argv[1:]
    wl_path = None
    if "--whitelist" in argv:
        i = argv.index("--whitelist")
        wl_path = argv[i + 1] if len(argv) > i + 1 else None
        if not wl_path:
            print("[verify] --whitelist 需要文件路径")
            sys.exit(2)
        argv = argv[:i] + argv[i + 2:]
    cmd = (argv[0] if argv else "").lower()
    if cmd == "preflight":
        sys.exit(preflight())
    if cmd == "verify":
        wl = load_whitelist(wl_path)
        if wl is None:
            sys.exit(2)
        sys.exit(verify(whitelist=wl))
    print(__doc__)
    sys.exit(2)
