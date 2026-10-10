#!/bin/sh
# MyERP 容器入口 —— 生产环境 fail-fast 前置检查，随后 exec 到 CMD。
#
# 为什么必须有这一层：
#   config.py:16  SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev'
#   config.py:17  SQLALCHEMY_DATABASE_URI = _normalize_database_url(os.environ.get('DATABASE_URL'))
#   而 _normalize_database_url() 在 DATABASE_URL 为空时**静默**回退到
#   'sqlite:///' + <basedir>/app.db（即镜像内的空 SQLite）。
#   生产上这就是「连不上 Postgres 却照常启动、数据全写进容器内临时库」的静默数据丢失，
#   故在此拦死；确需本地/单机 SQLite 调试时必须显式 ALLOW_SQLITE=1 放行。
#   （与 .env.example 的口径一致：Docker / 两地部署使用 PostgreSQL。）
set -e

if [ -z "${DATABASE_URL}" ]; then
    if [ "${ALLOW_SQLITE}" = "1" ]; then
        echo "[WARN] DATABASE_URL 未设置，但 ALLOW_SQLITE=1 ⇒ 使用镜像内 SQLite（仅限本地调试，数据不入库）" >&2
    else
        echo "[FATAL] 未设置 DATABASE_URL：config.py 会静默回退到镜像内的空 SQLite，生产环境禁止启动。" >&2
        echo "        请注入 DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<db>；" >&2
        echo "        确需本地 SQLite 调试请显式设置 ALLOW_SQLITE=1。" >&2
        exit 1
    fi
fi

case "${SECRET_KEY}" in
    ''|'dev')
        echo "[FATAL] SECRET_KEY 未设置或仍是默认值 'dev'（config.py:16 的兜底值）：会话/CSRF 签名密钥可预测，生产环境禁止启动。" >&2
        echo "        请注入 SECRET_KEY=$(python -c 'import secrets;print(secrets.token_urlsafe(48))')；" >&2
        echo "        本地调试请设置任意非 'dev' 值（如 SECRET_KEY=local-debug）。" >&2
        exit 1
        ;;
esac

exec "$@"
