"""迁移链 head 自检（无副作用）：只读 migrations/ 脚本，不启动 Flask 应用、不触碰任何数据库。

为什么不用 ``flask db heads``：
那条命令必须先 ``create_app()`` 才能拿到 Flask-Migrate 扩展的配置，而 ``create_app()`` 会执行
``_ensure_schema()`` → ``db.create_all()`` + ``_ENSURED_COLUMNS`` 补列。若未同时把 ``DATABASE_URL``
指向副本，模型里新增的表/列会被启动自愈**直接写进真实 app.db**。本项目已实际发生过一次
（2026-08-27，`NonconformityRecord` 新增 `target_type`/`target_id` 后，未带 `DATABASE_URL` 的
``flask db heads`` 把这两列补进了真实库，SHA256 由 BD18DA81…B0CCC 变为 F5DA2306…0E0F065）。

本脚本用 Alembic 的 ``ScriptDirectory`` 直接读脚本目录，只依赖 migrations/ 下的修订文件。

用法（仓库根目录）：
    python -B scripts/check_migration_heads.py

退出码：单一 head → 0；0 个或 >1 个 head → 1。
"""
import os
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    cfg = Config()
    cfg.set_main_option('script_location', os.path.join(ROOT, 'migrations'))
    script = ScriptDirectory.from_config(cfg)

    heads = script.get_heads()
    revisions = list(script.walk_revisions())
    print('HEADS=%s' % (heads,))
    print('head_count=%d  revisions=%d' % (len(heads), len(revisions)))

    if len(heads) != 1:
        print('FAIL: 期望单一 head，实际 %d 个：%s' % (len(heads), heads))
        return 1
    print('OK: 单一 head %s' % heads[0])
    return 0


if __name__ == '__main__':
    sys.exit(main())
