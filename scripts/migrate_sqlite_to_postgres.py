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

    for name in [m for m in list(sys.modules) if m == 'config' or m == 'app' or m.startswith('app.')]:
        del sys.modules[name]

    from sqlalchemy import create_engine, inspect, text, MetaData, Table
    from app import create_app, db

    app = create_app()
    src = create_engine(f'sqlite:///{sqlite_path.replace(os.sep, "/")}')
    with app.app_context():
        db.create_all()
        dest = db.engine
        src_insp = inspect(src)
        dst_insp = inspect(dest)
        src_tables = set(src_insp.get_table_names())
        dst_tables = set(dst_insp.get_table_names())
        # 按目标库 FK 拓扑尽量靠前：无依赖的先拷
        md = MetaData()
        md.reflect(bind=dest)
        ordered = list(md.sorted_tables)

        copied = 0
        skipped = []
        with src.connect() as sconn, dest.begin() as dconn:
            for table in ordered:
                name = table.name
                if name not in src_tables or name not in dst_tables:
                    continue
                src_cols = {c['name'] for c in src_insp.get_columns(name)}
                dst_cols = [c['name'] for c in dst_insp.get_columns(name)]
                common = [c for c in dst_cols if c in src_cols]
                if not common:
                    continue
                rows = sconn.execute(text(f'SELECT {", ".join(common)} FROM {name}')).mappings().all()
                if not rows:
                    continue
                dest_table = Table(name, md, autoload_with=dest)
                insert_cols = [c for c in common if c in dest_table.c]
                payload = [{k: row[k] for k in insert_cols} for row in rows]
                try:
                    dconn.execute(dest_table.insert(), payload)
                    copied += len(payload)
                    print(f'  {name}: {len(payload)} 行')
                except Exception as e:
                    skipped.append((name, str(e)))
                    print(f'  SKIP {name}: {e}')

        print(f'完成，约 {copied} 行。跳过 {len(skipped)} 张表。')
        if skipped:
            print('冲突表需要人工核对：')
            for n, err in skipped:
                print(f'  - {n}: {err}')


if __name__ == '__main__':
    main()
