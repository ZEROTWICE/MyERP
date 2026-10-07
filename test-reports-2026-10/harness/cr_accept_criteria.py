# -*- coding: utf-8 -*-
"""cr_accept_criteria.py —— 验收判据的**载体存在性**只读探针（t4 自证）

目的（对应 `28-第2轮执行纪律.md` 的 A-71/A-73/A-74 与「阴性用例要求」）：
    本文件交付的每一条判据都写明了「载体（file:line + 关键 token）」。若不机检，
    判据可能与生产代码脱钩（引用不存在的行/字段）⇒ 下游会把「判据不可判定」误当成
    「产品不合格」。故本探针逐条断言：

    1. 载体文件存在；2. 载体行号处**确实**含该关键 token（逐字比对，非模糊）；
    3. **无自指**：候选文件与探针自身、captain 核验脚本、reconcile 脚本一律排除，
       并逐条登记本次实际命中的文件（A-74 防护）。

只读声明：本探针只读文件与 git 元数据；**不修改任何生产代码 / 不写库 / 不发请求**。
运行（绝对路径解释器，A-7）：
    & 'F:\Miniconda\envs\wage\python.exe' -B test-reports-2026-10/harness/cr_accept_criteria.py
"""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# A-74：自指性排除域（本探针自身 + 核验/对账脚本族）
EXCLUDED_BASENAMES = {
    'cr_accept_criteria.py',        # 本探针自身
    'reconcile_r2.py',              # t1 对账脚本（自身族）
    'captain_r2_anchors.py', 'captain_r2_precheck.py', 'captain_r2_review.py',
    'captain_r2_status.py', 'captain_r2_targets.py', 'captain_r2_w6rest.py',
    'improve_plan.py', 'analysis_ledger.py', 'final_recount.py', 'verify_t4.py',
}

# 每条判据的载体：(编号, 文件相对路径, 行号, 该行必含的逐字 token, 判据 ID)
CARRIERS = [
    # ---- C-08：导入行级容错 / 导出零残留
    ('C-08', 'app/main/routes.py', 1935, 'def import_employees', 'B-08.1'),
    ('C-08', 'app/main/routes.py', 2284, 'def import_process_prices', 'B-08.1'),
    ('C-08', 'app/main/routes.py', 2681, 'def import_production_records', 'B-08.1'),
    ('C-08', 'app/main/routes.py', 3861, 'def import_bonus_penalties', 'B-08.1'),
    ('C-08', 'app/main/routes.py', 3987, 'def import_tasks', 'B-08.1'),
    ('C-08', 'app/main/routes.py', 4028, '第 {index + 2} 行', 'B-08.1'),
    ('C-08', 'app/main/routes.py', 4880, 'def import_finished_products', 'B-08.1'),
    ('C-08', 'app/main/routes.py', 4967, 'def import_raw_materials', 'B-08.1'),
    ('C-08', 'app/main/routes.py', 7685, 'def import_products', 'B-08.1'),
    ('C-08', 'app/main/quality.py', 1612, "'/api/quality/tasks/import'", 'B-08.1'),
    ('C-08', 'app/main/quality.py', 1656, '第 {lineno} 行', 'B-08.1'),
    ('C-08', 'app/main/routes.py', 1951, "current_app.config['TEMP_FOLDER']", 'B-08.2'),
    ('C-08', 'app/main/routes.py', 2180, 'def cleanup_temp_files', 'B-08.2'),
    ('C-08', 'app/main/routes.py', 2203, '@bp.before_request', 'B-08.2'),
    ('C-08', 'app/main/routes.py', 4116, 'excel_file.save(buf)', 'B-08.3'),
    ('C-08', 'app/main/routes.py', 4165, 'excel_file.save(buf)', 'B-08.3'),
    ('C-08', 'app/main/quality.py', 1368, "'/api/quality/records/export'", 'B-08.3'),
    ('C-08', 'app/main/quality.py', 1533, "'/api/quality/tasks/export'", 'B-08.3'),
    ('C-08', 'app/main/quality.py', 1579, "'/api/quality/tasks/template'", 'B-08.3'),
    # C-08 预登记缺口 1：两个成品/原料导入落 OS 临时目录（不在 TEMP_FOLDER，不被清理钩子覆盖）
    ('C-08', 'app/main/routes.py', 4892, 'tempfile.gettempdir()', 'C-08-缺口-1'),
    ('C-08', 'app/main/routes.py', 4979, 'tempfile.gettempdir()', 'C-08-缺口-1'),
    ('C-08', 'app/main/routes.py', 5083, 'def save_temp_file', 'C-08-缺口-1'),
    # C-08 预登记缺口 2：过期阈值（>5 分钟才删）
    ('C-08', 'app/main/routes.py', 2194, '> 300', 'C-08-缺口-2'),
    # ---- C-09：工价版本取值 + 三策略派工
    ('C-09', 'app/main/routes.py', 2717, 'ProcessPrice.query.filter', 'D-09.1'),
    ('C-09', 'app/main/routes.py', 2720, 'ProcessPrice.effective_date.desc()', 'D-09.1'),
    ('C-09', 'app/main/routes.py', 3902, 'process_code=data', 'D-09.2'),
    ('C-09', 'app/main/routes.py', 4020, 'process_code=data', 'D-09.2'),
    ('C-09', 'app/services/mes_service.py', 1819, 'record.quantity * record.process.price', 'D-09.2'),
    ('C-09', 'app/main/routes.py', 762, 'latest_versions = db.session.query(', 'D-09.3'),
    ('C-09', 'app/models.py', 2511, "'round_robin'", 'D-09.4'),
    ('C-09', 'app/main/routes.py', 8780, "rule.strategy == 'fixed'", 'D-09.4'),
    ('C-09', 'app/main/routes.py', 8783, "rule.strategy == 'weighted'", 'D-09.4'),
    ('C-09', 'app/models.py', 2537, 'weight = db.Column', 'C-09-缺口'),
    # ---- C-10：夹具幂等 + fixtures_manifest 台账
    ('C-10', 'test-reports-2026-10/harness/fixtures.py', 179, "internal_number=f'_hvRAW{i + 1}'", 'E-10.3'),
    ('C-10', 'test-reports-2026-10/harness/fixtures.py', 102, 'def _note', 'E-10.4'),
    ('C-10', 'test-reports-2026-10/harness/fixtures.py', 106, 'def manifest', 'E-10.4'),
    # ---- C-11：AC-15/16 现有载体
    ('C-11', 'test-reports-2026-10/harness/w2w3_probe.py', 429, "'N4'", 'F-11.AC15'),
    ('C-11', 'test-reports-2026-10/harness/w2w3_probe.py', 507, "'A1'", 'F-11.AC16'),
    # ---- C-11：AC-44/45/56 的行号载体（本任务新补判据的落点）
    ('C-11', 'app/services/mes_service.py', 1513, 'def shipment_allocated_product_ids', 'F-11.AC44'),
    ('C-11', 'app/services/mes_service.py', 1519, 'SHIPMENT_OPEN_STATUSES', 'F-11.AC44'),
    ('C-11', 'app/services/mes_service.py', 1542, 'def shipment_order_line_remaining_quantity', 'F-11.AC44'),
    ('C-11', 'app/services/mes_service.py', 1546, 'shipment_order_line_allocated_quantity', 'F-11.AC44'),
    ('C-11', 'app/services/mes_service.py', 1553, '使第二张草稿单「取不到该行」', 'F-11.AC44'),
    ('C-11', 'app/main/shipping.py', 120, "'/shipments/<int:id>/add_item'", 'F-11.AC44'),
    ('C-11', 'app/services/mes_service.py', 1643, 'finished_product.is_archived', 'F-11.AC45'),
    ('C-11', 'app/services/mes_service.py', 1644, '只拦显式 True', 'F-11.AC45'),
    ('C-11', 'app/services/mes_service.py', 1562, 'FinishedProduct.is_archived.is_(False)', 'F-11.AC45'),
    ('C-11', 'app/services/mes_service.py', 1563, 'FinishedProduct.is_archived.is_(None)', 'F-11.AC45'),
    ('C-11', 'app/services/mes_service.py', 1549, 'def shipment_candidate_stock', 'F-11.AC45'),
    ('C-11', 'app/services/mes_service.py', 1645, '已存档，不能发货', 'F-11.AC45'),
    ('C-11', 'app/main/routes.py', 6247, 'FinishedProduct.is_archived.is_(None)', 'F-11.AC56'),
    ('C-11', 'app/main/routes.py', 12122, 'is_archived=False', 'F-11.AC56'),
    ('C-11', 'app/main/routes.py', 4797, 'RawMaterial.is_archived.is_(False)', 'F-11.AC56'),
    ('C-11', 'app/main/routes.py', 4808, 'is_archived=False', 'F-11.AC56'),
    ('C-11', 'app/main/routes.py', 12065, 'is_archived=False', 'F-11.AC56'),
    ('C-11', 'app/main/routes.py', 12093, 'is_archived=False', 'F-11.AC56'),
    # ---- C-11：AC-49 通知零调用点（阴性事实的载体）
    ('C-11', 'app/services/notification_service.py', 484, 'def notify_inventory_warning', 'F-11.AC49'),
    # ---- C-06：权限断言面载体（既有命中非「权限断言」）
    ('C-06', 'app/permissions.py', 27, 'CAPABILITIES = {', 'G-06'),
]

# 逐条判据引用的证据文件必须存在（相对 ROOT）
EVIDENCE_FILES = [
    'test-reports-2026-10/harness/w2w3_probe.py',
    'test-reports-2026-10/harness/write_suite.py',
    'test-reports-2026-10/harness/uat_chains.py',
    'test-reports-2026-10/harness/fixtures.py',
    'test-reports-2026-10/16-W2W3修复验收判据.md',
    'test-reports-2026-10/17-W4W5修复验收判据.md',
    'test-reports-2026-10/27-38条对账与阶段A终态冻结.md',
    'test-reports-2026-10/phase1-snapshot/04-业务验收标准与端到端判据.md',
]


def read_lines(rel):
    path = os.path.join(ROOT, rel.replace('/', os.sep))
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read().splitlines()


def main():
    print('== cr_accept_criteria：判据载体存在性只读核验 ==')
    print('ROOT = %s' % ROOT)
    print('python = %s' % sys.version.replace('\n', ' '))
    print()

    ok, bad = 0, []
    cache = {}
    files_hit = {}

    # 0) 自指性排除域登记（并列运行期实际判定的排除名单）
    print('-- 自指性排除域（EXCLUDED_BASENAMES，%d 个）--' % len(EXCLUDED_BASENAMES))
    for name in sorted(EXCLUDED_BASENAMES):
        print('   excluded: %s' % name)
    print()

    for cid, rel, lineno, token, judge in CARRIERS:
        base = os.path.basename(rel)
        if base in EXCLUDED_BASENAMES:
            bad.append((cid, rel, lineno, token, 'EXCLUDED_BASENAMES 命中（自指风险）'))
            continue
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        if not os.path.isfile(path):
            bad.append((cid, rel, lineno, token, '文件不存在'))
            continue
        if rel not in cache:
            cache[rel] = read_lines(rel)
        lines = cache[rel]
        if lineno > len(lines):
            bad.append((cid, rel, lineno, token, '行号越界（文件仅 %d 行）' % len(lines)))
            continue
        line = lines[lineno - 1]
        if token in line:
            ok += 1
            files_hit.setdefault(rel, set()).add(cid)
            print('  [OK]   %-5s %-44s:%-6d %s' % (cid, rel, lineno, judge))
        else:
            bad.append((cid, rel, lineno, token, '第 %d 行不含 token；实际= %s'
                        % (lineno, line.strip()[:120])))
            print('  [FAIL] %-5s %-44s:%-6d %s' % (cid, rel, lineno, judge))

    print()
    print('-- 证据文件存在性（%d 个）--' % len(EVIDENCE_FILES))
    for rel in EVIDENCE_FILES:
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        exists = os.path.isfile(path)
        size = os.path.getsize(path) if exists else 0
        sha = ''
        if exists:
            with open(path, 'rb') as fh:
                sha = hashlib.sha256(fh.read()).hexdigest()[:16].upper()
        print('  [%s] %-70s %8d B  %s' % ('OK' if exists else 'FAIL', rel, size, sha))
        if not exists:
            bad.append(('evidence', rel, 0, '', '证据文件不存在'))

    print()
    print('-- 运行期实际命中的文件（A-74 登记）--')
    for rel in sorted(files_hit):
        print('   %-70s 判据数=%d' % (rel, len(files_hit[rel])))

    print()
    print('-- 生产面零漂移（只读复核）--')
    try:
        tree = subprocess.run(['git', 'rev-parse', 'HEAD:app'], cwd=ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        tree_sha = tree.stdout.decode('utf-8', 'replace').strip()
        print('   git rev-parse HEAD:app = %s' % tree_sha)
        print('   期望（t1 冻结）= c8f7d4abca1567b6219dbd77f22c82722f877ad6')
        freeze_ok = (tree_sha == 'c8f7d4abca1567b6219dbd77f22c82722f877ad6')
        print('   app/ tree 恒等 = %s' % ('YES' if freeze_ok else 'NO'))
        diff = subprocess.run(['git', 'diff', '--stat', '--', 'app'],
                              cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        diff_txt = diff.stdout.decode('utf-8', 'replace').strip()
        print('   git diff --stat -- app  工作区改动 = %s' % ('空' if not diff_txt else diff_txt[:200]))
    except Exception as exc:  # pragma: no cover
        print('   git 复核异常：%s' % exc)

    print()
    print('== 汇总：载体命中 %d 条 / 失败 %d 条 ==' % (ok, len(bad)))
    for item in bad:
        print('   FAIL %s %s:%s token=%r 原因=%s' % (item[0], item[1], item[2], item[3], item[4]))
    print('RESULT: %s' % ('OK' if not bad else 'FAILED'))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
