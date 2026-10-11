"""31 张 create_all 表 vs 迁移 create_table 对拍（B17-05，前置 B17-17）。

两个口径，都要看：

字面口径
    只认迁移里**字面写出表名**的 ``op.create_table('name', ...)``。读数冻结在
    B17-00 契约（§2-B17-05 / A-12）：迁移文件 35 / 含 create_table 14 文件 /
    无守卫 11 / c02604883c72 24 处 / 字面建表名去重 49 / 差集 31。

幂等口径
    再去掉「存在性判断 + 变量表名」的幂等迁移已覆盖的表
    （``p0p2messtables_add_create_all_tables.py`` 的 ``_CREATION_ORDER`` 循环），
    差集必须为 0 —— 这 31 张表确实有迁移通道，只是静态文本看不出来。

口径来源：``create_all`` 的 metadata 共 74 张业务表（无 ``alembic_version``），真实库
75 张 = 74 + ``alembic_version``，所以「含该表口径」的差集是 32、不含是 31（A-12）。

**为什么不做全链重放**：迁移链里的早期修订含 create→alter→drop 的临时表操作，在空库上
不可重放（B10-01-边界 / 81- §批次17 明示不得把「全链重放」当承诺）。本脚本只做静态对拍
+ 单头检查，不碰任何库。

安全：不调用 ``create_app()``（那会触发 ``_ensure_schema()`` 自愈写库）；只导入
``app.models`` 取 metadata 定义，并把 ``DATABASE_URL`` 指到一个**永不创建**的临时路径，
结束时断言该文件不存在 —— 作为「脚本零写库」的证据。

用法（仓库根目录）：
    python -B scripts/check_table_parity.py
    python -B scripts/check_table_parity.py --quiet

退出码：全部读数与冻结基线一致且幂等口径差集为 0 → 0；否则 1。
"""
import argparse
import ast
import os
import pathlib
import re
import sys
import tempfile

from sqlalchemy.dialects import postgresql, sqlite

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSIONS = ROOT / 'migrations' / 'versions'
IDEMPOTENT = VERSIONS / 'p0p2messtables_add_create_all_tables.py'


class _MockEngine:
    """只给 `_build_alter_add_column()` 用：它只需要 `engine.dialect`。

    自带一个最小 dialect 垫片，避免为「离线拼 SQL」真的去 create_engine
    （那会连带 mock 策略弃用告警与连接对象，本检查一条都不需要）。
    """

    def __init__(self, name):
        base = postgresql.dialect() if name == 'postgresql' else sqlite.dialect()
        self.dialect = base


def _mock_engine(name):
    return _MockEngine(name)

# 冻结基线（B17-00 契约冻结 §2-B17-05 / A-12），现场重测于批次17。
FROZEN = {
    'migration_files': 35,
    'files_with_create_table': 14,
    'files_without_guard': 11,
    'busiest_file': ('c02604883c72', 24),
    'metadata_tables': 74,
    'literal_names': 49,
    'literal_diff': 31,
    'migration_only_extras': 6,
}

# 迁移里有、create_all metadata 没有的名字，按来源分类；不在分类里的一律报红。
def _classify_extra(name):
    if name.startswith('_alembic_tmp_'):
        return 'batch_alter_table 事务临时表'
    if name == 'sqlite_sequence':
        return 'SQLite 自增序列内建表'
    if name in ('delivery_schedules', 'sales_order_delivery_batches'):
        # B10-02 口径允许「清理或显式登记保留」：这两个名字只出现在 011e395c1aa4 /
        # a3f28e475446 / 83bfde43921e 的 create/alter/drop 里，app/models.py 没有对应模型，
        # create_all 的 74 张表里没有它们，实测真实库（75 张）同样没有 ⇒ 登记保留原迁移，
        # 不改写任何既有 revision（migrations/ 零改动）。
        return '历史碎片（无模型、create_all 与真实库均无此表，登记保留）'
    return None


RX_CALL = re.compile(r'op\.create_table\(')
RX_LITERAL = re.compile(r"""op\.create_table\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]""")


def scan_migrations():
    """逐文件统计 create_table 次数与守卫情况。"""
    files = sorted(VERSIONS.glob('*.py'))
    rows = []
    for path in files:
        src = path.read_text(encoding='utf-8')
        tree = ast.parse(src)
        calls, guards = [], []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'create_table'):
                calls.append(node.lineno)
            if isinstance(node, ast.If):
                test = ast.dump(node.test)
                if 'has_table' in test or 'get_table_names' in test:
                    lines = [n.lineno for st in node.body
                             for n in ast.walk(st) if hasattr(n, 'lineno')]
                    if lines:
                        guards.append((min(lines), max(lines)))
        guarded = [ln for ln in calls if any(lo <= ln <= hi for lo, hi in guards)]
        rows.append({
            'name': path.name,
            # calls 走文本口径（口径与 B17-00 契约一致：p0p2messtables 的 docstring 里
            # 也有一处 op.create_table( 文本，故 56 次）；守卫分类走 AST 口径。
            'calls': len(RX_CALL.findall(src)),
            'ast_calls': len(calls),
            'literal': RX_LITERAL.findall(src),
            'unguarded': len(calls) - len(guarded),
        })
    return files, rows


def idempotent_channel():
    """读幂等迁移的 _CREATION_ORDER，并核对它真的一表一守卫地建表。"""
    src = IDEMPOTENT.read_text(encoding='utf-8')
    tree = ast.parse(src)
    order, tables, problems = None, None, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == '_CREATION_ORDER':
                    order = [e.value for e in node.value.elts
                             if isinstance(e, ast.Constant)]
                elif target.id == '_TABLES':
                    tables = [k.value for k in node.value.keys
                              if isinstance(k, ast.Constant)]
    if not order:
        return None, ['幂等迁移里找不到 _CREATION_ORDER']
    if tables is None:
        problems.append('幂等迁移里找不到 _TABLES')
    elif sorted(tables) != sorted(order):
        problems.append('_TABLES 与 _CREATION_ORDER 名单不一致')

    def find(name):
        return next((n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == name), None)

    ensure = find('_ensure_table')
    if ensure is None:
        problems.append('幂等迁移里找不到 _ensure_table()')
    else:
        guarded = any(isinstance(n, ast.If) and 'get_table_names' in ast.dump(n.test)
                      for n in ast.walk(ensure))
        if not guarded:
            problems.append('_ensure_table() 没有存在性判断（不是幂等建表）')
    upgrade = find('upgrade')
    if upgrade is None or '_CREATION_ORDER' not in ast.dump(upgrade):
        problems.append('upgrade() 没有按 _CREATION_ORDER 循环建表')
    return order, problems


def read_metadata():
    """取 create_all 的 metadata 表名；不建应用、不碰库。"""
    guard = os.path.join(tempfile.mkdtemp(prefix='b17_parity_'), 'never_created.db')
    os.environ['DATABASE_URL'] = 'sqlite:///' + guard.replace('\\', '/')
    sys.path.insert(0, str(ROOT))
    from app import _ENSURED_COLUMNS, db
    from app import models  # noqa: F401  导入模型即注册 metadata

    names = sorted(db.metadata.tables)
    bad = [(t, c) for t, cols in _ENSURED_COLUMNS.items() for c, _ in cols
           if t not in db.metadata.tables or c not in db.metadata.tables[t].columns]
    return names, len(_ENSURED_COLUMNS), sum(len(v) for v in _ENSURED_COLUMNS.values()), bad, guard


def heads():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option('script_location', str(ROOT / 'migrations'))
    return ScriptDirectory.from_config(cfg).get_heads()


def check_alter_quoting():
    """B18 回归：_ensure_schema() 的补列 SQL 必须给标识符加方言引号。

    病史（2026-10-11 生产库只读探针实测）：`user` 是 PG 保留字，裸写成
    ``ALTER TABLE user ADD COLUMN …`` 会抛 ``psycopg2.errors.SyntaxError``，
    而该异常在 `_ensure_schema()` 里被 except 吞成一行日志、不阻断启动
    ⇒ 生产库列永远补不上，而 SQLite 上永远测不出来（安全区不报错的缺陷）。

    判据（正则，不实际建应用、不碰库）：`_ensure_schema()` 函数体里出现的每条
    ``ALTER TABLE`` 都必须写成 ``ALTER TABLE "``（带引号）。
    """
    src = (ROOT / 'app' / '__init__.py').read_text(encoding='utf-8')
    return scan_alter_quoting(src)


def scan_alter_quoting(src):
    """扫 ``app/__init__.py`` 两个函数的源码文本，判补列 SQL 的标识符有没有加引号。

    覆盖两条路径：① 构造点 ``_build_alter_add_column()`` 必须写出带引号的模板；
    ② 自愈流程 ``_ensure_schema()`` 自己不许再出现任何裸 ``ALTER TABLE`` 字面量
    （绕开构造函数的写法要在这里被拦下）。只看字符串字面量 ⇒ 注释里的示例串不误判。
    """
    tree = ast.parse(src)
    targets = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            targets[node.name] = node
    if ('_build_alter_add_column' not in targets
            or '_ensure_schema' not in targets):
        return ('找不到 _build_alter_add_column()/_ensure_schema()'
                '（B18 引号回归检查无法执行）')

    rx_bad = re.compile(r'ALTER TABLE (?!")')
    # 模板里表名/列名必须是**未被手写引号包裹**的占位符：quote() 自带引号，
    # 手写成 "\"{tbl}\"" 会拼出 ""user""（零长度定界标识符），2026-10-11 实测踩过。
    rx_placeholder = re.compile(r'ALTER TABLE \{')
    problems = []
    builder = targets['_build_alter_add_column']
    builder_strs = [n.value for n in ast.walk(builder)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    if not any('ADD COLUMN' in s and rx_placeholder.search(s) for s in builder_strs):
        problems.append('_build_alter_add_column() 未写出占位符模板 '
                        '（应形如 ALTER TABLE {tbl} ADD COLUMN {col} …）')

    # 粒度取「函数体内是否调用 quote()」：够挡住整个写法（含本次修复前的 f-string
    # 版本），但挡不住「只给表名加引号、漏了列名」这种半吊子改动。
    # ponytail: 不做数据流追踪，真要覆盖半吊子写法就升级成模板变量逐一对账。
    if not any(isinstance(n, ast.Attribute) and n.attr == 'quote'
               for n in ast.walk(builder)):
        problems.append('_build_alter_add_column() 未调用 '
                        'identifier_preparer.quote() 给表名/列名加引号')

    for n in ast.walk(targets['_ensure_schema']):
        if not isinstance(n, ast.Constant) or not isinstance(n.value, str):
            continue
        if rx_bad.search(n.value):
            problems.append('_ensure_schema() 里有未加引号的 ALTER TABLE 字面量：%r'
                            % n.value[:80])
    if problems:
        return '；'.join(problems) + '（PG 保留字如 user 会 SyntaxError 且被吞）'
    return None


def check_ensured_ddl():
    """B18 回归：`_ENSURED_COLUMNS` 每条都必须在 SQLite/PG 两种方言下生成合法补列 DDL。

    病史（2026-10-11 一次性 PG 测试库实测）：
    `BOOLEAN DEFAULT 0` 在 PG 上抛 DatatypeMismatch（boolean vs integer 不同型），
    而异常在 `_ensure_schema()` 里被 except 吞成一行日志 ⇒ 生产库列补不上，
    SQLite 上永远测不出来。这里用 `_build_alter_add_column()` 按方言实算 DDL，只读。
    """
    sys.path.insert(0, str(ROOT))
    try:
        from app import _ENSURED_COLUMNS, _build_alter_add_column
    except Exception as e:  # 导入失败要报出来，不许静默跳过
        return '无法导入 _ENSURED_COLUMNS/_build_alter_add_column：%r' % (e,)

    problems = []
    for dialect in ('sqlite', 'postgresql'):
        engine = _mock_engine(dialect)
        # 布尔默认值两种方言写法不同：PG 强类型只认 FALSE/TRUE，SQLite 只认 0/1。
        rx_ok = re.compile(r' BOOLEAN DEFAULT (0|1)$') if dialect == 'sqlite' \
            else re.compile(r' BOOLEAN DEFAULT (FALSE|TRUE)$')
        for table, columns in sorted(_ENSURED_COLUMNS.items()):
            for name, coltype in columns:
                ddl = _build_alter_add_column(engine, table, name, coltype, dialect)
                if ' BOOLEAN DEFAULT ' in ddl and not rx_ok.search(ddl):
                    problems.append('%s：%s（该方言不接受这个默认值写法）' % (dialect, ddl))
                    break
            if problems:
                break
        if problems:
            break
    if problems:
        return problems[0]
    return None


def main():
    parser = argparse.ArgumentParser(description='31 张 create_all 表 vs 迁移 create_table 对拍（B17-05）')
    parser.add_argument('--quiet', action='store_true', help='只打印结论行')
    args = parser.parse_args()

    def say(line):
        if not args.quiet or line.startswith(('RESULT', 'FAIL')):
            print(line)

    files, rows = scan_migrations()
    literal_names = sorted({n for row in rows for n in row['literal']})
    create_table_files = [r for r in rows if r['calls']]
    unguarded = [r['name'] for r in create_table_files if r['unguarded'] == r['ast_calls']]
    busiest = max(create_table_files, key=lambda r: r['calls'])
    meta, ensured_tables, ensured_cols, ensured_bad, guard = read_metadata()
    order, idem_problems = idempotent_channel()
    head_list = heads()

    literal_in_meta = sorted(set(literal_names) & set(meta))
    extras = sorted(set(literal_names) - set(meta))
    literal_diff = sorted(set(meta) - set(literal_names))
    covered = set(literal_names) | set(order or [])
    idem_diff = sorted(set(meta) - covered)
    unknown_extras = [n for n in extras if _classify_extra(n) is None]
    # 真实库口径：75 = 74 业务表 + alembic_version（A-12）
    db_tables = len(meta) + 1
    diff_with_alembic = db_tables - len(literal_in_meta)

    say('MIGRATION_FILES=%d' % len(files))
    say('FILES_WITH_CREATE_TABLE=%d' % len(create_table_files))
    say('UNGUARDED_FILES=%d  %s' % (len(unguarded), unguarded))
    say('CREATE_TABLE_CALLS=%d  (最密文件 %s… %d 处)'
        % (sum(r['calls'] for r in rows), busiest['name'][:12], busiest['calls']))
    say('CREATE_TABLE_LITERAL_NAMES=%d' % len(literal_names))
    say('CREATE_ALL_TABLES=%d  (不含 alembic_version；真实库口径 %d)' % (len(meta), db_tables))
    say('LITERAL_DIFF=%d  (含 alembic_version 口径 = %d)' % (len(literal_diff), diff_with_alembic))
    say('IDEMPOTENT_COVERED=%d  (p0p2messtables._CREATION_ORDER)  IDEMPOTENT_DIFF=%d'
        % (len(order or []), len(idem_diff)))
    say('MIGRATION_ONLY_EXTRAS=%d  UNKNOWN_EXTRAS=%d'
        % (len(extras), len(unknown_extras)))
    for name in extras:
        say('  extra  %-34s %s' % (name, _classify_extra(name) or '未登记（报红）'))
    say('ENSURED_COLUMNS=%d 张表 / %d 列  INCONSISTENT=%d'
        % (ensured_tables, ensured_cols, len(ensured_bad)))
    say('HEADS=%s' % (head_list,))

    problems = []
    if len(files) != FROZEN['migration_files']:
        problems.append('迁移文件 %d，冻结基线 %d' % (len(files), FROZEN['migration_files']))
    if len(create_table_files) != FROZEN['files_with_create_table']:
        problems.append('含 create_table 文件 %d，冻结基线 %d'
                        % (len(create_table_files), FROZEN['files_with_create_table']))
    if len(unguarded) != FROZEN['files_without_guard']:
        problems.append('无守卫 create_table 文件 %d，冻结基线 %d'
                        % (len(unguarded), FROZEN['files_without_guard']))
    if busiest['calls'] != FROZEN['busiest_file'][1] or not busiest['name'].startswith(FROZEN['busiest_file'][0]):
        problems.append('最密文件读数 %s=%d，冻结基线 %s=%d'
                        % (busiest['name'], busiest['calls'], *FROZEN['busiest_file']))
    if len(meta) != FROZEN['metadata_tables']:
        problems.append('create_all 表 %d，冻结基线 %d' % (len(meta), FROZEN['metadata_tables']))
    if len(literal_names) != FROZEN['literal_names']:
        problems.append('字面建表名 %d，冻结基线 %d' % (len(literal_names), FROZEN['literal_names']))
    if len(literal_diff) != FROZEN['literal_diff']:
        problems.append('字面口径差集 %d，冻结基线 %d（B17-00 契约 §2-B17-05，如属实需同步改契约）'
                        % (len(literal_diff), FROZEN['literal_diff']))
    if diff_with_alembic != FROZEN['literal_diff'] + 1:
        problems.append('含 alembic_version 口径差集 %d，期望 %d（A-12）'
                        % (diff_with_alembic, FROZEN['literal_diff'] + 1))
    if idem_diff:
        problems.append('幂等口径差集 %d 张表没有被任何迁移覆盖：%s'
                        % (len(idem_diff), idem_diff))
    problems.extend(idem_problems)
    if len(extras) != FROZEN['migration_only_extras']:
        problems.append('迁移多出的名字 %d 个，冻结基线 %d' % (len(extras), FROZEN['migration_only_extras']))
    if unknown_extras:
        problems.append('未登记来源的迁移多出名字 %d 个：%s' % (len(unknown_extras), unknown_extras))
    if ensured_bad:
        problems.append('_ENSURED_COLUMNS 与 metadata 不一致 %d 处：%s' % (len(ensured_bad), ensured_bad))
    quoting_problem = check_alter_quoting()
    if quoting_problem:
        problems.append(quoting_problem)
    ddl_problem = check_ensured_ddl()
    if ddl_problem:
        problems.append('_ENSURED_COLUMNS DDL 方言不合规：%s' % ddl_problem)
    if len(head_list) != 1:
        problems.append('head 数量 %d：%s' % (len(head_list), head_list))
    if os.path.exists(guard):
        problems.append('脚本写了一个库（%s 被创建）——本脚本必须零写库' % guard)

    if not args.quiet:
        print('LITERAL_DIFF_TABLES=%s' % (literal_diff,))
        print('  （以上 31 张由幂等迁移 p0p2messtables 覆盖，故幂等口径差集为 %d）' % len(idem_diff))
    if problems:
        for p in problems:
            print('FAIL: %s' % p)
        print('RESULT=FAIL (%d 项)' % len(problems))
        return 1
    print('RESULT=OK 字面口径差集 %d（A-12）/ 幂等口径差集 0 / 单头 %s / 零写库'
          % (len(literal_diff), head_list[0]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
