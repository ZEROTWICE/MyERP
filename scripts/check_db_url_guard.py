#!/usr/bin/env python
"""DATABASE_URL 前置闸门（GAP-03 交付件；B13-02 手册 §5.3 前置 ④ 的 guard）。

判据（给可读原因 + 退出码，不连库、不建库、不写文件）：
  * URI 解析到**真实库** `<repo>/app.db` 且未显式授权 ⇒ 拒绝（exit 1）
  * URI 指向副本 / 内存库 / 非 sqlite（PG 等）        ⇒ 放行（exit 0）
  * `--i-have-authorization "<授权人>" "<时点>"`      ⇒ 放行真实库并打印留档

自检（GAP-03 要求的假库路径正/负两条用例）：
  `--expect reject`：真实库必被拒 **且** 副本/内存/PG 必被放行 ⇒ 与预期一致时 exit 0
  `--expect allow` ：带授权时真实库必被放行                    ⇒ 与预期一致时 exit 0

退出码：0 放行或自检一致 ／ 1 拒绝 ／ 2 用法或环境错误。
"""
import argparse
import os
import sys
import tempfile
from urllib.parse import unquote, urlsplit

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
REAL_DB = os.path.join(REPO_ROOT, 'app.db')
DEFAULT_URI = 'sqlite:///' + REAL_DB


def is_real_db(uri):
    """URI 是否解析到真实库 `<repo>/app.db`（只认 sqlite 文件路径）。"""
    if not uri:
        return True  # 空值 ⇒ config.py 的默认值就是真实库
    parts = urlsplit(uri)
    if not parts.scheme.startswith('sqlite'):
        return False  # PG 等非 sqlite 目标：不是本项目真实库
    path = unquote(parts.path)
    if not path or path == ':memory:':
        return False
    if parts.netloc and not path:  # sqlite://host/path 形式
        path = parts.netloc
    if len(path) > 2 and path[0] == '/' and path[2] == ':':
        path = path[1:]  # sqlite:///C:/x/app.db ⇒ C:/x/app.db（Windows 本机运行）
    if not os.path.isabs(path):
        path = os.path.join(REPO_ROOT, path)
    return os.path.realpath(path) == os.path.realpath(REAL_DB)


def verdict(uri, authorization=None):
    """⇒ (allow: bool, reason: str)。"""
    if not is_real_db(uri):
        return True, 'URI 未指向真实库 ⇒ 放行（副本/内存库/非 sqlite 目标）'
    if authorization:
        who, when = authorization
        if who.strip() and when.strip():
            return True, '真实库 + 显式授权（授权人=%r 时点=%r）⇒ 放行并留档' % (who, when)
        return False, '真实库 + --i-have-authorization 需要非空授权人 AND 时点'
    return False, ('URI 指向真实库 %s ⇒ 拒绝（未显式授权；'
                   '需 --i-have-authorization "<授权人>" "<时点>"）' % REAL_DB)


def _selftest(expect):
    """假库路径正/负两条用例自检；返回 (ok, lines)。"""
    tmp_copy = os.path.join(tempfile.gettempdir(), 'guard_case_copy.db')
    cases = [
        ('真实库', DEFAULT_URI, None, False),
        ('真实库+授权', DEFAULT_URI, ('selftest', 'n/a'), True),
        ('?mode=ro 真实库', DEFAULT_URI + '?mode=ro', None, False),
        ('副本', 'sqlite:///' + tmp_copy, None, True),
        ('内存库', 'sqlite:///:memory:', None, True),
        ('空值(默认=真实库)', None, None, False),
        ('PG', 'postgresql+psycopg2://u:p@127.0.0.1:5432/erpdb', None, True),
    ]
    cases = [c for c in cases if (c[2] is not None) == (expect == 'allow')]
    lines, bad = [], []
    for label, uri, auth, want in cases:
        got, reason = verdict(uri, auth)
        mark = 'OK ' if got == want else 'BAD'
        if got != want:
            bad.append(label)
        lines.append('  [%s] %-18s want=%-5s got=%-5s %s' % (mark, label, want, got, reason))
    return (not bad), lines + (['  失败用例：%s' % bad] if bad else [])


def main():
    ap = argparse.ArgumentParser(description='DATABASE_URL 前置闸门（只读判定）')
    ap.add_argument('--db-url', help='待判定 URI；缺省取环境变量 DATABASE_URL（空 ⇒ 默认真实库）')
    ap.add_argument('--expect', choices=['reject', 'allow'],
                    help='自检模式：断言判定与预期一致（一致 ⇒ exit 0）')
    ap.add_argument('--i-have-authorization', dest='authorization', nargs=2,
                    metavar=('AUTHORIZER', 'WHEN'), help='显式授权通道：授权人 + 时点')
    args = ap.parse_args()

    if args.expect:
        ok, lines = _selftest(args.expect)
        print('[check_db_url_guard] 自检 --expect %s' % args.expect)
        print('\n'.join(lines))
        print('[RESULT] %s' % ('OK' if ok else 'FAIL'))
        return 0 if ok else 1

    uri = args.db_url if args.db_url is not None else os.environ.get('DATABASE_URL')
    allow, reason = verdict(uri, args.authorization)
    print('[check_db_url_guard] URI=%s' % (uri or '<默认 ' + DEFAULT_URI + '>'))
    print('[check_db_url_guard] 真实库=%s' % REAL_DB)
    print('[check_db_url_guard] %s：%s' % ('放行' if allow else '拒绝', reason))
    print('[RESULT] %s' % ('ALLOW' if allow else 'REJECT'))
    return 0 if allow else 1


if __name__ == '__main__':
    sys.exit(main())
