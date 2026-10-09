"""老库升级一次性脚本（B17-03）：启动自愈 + 把 alembic 版本固化为单 head。

为什么不是 ``flask db upgrade``：31 张表的 schema 事实来源是 ``db.create_all()`` +
``app/__init__.py`` 的 ``_ENSURED_COLUMNS``/``_ensure_schema()`` 启动自愈；迁移链虽已收敛为
单 head ``p1nonctarget``，但**全链重放不可行**（早期修订含 create→alter→drop 的临时表操作，
且 ``batch_alter_table`` 不接受 ``create_all()`` 建出的内联匿名 UNIQUE 约束 —— 见
``docs/交付说明-P0P1.md`` §6.2 第 9 项）。所以老库（缺表 / 缺列 / 版本号停在旧值）的升级路径
就是文档里那条「自愈 + stamp」，本脚本把它固化成一条命令：

    1) 备份目标库到 ``<db>.bak-<时间戳>``
    2) ``create_app()`` → ``_ensure_schema()``：缺表 ``create_all()``、缺列 ``ALTER TABLE ADD COLUMN``
    3) ``python -m flask db stamp <单 head>``（子进程；``DATABASE_URL`` 只指向目标库）
    4) 复查表/列计数、``alembic_version``、单 head

纪律：
  - 禁用 ``flask db migrate``（AGENTS.md）：脚本里的 alembic 命令只有 ``stamp``，不做任何 DDL 生成；
  - 目标库必须由 ``--db`` 显式给出，脚本不去猜 ``DATABASE_URL``；自愈后还要再断言一次
    ``SQLALCHEMY_DATABASE_URI`` 落在该路径上，防误写别的库（本项目 2026-08-27 已误写过一次真实 ``app.db``）；
  - 缺省 **dry-run**（纯只读打开），真正写入要加 ``--apply``；
  - 幂等：连跑两次，第二次 exit 0 且 schema 无变化。

用法（仓库根目录）：
    python -B scripts/upgrade_legacy_db.py --db /path/to/legacy.db            # 预演（只读）
    python -B scripts/upgrade_legacy_db.py --db /path/to/legacy.db --apply    # 执行
    python -B scripts/upgrade_legacy_db.py --db /path/to/legacy.db --apply --no-backup

退出码：0 = 成功（dry-run 通过 / apply 完成且复查一致）；1 = 任一步失败。
"""
import argparse
import datetime
import hashlib
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 固化：迁移链当前单 head（B17-00 契约 §2-B17-03）。漂移即报错，不静默跟着换目标。
HEAD = 'p1nonctarget'


def heads():
    """读迁移脚本目录的 head（不建应用、不碰库），与 check_migration_heads.py 同口径。"""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option('script_location', str(ROOT / 'migrations'))
    return ScriptDirectory.from_config(cfg).get_heads()


def read_db(path):
    """只读读数：表名 / 列数 / alembic_version。"""
    con = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
    try:
        tabs = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
        cols = sum(len(list(con.execute('pragma table_info("%s")' % t.replace('"', '""'))))
                   for t in tabs)
        ver = ([r[0] for r in con.execute('select version_num from alembic_version')]
               if 'alembic_version' in tabs else [])
    finally:
        con.close()
    return tabs, cols, ver


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def self_heal(db_path):
    """跑一次 create_app()，让启动自愈补齐缺表缺列（不再做其它事）。"""
    os.environ['DATABASE_URL'] = 'sqlite:///' + db_path.replace('\\', '/')
    for name in [m for m in list(sys.modules)
                 if m == 'config' or m == 'app' or m.startswith('app.')]:
        del sys.modules[name]
    sys.path.insert(0, str(ROOT))

    from app import create_app

    app = create_app()
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if os.path.normcase(db_path) not in os.path.normcase(uri.replace('/', os.sep)):
        raise RuntimeError('隔离失败：SQLALCHEMY_DATABASE_URI=%r 没指向目标库 %r，拒绝继续'
                           % (uri, db_path))


def stamp(db_path, head):
    """子进程执行 ``flask db stamp <head>``（DATABASE_URL 只指向目标库）。"""
    env = dict(os.environ,
               DATABASE_URL='sqlite:///' + db_path.replace('\\', '/'),
               FLASK_APP='main.py')
    cmd = [sys.executable, '-m', 'flask', 'db', 'stamp', head]
    print('RUN: DATABASE_URL=%s FLASK_APP=main.py %s'
          % (env['DATABASE_URL'], ' '.join(cmd[1:])))
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True)
    for line in (proc.stdout + proc.stderr).splitlines():
        print('  | %s' % line)
    return proc.returncode


def main():
    parser = argparse.ArgumentParser(
        description='老库升级一次性脚本：启动自愈 + flask db stamp 单 head（B17-03）')
    parser.add_argument('--db', required=True,
                        help='目标库路径（显式给出；脚本不会去猜 DATABASE_URL）')
    parser.add_argument('--apply', action='store_true',
                        help='真正写入（备份 + 自愈 + stamp）；缺省只做只读预演')
    parser.add_argument('--no-backup', action='store_true', help='跳过 .bak 备份（不推荐）')
    args = parser.parse_args()

    db = str(pathlib.Path(args.db).resolve())
    if not os.path.isfile(db):
        print('FAIL: 目标库不存在：%s' % db)
        return 1

    head_list = heads()
    if head_list != [HEAD]:
        print('FAIL: 迁移链 head=%s，脚本固化的目标是 %s；先跑 scripts/check_migration_heads.py'
              % (head_list, HEAD))
        return 1

    before_tabs, before_cols, before_ver = read_db(db)
    print('DB=%s' % db)
    print('TABLES_BEFORE=%d COLUMNS_BEFORE=%d ALEMBIC_VERSION_BEFORE=%s'
          % (len(before_tabs), before_cols, before_ver or '[]'))
    print('HEAD_TARGET=%s (链上唯一 head)' % HEAD)
    if db == str((ROOT / 'app.db').resolve()):
        print('注意：--db 指向仓库真实库 app.db；%s'
              % ('本次会真实写入（已加 --apply）' if args.apply else '本次只读预演，不会写入'))

    if not args.apply:
        print('DRY_RUN=1 未做任何写入（加 --apply 才会：备份 → 自愈 → stamp → 复查）')
        print('PLAN=1) backup %s.bak-<时间戳>  2) create_app() 自愈  3) python -m flask db stamp %s  4) 复查'
              % (db, HEAD))
        print('RESULT=OK (dry-run)')
        return 0

    if not args.no_backup:
        backup = '%s.bak-%s' % (db, datetime.datetime.now().strftime('%Y%m%d%H%M%S'))
        shutil.copy2(db, backup)
        print('BACKUP=%s sha256=%s' % (backup, sha256(backup)[:12]))

    print('STEP=1/3 启动自愈：create_app() → _ensure_schema()（create_all + _ENSURED_COLUMNS）')
    self_heal(db)
    mid_tabs, mid_cols, mid_ver = read_db(db)
    added_tables = sorted(set(mid_tabs) - set(before_tabs))
    print('STEP=1/3 自愈完成：TABLES=%d (+%d) COLUMNS=%d (+%d) ALEMBIC_VERSION=%s'
          % (len(mid_tabs), len(added_tables), mid_cols, mid_cols - before_cols,
             mid_ver or '[]'))
    if added_tables:
        print('  ADDED_TABLES=%s' % added_tables)

    print('STEP=2/3 固化版本号：flask db stamp %s' % HEAD)
    rc = stamp(db, HEAD)
    if rc != 0:
        print('FAIL: flask db stamp 退出码 %d' % rc)
        return 1

    print('STEP=3/3 复查')
    after_tabs, after_cols, after_ver = read_db(db)
    print('TABLES_AFTER=%d COLUMNS_AFTER=%d ALEMBIC_VERSION_AFTER=%s'
          % (len(after_tabs), after_cols, after_ver))
    print('HEADS=%s' % (head_list,))

    problems = []
    if after_ver != [HEAD]:
        problems.append('alembic_version=%s，期望 [%r]' % (after_ver, HEAD))
    if sorted(after_tabs) != sorted(mid_tabs) or after_cols != mid_cols:
        problems.append('stamp 之后 schema 变了（表 %d→%d / 列 %d→%d）'
                        % (len(mid_tabs), len(after_tabs), mid_cols, after_cols))
    if len(head_list) != 1:
        problems.append('head 数量 %d' % len(head_list))
    for problem in problems:
        print('FAIL: %s' % problem)
    if problems:
        print('RESULT=FAIL (%d 项)' % len(problems))
        return 1
    print('RESULT=OK 表 %d→%d、列 %d→%d、alembic_version %s→%s、单 head %s'
          % (len(before_tabs), len(after_tabs), before_cols, after_cols,
             before_ver or '[]', after_ver[0], HEAD))
    return 0


if __name__ == '__main__':
    sys.exit(main())
