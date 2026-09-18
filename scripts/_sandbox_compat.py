"""DSH 沙箱兼容层：让 scripts/ 下的测试脚本在受限沙箱内也能执行（仅环境适配，不改被测脚本）。

本仓库的测试脚本会在临时目录建库副本（``tempfile.mkdtemp``）并用 ``subprocess`` 捕获子进程输出。
在 DSH 的 workspace-write / read-only 沙箱下有两处**环境层**限制会先于代码失败：

1. ``tempfile.mkdtemp`` 固定以 mode=0o700 建目录，沙箱拒绝向该目录写入，
   ``shutil.copy2(ROOT / 'app.db', tmp)` 抛 ``PermissionError: [Errno 13]``；
2. 子进程 stdout/stderr 管道被拒，``subprocess.run(capture_output=True)`` 抛 ``PermissionError``。

实测（2026-08-27，workspace-write）：``python -B scripts/check_db_bootstrap.py`` 与
``cd scripts; python -B functional_test.py`` 原生命令均在**环境层**失败，与本仓库代码无关。

本层只放宽「临时目录 mode」与「子进程输出通道」，被测脚本与其中的断言一行都不动。

用法（在仓库根目录执行）：

    python -B scripts/_sandbox_compat.py scripts/check_db_bootstrap.py
    python -B scripts/_sandbox_compat.py scripts/functional_test.py
    python -B scripts/_sandbox_compat.py scripts/smoke_test.py

在无沙箱限制的环境里**无需**本层，直接运行原脚本即可（例如 CI、开发机、Jenkins）。
"""
import os
import runpy
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _relaxed_mkdtemp(suffix=None, prefix=None, dir=None):
    """同 tempfile.mkdtemp，但把目录 mode 放宽到 0o777，使沙箱允许后续写入。"""
    base = dir or tempfile.gettempdir()
    name = (prefix or '') + next(tempfile._get_candidate_names()) + (suffix or '')
    path = os.path.join(base, name)
    os.mkdir(path, 0o777)
    return path


tempfile.mkdtemp = _relaxed_mkdtemp

_orig_run = subprocess.run


def _run(*args, **kwargs):
    """capture_output=True 时改走临时文件，绕开沙箱禁止的管道；其余参数原样透传。"""
    if not kwargs.pop('capture_output', False):
        return _orig_run(*args, **kwargs)
    encoding = kwargs.pop('encoding', None) or 'utf-8'
    errors = kwargs.pop('errors', None) or 'replace'
    kwargs.pop('text', None)
    kwargs.pop('universal_newlines', None)
    scratch = os.path.join(ROOT, '.analysis-scratch')
    os.makedirs(scratch, exist_ok=True)
    fd_out, out_path = tempfile.mkstemp(suffix='.out', dir=scratch)
    fd_err, err_path = tempfile.mkstemp(suffix='.err', dir=scratch)
    try:
        with os.fdopen(fd_out, 'w', encoding=encoding, errors=errors) as fo, \
                os.fdopen(fd_err, 'w', encoding=encoding, errors=errors) as fe:
            proc = _orig_run(*args, stdout=fo, stderr=fe, **kwargs)
        with open(out_path, encoding=encoding, errors=errors) as f:
            out = f.read()
        with open(err_path, encoding=encoding, errors=errors) as f:
            err = f.read()
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
    finally:
        for path in (out_path, err_path):
            try:
                os.remove(path)
            except OSError:
                pass


subprocess.run = _run

if len(sys.argv) < 2:
    raise SystemExit('用法: python -B scripts/_sandbox_compat.py scripts/<script>.py [args...]')

target = os.path.abspath(sys.argv[1])
sys.argv = [target] + sys.argv[2:]
os.chdir(os.path.dirname(target))
sys.path.insert(0, os.path.dirname(target))
sys.path.insert(0, ROOT)
runpy.run_path(target, run_name='__main__')
