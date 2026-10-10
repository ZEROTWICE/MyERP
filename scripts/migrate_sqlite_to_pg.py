"""SQLite -> PostgreSQL 16 一次性数据迁移（源库只读连接，绝不写 app.db）。

用法（仓库根目录、wage 环境，目标连接串走 DATABASE_URL 环境变量）：
    # 只打印迁移计划，不写入
    DATABASE_URL=postgresql+psycopg2://erpuser:erpuser@192.168.50.243:25432/erpdb \
        /opt/wage-venv/bin/python scripts/migrate_sqlite_to_pg.py --dry-run
    # 实际迁移（幂等：每次先 TRUNCATE 目标表再灌入，可重跑）
    DATABASE_URL=... /opt/wage-venv/bin/python scripts/migrate_sqlite_to_pg.py

设计要点：
- 源库以 file:...?mode=ro 的 URI 打开，SQLite 在连接层面拒绝一切写操作；
  脚本首尾各算一次 sha256，自证源库未被改动。
- 不调用 create_app()：其 _ensure_schema() 启动自愈与空库自举会写目标库，
  这里只导入 app.models 取 metadata（表结构以已建好的 PG 为准）。
- 类型转换全部交给 SQLAlchemy：按反射出的源表读（SQLite 的 0/1 布尔、
  DATETIME/DATE 字符串、JSON 文本自动转成 bool/datetime/dict 等 Python 类型），
  再按模型表写入（psycopg2 原生接受这些类型）。
- SQLite 不校验列类型，数值列可能存有字符串脏值（本库实测 3 处：空串与 'low'），
  PG 的 INTEGER/FLOAT 会直接拒收。规则：空串 -> NULL；可解析数字串 -> 数值；
  解析不了 -> NULL 并逐处打印告警供人工复核；修正后仍违反 NOT NULL 的行
  整行跳过并留档（不臆造哨兵值）。
- 写入在单事务内完成：一条 TRUNCATE 清空全部表（外键互连的表必须在同一条
  语句里清）+ 按 sorted_tables 外键拓扑顺序灌入，任何一步失败整体回滚；
  灌完后复用 app.db_bootstrap.reset_sequences 对齐序列——显式插入 id 不会
  推进 PG 的 serial/identity 序列，不 setval 的话新插入记录立刻主键冲突。
- alembic_version 不在模型 metadata 内，自然跳过（PG 侧也没有该表）。
- 迁移后自验：逐表行数比对、序列 last_value = max(id)+1 且 is_called=false、
  抽查 process_price / employee / user 各前 5 行逐字段一致。

退出码：0 = 迁移且校验全部通过；1 = 校验发现问题或迁移失败。
"""
import argparse
import hashlib
import os
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 抽查数据一致性的关键表（行数 Top 1 + 人事 + 登录账号）
SPOT_CHECK_TABLES = ('process_price', 'employee', 'user')


def sha256_file(path):
    """流式算文件指纹，用于迁移前后自证源库只读、未被改动。"""
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_numeric_string(value, column, table_name, row_id, coercions):
    """数值列里 SQLite 存的字符串脏值修正，返回应写入的值。

    空串语义是「未填写」-> NULL；'5' 这类可解析串转真数值；
    'low' 这类解析不了的一律 NULL 并记录告警，语义留给人工复核。
    """
    from sqlalchemy import Float, Numeric

    text = value.strip()
    if not text:
        coercions.append(f'{table_name}.{column.name} id={row_id}: 空串 -> NULL')
        return None
    try:
        return float(text) if isinstance(column.type, (Float, Numeric)) else int(text)
    except ValueError:
        coercions.append(
            f'{table_name}.{column.name} id={row_id}: 非数值字符串 {value!r} -> NULL')
        return None


def read_source_rows(src_engine, src_conn, tables):
    """按 tables（外键拓扑序）读出全部源数据，返回 (计划, 类型修正清单, 跳过行清单)。

    计划元素为 (模型表, 共同列名, 行字典列表)。必须经反射出的源表读：
    裸 SQL 拿不到列类型，DATETIME 会以字符串、BOOLEAN 会以 0/1 返回，
    插 PG 时类型对不上；反射后 SQLAlchemy 自动完成类型转换。

    空串修正后若撞上 NOT NULL 约束（SQLite 不把空串当 NULL，等于历史遗留
    绕过了约束），整行跳过并记录——不臆造哨兵值，留给人工复核。
    """
    from sqlalchemy import Float, Integer, MetaData, Numeric, Table, select

    src_meta = MetaData()
    plan = []
    coercions = []
    skips = []
    for table in tables:
        src_table = Table(table.name, src_meta, autoload_with=src_engine)
        common = [c.name for c in table.columns if c.name in src_table.c]
        numeric_cols = {c.name: c for c in table.columns
                        if c.name in common
                        and isinstance(c.type, (Integer, Float, Numeric))}
        notnull_cols = [c.name for c in table.columns
                        if c.name in common and not c.nullable]
        out_rows = []
        for r in src_conn.execute(
                select(*[src_table.c[c] for c in common])).mappings():
            row = dict(r)
            for name, col in numeric_cols.items():
                value = row.get(name)
                if isinstance(value, str):
                    row[name] = _coerce_numeric_string(
                        value, col, table.name, row.get('id'), coercions)
            violated = [n for n in notnull_cols if row.get(n) is None]
            if violated:
                skips.append(f'{table.name} id={row.get("id")}: '
                             f'NOT NULL 列 {violated} 为空，整行跳过')
                continue
            out_rows.append(row)
        plan.append((table, common, out_rows))
    return plan, coercions, skips


def verify_migration(plan, dst_engine):
    """迁移后校验：逐表行数、序列对齐、关键表前 5 行抽查。返回问题列表。"""
    from sqlalchemy import text

    problems = []
    count_ok = 0
    with dst_engine.connect() as conn:
        for table, _, rows in plan:
            dst_count = conn.execute(
                text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
            if dst_count != len(rows):
                problems.append(f'行数不一致 {table.name}: 源 {len(rows)} / 目标 {dst_count}')
            else:
                count_ok += 1

        seq_ok = 0
        for table, _, _ in plan:
            for col in table.primary_key.columns:
                seq = conn.execute(
                    text('SELECT pg_get_serial_sequence(:t, :c)'),
                    {'t': f'"{table.name}"', 'c': col.name}).scalar()
                if not seq:
                    continue
                last_value, is_called = conn.execute(
                    text(f'SELECT last_value, is_called FROM {seq}')).one()
                max_id = conn.execute(
                    text(f'SELECT COALESCE(MAX("{col.name}"), 0) FROM "{table.name}"')).scalar()
                # reset_sequences 用 setval(seq, max+1, false)，故下一号恰为 max+1
                if last_value != max_id + 1 or is_called:
                    problems.append(
                        f'序列未对齐 {table.name}.{col.name}: last_value={last_value} '
                        f'is_called={is_called}，期望 {max_id + 1}/false')
                else:
                    seq_ok += 1

        for table, common, rows in plan:
            if table.name not in SPOT_CHECK_TABLES:
                continue
            pk = list(table.primary_key.columns)[0].name
            src_top = sorted(rows, key=lambda r: r[pk])[:5]
            dst_top = [dict(r) for r in conn.execute(
                table.select().order_by(table.c[pk]).limit(5)).mappings().all()]
            diffs = ([f'行数 源 {len(src_top)} / 目标 {len(dst_top)}']
                     if len(src_top) != len(dst_top) else [])
            for i, (s, d) in enumerate(zip(src_top, dst_top)):
                for key in common:
                    if s.get(key) != d.get(key):
                        diffs.append(f'第{i + 1}行[{key}]: 源={s.get(key)!r} 目标={d.get(key)!r}')
            if diffs:
                problems.append(f'抽查不一致 {table.name}: ' + '; '.join(diffs))
            else:
                ids = [r[pk] for r in src_top]
                print(f'  抽查 {table.name}: 前 {len(ids)} 行（{pk}={ids}）逐字段一致')

        print(f'行数比对 {count_ok}/{len(plan)} 张表一致，序列对齐 {seq_ok} 个')
    return problems


def main():
    parser = argparse.ArgumentParser(
        description='SQLite -> PostgreSQL 16 一次性数据迁移（源库只读，TRUNCATE 后重灌，可重跑）')
    parser.add_argument('--sqlite', default=str(ROOT / 'app.db'),
                        help='源 SQLite 库路径（默认仓库根 app.db，以只读方式打开）')
    parser.add_argument('--database-url', default=None,
                        help='目标 PostgreSQL 连接串（默认取环境变量 DATABASE_URL）')
    parser.add_argument('--dry-run', action='store_true',
                        help='只打印迁移计划，不写入目标库')
    args = parser.parse_args()

    sqlite_path = os.path.abspath(args.sqlite)
    if not os.path.isfile(sqlite_path):
        raise SystemExit(f'源库不存在: {sqlite_path}')
    database_url = args.database_url or os.environ.get('DATABASE_URL')
    if not database_url:
        raise SystemExit('缺少目标库连接串：请设置 DATABASE_URL 或传 --database-url')
    if not database_url.startswith('postgresql'):
        raise SystemExit('目标必须是 PostgreSQL 连接串（postgresql+psycopg2://...）')

    # 只导入 models 拿 metadata；不 create_app()，避免启动自愈/空库自举写目标库
    from app import db
    import app.models  # noqa: F401
    tables = db.metadata.sorted_tables

    from sqlalchemy import create_engine, inspect, text

    digest_before = sha256_file(sqlite_path)
    # file:...?mode=ro —— SQLite 连接级只读，任何写操作在驱动层直接报错
    src_engine = create_engine(f'sqlite:///file:{sqlite_path}?mode=ro&uri=true')
    dst_engine = create_engine(database_url)
    return_code = 0
    try:
        src_table_names = set(inspect(src_engine).get_table_names())
        missing = [t.name for t in tables if t.name not in src_table_names]
        if missing:
            raise SystemExit(f'源库缺少模型表: {missing}')
        with src_engine.connect() as src_conn:
            plan, coercions, skips = read_source_rows(src_engine, src_conn, tables)
        if coercions:
            print(f'类型修正 {len(coercions)} 处（SQLite 宽松类型遗留，PG 严格类型拒收）:')
            for line in coercions:
                print(f'  ~ {line}')
        if skips:
            print(f'跳过 {len(skips)} 行（修正后仍违反 NOT NULL，无法保真迁移，见末尾汇总）:')
            for line in skips:
                print(f'  ✗ {line}')
        total = sum(len(rows) for _, _, rows in plan)
        nonempty = [(t.name, len(rows)) for t, _, rows in plan if rows]

        if args.dry_run:
            print(f'[dry-run] 源库 {sqlite_path}（sha256 {digest_before[:16]}…）')
            print(f'[dry-run] 目标 {database_url.rsplit("@", 1)[-1]}：'
                  f'{len(tables)} 张表 TRUNCATE 后重灌，合计 {total} 行')
            for name, count in nonempty:
                print(f'[dry-run]   {name}: {count} 行')
            print('[dry-run] alembic_version 不在模型 metadata 内，自动跳过')
        else:
            print(f'源库 sha256（迁移前）: {digest_before}')
            print(f'开始迁移：TRUNCATE {len(tables)} 张表后按外键拓扑灌入 {total} 行...')
            with dst_engine.begin() as conn:
                # 外键互连的表必须放进同一条 TRUNCATE；RESTART IDENTITY 先归零序列，
                # 灌完数据后再统一 setval 到 max(id)+1
                names = ', '.join(f'"{t.name}"' for t in tables)
                conn.execute(text(f'TRUNCATE TABLE {names} RESTART IDENTITY'))
                for table, common, rows in plan:
                    if rows:
                        conn.execute(table.insert(), rows)
                        print(f'  已灌入 {table.name}: {len(rows)} 行')
            # 复用空库自举的序列重置（含 user 保留字的引号处理），单一实现
            from app.db_bootstrap import reset_sequences
            reset_sequences(dst_engine)
            print('序列已重置（setval max(id)+1），开始校验...')
            problems = verify_migration(plan, dst_engine)
            if problems:
                return_code = 1
                print(f'校验发现 {len(problems)} 个问题：')
                for problem in problems:
                    print(f'  ✗ {problem}')
            else:
                skipped_note = f'，跳过 {len(skips)} 行（见上方清单）' if skips else ''
                print(f'校验通过：{len(tables)} 张表行数一致、序列已对齐、'
                      f'抽查 {", ".join(SPOT_CHECK_TABLES)} 前 5 行一致{skipped_note}。')
    except Exception:
        return_code = 1
        traceback.print_exc()
    finally:
        src_engine.dispose()
        dst_engine.dispose()
        digest_after = sha256_file(sqlite_path)
        if digest_after != digest_before:
            return_code = 1
            print(f'✗ 源库 sha256 发生变化: {digest_before} -> {digest_after}')
        else:
            print(f'源库 sha256 迁移前后一致（只读未被改动）: {digest_after}')
    return return_code


if __name__ == '__main__':
    sys.exit(main())
