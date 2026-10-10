"""空库自举：目标库里一个账号都没有时，从 SQLite 种子库整体导入一次。

`scripts/migrate_sqlite_to_postgres.py` 复用这里的 copy_sqlite_into/reset_sequences，
拷贝顺序与序列重置只有一份实现。
"""
import os

from sqlalchemy import MetaData, Table, create_engine, inspect, select, text

# 多 worker 同时启动时只让一个进程执行导入，键值固定即可
_ADVISORY_LOCK_KEY = 8723011


def copy_sqlite_into(dest_engine, sqlite_path):
    """按目标库外键拓扑把 SQLite 数据拷进 dest_engine，返回 (行数, [(表名, 错误)])。"""
    src = create_engine('sqlite:///' + os.path.abspath(sqlite_path).replace(os.sep, '/'))
    try:
        src_tables = set(inspect(src).get_table_names())
        dst_tables = set(inspect(dest_engine).get_table_names())

        md = MetaData()
        md.reflect(bind=dest_engine)
        src_md = MetaData()

        copied = 0
        skipped = []
        with src.connect() as sconn, dest_engine.begin() as dconn:
            for table in md.sorted_tables:
                if table.name not in src_tables or table.name not in dst_tables:
                    continue
                # 必须按反射出的源表读，裸 SQL 拿不到列类型，
                # DATETIME/DATE 会以字符串返回，插入目标库时报 TypeError
                src_table = Table(table.name, src_md, autoload_with=src)
                common = [c.name for c in table.columns if c.name in src_table.c]
                if not common:
                    continue
                rows = sconn.execute(
                    select(*[src_table.c[c] for c in common])
                ).mappings().all()
                if not rows:
                    continue
                # 每张表一个 SAVEPOINT：Postgres 上一次报错会让整个事务进入 aborted，
                # 不隔离的话第一张冲突表会连带后面所有表一起失败。
                try:
                    with dconn.begin_nested():
                        dconn.execute(table.insert(), [{k: r[k] for k in common} for r in rows])
                    copied += len(rows)
                except Exception as e:
                    skipped.append((table.name, str(e)))
        return copied, skipped
    finally:
        src.dispose()


def reset_sequences(dest_engine):
    """显式插入 id 不会推进 Postgres 的 serial 序列，不重置则新建记录立刻主键冲突。"""
    if dest_engine.dialect.name != 'postgresql':
        return
    md = MetaData()
    md.reflect(bind=dest_engine)
    with dest_engine.begin() as conn:
        for table in md.sorted_tables:
            for col in table.primary_key.columns:
                # 表名可能是保留字（本项目的 user 表），必须带引号交给 pg_get_serial_sequence
                seq = conn.execute(
                    text('SELECT pg_get_serial_sequence(:t, :c)'),
                    {'t': f'"{table.name}"', 'c': col.name},
                ).scalar()
                if not seq:
                    continue
                conn.execute(
                    text(f'SELECT setval(:s, COALESCE((SELECT MAX("{col.name}") '
                         f'FROM "{table.name}"), 0) + 1, false)'),
                    {'s': seq},
                )


def seed_path_for(app):
    """种子库路径。不挂载/不存在就等于关掉自举，不需要额外开关。"""
    return os.environ.get('SEED_SQLITE_PATH') or os.path.join(
        os.path.dirname(app.root_path), 'seed.db'
    )


def bootstrap_if_empty(app):
    """首次启动初始化：库里没有任何账号时执行，之后每次启动都是空操作。

    两条路径（按优先级）：
    1. 种子库文件存在（SEED_SQLITE_PATH 或 <repo 根>/seed.db）⇒ 整体导入
    2. 种子库不存在但 INIT_ADMIN_PASSWORD 已设置 ⇒ 创建一个 admin 账号，
       用户名取 INIT_ADMIN_USERNAME（默认 'admin'），密码取 INIT_ADMIN_PASSWORD。
       用于全新部署（如云服务器空 PG），不需要上传种子数据。
    两者都不满足 ⇒ 空操作（应用能启动但无账号可登录，日志里有告警）。
    """
    from app import db
    from app.models import User

    seed_path = seed_path_for(app)
    # 宿主机路径不存在时 Docker 会把挂载点建成目录，所以必须判 isfile
    if not os.path.isfile(seed_path):
        _init_admin_if_empty(app, User)
        return

    try:
        if db.session.query(User.id).first() is not None:
            return

        engine = db.engine
        if engine.dialect.name != 'postgresql':
            _import_seed(app, engine, seed_path)
            return

        with engine.connect() as conn:
            if not conn.execute(
                text('SELECT pg_try_advisory_lock(:k)'), {'k': _ADVISORY_LOCK_KEY}
            ).scalar():
                app.logger.info('初始化导入正由另一个进程执行，本进程跳过')
                return
            try:
                # 抢到锁期间别的进程可能已经导完，锁内再确认一次
                if conn.execute(text('SELECT 1 FROM "user" LIMIT 1')).first() is None:
                    _import_seed(app, engine, seed_path)
            finally:
                conn.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': _ADVISORY_LOCK_KEY})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'初始化导入失败: {e}')


def _import_seed(app, engine, seed_path):
    app.logger.warning(f'目标库为空，开始从种子库初始化：{seed_path}')
    copied, skipped = copy_sqlite_into(engine, seed_path)
    reset_sequences(engine)
    app.logger.warning(f'初始化导入完成，共 {copied} 行；跳过 {len(skipped)} 张表')
    for name, err in skipped:
        app.logger.error(f'初始化导入跳过表 {name}: {err}')


def _init_admin_if_empty(app, User):
    """种子库不存在时的回退：用 INIT_ADMIN_PASSWORD 创建一个 admin 账号。

    用于全新部署（如云服务器空 PG），不需要上传种子数据。
    两个环境变量：
      INIT_ADMIN_USERNAME — 用户名，默认 'admin'
      INIT_ADMIN_PASSWORD — 密码（必填；未设则不创建，日志告警）
    """
    from app import db

    try:
        if db.session.query(User.id).first() is not None:
            return

        password = os.environ.get('INIT_ADMIN_PASSWORD', '').strip()
        if not password:
            app.logger.warning(
                '目标库为空且无种子库（SEED_SQLITE_PATH），INIT_ADMIN_PASSWORD 也未设置 ⇒ '
                '不创建任何账号。要初始化：在 .env 加 INIT_ADMIN_PASSWORD=<你的密码> 后重启，'
                '或挂载种子库（./app.db:/app/seed.db:ro）。'
            )
            return

        username = os.environ.get('INIT_ADMIN_USERNAME', 'admin').strip() or 'admin'
        if User.query.filter_by(username=username).first() is not None:
            return

        user = User(username=username, role='admin')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        app.logger.warning(
            f'目标库为空：已创建管理员账号 {username!r}（INIT_ADMIN_PASSWORD），'
            '请登录后立即修改密码。'
        )
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'创建初始管理员失败: {e}')
