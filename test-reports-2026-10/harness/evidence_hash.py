#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""evidence_hash.py —— ``test-reports-2026-10/evidence/**`` 的「只追加」防篡改基线（W0 / E-01 / G-10）。

它闭合三条实测缺陷（出处：`07-测试与工程改进报告.md` §4.3 / §8.2，机读 `evidence/improve/fix_plan.json`）：

* **D-5 / T-01**：复跑**静默覆盖**原件 —— t3 复跑把 t2 的 6 个文件 run_id 从
  ``t2-final-20261006`` 改写成 ``t3-repro-20261006``，且无任何告警。⇒ 落盘改为
  ``evidence/harness/<RUN_ID>/``（``harness/_env.py``，E-01 第 1 条），本脚本负责「改写/删除即失败」。
* **T-08 / A-36**：``evidence/harness/artifact_hashes.json``（t2 自述的「哈希权威副本」）
  **根本不存在**（自述 17 文件 vs 实测 16 文件 / 314482 B，差额正是该索引）⇒ **无基线**。
  ⇒ ``--freeze`` 为**每个** evidence 子目录生成一份本目录索引，并在根目录生成递归总账。
* **A-40**：不得为「复现结论」重跑会产生 evidence 的脚本。⇒ 基线一旦建立，复跑恢复为常规动作
  （新增 = 报告，改写/删除 = 失败）。

三种模式（仓库根目录，绝对路径解释器；PATH 上的 ``python`` 无 Flask）：:

    # 1) 建立/扩展基线（只**新增**索引文件，既有索引与既有制品一字不动）
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/evidence_hash.py --freeze

    # 2) 校验（默认模式）：既有文件被改写/删除 ⇒ 退出码非 0；新增文件 ⇒ 报告 added（允许）
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/evidence_hash.py

    # 3) 对抗自检：1 组阳性 + 5 组阴性注入（改写 / 删除 / 新增 / 同名写入守卫 / 索引不可覆盖）
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/evidence_hash.py --selftest

基线与索引语义（口径写死，便于下游 TL-04/CI 复用）::

    索引快照     = ``artifact_hashes.json``（首份）/ ``artifact_hashes.<run_id>.json``（补齐快照）
                   —— 每份都是**只追加**的冻结快照，既有快照**绝不改写/删除**
    索引条目数   = 该目录**直接**子文件中「非索引文件」被快照并集覆盖的数量（索引自身不列入）
    根目录索引   = 既是 ``evidence/`` 的本目录索引（``files``），也是全树递归总账（``tree`` + ``dirs``）
    只追加       = 新增文件 ⇒ ``added``（允许）；改写/删除既有文件 ⇒ ``modified``/``deleted``（失败）
    自愈         = 目录在冻结后又新增文件 ⇒ ``--freeze`` 补一份新快照（``<dir>`` 的覆盖自检随之恢复）
    流水例外     = ``evidence_journal.jsonl`` 允许**追加**（前缀哈希必须不变；截断/改写 ⇒ 失败）
    ``--freeze`` 的 guard：目标名已被占用 ⇒ 改名 ``<name>.<run_id>.json`` 保留，**绝不覆盖**

退出码：``0`` 无违规；``1`` 有违规（改写/删除/流水前缀损坏/无基线）；``2`` 自检未达预期；``3`` 用法错误。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
if HARNESS_DIR not in sys.path:
    sys.path.insert(0, HARNESS_DIR)

try:  # A-14：中文/箭头在 GBK 控制台会抛 UnicodeEncodeError
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import _env  # noqa: E402  （提供 REPORTS_ROOT / EVIDENCE_ROOT / RUN_ID / guard_write / save_evidence）

SCHEMA = 'w0-evidence-index/1'
INDEX_RE = re.compile(r'^artifact_hashes(\..*)?\.json$')
JOURNAL_NAME = _env.EVIDENCE_JOURNAL_NAME
DEFAULT_ROOT = os.path.join(_env.REPORTS_ROOT, 'evidence')
RUN_ID = os.environ.get('HARNESS_RUN_ID') or time.strftime('w0-evidence-%Y%m%d-%H%M%S')

EXIT_OK, EXIT_VIOLATION, EXIT_SELFTEST, EXIT_USAGE = 0, 1, 2, 3


# --------------------------------------------------------------------------- 基础
def is_index(name):
    """索引文件：``artifact_hashes.json`` / ``artifact_hashes.w0.json`` / 其它同前缀 JSON。"""
    return bool(INDEX_RE.match(name))


def is_journal(name):
    return name == JOURNAL_NAME


def pick_index(directory):
    """本目录的权威索引（人读/兼容用）：优先 W0 快照，否则用既有 ``artifact_hashes.json``。"""
    for cand in ('artifact_hashes.w0.json', 'artifact_hashes.json'):
        if os.path.exists(os.path.join(directory, cand)):
            return cand
    return None


def dir_index_files(directory):
    """本目录下**全部**索引快照（只追加：每次冻结一份，既有快照永不改写/删除）。"""
    if not os.path.isdir(directory):
        return []
    return sorted(n for n in os.listdir(directory) if is_index(n))


def index_snapshot_names(directory):
    """本目录已有索引快照覆盖到的文件名集合（取各快照 ``files`` 的并集）。"""
    names = set()
    for name in dir_index_files(directory):
        try:
            with open(os.path.join(directory, name), encoding='utf-8') as fh:
                doc = json.load(fh)
        except Exception:
            continue
        files = doc.get('files')
        if isinstance(files, dict):
            names.update(files)
    return names


def is_w0_index(path):
    """该索引是否已是 W0 生成的（``schema == w0-evidence-index/1``）。"""
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding='utf-8') as fh:
            head = fh.read(4096)
        return f'"{SCHEMA}"' in head
    except Exception:
        return False


def index_inventory(root, exclude_path=None):
    """全树索引快照清单（不含 ``exclude_path`` 自己）⇒ 用于「删基线即失败」的反洗白判据。

    动机（captain 复核 A-50 时提出的最危险形态）：若只比「当前目录 vs 快照」，那么**删掉旧快照**
    就能让改写/删除消失。⇒ 每份快照都钉住**写它时全树其它索引**的 (bytes, SHA256)；
    校验时逐项复算，缺失或哈希不符 ⇒ ``baseline_tampered`` 违规。
    """
    exclude_path = os.path.abspath(exclude_path) if exclude_path else None
    inv = {}
    for dirpath, _dn, filenames in os.walk(root):
        for name in sorted(filenames):
            if not is_index(name):
                continue
            full = os.path.join(dirpath, name)
            if exclude_path and os.path.abspath(full) == exclude_path:
                continue
            inv[rel_posix(root, full)] = {'bytes': os.path.getsize(full), 'sha256': sha256_file(full)}
    return inv


def snapshot_doc(root, reldir, dir_files, entries, run_id, recursive=False, registry=None, target=None):
    """构造一份快照 doc（各目录共用，字段口径统一）。"""
    d = os.path.join(root, reldir)
    doc = {
        'schema': SCHEMA,
        'run_id': run_id,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'generated_by': 'harness/evidence_hash.py --freeze（W0 / E-01 / G-10）',
        'dir': reldir,
        'scope': ('test-reports-2026-10/evidence/** 全量（递归）的防篡改基线；同时是本目录索引'
                  if recursive else '本目录**直接**子文件的防篡改基线（索引自身除外）'),
        'recursive': bool(recursive),
        'file_count': len(dir_files),
        'total_bytes': sum(entries[f'{reldir}/{n}']['bytes'] if reldir != '.' else entries[n]['bytes']
                           for n in dir_files),
        'file_count_rule': '只数「本目录直接子文件」并**排除一切 artifact_hashes*.json 索引快照**；'
                           'file_count 是**冻结时刻**的计数，后续只追加快照、绝不回写',
        'excluded_index_files': dir_index_files(d) + (
            [os.path.basename(target)] if target and os.path.basename(target) not in dir_index_files(d)
            else []),
        'policy': '只追加（两级）：① 改写/删除既有文件 ⇒ 违规；② 未登记的新增（本目录已索引但未补快照）'
                  ' ⇒ 「覆盖缺项」违规，须跑 --freeze 登记（登记是**显式动作**，不是覆盖）',
        'no_rewrite_guarantee': '既有快照与新快照都不会被改写/删除；改写/删除既有文件永远无法靠重新冻结洗白'
                                '（旧快照的哈希仍是判据）',
        'append_only_files': [JOURNAL_NAME],
        'files': {n: {k: (entries[n][k] if reldir == '.' else entries[f'{reldir}/{n}'][k])
                      for k in ('bytes', 'sha256', 'append_only')} for n in dir_files},
        'index_inventory': index_inventory(root, exclude_path=target),
    }
    if recursive:
        doc['index_glob'] = 'artifact_hashes*.json'
        doc['self_excluded'] = '所有 artifact_hashes*.json 自身不列入 files（写入自身哈希自相矛盾）'
        doc['tree_file_count'] = len(entries)
        doc['tree_total_bytes'] = sum(m['bytes'] for m in entries.values())
        doc['tree'] = entries
        doc['dirs'] = registry or []
        doc['verify_instructions'] = [
            'python -B test-reports-2026-10/harness/evidence_hash.py（默认即校验模式）',
            '改写/删除任一既有文件 ⇒ exit 1；未登记的新增 ⇒ coverage_gap ⇒ exit 1（跑 --freeze 登记）',
            '删除/改写任一索引快照 ⇒ baseline_tampered ⇒ exit 1（index_inventory 反洗白判据）',
            '真实库不受影响：本脚本只读 evidence/** 与写索引，不碰 app.db',
        ]
    return doc

def freeze_target(directory, dir_files, run_id=RUN_ID):
    """该目录该写到哪个索引文件（**幂等且只追加**；已覆盖 ⇒ 返回 None）。

    命名规范（统一定义，避免「A 目录里出现 B 目录的标识」这类引用歧义）::

        artifact_hashes.json            首份快照（目录本来没有索引时用这个名字）
        artifact_hashes.w0.json         W0 首份快照（目录已有历史索引占用了 canonical 名时）
        artifact_hashes.snap<N>.json    第 N 份只追加快照（N≥2，序号只与本目录有关）

    已覆盖本目录全部文件 ⇒ 返回 None（**绝不重复生成、绝不改写既有快照**）；
    否则：``artifact_hashes.json`` 缺失 ⇒ 写它；否则按上表写一份**新**快照。
    """
    covered = index_snapshot_names(directory)
    if not (set(dir_files) - covered):
        return None
    canonical = os.path.join(directory, 'artifact_hashes.json')
    if not os.path.exists(canonical):
        return canonical
    n = 2
    while os.path.exists(os.path.join(directory, f'artifact_hashes.snap{n}.json')):
        n += 1
    return os.path.join(directory, f'artifact_hashes.snap{n}.json')


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def prefix_sha256(path, length):
    """前 ``length`` 字节的 SHA256（用于「流水只许追加」判据）。"""
    h = hashlib.sha256()
    remaining = length
    with open(path, 'rb') as fh:
        while remaining > 0:
            chunk = fh.read(min(1 << 20, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest().upper()


def rel_posix(root, path):
    return os.path.relpath(path, root).replace('\\', '/')


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def write_guarded(path, text, run_id=RUN_ID, tee=None):
    """只追加写：目标已存在 ⇒ 改名保留（绝不覆盖）。返回 ``(实际路径, 是否改名)``。"""
    target, renamed = _env.guard_write(path, run_id=run_id)
    ensure_dir(os.path.dirname(target))
    with open(target, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    if tee is not None:
        tee(f'[guard] {"改名保留" if renamed else "新建"} {os.path.basename(target)}'
            + (f'（请求名被占用：{os.path.basename(path)}）' if renamed else ''))
    return target, renamed


def dump_text(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + '\n'


# --------------------------------------------------------------------------- 扫描
def scan_tree(root):
    """全树扫描（递归）：``{relpath: {bytes, sha256, append_only}}``，排除一切索引文件。"""
    entries = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if is_index(name):
                continue
            full = os.path.join(dirpath, name)
            entries[rel_posix(root, full)] = {
                'bytes': os.path.getsize(full),
                'sha256': sha256_file(full),
                'append_only': is_journal(name),
            }
    return entries


def dirs_with_files(root):
    """``{reldir: [直接子文件(非索引), ...]}``；根目录记为 ``'.'``。只收录有直接文件的目录。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        files = sorted(n for n in filenames if not is_index(n))
        if files:
            out[rel_posix(root, dirpath)] = files
    return out


def dir_summary_map(root, entries):
    """每个目录的（非索引）直接文件数与字节数，来自递归 entries，避免二次 IO。"""
    summary = {}
    for rel, meta in entries.items():
        d = os.path.dirname(rel) or '.'
        item = summary.setdefault(d, {'files': 0, 'bytes': 0})
        item['files'] += 1
        item['bytes'] += meta['bytes']
    return summary


# --------------------------------------------------------------------------- 冻结
def freeze(root, run_id=RUN_ID, tee=None):
    """建立/扩展基线：只为**尚未登记（未被任何快照覆盖）**的目录写**新快照**，绝不改写/删除既有快照。"""
    tee = tee or (lambda *_a: None)
    reported = {'written': [], 'skipped_existing': [], 'guard_renamed': []}
    dir_files = dirs_with_files(root)
    entries = scan_tree(root)

    # 1) 各子目录（非根）：只为「有未登记文件」的目录写新快照
    for reldir in sorted(dir_files):
        if reldir == '.':
            continue
        d = os.path.join(root, reldir)
        target = freeze_target(d, dir_files[reldir], run_id=run_id)
        if target is None:
            reported['skipped_existing'].append({'dir': reldir, 'index': pick_index(d) or ''})
            continue
        doc = snapshot_doc(root, reldir, dir_files[reldir], entries, run_id, target=target)
        written, renamed = write_guarded(target, dump_text(doc), run_id=run_id, tee=tee)
        reported['written'].append({'dir': reldir, 'index': rel_posix(root, written)})
        if renamed:
            reported['guard_renamed'].append(rel_posix(root, written))

    # 2) 根目录：本目录索引 + 全树递归总账（同一份文件承担两个角色）
    root_entries = sorted(dir_files.get('.', []))
    registry = []
    for reldir in sorted(dir_files):
        d = os.path.join(root, reldir)
        covered = index_snapshot_names(d)
        listed = sum(1 for n in dir_files[reldir] if n in covered)
        snapshots = dir_index_files(d)
        registry.append({
            'dir': reldir,
            'index': (f'{reldir}/{pick_index(d)}' if reldir != '.' else pick_index(d)) if pick_index(d) else None,
            'index_snapshots': [f'{reldir}/{n}' if reldir != '.' else n for n in snapshots],
            'legacy_index': (f'{reldir}/artifact_hashes.json' if reldir != '.' else 'artifact_hashes.json')
                            if os.path.exists(os.path.join(d, 'artifact_hashes.json')) else None,
            'index_entries_for_this_dir': listed,
            'dir_files_excl_index': len(dir_files[reldir]),
            'conforms': listed == len(dir_files[reldir]),
        })

    canonical_root = os.path.join(root, 'artifact_hashes.json')
    if not os.path.exists(canonical_root):
        target = canonical_root      # 根总账是校验锚点，必须存在（即使根目录没有直接文件）
    else:
        target = freeze_target(root, root_entries, run_id=run_id)
    if target is None:
        reported['skipped_existing'].append({'dir': '.', 'index': pick_index(root) or ''})
    else:
        doc = snapshot_doc(root, '.', root_entries, entries, run_id, recursive=True,
                           registry=registry, target=target)
        written, renamed = write_guarded(target, dump_text(doc), run_id=run_id, tee=tee)
        reported['written'].append({'dir': '.', 'index': rel_posix(root, written)})
        if renamed:
            reported['guard_renamed'].append(rel_posix(root, written))
    return reported


# --------------------------------------------------------------------------- 校验
def load_baseline(root):
    """读基线：根索引的递归 ``tree``（若缺，则合并各目录索引的 ``files``）。"""
    ledger = os.path.join(root, 'artifact_hashes.json')
    if not os.path.exists(ledger):
        return None, 'no_baseline'
    with open(ledger, encoding='utf-8') as fh:
        doc = json.load(fh)
    entries = {}
    if isinstance(doc.get('tree'), dict):
        entries.update(doc['tree'])
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not is_index(name):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding='utf-8') as fh:
                    sub = json.load(fh)
            except Exception:
                continue
            if isinstance(sub.get('tree'), dict):      # 任一总账快照都并入（只追加：并集只增不减）
                for rel, meta in sub['tree'].items():
                    if isinstance(meta, dict):
                        entries.setdefault(rel, meta)
            files = sub.get('files')
            if not isinstance(files, dict):
                continue
            for fname, meta in files.items():
                if not isinstance(meta, dict):
                    continue
                rel = rel_posix(root, os.path.join(dirpath, fname))
                entries.setdefault(rel, {'bytes': meta.get('bytes'),
                                         'sha256': (meta.get('sha256') or '').upper(),
                                         'append_only': bool(meta.get('append_only'))})
    return {'doc': doc, 'entries': entries}, None


def verify(root, strict_index=False, strict_coverage=True):
    """只追加校验。

    四类违规（都会让判定为 ``violation`` / 退出码 1）::

        modified / deleted / journal_prefix_broken  既有文件被改写、删除，或只追加流水被截断
        coverage_gap                                本目录已索引，却出现了**未登记**的新增文件
                                                    （= A-50 形态；登记方式：跑 --freeze 补一份新快照）
        phantom_entry                               快照里列了、目录里没有的文件（删除/改名的痕迹）
        baseline_tampered                           索引快照自身被删除或改写（``index_inventory`` 反洗白判据）

    ``strict_coverage=False`` 可把 ``coverage_gap`` 降级为「允许的 added」（默认**开**，即必须显式登记）。
    """
    report = {
        'harness': 'evidence_hash.py',
        'mode': 'verify',
        'schema': SCHEMA,
        'run_id': RUN_ID,
        'evidence_root': root,
        'checked_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'strict_index': bool(strict_index), 'strict_coverage': bool(strict_coverage),
        'violations': [], 'modified': [], 'deleted': [], 'journal_broken': [],
        'added': [], 'index_missing': [], 'coverage_gap': [], 'phantom_entry': [],
        'baseline_tampered': [], 'dirs': [],
    }
    baseline, err = load_baseline(root)
    if baseline is None:
        report['verdict'] = 'no_baseline'
        report['counts'] = {'baseline_files': 0, 'current_files': len(scan_tree(root)),
                            'modified': 0, 'deleted': 0, 'journal_broken': 0, 'added': 0,
                            'index_missing': 0, 'coverage_gap': 0, 'phantom_entry': 0,
                            'baseline_tampered': 0,
                            'dirs_conform': 0, 'dirs_total': len(dirs_with_files(root))}
        report['violations'].append({
            'kind': 'no_baseline',
            'problem': f'根索引 {rel_posix(root, os.path.join(root, "artifact_hashes.json"))} 不存在 ⇒ 无法校验'
                       '（这正是 T-08/A-36 的形态：无防篡改基线）',
            'required_fix': '先跑 --freeze 建立基线',
        })
        return report

    base_entries = baseline['entries']
    current = scan_tree(root)

    for rel, meta in sorted(base_entries.items()):
        cur = current.get(rel)
        if cur is None:
            report['deleted'].append(rel)
            report['violations'].append({'kind': 'deleted', 'path': rel,
                                         'problem': '基线中的文件已不存在（删除即失败）'})
            continue
        if meta.get('append_only') or cur.get('append_only'):
            n = int(meta.get('bytes') or 0)
            if cur['bytes'] < n or prefix_sha256(os.path.join(root, *rel.split('/')), n) != meta['sha256']:
                report['journal_broken'].append(rel)
                report['violations'].append({
                    'kind': 'journal_prefix_broken', 'path': rel,
                    'problem': f'只追加流水的前 {n} 字节哈希已变（或被截断）'
                               f'：基线 {str(meta.get("sha256"))[:16]}… / 实测 '
                               f'{prefix_sha256(os.path.join(root, *rel.split("/")), n)[:16]}…'})
            continue
        if cur['sha256'] != meta.get('sha256'):
            report['modified'].append({'path': rel, 'baseline_bytes': meta.get('bytes'),
                                       'current_bytes': cur['bytes'],
                                       'baseline_sha256': meta.get('sha256'),
                                       'current_sha256': cur['sha256']})
            report['violations'].append({
                'kind': 'modified', 'path': rel,
                'problem': f'基线哈希被改写：{str(meta.get("sha256"))[:16]}… → {cur["sha256"][:16]}…',
                'required_fix': '原件不可修改；如需保留新内容，请用新 run_id 落盘到新目录'})

    report['added'] = sorted(set(current) - set(base_entries))

    # --- 反洗白：索引快照自身不得被删除/改写（index_inventory 判据）
    inventories = {}
    for dirpath, _dn, filenames in os.walk(root):
        for name in filenames:
            if not is_index(name):
                continue
            try:
                with open(os.path.join(dirpath, name), encoding='utf-8') as fh:
                    sub = json.load(fh)
            except Exception:
                continue
            if isinstance(sub.get('index_inventory'), dict):
                for rel, meta in sub['index_inventory'].items():
                    if isinstance(meta, dict):
                        inventories.setdefault(rel, meta)   # 最旧快照的钉法优先（setdefault 不覆盖）
    for rel, meta in sorted(inventories.items()):
        path = os.path.join(root, *rel.split('/'))
        if not os.path.exists(path):
            problem = '基线索引快照被删除 ⇒ 防篡改基线不完整（反洗白判据）'
        elif sha256_file(path) != meta.get('sha256'):
            problem = (f'基线索引快照被改写：{str(meta.get("sha256"))[:16]}… → '
                       f'{sha256_file(path)[:16]}…（反洗白判据）')
        else:
            continue
        report['baseline_tampered'].append({'path': rel, 'problem': problem})
        report['violations'].append({'kind': 'baseline_tampered', 'path': rel, 'problem': problem,
                                     'required_fix': '索引快照只追加；被删/被改必须从备份恢复，'
                                                     '不得靠重新冻结洗白'})

    # --- 每目录「有索引快照 + 快照并集覆盖本目录全部非索引文件」自检
    dir_files = dirs_with_files(root)
    for reldir in sorted(dir_files):
        d = os.path.join(root, reldir)
        snapshots = dir_index_files(d)
        covered = index_snapshot_names(d)
        item = {'dir': reldir,
                'index': (f'{reldir}/{pick_index(d)}' if reldir != '.' else pick_index(d)) if pick_index(d) else None,
                'index_snapshots': [f'{reldir}/{n}' if reldir != '.' else n for n in snapshots],
                'legacy_index': (f'{reldir}/artifact_hashes.json' if reldir != '.' else 'artifact_hashes.json')
                                if os.path.exists(os.path.join(d, 'artifact_hashes.json')) else None,
                'dir_files_excl_index': len(dir_files[reldir]),
                'index_entries': sum(1 for n in dir_files[reldir] if n in covered),
                'uncovered': sorted(n for n in dir_files[reldir] if n not in covered)[:10],
                'conforms': False}
        if not snapshots:
            report['index_missing'].append(reldir)
            item['problem'] = '该目录没有 artifact_hashes*.json 索引快照'
            if strict_index:
                report['violations'].append({'kind': 'index_missing', 'path': reldir,
                                             'problem': item['problem'],
                                             'required_fix': '跑 --freeze 为该目录补索引快照'})
        else:
            item['conforms'] = item['index_entries'] == item['dir_files_excl_index']
            phantoms = sorted(n for n in covered if n not in dir_files[reldir])
            item['phantom'] = phantoms
            # 权威快照：**最新（files 最多）**的那份；索引不可回写，故 canonical 的 file_count 只是冻结时刻值
            best, best_n = None, -1
            for name in snapshots:
                try:
                    with open(os.path.join(d, name), encoding='utf-8') as fh:
                        sub = json.load(fh)
                except Exception:
                    continue
                n_files = len(sub.get('files') or {})
                if n_files > best_n or (n_files == best_n and name > (best or '')):
                    best, best_n = name, n_files
            item['authoritative_index'] = (f'{reldir}/{best}' if reldir != '.' else best) if best else None
            item['authoritative_file_count'] = best_n if best else 0
            item['count_rule'] = ('权威快照 = 本目录 files 最多的那份；file_count 为冻结时刻计数，'
                                  'artifact_hashes*.json 自身不计入')
            if not item['conforms']:
                item['problem'] = (f'索引快照未覆盖本目录 {len(item["uncovered"])} 个（或更多）文件'
                                   f'（= A-50 形态：冻结之后又追加了无索引文件）')
                report['coverage_gap'].append({'dir': reldir,
                                               'uncovered': item['uncovered'],
                                               'dir_files_excl_index': item['dir_files_excl_index'],
                                               'index_entries': item['index_entries']})
                if strict_coverage:
                    report['violations'].append({
                        'kind': 'coverage_gap', 'path': reldir,
                        'problem': item['problem'] + f'：{item["uncovered"]}',
                        'required_fix': '跑 --freeze 补一份新快照（只追加，既有快照一字不动）'
                                        '；或把这些文件移出 evidence/**'})
            if phantoms:
                report['phantom_entry'].append({'dir': reldir, 'names': phantoms})
                report['violations'].append({
                    'kind': 'phantom_entry', 'path': reldir,
                    'problem': f'索引快照列出了本目录并不存在的文件：{phantoms}',
                    'required_fix': '查清是删除还是改名；基线不做删除⇒属违规'})
        report['dirs'].append(item)

    report['counts'] = {
        'baseline_files': len(base_entries),
        'current_files': len(current),
        'modified': len(report['modified']),
        'deleted': len(report['deleted']),
        'journal_broken': len(report['journal_broken']),
        'added': len(report['added']),
        'index_missing': len(report['index_missing']),
        'coverage_gap': len(report['coverage_gap']),
        'phantom_entry': len(report['phantom_entry']),
        'baseline_tampered': len(report['baseline_tampered']),
        'dirs_conform': sum(1 for d in report['dirs'] if d['conforms']),
        'dirs_total': len(report['dirs']),
    }
    report['verdict'] = 'ok' if not report['violations'] else 'violation'
    report['real_db_sha256'] = _env.sha256_file(_env.REAL_DB) if os.path.exists(_env.REAL_DB) else None
    report['real_db_matches_pinned'] = report['real_db_sha256'] == _env.REAL_DB_SHA256_EXPECTED
    return report


def print_report(report, tee):
    c = report.get('counts', {})
    tee('=' * 78)
    tee(f'[evidence_hash] 模式={report["mode"]} run_id={report["run_id"]}')
    tee(f'[evidence_hash] 证据根 {report["evidence_root"]}')
    if report['verdict'] == 'no_baseline':
        tee(f'[evidence_hash] 判定 = NO_BASELINE（无防篡改基线，退出码 1）'
            f'  当前文件数={c.get("current_files")}')
        for v in report['violations']:
            tee(f'  [VIOLATION/{v["kind"]}] {v["problem"]}')
        tee('=' * 78)
        return
    tee(f'[evidence_hash] 基线文件数={c["baseline_files"]}  当前文件数={c["current_files"]}'
        f'  改写={c["modified"]}  删除={c["deleted"]}  流水损坏={c["journal_broken"]}'
        f'  新增(允许)={c["added"]}  覆盖缺项={c["coverage_gap"]}  幽灵条目={c["phantom_entry"]}')
    for v in report['violations']:
        tee(f'  [VIOLATION/{v["kind"]}] {v["path"]}: {v["problem"]}')
    for a in report['added'][:20]:
        tee(f'  [ADDED/允许] {a}')
    if len(report['added']) > 20:
        tee(f'  [ADDED/允许] …另有 {len(report["added"]) - 20} 项')
    tee(f'[evidence_hash] 每目录索引自检：{c["dirs_conform"]}/{c["dirs_total"]} 目录「快照并集」覆盖本目录全部非索引文件')
    for d in report['dirs']:
        flag = 'OK ' if d['conforms'] else ('NOINDEX' if not d.get('index_snapshots') else 'DIFF')
        extra = '' if d['conforms'] else f' 未覆盖={d.get("uncovered")}'
        tee(f'  [{flag}] {d["dir"]}: 权威快照={d.get("authoritative_index")}'
            f'({d.get("authoritative_file_count")}) 快照={d.get("index_snapshots")}'
            f' 覆盖={d["index_entries"]}/{d["dir_files_excl_index"]}{extra}')
    tee(f'[evidence_hash] 判定 = {report["verdict"].upper()}（退出码 {EXIT_OK if report["verdict"] == "ok" else EXIT_VIOLATION}）')
    tee('=' * 78)


# --------------------------------------------------------------------------- 对抗自检
def selftest(root, run_id=RUN_ID, tee=None):
    """对抗自检：在**完全受控的合成证据树**上做阳性对照 + 阴性注入。

    为什么不在真实树上做对照：真实树是多人并发写入的活体（他人会删除/追加自己的日志），
    阳性对照会被并发写入带红，从而掩盖判据本身的问题。合成树把「判据是否敏感/是否健全」
    与「活体现在健康与否」解耦；真实树的当前读数只作**信息项**打印，不计入判定。
    """
    tee = tee or (lambda *_a: None)
    scratch = _env.tmp_dir('evidence_hash_selftest')
    cases = []
    lines = []

    def case(cid, title, expected, actual, ok):
        cases.append({'id': cid, 'title': title, 'expected': expected, 'actual': actual,
                      'verdict': 'passed' if ok else 'failed'})
        lines.append(f'  [{"PASS" if ok else "FAIL"}] {cid} {title}')
        lines.append(f'        expected={expected!r}')
        lines.append(f'        actual  ={actual!r}')

    def w(path, text):
        ensure_dir(os.path.dirname(path))
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)

    # ---------------------------------------------------------------- 合成树（受控）
    tree = os.path.join(scratch, 'synthetic_evidence')
    if os.path.exists(tree):
        shutil.rmtree(tree, ignore_errors=True)
    w(os.path.join(tree, 'alpha', 'a.txt'), 'alpha/a v1\n')
    w(os.path.join(tree, 'alpha', 'b.json'), '{"k": 1}\n')
    w(os.path.join(tree, 'alpha', 'sub', 'deep.txt'), 'nested\n')
    w(os.path.join(tree, 'beta', 'run.txt'), 'beta run\n')
    w(os.path.join(tree, 'beta', JOURNAL_NAME),
      json.dumps({'ts': 't0', 'written': 'run.txt'}, ensure_ascii=False) + '\n')
    tee(f'[selftest] 合成受控树 {tree}')

    fr0 = freeze(tree, run_id=run_id, tee=tee)
    ok0 = verify(tree)
    case('EH-P1', '阳性对照：合成树 --freeze 后 --verify 必须通过',
         {'verdict': 'ok', 'indexes_written': len(fr0['written'])},
         {'verdict': ok0['verdict'], 'indexes_written': len(fr0['written']),
          'counts': ok0['counts']},
         ok0['verdict'] == 'ok' and len(fr0['written']) >= 3)

    det1, det2 = verify(tree), verify(tree)
    case('EH-P2', '阳性对照：同一状态连续两次校验 ⇒ 读数完全一致（确定性）',
         {'counts_equal': True},
         {'counts_equal': det1['counts'] == det2['counts'], 'counts': det1['counts']},
         det1['counts'] == det2['counts'])

    # ---------------------------------------------------------------- 阴性注入
    victim = os.path.join(tree, 'alpha', 'a.txt')
    original = open(victim, 'rb').read()

    with open(victim, 'ab') as fh:                      # N1：改写一个字节
        fh.write(b'\n# tampered-by-selftest\n')
    r = verify(tree)
    case('EH-N1', '阴性：改写 alpha/a.txt 一个字节 ⇒ 校验必须失败',
         {'verdict': 'violation', 'modified>=1': True},
         {'verdict': r['verdict'], 'modified': r['counts']['modified']},
         r['verdict'] == 'violation' and r['counts']['modified'] >= 1)
    with open(victim, 'wb') as fh:
        fh.write(original)

    victim2 = os.path.join(tree, 'beta', 'run.txt')     # N2：删除
    saved2 = open(victim2, 'rb').read()
    os.remove(victim2)
    r = verify(tree)
    case('EH-N2', '阴性：删除 beta/run.txt ⇒ 校验必须失败（含幽灵条目）',
         {'verdict': 'violation', 'deleted>=1': True, 'phantom>=1': True},
         {'verdict': r['verdict'], 'deleted': r['counts']['deleted'],
          'phantom': r['counts']['phantom_entry']},
         r['verdict'] == 'violation' and r['counts']['deleted'] >= 1
         and r['counts']['phantom_entry'] >= 1)
    with open(victim2, 'wb') as fh:
        fh.write(saved2)

    # N3（A-50 回归）：冻结后在已索引目录追加文件、不补快照 ⇒ 默认判据必须非 0；--freeze 后必须转正
    extra = os.path.join(tree, 'alpha', 'a50_coverage_gap_probe.txt')
    w(extra, 'added after freeze, without new snapshot（A-50 形态）\n')
    r_gap = verify(tree)
    r_gap_off = verify(tree, strict_coverage=False)
    fr_a50 = freeze(tree, run_id=run_id + '-a50', tee=tee)
    r_fixed = verify(tree)
    case('EH-N3', 'A-50 回归：冻结后新增文件 ⇒ coverage_gap 非 0；放宽时允许；--freeze 补快照后转 0',
         {'gap_verdict': 'violation', 'gap_kind': 'coverage_gap',
          'relaxed_verdict': 'ok', 'after_freeze_verdict': 'ok'},
         {'gap_verdict': r_gap['verdict'],
          'gap_kinds': sorted({v['kind'] for v in r_gap['violations']}),
          'relaxed_verdict': r_gap_off['verdict'],
          'after_freeze_verdict': r_fixed['verdict'],
          'new_snapshots': len(fr_a50['written'])},
         r_gap['verdict'] == 'violation'
         and any(v['kind'] == 'coverage_gap' for v in r_gap['violations'])
         and r_gap_off['verdict'] == 'ok' and r_fixed['verdict'] == 'ok')

    # N4：--freeze 幂等（第二次写 0、既有快照哈希不变、无 guard 改名、冻结后覆盖自检全通过）
    def index_state(r):
        state = {}
        for dirpath, _dn, filenames in os.walk(r):
            idx = sorted(n for n in filenames if is_index(n))
            if idx:
                state[rel_posix(r, dirpath)] = {n: sha256_file(os.path.join(dirpath, n)) for n in idx}
        return state

    before_state = index_state(tree)
    fr1 = freeze(tree, run_id=run_id + '-idem', tee=tee)
    fr2 = freeze(tree, run_id=run_id + '-idem', tee=tee)
    after_state = index_state(tree)
    unchanged = all(name in after_state.get(d, {}) and after_state[d][name] == h
                    for d, names in before_state.items() for name, h in names.items())
    healed = verify(tree)
    case('EH-N4', '--freeze 幂等 + 自愈：既有快照哈希不变、第二次写 0 个、冻结后覆盖自检全通过',
         {'second_freeze_writes': 0, 'existing_snapshots_unchanged': True, 'guard_renamed': 0,
          'dirs_conform': 'dirs_total'},
         {'first_freeze_writes': len(fr1['written']), 'second_freeze_writes': len(fr2['written']),
          'existing_snapshots_unchanged': unchanged,
          'guard_renamed': len(fr1['guard_renamed']) + len(fr2['guard_renamed']),
          'dirs_conform': f'{healed["counts"]["dirs_conform"]}/{healed["counts"]["dirs_total"]}'},
         len(fr2['written']) == 0 and unchanged
         and not fr1['guard_renamed'] and not fr2['guard_renamed']
         and healed['counts']['dirs_conform'] == healed['counts']['dirs_total'])

    # N5：流水只许追加（追加行 ⇒ 通过；截断 ⇒ 失败）
    jpath = os.path.join(tree, 'beta', JOURNAL_NAME)
    with open(jpath, 'a', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps({'ts': 't1', 'note': 'append'}, ensure_ascii=False) + '\n')
    r_append = verify(tree)
    with open(jpath, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('x')
    r_trunc = verify(tree)
    case('EH-N5', f'{JOURNAL_NAME}：追加行 ⇒ 通过；截断 ⇒ 失败',
         {'append': 'ok', 'truncate': 'violation'},
         {'append': r_append['verdict'], 'truncate': r_trunc['verdict'],
          'journal_broken': r_trunc['counts']['journal_broken']},
         r_append['verdict'] == 'ok' and r_trunc['verdict'] == 'violation')

    # N6：同名写入必须「改名保留」而非覆盖（走 _env.save_evidence 端到端）
    probe = 'w0_guard_injection_probe.txt'
    p1 = _env.save_evidence(probe, 'FIRST-CONTENT\n')
    first_bytes = open(p1, 'rb').read()
    p2 = _env.save_evidence(probe, 'SECOND-CONTENT\n')
    kept = os.path.exists(p1) and open(p1, 'rb').read() == first_bytes
    case('EH-N6', '阴性：同名二次写入 ⇒ 改名保留（原件字节不变），绝不覆盖',
         {'original_path_kept': True, 'second_write_renamed': True},
         {'original': rel_posix(_env.EVIDENCE_ROOT, p1),
          'second': rel_posix(_env.EVIDENCE_ROOT, p2),
          'original_kept': kept, 'renamed': os.path.basename(p1) != os.path.basename(p2)},
         kept and os.path.basename(p1) != os.path.basename(p2))

    # N7（captain 复核要求）：**禁止用「重新冻结」洗白**
    #   ① 改写既有文件后再跑 --freeze ⇒ 违规必须依然存在（旧快照哈希仍是判据）
    #   ② 删掉一份基线快照 ⇒ 必须由 index_inventory 判为 baseline_tampered
    v3 = os.path.join(tree, 'alpha', 'sub', 'deep.txt')
    keep3 = open(v3, 'rb').read()
    with open(v3, 'ab') as fh:
        fh.write('\n# laundering attempt（重新冻结也洗不掉）\n'.encode('utf-8'))
    fr_wash = freeze(tree, run_id=run_id + '-wash', tee=tee)
    r_wash = verify(tree)
    snaps_alpha = dir_index_files(os.path.join(tree, 'alpha'))
    victim_idx = os.path.join(tree, 'alpha', snaps_alpha[0]) if snaps_alpha else None
    if victim_idx:
        os.remove(victim_idx)
    r_tamper = verify(tree)
    with open(v3, 'wb') as fh:
        fh.write(keep3)
    case('EH-N7', '禁止洗白：① 改写后 --freeze 仍判违规；② 删除基线快照 ⇒ baseline_tampered',
         {'after_freeze_still_violation': True, 'snapshot_deletion_detected': True},
         {'freeze_writes': len(fr_wash['written']), 'verdict_after_freeze': r_wash['verdict'],
          'modified_after_freeze': r_wash['counts']['modified'],
          'verdict_after_snapshot_delete': r_tamper['verdict'],
          'baseline_tampered': r_tamper['counts']['baseline_tampered']},
         r_wash['verdict'] == 'violation' and r_wash['counts']['modified'] >= 1
         and r_tamper['verdict'] == 'violation' and r_tamper['counts']['baseline_tampered'] >= 1)

    # ---------------------------------------------------------------- 真实树读数（信息项，不计判定）
    live = verify(root)
    live_line = (f'  [INFO] 真实证据树当前读数：verdict={live["verdict"]}'
                 f' 改写={live.get("counts", {}).get("modified")}'
                 f' 删除={live.get("counts", {}).get("deleted")}'
                 f' 覆盖缺项={live.get("counts", {}).get("coverage_gap")}'
                 f' 幽灵条目={live.get("counts", {}).get("phantom_entry")}'
                 f'（并发写入者的删改会在此显现，不计入本自检判定）')
    lines.append(live_line)

    passed = sum(1 for c in cases if c['verdict'] == 'passed')
    summary = {'harness': 'evidence_hash.py', 'mode': 'selftest', 'run_id': run_id,
               'synthetic_tree': tree, 'evidence_root': root,
               'live_tree_read': {'verdict': live['verdict'], 'counts': live.get('counts')},
               'passed': passed, 'failed': len(cases) - passed, 'cases': cases}
    header = ['=' * 78, f'[evidence_hash] 对抗自检 run_id={run_id}（受控合成树）', '=' * 78]
    for line in header + lines:
        tee(line)
    tee(f'[evidence_hash] 自检结果 {passed}/{len(cases)} 通过'
        f' ⇒ 退出码 {EXIT_OK if passed == len(cases) else EXIT_SELFTEST}')
    try:
        shutil.rmtree(tree, ignore_errors=True)   # 合成树属 scratch，不留在证据树里
    except Exception:
        pass
    return summary, '\n'.join(header + lines) + '\n'


# --------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description='evidence/** 只追加防篡改基线（W0 / E-01 / G-10）')
    ap.add_argument('--evidence-root', default=DEFAULT_ROOT, help='证据根（默认 test-reports-2026-10/evidence）')
    ap.add_argument('--freeze', action='store_true', help='建立/扩展基线：只新增缺失的索引，绝不覆盖')
    ap.add_argument('--selftest', action='store_true', help='对抗自检（1 阳性 + 5 阴性注入 + 1 A-50 回归）')
    ap.add_argument('--strict-index', action='store_true', help='把「目录完全没有索引快照」也算违规')
    ap.add_argument('--no-strict-coverage', dest='strict_coverage', action='store_false',
                    help='放宽 A-50 判据（默认**开**：索引快照未覆盖本目录文件 ⇒ 非 0）')
    ap.add_argument('--transcript', action='store_true',
                    help='把本工具的控制台原文经 _env.save_evidence 落盘到证据 run 目录（默认不写盘、零副作用）')
    ap.add_argument('--json', action='store_true', help='stdout 额外打印机读 JSON')
    ap.add_argument('--out', default=None, help='把机读 JSON 写到指定路径（guard：已存在则改名保留）')
    ap.add_argument('--run-id', default=RUN_ID, help='本次运行标识（默认 HARNESS_RUN_ID 或时间戳）')
    args = ap.parse_args()

    root = os.path.abspath(args.evidence_root)
    if not os.path.isdir(root):
        sys.stderr.write(f'[evidence_hash] 证据根不存在：{root}\n')
        return EXIT_USAGE

    transcript = []
    tee = transcript.append
    tee(f'[evidence_hash] 解释器 {sys.executable}')
    tee(f'[evidence_hash] 仓库根 {_env.REPO_ROOT}')
    tee(f'[evidence_hash] run_id={args.run_id}  模式='
        f'{"freeze" if args.freeze else ("selftest" if args.selftest else "verify")}')
    tee(f'[evidence_hash] strict_coverage={"on" if args.strict_coverage else "off"}'
        f'（A-50 判据：索引快照未覆盖本目录文件 ⇒ 违规）')

    if args.selftest:
        summary, text = selftest(root, run_id=args.run_id, tee=tee)
        summary['real_db_sha256'] = _env.sha256_file(_env.REAL_DB)
        summary['real_db_matches_pinned'] = summary['real_db_sha256'] == _env.REAL_DB_SHA256_EXPECTED
        out_path = _env.save_evidence('evidence_hash_selftest.out.txt', '\n'.join(transcript) + '\n')
        json_path = args.out or _env.save_evidence('evidence_hash_selftest.json', dump_text(summary))
        print('\n'.join(transcript))
        print(f'[evidence_hash] 自检原始输出：{rel_posix(_env.REPO_ROOT, out_path)}')
        print(f'[evidence_hash] 自检机读：{rel_posix(_env.REPO_ROOT, json_path)}')
        return EXIT_OK if summary['failed'] == 0 else EXIT_SELFTEST

    if args.freeze:
        fr = freeze(root, run_id=args.run_id, tee=tee)
        tee(f'[freeze] 新写索引 {len(fr["written"])} 个，既有索引跳过 {len(fr["skipped_existing"])} 个，'
            f'guard 改名 {len(fr["guard_renamed"])} 个')
        for w in fr['written']:
            tee(f'  [written] {w["index"]}')
        for s in fr['skipped_existing']:
            tee(f'  [kept]    {s["dir"]}/{s["index"]}（已存在且已覆盖，未重写）')
        report = verify(root, strict_index=args.strict_index, strict_coverage=args.strict_coverage)
        report['freeze'] = fr
    else:
        report = verify(root, strict_index=args.strict_index, strict_coverage=args.strict_coverage)

    print_report(report, tee)
    if args.transcript:
        # 走 _env.save_evidence ⇒ 同目录 evidence_journal.jsonl 有台账行（避免 A-50 那类「无索引无台账」文件）
        tp = _env.save_evidence(f'evidence_hash_{report["mode"]}.out.txt', '\n'.join(transcript) + '\n')
        tee(f'[evidence_hash] 控制台原文（经 save_evidence，带台账）：{rel_posix(_env.REPO_ROOT, tp)}')
    if args.out:
        out_json, renamed = write_guarded(os.path.abspath(args.out), dump_text(report), run_id=args.run_id)
        tee(f'[evidence_hash] 机读报告：{out_json}（改名={renamed}）')
        if os.path.abspath(args.out).startswith(root + os.sep):
            tee('[evidence_hash] 注意：报告写在 evidence/** 内 ⇒ 本次冻结之后它才出现，'
                '下次校验会报 coverage_gap；请再跑一次 --freeze（只追加）即可覆盖')
    text = '\n'.join(transcript) + '\n'
    print(text)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else '')
    return EXIT_OK if report['verdict'] == 'ok' else EXIT_VIOLATION


if __name__ == '__main__':
    sys.exit(main())
