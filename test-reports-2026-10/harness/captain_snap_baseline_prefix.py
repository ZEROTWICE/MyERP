"""captain：为 baseline-prefix 生成规范化快照（不改动既有冻结索引）。

背景（A-51）：`baseline-prefix/artifact_hashes.json` 由 captain 手工生成，
同一文件内哈希大小写不一致（`pre-fix-baseline.json` 小写、其余大写），
导致大小写敏感比对误报。按 E-01 规范「只追加快照」，本脚本新增
`artifact_hashes.snap3.json`（统一大写 + 与当前目录实际内容对账），
供 E-01 的并集口径使用；既有 `artifact_hashes.json` 一字不改。
"""
import hashlib
import io
import json
import os
import time

D = os.path.join("test-reports-2026-10", "evidence", "baseline-prefix")
OUT = os.path.join(D, "artifact_hashes.snap3.json")


def is_index(f):
    return f.startswith("artifact_hashes") and f.endswith(".json")


buf = io.StringIO()


def w(*a):
    print(*a, file=buf)


files = {}
for f in sorted(os.listdir(D)):
    p = os.path.join(D, f)
    if not os.path.isfile(p) or is_index(f):
        continue
    with open(p, "rb") as fh:
        data = fh.read()
    files[f] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest().upper(), "append_only": False}

doc = {
    "schema": "w0-evidence-index/1",
    "run_id": "captain-baseline-prefix-snap3",
    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "generated_by": "captain（A-51 规范化：统一大写 + 对账当前目录）",
    "dir": "baseline-prefix",
    "scope": "本目录直接文件的防篡改基线（索引自身除外）",
    "recursive": False,
    "policy": "只追加：改写/删除既有文件即校验失败；新增文件允许（报告 added）",
    "file_count": len(files),
    "file_count_rule": "artifact_hashes*.json 自身不计入 file_count",
    "supersedes_note": "本快照为规范化补充；既有 artifact_hashes.json 保持不变（不可改写冻结件）",
    "total_bytes": sum(v["bytes"] for v in files.values()),
    "files": files,
}

if os.path.exists(OUT):
    print("EXISTS, 不覆盖：", OUT)
else:
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    print("written ->", OUT)

w("当前目录非索引文件 %d 个：" % len(files))
for k, v in files.items():
    w("   %-44s %8d  %s" % (k, v["bytes"], v["sha256"][:16]))
open(os.path.join(D, "snap3-note.txt"), "w", encoding="utf-8").write(buf.getvalue())
print(buf.getvalue())
