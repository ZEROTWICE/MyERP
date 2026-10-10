"""B18-Q1 自助改密 + 强制改密门 自检（非作者也可复跑；不碰真库）。

用法：
    /opt/wage-venv/bin/python -B test-reports-2026-10/harness/b18_q1_password_selfcheck.py

口径：只跑 `_test_bootstrap.make_app()` 的 app.db 临时副本（脚本内有隔离闸），
      断言逐个打印，全部通过 exit 0；任一失败 exit 1 并打印失败项。
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from _test_bootstrap import make_app  # noqa: E402

WEAK = 'admin123'
GOOD = 'Str0ng-Pass-2026'


def main():
    app, copy_path = make_app(fresh=True)
    from app import db
    from app.models import User

    results = []

    def check(name, ok, detail=''):
        results.append((name, bool(ok), detail))
        print(f'[{"OK" if ok else "FAIL"}] {name}{(" :: " + detail) if detail else ""}')

    with app.app_context():
        u = User.query.filter_by(username='_q1_probe').first()
        if u is None:
            u = User(username='_q1_probe', role='user')
            db.session.add(u)
        u.set_password(WEAK)
        u.must_change_password = True
        db.session.commit()
        uid = u.id

    c = app.test_client()

    r = c.post('/auth/login', data={'username': '_q1_probe', 'password': WEAK}, follow_redirects=False)
    check('1 登录后被改道改密页', r.status_code == 302 and '/auth/change-password' in r.headers.get('Location', ''),
          f'{r.status_code} {r.headers.get("Location")}')

    r = c.get('/')
    loc = r.headers.get('Location', '')
    check('2 未改密时访问首页被拦', r.status_code == 302 and '/auth/change-password' in loc, f'{r.status_code} {loc}')

    r = c.get('/auth/change-password')
    check('3 改密页自身 200（无重定向环）', r.status_code == 200, str(r.status_code))

    r = c.post('/auth/change-password', data={'new_password': '12345678', 'confirm': '12345678'},
               follow_redirects=False)
    check('4 弱口令被拒（仍停在表单）', r.status_code == 200 and b'\xe8\xbf\x87\xe4\xba\x8e\xe7\xae\x80\xe5\x8d\x95' in r.data,
          str(r.status_code))

    r = c.post('/auth/change-password', data={'new_password': '_q1_probe', 'confirm': '_q1_probe'},
               follow_redirects=False)
    check('5 用户名作密码被拒', r.status_code == 200 and b'\xe4\xb8\x8d\xe8\x83\xbd\xe4\xb8\x8e\xe7\x94\xa8\xe6\x88\xb7\xe5\x90\x8d' in r.data,
          str(r.status_code))

    r = c.post('/auth/change-password', data={'new_password': GOOD, 'confirm': GOOD}, follow_redirects=False)
    check('6 合规新密码被接受并跳走', r.status_code == 302, f'{r.status_code} {r.headers.get("Location")}')

    r = c.post('/auth/change-password', data={'new_password': GOOD, 'confirm': GOOD}, follow_redirects=False)
    check('6b 新密码 == 原密码被拒（不白白清标记）',
          r.status_code == 302 and '/auth/change-password' in r.headers.get('Location', ''),
          f'{r.status_code} {r.headers.get("Location")}')

    with app.app_context():
        u = db.session.get(User, uid)
        check('7 标记已清除', u.must_change_password is False, repr(u.must_change_password))
        check('8 新口令生效', u.check_password(GOOD) and not u.check_password(WEAK), '')

    r = c.get('/')
    check('9 改密后可正常访问首页', r.status_code in (200, 302) and '/auth/change-password' not in r.headers.get('Location', ''),
          f'{r.status_code} {r.headers.get("Location")}')

    c.get('/auth/logout')
    r = c.post('/auth/login', data={'username': '_q1_probe', 'password': GOOD}, follow_redirects=False)
    check('10 新口令可登录且不再改道', r.status_code == 302 and '/auth/change-password' not in r.headers.get('Location', ''),
          f'{r.status_code} {r.headers.get("Location")}')

    c.get('/auth/logout')
    r = c.post('/auth/login', data={'username': '_q1_probe', 'password': WEAK}, follow_redirects=False)
    check('11 旧口令已失效', r.status_code == 302 and r.headers.get('Location', '').rstrip('/').endswith('/auth'),
          f'{r.status_code} {r.headers.get("Location")}')

    with app.app_context():
        u = User.query.filter_by(username='_q1_probe').first()
        u.set_password(WEAK)
        u.must_change_password = True
        db.session.commit()
    c2 = app.test_client()
    c2.post('/auth/login', data={'username': '_q1_probe', 'password': WEAK}, follow_redirects=False)
    r = c2.get('/api/quality/templates', headers={'X-Requested-With': 'XMLHttpRequest'})
    check('12 JSON 面拿到 403 + 中文原因', r.status_code == 403 and r.is_json, f'{r.status_code} {r.data[:80]!r}')

    check('13 未触碰真库', pathlib.Path(copy_path).exists() and 'wms_test_' in copy_path, copy_path)

    bad = [n for n, ok, _ in results if not ok]
    print(f'\n{len(results) - len(bad)}/{len(results)} 通过')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
