"""空库自举自检：在临时空库上跑 create_app()，验证种子数据被导入且不会重复导入。

用法：
    F:\\Miniconda\\envs\\wage\\python.exe -B scripts/check_db_bootstrap.py

Postgres 专有分支（advisory lock / setval / ALTER 加宽）本地无法覆盖，
这里验证的是拷贝顺序、列匹配、空库判定与幂等。
"""
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _fresh_app(target_path, seed_path):
    """指向目标库重建应用，模块缓存每次清干净，避免连到真实库。"""
    os.environ['DATABASE_URL'] = 'sqlite:///' + target_path.replace('\\', '/')
    os.environ['SEED_SQLITE_PATH'] = seed_path
    for name in [m for m in list(sys.modules)
                 if m == 'config' or m == 'app' or m.startswith('app.')]:
        del sys.modules[name]

    from app import create_app

    app = create_app()
    assert os.path.normcase(target_path) in os.path.normcase(
        app.config['SQLALCHEMY_DATABASE_URI'].replace('/', os.sep)
    ), '目标库没落在临时文件上，可能连到了真实库'
    return app


def boot(target_path, seed_path):
    """在指定目标库上新建一次应用，返回 (账号数, admin 的哈希)。"""
    app = _fresh_app(target_path, seed_path)

    from app import db
    from app.models import User

    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        return db.session.query(User).count(), (admin.password_hash if admin else None)


def copy_check(target_path, seed_path):
    """绕过自举直接拷一次，返回 (行数, 被跳过的表)。

    整张表插入失败只会记日志，账号数断言照样通过。DATETIME 列曾因裸 SQL
    读成字符串而让 24 张业务表全军覆没，必须单独盯住 skipped。
    """
    app = _fresh_app(target_path, os.path.join(os.path.dirname(target_path), '.no-seed'))

    from app import db
    from app.db_bootstrap import copy_sqlite_into

    with app.app_context():
        # 真实顺序是先自举拷贝、后 _seed_system_configs 补缺；这里 create_app()
        # 已经把默认配置写进去了，不清掉会撞主键，测出的是假冲突
        db.session.execute(db.text('DELETE FROM system_configs'))
        db.session.commit()
        return copy_sqlite_into(db.engine, seed_path)


def main():
    tmp = tempfile.mkdtemp(prefix='bootstrap_check_')
    seed = os.path.join(tmp, 'seed.db')
    target = os.path.join(tmp, 'target.db')
    shutil.copy2(ROOT / 'app.db', seed)

    seed_users, seed_hash = boot(os.path.join(tmp, 'seedcheck.db'), seed)
    print(f'种子库账号数（经自举导入到空库）= {seed_users}')
    assert seed_users > 0, '空库自举后仍然没有任何账号'
    assert seed_hash and len(seed_hash) in (102, 162), f'admin 哈希异常: {seed_hash!r}'

    first, hash1 = boot(target, seed)
    second, hash2 = boot(target, seed)
    print(f'首次启动导入 {first} 个账号，再次启动后 {second} 个')
    assert first == second, f'第二次启动重复导入了：{first} -> {second}'
    assert hash1 == hash2 == seed_hash, '哈希在导入过程中被改写或截断'

    # 不挂载种子库时应当安全跳过，而不是报错
    empty_target = os.path.join(tmp, 'noseed.db')
    none_count, _ = boot(empty_target, os.path.join(tmp, 'does-not-exist.db'))
    print(f'无种子库时账号数 = {none_count}')
    assert none_count == 0, '没有种子库却导入了数据'

    copied, skipped = copy_check(os.path.join(tmp, 'copycheck.db'), seed)
    print(f'直接拷贝 {copied} 行，跳过 {len(skipped)} 张表')
    assert copied > 0, '一行都没拷进去'
    assert not skipped, '有表整张被跳过：' + '；'.join(
        f'{name}: {err[:120]}' for name, err in skipped[:5]
    )

    shutil.rmtree(tmp, ignore_errors=True)
    print('OK: 空库自举、幂等、无种子库跳过、整表无遗漏 均通过')


if __name__ == '__main__':
    main()
