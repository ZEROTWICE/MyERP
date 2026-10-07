"""阴性验证：证明 regression_preflight.py 的 verify 能抓出「覆盖」。"""
import hashlib
import json
import os
import subprocess
import sys

PY = r"F:\Miniconda\envs\wage\python.exe"
ROOT = os.getcwd()
TOOL = os.path.join("test-reports-2026-10", "harness", "regression_preflight.py")
TARGET = os.path.join("test-reports-2026-10", "evidence", "baseline-prefix", "snap3-note.txt")

orig = open(TARGET, "rb").read()
print("目标文件 %s（%d B）" % (TARGET, len(orig)))

results = {}

# 1) 覆盖写入（模拟 D-5 复发）
with open(TARGET, "wb") as fh:
    fh.write(orig + b"\n[MUTATED BY NEGATIVE TEST]\n")
r = subprocess.run([PY, "-B", TOOL, "verify"], capture_output=True, text=True, encoding="utf-8")
results["after_mutation_exit"] = r.returncode
hit = [ln for ln in (r.stdout or "").splitlines() if "snap3-note" in ln or "判定" in ln or "modified=" in ln]
results["after_mutation_lines"] = hit
print("覆盖后 verify: exit=%s" % r.returncode)
for ln in hit:
    print("   ", ln)

# 2) 恢复原字节
with open(TARGET, "wb") as fh:
    fh.write(orig)
r2 = subprocess.run([PY, "-B", TOOL, "verify"], capture_output=True, text=True, encoding="utf-8")
results["after_restore_exit"] = r2.returncode
hit2 = [ln for ln in (r2.stdout or "").splitlines() if "modified=" in ln or "判定" in ln]
results["after_restore_lines"] = hit2
print("恢复后 verify: exit=%s" % r2.returncode)
for ln in hit2:
    print("   ", ln)

print()
print("阴性测试结论：覆盖被检出 = %s；恢复后回归 OK = %s"
      % (results["after_mutation_exit"] == 1, results["after_restore_exit"] == 0))

out = os.path.join("test-reports-2026-10", "evidence", "harness", "preflight-negative-test.txt")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(json.dumps(results, ensure_ascii=False, indent=1))
print("written ->", out)
