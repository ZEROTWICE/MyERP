"""改动检测器：对比 app/ scripts/ 等已跟踪文件与改动前基线，列出新增/修改/删除。

用法（仓库根目录）：
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/check_changes.py

退出码：0 = 无改动；1 = 有改动（列出清单）。
只读：不写任何文件，不 import 应用，不打开数据库。
"""
import hashlib
import json
import os
import subprocess
import sys

BASELINE = os.path.join("test-reports-2026-10", "evidence", "baseline-prefix", "pre-fix-baseline.json")


def sha256_of(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    if not os.path.isfile(BASELINE):
        print("BASELINE MISSING: %s" % BASELINE)
        return 2
    base = json.load(open(BASELINE, encoding="utf-8"))
    old = {r["path"]: r for r in base["files"]}

    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, encoding="utf-8")
    now_paths = [p.replace("\\", "/") for p in tracked.stdout.splitlines() if os.path.isfile(p)]
    now = set(now_paths)
    oldset = set(old)

    added = sorted(now - oldset)
    removed = sorted(oldset - now)
    modified = []
    unchanged = 0
    for p in sorted(now & oldset):
        try:
            if os.path.getsize(p) != old[p]["bytes"] or sha256_of(p) != old[p]["sha256"]:
                modified.append(p)
            else:
                unchanged += 1
        except OSError as exc:
            modified.append("%s (读取失败: %s)" % (p, exc))

    print("基线 HEAD: %s  文件数: %d" % (base.get("head"), base.get("file_count")))
    print("当前已跟踪文件数: %d" % len(now_paths))
    print("未变: %d" % unchanged)
    print("--- 修改 (%d) ---" % len(modified))
    for p in modified:
        print("  M %s" % p)
    print("--- 新增 (%d) ---" % len(added))
    for p in added:
        print("  A %s" % p)
    print("--- 删除 (%d) ---" % len(removed))
    for p in removed:
        print("  D %s" % p)

    changed = len(modified) + len(added) + len(removed)
    print("RESULT: %s" % ("CLEAN (无改动)" if changed == 0 else "CHANGED (%d)" % changed))
    return 0 if changed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
