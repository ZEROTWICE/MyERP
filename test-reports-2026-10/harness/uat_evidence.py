"""生成 t5 证据包：真实库只读探针原生输出 + 计划性命令实跑证据（过程材料，t5 自用）。

用法（仓库根目录）：
    F:\\Miniconda\\envs\\wage\\python.exe -B test-reports-2026-10/harness/uat_evidence.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS_ROOT = os.path.dirname(HERE)
# 本任务的证据落点：evidence/uat/（不用 _env.EVIDENCE_DIR = evidence/harness/）
EVIDENCE_DIR = os.path.join(REPORTS_ROOT, 'evidence', 'uat')
sys.path.insert(0, HERE)
from _env import ensure_dir, run_child, sha256_file  # noqa: E402

PLANNED = [
    ['-c', "import ast,sys;ast.parse(open(r'"
     "test-reports-2026-10/harness/uat_chains.py',encoding='utf-8').read());print('AST OK')"],
    ['test-reports-2026-10/harness/_diag_quality_status.py'],
]


def main():
    ensure_dir(EVIDENCE_DIR)
    out = {'evidence_dir': EVIDENCE_DIR, 'runs': []}
    for args in PLANNED:
        label = 'ast_parse_uat_chains' if args[0] == '-c' else 'real_db_probe'
        res = run_child(args, label=label, timeout=600)
        out['runs'].append({k: res[k] for k in
                            ('argv_display', 'cwd', 'exit_code', 'evidence_level', 'duration_s',
                             'real_db_sha256_before', 'real_db_sha256_after', 'real_db_unchanged')})
        out['runs'][-1]['stdout'] = res['stdout'][-4000:]
        out['runs'][-1]['stderr'] = res['stderr'][-2000:]
        text = (f"argv: {res['argv_display']}\ncwd: {res['cwd']}\nexit_code: {res['exit_code']}\n"
                f"evidence_level: {res['evidence_level']}\n"
                f"real_db_sha256 before={res['real_db_sha256_before']}\n"
                f"real_db_sha256 after ={res['real_db_sha256_after']}\n"
                f"duration_s: {res['duration_s']}\n--- stdout ---\n{res['stdout']}\n"
                f"--- stderr ---\n{res['stderr']}\n")
        with open(os.path.join(EVIDENCE_DIR, f'{label}.txt'), 'w', encoding='utf-8',
                  newline='\n') as fh:
            fh.write(text)
    with open(os.path.join(EVIDENCE_DIR, 'planned_runs.json'), 'w', encoding='utf-8',
              newline='\n') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    files = {}
    for name in sorted(os.listdir(EVIDENCE_DIR)):
        p = os.path.join(EVIDENCE_DIR, name)
        if os.path.isfile(p) and name != 'artifact_hashes.json':
            files[name] = {'bytes': os.path.getsize(p), 'sha256': sha256_file(p)}
    with open(os.path.join(EVIDENCE_DIR, 'artifact_hashes.json'), 'w', encoding='utf-8',
              newline='\n') as fh:
        json.dump({'run_id': os.environ.get('UAT_RUN_ID', 't5-uat-final'), 'files': files},
                  fh, ensure_ascii=False, indent=2)
    print(json.dumps(files, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
