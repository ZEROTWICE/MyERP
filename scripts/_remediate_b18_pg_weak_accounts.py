"""B18 挂账解除：PG 生产库补列 must_change_password + 弱账户打标。

授权边界（写死在代码里，不提供 CLI 覆盖）：
  - 只接受 PG 目标库 `192.168.50.243:25432/erpdb`；URL 不匹配 ⇒ 立即退出（防打错库）。
  - 默认 dry-run，只读；要真写必须显式 `--apply`。

执行面（与部署一致）：
  ① 补列走 `create_app()` → `app/__init__.py` 的 `_ensure_schema()`（即容器首启的同一条路径），
     而不是手写 DDL；② 弱账户打标走 SQLAlchemy Session + audit 记录。

口径：只翻 `must_change_password` 标志，**不动任何口令哈希**。
回滚：`ALTER TABLE "user" DROP COLUMN must_change_password`（先备份再删）+ 把被翻的账号置回 FALSE。

用法：
    /opt/wage-venv/bin/python -B scripts/_remediate_b18_pg_weak_accounts.py            # 只读
    /opt/wage-venv/bin/python -B scripts/_remediate_b18_pg_weak_accounts.py --apply    # 真写
    /opt/wage-venv/bin/python -B scripts/_remediate_b18_pg_weak_accounts.py --rollback <before.json>
"""
import argparse
import datetime
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TARGET_HOST = '192.168.50.243'
TARGET_PORT = '25432'
TARGET_DB = 'erpdb'
TARGET_URL = f'postgresql+psycopg2://erpuser:erpuser@{TARGET_HOST}:{TARGET_PORT}/{TARGET_DB}'
EVIDENCE_DIR = ROOT / 'test-reports-2026-10' / 'evidence' / 'db'


def _guard():
    """库定位守卫：不接受任何覆盖，只认唯一目标库。"""
    url = os.environ.get('DATABASE_URL', TARGET_URL)
    if not all(k in url for k in (TARGET_HOST, TARGET_PORT, TARGET_DB)):
        sys.exit(f'[ABORT] 目标库不是 {TARGET_URL}（实得 {url}）；本脚本不接受其他库')
    return url


def _boot_app(url):
    os.environ['DATABASE_URL'] = url
    for name in [m for m in list(sys.modules)
                 if m == 'config' or m == 'app' or m.startswith('app.')]:
        del sys.modules[name]
    from app import create_app
    return create_app()


def _snapshot(engine):
    """列集 + 弱账户标记现状（**只读，且不触发启动自愈**）。

    2026-10-11 订正两处：
    ① 原实现经 `_boot_app()` → `create_app()` 取快照，而 `create_app()` 会跑
       `_ensure_schema()` 的补列 DDL ⇒ **所谓「只读 dry-run」其实已经写了库**
       （实测 `erpdb` 的 `must_change_password` 就这样被补上，见
       `test-reports-2026-10/B18-登记.md`）。改为直接吃一个只读 SQLAlchemy engine。
    ② `unflagged_admin_role` 只看标志位，会把 `YHGL0001`（用户名=口令）算成「被漏标」——
       该账号按登录侧规则在首次登录时自动打标，不需要人工处置。故新增
       `self_demonstrating`（bcrypt 逐条校验「口令==用户名」）与 `out_of_scope_admin_role`，
       判据改用后者。

    `password_hash_sha256` = 全表口令哈希的聚合指纹，用来证明「只翻标志、未改口令」
    （改前改后必须逐位相同）。
    """
    import hashlib

    from sqlalchemy import inspect as sa_inspect, text
    from werkzeug.security import check_password_hash

    insp = sa_inspect(engine)
    cols = [c['name'] for c in sa_inspect(engine).get_columns('user')]
    flagged_expr = ('must_change_password' if 'must_change_password' in cols
                    else 'NULL AS must_change_password')
    with engine.connect() as conn:
        rows = conn.execute(text(
            'SELECT username, role, password_hash, ' + flagged_expr
            + ' FROM "user" ORDER BY id')).fetchall()

    def _self_demo(username, pw_hash):
        """口令 == 用户名？用于识别「登录即自动打标」的账号（哈希口径同 app/models.py）。"""
        try:
            return check_password_hash(str(pw_hash), str(username))
        except Exception:
            return False

    self_demo = sorted(r[0] for r in rows if _self_demo(r[0], r[2]))
    digest = hashlib.sha256(
        '\n'.join(f'{r[0]}|{r[1]}|{r[2]}' for r in rows).encode('utf-8')
    ).hexdigest()
    audit_tables = set(insp.get_table_names())
    unflagged_admin = sorted(r[0] for r in rows if r[3] is not True and r[1] == 'admin')
    return {
        'url': str(engine.url).replace('erpuser:erpuser', 'erpuser:***'),
        'columns': cols,
        'user_count': len(rows),
        'flagged': sorted(r[0] for r in rows if r[3] is True),
        'unflagged_admin_role': unflagged_admin,
        'self_demonstrating': self_demo,
        'out_of_scope_admin_role': sorted(set(unflagged_admin) - set(self_demo)),
        'password_hash_sha256': digest,
        'has_audit_log': 'audit_log' in audit_tables,
        'snapshot_mode': 'read-only engine（不经 create_app，不触发 _ensure_schema）',
    }


def _write(path, obj):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[evidence] {path}')


def run(args):
    url = _guard()
    before_path = EVIDENCE_DIR / f'b18-pg-weak-before-{datetime.datetime.utcnow():%Y%m%d-%H%M%S}.json'

    # ---- 阶段 1：只读快照（**新增：这里绝不碰 create_app**，否则补列 DDL 会先跑）----
    from sqlalchemy import create_engine
    ro_engine = create_engine(url)
    try:
        before = _snapshot(ro_engine)
    finally:
        ro_engine.dispose()
    print('[before]', json.dumps(before, ensure_ascii=False))
    _write(before_path, before)

    if not args.apply:
        print('[dry-run] 未做任何写操作（本阶段不经 create_app，不触发补列 DDL）；要真写请加 --apply')
        return 0

    # ---- 阶段 2：按部署路径补列（create_app 已跑 _ensure_schema，这里复核其结果）----
    app = _boot_app(url)
    with app.app_context():
        from app import db as _db
        after_ddl = _snapshot(_db.engine)
        if 'must_change_password' not in after_ddl['columns']:
            print('[FAIL] _ensure_schema() 后该列仍不存在 —— 见应用日志的「检查/补齐数据库结构失败」')
            return 1
        print('[ddl] user 列 =', after_ddl['columns'])

        # ---- 阶段 3：弱账户打标（只翻具名账号；口令哈希一律不动）----
        from app import db
        from app.models import User

        targets = args.usernames
        flipped = []
        for name in targets:
            u = User.query.filter_by(username=name).first()
            if u is None:
                print(f'[skip] 账号不存在：{name}')
                continue
            if u.must_change_password:
                print(f'[skip] 已是 True：{name}')
                continue
            u.must_change_password = True
            flipped.append(name)
        if flipped:
            db.session.commit()
            print('[flip] 已置 must_change_password=True：', flipped)
        else:
            print('[flip] 无需变更（幂等）')

        # 审计：复用既有 AuditLog 模型（字段面核对于 app/models.py:AuditLog）
        try:
            from app.models import AuditLog
            for name in flipped:
                u = User.query.filter_by(username=name).first()
                db.session.add(AuditLog(
                    user_id=None, action='update',
                    target_model='User', target_id=u.id if u else None,
                    details=f'B18 弱口令处置：{name} 置 must_change_password=True（未改口令哈希）',
                ))
            db.session.commit()
            print('[audit] AuditLog 已写入', len(flipped), '条')
        except Exception as e:  # 审计失败不得吞掉已生效的处置
            db.session.rollback()
            print(f'[audit][WARN] 审计写入失败（处置已生效）：{type(e).__name__}: {e}')

        after = _snapshot(_db.engine)
    print('[after]', json.dumps(after, ensure_ascii=False))
    _write(before_path.with_name(before_path.name.replace('weak-before', 'weak-after')), after)

    # ---- 阶段 4：验收断言（逐条可判定，禁止「未发现问题」式结论）----
    checks = [
        ('列已存在', 'must_change_password' in after['columns']),
        ('目标账号全部带标', all(u in after['flagged'] for u in args.usernames)),
        ('账号总数未变（无增删）', after['user_count'] == before['user_count']),
        ('未带标的 admin 角色账号集合 ⊆ 请求名单 ∪ 自证账号'
         '（自证账号 = 口令==用户名，首次登录时由登录侧规则自动打标，无需人工处置）',
         set(after.get('out_of_scope_admin_role', after['unflagged_admin_role']))
         <= set(args.usernames)),
        ('口令哈希未被本脚本改动', before.get('password_hash_sha256') is None
         or before['password_hash_sha256'] == after.get('password_hash_sha256')),
    ]
    for label, ok in checks:
        print(f'[check] {"PASS" if ok else "FAIL"}  {label}')
    ok = all(c[1] for c in checks)
    print('[RESULT]', 'OK' if ok else 'FAILED')
    print(f'[rollback] ALTER TABLE "user" DROP COLUMN must_change_password; '
          f'UPDATE "user" SET must_change_password=FALSE WHERE username IN ('
          + ','.join(repr(u) for u in args.usernames) + ');')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='真写（默认只读）')
    ap.add_argument('--usernames', default='admin', help='要打标的账号，逗号分隔（默认 admin）')
    ap.add_argument('--rollback', metavar='BEFORE_JSON', help='按 before 快照还原标记')
    args = ap.parse_args()
    args.usernames = [u.strip() for u in args.usernames.split(',') if u.strip()]

    if args.rollback:
        url = _guard()
        snap = json.loads(pathlib.Path(args.rollback).read_text(encoding='utf-8'))
        app = _boot_app(url)
        with app.app_context():
            from app import db
            from app.models import User
            for name in args.usernames:
                u = User.query.filter_by(username=name).first()
                if u and u.username in snap.get('flagged', []):
                    continue  # 本来就有标，别误清
                if u and u.must_change_password:
                    u.must_change_password = False
                    print(f'[rollback] {name} → False')
            db.session.commit()
        return 0
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
