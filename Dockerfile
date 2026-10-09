# MyERP 生产镜像
#
# 交付路径：GitHub Actions（.github/workflows/docker-deploy.yml，context=.）构建 →
#           push 到私有 Docker Hub（zerotwice/myerp）；不在 Windows/Linux 主机上直接部署。
# 行尾：本文件必须为 LF（.gitattributes 已钉 `* text=auto eol=lf`）。
#       CRLF 会破坏 RUN 的 `\` 续行，导致构建在解析阶段就失败。

# ---- 基底 ----
# 依据：python:3.9-slim 的 3.9 已 EOL，不再有安全更新。
# 改用 python:3.11-slim-bookworm —— 本地已验证环境 /opt/wage-venv 的解释器就是 Python 3.11.2，
# requirements.lock 的全套钉版在该解释器上实测跑通全量门禁
# （functional_test / permission_matrix / smoke_test 全部 exit 0），
# 故镜像解释器与「已实测通过」的解释器同为 3.11.x；bookworm 亦是 python:3.11-slim 的稳定标签。
FROM python:3.11-slim-bookworm

# 统一容器内 Python 行为：
#   PYTHONDONTWRITEBYTECODE=1 不落 .pyc（只读层 + 非 root 下无意义且污染镜像）
#   PYTHONUNBUFFERED=1        stdout/stderr 不缓冲，日志实时可见（docker logs / 编排采集）
#   PIP_NO_CACHE_DIR=1        pip 不写 wheel 缓存
#   PYTHONFAULTHANDLER=1      段错误时打印 Python 栈，便于容器内定位
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONFAULTHANDLER=1

WORKDIR /app

# ---- 系统依赖 ----
# libmagic1：python-magic 的运行时依赖（lock 内已钉 python-magic==0.4.27）。当前代码路径尚未
#            import magic，但只有装上 libmagic1，这个已钉版的依赖才真正可用，否则是"装了用不了"。
# tzdata   ：slim 基底不带 tz 数据库，pandas / dateutil 做本地时区换算会失真。
# 装完清 /var/lib/apt/lists/*，避免把 apt 索引留在镜像层里。
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 tzdata \
 && rm -rf /var/lib/apt/lists/*

# ---- 依赖层（置于 COPY . . 之前：改源码不使依赖层缓存失效）----
# requirements.lock 由 `python -B scripts/check_doc_claims.py --write-lock` 生成（其头部注明"勿手改"），
# 但它的生成平台是 win32 / Python 3.9.21，因此含 pywin32==311 —— Linux 上无 wheel，装必然失败。
# 处理方式：**不修改 lock 本体**，只在构建期过滤掉 pywin32 行。
# 同时加一道确定性完整性校验：lock 头部 `# requirements.txt sha256: …` 必须等于镜像内
# requirements.txt 的 sha256。已实测该值 4BDA793697D6AEB2FAFE300B832A429131A9FCD8CEC88A6FC64D3393DD161478
# 正是 **LF 版** requirements.txt 的摘要（.gitattributes 强制 eol=lf，任何平台 checkout 均为 LF），
# 故校验不会误报；不一致即 fail-fast，拦截"改了 requirements.txt 忘了重新生成 lock"的静默漂移。
COPY requirements.txt requirements.lock ./
RUN set -eu; \
    grep -viE '^[[:space:]]*pywin32([[:space:]]|$|==)' requirements.lock > /tmp/requirements.lock.linux; \
    if grep -qiE '^[[:space:]]*pywin32([[:space:]]|$|==)' /tmp/requirements.lock.linux; then \
        echo 'FATAL: 过滤后仍残留 pywin32，检查过滤正则'; exit 1; \
    fi; \
    EXPECTED="$(grep -oE 'requirements\.txt sha256: *[0-9A-Fa-f]{64}' requirements.lock | grep -oE '[0-9A-Fa-f]{64}' | head -n 1)"; \
    if [ -n "$EXPECTED" ]; then \
        ACTUAL="$(python -c 'import hashlib;print(hashlib.sha256(open("requirements.txt","rb").read()).hexdigest().upper())')"; \
        if [ "$EXPECTED" != "$ACTUAL" ]; then \
            echo "FATAL: requirements.txt sha256=$ACTUAL 与 requirements.lock 头部 $EXPECTED 不一致；请重新运行 python -B scripts/check_doc_claims.py --write-lock"; \
            exit 1; \
        fi; \
        echo "OK: requirements.lock 与 requirements.txt sha256 一致（$ACTUAL）"; \
    else \
        echo 'WARN: requirements.lock 头部缺少 requirements.txt sha256 行，跳过一致性校验'; \
    fi; \
    pip install --no-cache-dir -r /tmp/requirements.lock.linux; \
    rm -f /tmp/requirements.lock.linux

# ---- 应用代码 ----
# .dockerignore 已排除 3.6G 的 test-reports-2026-10/ 等证据与临时目录；
# 必须保留的 app/（含 static、templates）、main.py、wsgi.py、config.py、migrations/、scripts/ 均在。
COPY . .

# ---- 运行时目录 + 非 root 用户（uid 10001）----
# uploads/ 是纯运行时数据、已被 .dockerignore 排除 ⇒ 必须在镜像内自建（含 TEMP_FOLDER=uploads/temp，
# 见 app/__init__.py 的 os.makedirs）；instance/ 供 Flask instance_path 使用。
# 二者必须归运行用户所有，否则非 root 进程启动时 create_app() 的 os.makedirs 会因权限失败。
# entrypoint 显式 chmod +x，不依赖构建上下文里的可执行位。
# 目录权限显式钉死 755：只靠 COPY 会继承宿主机/checkout 的 umask，若 /app 变成 555，
# 非 root 进程连 ALLOW_SQLITE=1 时的 sqlite:////app/app.db 都建不出来。
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /app/uploads/temp /app/instance \
 && chmod 755 /app /app/docker /app/uploads /app/uploads/temp /app/instance \
 && chmod +x /app/docker/entrypoint.sh \
 && chown -R app:app /app

# app 用户没有家目录；HOME 指到 /app，避免个别库 expanduser 落到不存在的 /home/app
ENV HOME=/app

USER app

ENV FLASK_APP=main.py

EXPOSE 5000

# ---- 健康检查 ----
# 探测路径是 /auth/login，**不是** /login：auth 蓝图在 app/__init__.py:251 注册时带了
# url_prefix='/auth'（app/auth/routes.py:7 的 @bp.route('/login') ⇒ 真实路径 /auth/login）。
# 实测（本地起真实 gunicorn）：GET /login → 404、GET /auth/login → 200、GET / → 302 跟随到 /auth/login。
# 若按 /login 探测，容器会永久 unhealthy。
# 基底镜像无 curl/wget，故用 python 标准库；写成单行避免 HEALTHCHECK 里 `\` 续行与 shell 语义的歧义。
# 非 2xx/3xx 时 urllib 抛异常 ⇒ 命令非 0 退出 ⇒ 容器标记 unhealthy。
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','5000')+'/auth/login',timeout=4)" || exit 1

# ---- 启动 ----
# entrypoint 做生产 fail-fast 前置检查（DATABASE_URL / SECRET_KEY），随后 exec 到 CMD。
# gunicorn 参数全部走 docker/gunicorn.conf.py 的 env 覆盖（PORT / WEB_CONCURRENCY / GUNICORN_TIMEOUT）。
# 原 `ENV FLASK_ENV=production` 已删除：Flask 2.3 起弃用、Flask 3.x 完全失效，留着只会误导。
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "-c", "docker/gunicorn.conf.py", "main:app"]
