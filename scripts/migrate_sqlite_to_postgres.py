"""将 SQLite 业务库一次性迁到 PostgreSQL。

用法（在项目根、wage 环境）：
    F:\\Miniconda\\envs\\wage\\python.exe scripts/migrate_sqlite_to_postgres.py ^
        --sqlite app.db --postgres postgresql://myerp:myerp@127.0.0.1:5432/myerp

目标库会先 create_all（表结构以当前模型为准），再按表拷贝源库已有数据。
不覆盖目标库已有行（遇到主键冲突会跳过该表并打印警告）。
"""
import argparse
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description='SQLite -> PostgreSQL 一次性迁移')
    parser.add_argument('--sqlite', default=str(ROOT / 'app.db'))
    parser.add_argument('--postgres', required=True, help='postgresql://user:pass@host:5432/dbname')
    args = parser.parse_args()

    sqlite_path = os.path.abspath(args.sqlite)
    if not os.path.exists(sqlite_path):
        raise SystemExit(f'SQLite 文件不存在: {sqlite_path}')

    os.environ['DATABASE_URL'] = args.postgres
    os.environ['SITE_CODE'] = os.environ.get('SITE_CODE', '')
    # 拷贝由本脚本负责，别让 create_app() 里的空库自举同时再导一遍
    os.environ['SEED_SQLITE_PATH'] = os.path.join(str(ROOT), '.no-seed')

    for name in [m for m in list(sys.modules) if m == 'config' or m == 'app' or m.startswith('app.')]:
        del sys.modules[name]

    from app import create_app, db
    from app.db_bootstrap import copy_sqlite_into, reset_sequences

    app = create_app()
    with app.app_context():
        db.create_all()
        copied, skipped = copy_sqlite_into(db.engine, sqlite_path)
        reset_sequences(db.engine)

        print(f'完成，约 {copied} 行。跳过 {len(skipped)} 张表。')
        if skipped:
            print('冲突表需要人工核对：')
            for n, err in skipped:
                print(f'  - {n}: {err}')


if __name__ == '__main__':
    main()
