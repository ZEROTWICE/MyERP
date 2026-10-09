# Docker 镜像：GitHub Actions 无人值守构筑 + 推送私有 Docker Hub

- 基线 HEAD：`899d6200039a86d25bc75a36f60bd516ad787624`（`main` == `github/main`）
- 日期：2026-10-09
- 部署形态：**不再在 Windows/Linux 主机直装**，改为 GH Actions 构筑镜像 → 推送到私有 Docker Hub（`zerotwice/myerp`）→ 由容器平台拉取运行。

## 0. 结论摘要

| # | 结论 |
| --- | --- |
| 交付 | GH Actions 双路径：`push → main` **构筑 + 推送**（`:latest` + `:<sha>`）；`pull_request → main` **只构筑不推送**（`build-check`）。⇒「每次 push 前先证明 Dockerfile 可被自动构筑」由 PR 路径保证。 |
| 改动面 | `Dockerfile`、`.dockerignore`、`.github/workflows/docker-deploy.yml` 三个文件 + 本报告。未触碰 `app/**`、`scripts/**`、`test-reports-2026-10/**`、`app.db`。 |
| 风险点 | 8 条全部逐条复核（§2）：**7 条已满足或已修**，1 条（多架构）给出判断与代价。 |
| 验证手段 | 本容器**无 docker daemon / CLI**（`docker`/`podman`/`buildah`/`nerdctl`/`kaniko`/`skopeo` 全部 MISSING）⇒ **没有也不可能跑过 `docker build`**。所有结论来自：静态审查（含行号）+ 本机等价复算（Dockerfile 里那段 `RUN` 原样在 `/tmp` 沙箱执行、非 root 起真实 gunicorn、`pip --dry-run` 标签解析、`.dockerignore` 语义模拟）。逐条附「工具 + 口径 + 值」。 |

## 1. 改动清单（每处改动为什么是必要的）

### 1.1 `Dockerfile`（107 → 131 行，全部为注释与 1 行 ENV 改动）

| 位置 | 改动 | 为什么 GH Actions 构筑/推送需要它 |
| --- | --- | --- |
| `Dockerfile:5-6` | 新增文件头「触发」说明 | 交付形态从「主机直装」变为「CI 构筑 + push」。把触发矩阵写进镜像定义，避免下一个人以为 `Dockerfile` 只在 push 后生效而漏掉 PR 校验路径。 |
| `Dockerfile:16-19` | 新增基底 glibc 约束注释 | 已实测 `pandas==2.3.3` 的 cp311 wheel 只带 `manylinux_2_24/manylinux_2_28` 标签 ⇒ **要求 glibc ≥ 2.28**。换成 Alpine(musl) 或更老基底，CI 上就会失去 wheel、退化为源码编译或直接 404 —— 这是最容易在「优化镜像体积」时踩的坑，写死在基底旁边。 |
| `Dockerfile:95-99` | `ENV FLASK_APP=main.py` → **`ENV FLASK_APP=main:app`** | `main.py` 里只有 `app = create_app()`。写文件名形式时 Flask 3.x 走自动探测，只有 `flask run` 稳；`flask db` / `flask shell` 需要确定性拿到 app 对象。改成 `main:app` 后，容器内**所有**入口（gunicorn CMD、flask CLI、健康检查）指向同一个对象，与 `CMD ... main:app` 完全一致。 |
| `Dockerfile:106-108` | 订正健康检查注释里 `/` 的 302 目标 | 原注释写「`GET /` → 302 跟随到 `/auth/login`」，实测是 `302 → Location: /auth/?next=http://<host>/`。注释与实测不符会在排障时把人带偏（尤其配合 `curl -L` 时的重定向语义）。 |
| `Dockerfile:114-125` | 新增「数据库不进镜像（运行期挂卷）」段 | 给出容器里数据库的正确落法：**挂卷 + `DATABASE_URL`**，空库首次启动由 `create_app()` 的启动自愈建表；显式写明**禁止 `flask db migrate`**、老库走 `flask db stamp p1nonctarget`；并写清 `SEED_SQLITE_PATH`/`/app/seed.db` 在本仓库都不存在（自举实际关闭）。这是「镜像不含真实库」之后必须配套说明的运行时契约。 |

> 未改动但已复核为正确的既有内容：`apt` 单层安装 + 清 `apt/lists`（`:39-41`）、`COPY requirements.txt requirements.lock` 独立依赖层（`:51`）、`pywin32` 过滤 + sha256 闸门（`:52-69`）、非 root `app`(uid 10001) 与目录属主（`:83-88`）、`HEALTHCHECK` 探针（`:112`）——理由见 §2 对应风险点。

### 1.2 `.dockerignore`（62 → 78 行）

| 位置 | 改动 | 为什么 |
| --- | --- | --- |
| `.dockerignore:24-36` | 补 `**/__pycache__`、`**/*.pyc`、`**/*.pyo`、`**/.pytest_cache`（保留原裸写法）+ 机制注释 | `.dockerignore` 用的是 Go `filepath.Match` 语义，**`*` 不跨 `/`**，且不含 `/` 的模式只在**上下文根**生效 ⇒ 原来那句裸 `__pycache__` 只挡得住仓库根那一层。实测改前有 **11 处嵌套 `__pycache__`（合计 ≈2.2 MiB，其中 `app/main/__pycache__` 1.3 MiB）进入构建上下文**。CI 上上下文越大，`context` 打包上传越慢（且这些 `.pyc` 是 3.9/3.11 混杂的历史产物，进镜像纯属污染）。 |
| `.dockerignore:42-53` | 补 `*.sqlite`、`*.sqlite3`、`**/*.db*`、`**/*.sqlite*` + 机制注释 | 裸 `*.db` 同样只匹配根那一层，挡不住嵌套的 `app/data.sqlite`（实测该文件改前确实漏进上下文）。镜像里出现任何 `*.db` 都是事故面：本项目 `config.py:6-12` 在 `DATABASE_URL` 为空时会**静默回退**到 `<basedir>/app.db`。 |

**改前/改后实测（工具：自写的 `moby/patternmatcher` 等价实现 `/tmp/di_audit.py`，口径：逐文件求「最后一个命中的模式」，`**` 递归）：**

| | 上下文文件数 | 大小 |
| --- | --- | --- |
| 改前 | 370 | 20.58 MiB |
| 改后 | **298** | **18.56 MiB** |
| 差 | 新排除 72 个 / 2.02 MiB，**新增入上下文 0 个** | |

必备文件全部仍在上下文内（抽查 `main.py`、`wsgi.py`、`config.py`、`requirements.lock`、`docker/entrypoint.sh`、`docker/gunicorn.conf.py`、`app/__init__.py`、`migrations/env.py`、`migrations/versions/*`（35 个）、`app/templates/**`（87 个）、`app/static/**`（98 个）→ **缺失 0**）；`app.db`、`app/data.sqlite`、`uploads/`、`instance/`、`docs/`、`test-reports-2026-10/`、`.github/`、`.git/`、`__pycache__` 命中数 **全部为 0**。

### 1.3 `.github/workflows/docker-deploy.yml`（83 → 130 行）

| 位置 | 改动 | 为什么 |
| --- | --- | --- |
| `:4-8` | 文件头补「触发与职责」矩阵 | 流水线是本次交付的入口，先把「哪条路径推、哪条只构建」写清楚。 |
| `:14-15` | 新增 `pull_request: branches: [main]` | **这是「每次 push 前保证 Dockerfile 可被 GH Actions 构筑」的唯一实现方式**：改造前只有 `push`/`workflow_dispatch`，改动只有在合进 `main` 之后才第一次被验证 —— 一旦构建失败，坏提交已经在 `main` 上了。 |
| `:19-20` | 新增顶层 `permissions: contents: read` | 显式最小权限。推送镜像用的是 Docker Hub Secrets，不需要 `GITHUB_TOKEN` 的写权限；顶层声明可避免仓库默认权限放宽时被默认值带跑。 |
| `:23-25` | 新增 `concurrency`（`cancel-in-progress: false`） | 同一 ref 上连续 push 会并发跑多条发布流水线，两条同时 `push :latest` 时「后完成的旧 sha」会把 `:latest` 覆盖回去。改为排队而非取消，既不丢发布也不覆盖错 tag。 |
| `:77` | `build-and-push` 加 `if: github.event_name != 'pull_request'` | 与 PR 触发互斥：PR 上**不推送**，避免未合并代码覆盖 `:latest` / 污染私有仓库 tag 空间。 |
| `:79`、`:112` | 两个构建 job 各加 `timeout-minutes: 30` | 构建卡住（网络/上游 registry）时默认 6 小时才结束，会白烧额度；30 分钟对 18.56 MiB 上下文 + 45 个 wheel 是宽裕上限。 |
| `:105-130` | 新增 `build-check` job（`if: github.event_name == 'pull_request'`，`push: false`，不登录、不需要任何 Secret） | PR 上的构筑校验。**故意不配 `docker/login-action`**：fork PR 拿不到 Secrets，一旦依赖登录，外部贡献者的 PR 会永久红。 |
| 保持不变 | `gate` job 仍 `continue-on-error: true`、`build-and-push` 仍**无** `needs` | 仓内 `test-reports-2026-10/harness/ci_lint.py --phase first` 的硬判据锁死「第一阶段：build-and-push 无 needs + gate 为 continue-on-error」，改成 `needs: gate` 会让 `ci_gates`/`ci_lint` 立即变红。见 §4.1。 |

---

## 2. 八个风险点：逐条结论 + 证据

> 证据口径统一说明：本容器**没有 docker**，所以凡涉及「镜像内行为」的结论，都用**在本机复算等价步骤**取得：本机就是 `Debian 12 (bookworm) / glibc 2.36`，与基底 `python:3.11-slim-bookworm` 同族同版本线；`/opt/wage-venv/bin/python` 是 Python **3.11.2**，其 `pip freeze` 与过滤后的 `requirements.lock` 完全一致（仅 `et-xmlfile`/`importlib-metadata`/`typing-extensions` 的 `-`↔`_` 写法差异）。

### 风险 1 —— `requirements.lock` 含 `pywin32==311`（Windows-only）

**结论：已正确处理，Linux 构筑不会因此失败。** 钉版本体不动（头部注明「勿手改」），过滤发生在构建期，并且过滤是**双重**的（粗过滤 + 残留复查）。

证据：

1. 事实源：`requirements.lock` 共 57 行，第 46 行是 `pywin32==311`；头部注释注明生成平台为 win32 / Python 3.9.21，并带 `# requirements.txt sha256: 4BDA793697D6AEB2FAFE300B832A429131A9FCD8CEC88A6FC64D3393DD161478`。
2. **原样复算**：把 `Dockerfile:52-69` 那段 `RUN` 抽出（`awk` 抽 `RUN set -eu; \` 到 `rm -f /tmp/requirements.lock.linux`，去掉行首 `RUN `）存成 `/tmp/rbsim/block.sh`，在 `/tmp/rbsim/work`（放着真实的 `requirements.txt` + `requirements.lock`）用 `sh -c` 执行，`pip`/`python` 用 stub 替身（stub 记录 argv 并把 `-r` 指向的文件另存）。结果：
   - stdout：`OK: requirements.lock 与 requirements.txt sha256 一致（4BDA793697D6AEB2FAFE300B832A429131A9FCD8CEC88A6FC64D3393DD161478）`
   - stub 收到的 argv：`install --no-cache-dir -r /tmp/requirements.lock.linux`
   - 送入 pip 的过滤后 lock：**56 行，`grep -c -i pywin32` = 0**，且与单独跑过滤命令生成的 `/tmp/probe/req.linux.txt` **逐字节相同**（`cmp` 无输出）
   - 退出码 0；`/tmp/requirements.lock.linux` 已被 `rm -f` 清掉（`ls` 报 No such file）
3. **过滤后真的装得上**：`/opt/wage-venv/bin/python -m pip install --dry-run --ignore-installed --only-binary=:all: -r <过滤后 lock>`（宿主平台 = glibc 2.36 + cp311，即基底同类平台）⇒ `Would install … pandas-2.3.3 … greenlet-3.2.4 … python-magic-0.4.27 …`，**45 个包全部命中 wheel，无需任何编译器**。
4. **反向测试（闸门不是摆设）**：把 `requirements.txt` 追加 1 个换行后重跑同一段脚本 ⇒ `FATAL: requirements.txt sha256=6FA3BA55… 与 requirements.lock 头部 4BDA7936… 不一致`，退出码 **1**，且 stub 的调用记录文件根本没生成 ⇒ `pip install` **完全未被执行**（fail-fast 在装依赖之前）。复原文件后重跑恢复 0。
5. **残留复查的活性**：残留检查与粗过滤用的是同一个正则（`-i`），正常路径下确实不可能命中 —— 但它是防御「正则被改坏」的。用 `sed 's/grep -viE/grep -vE/'` 模拟「丢了 `-i`」的退化后，对同一份含 `PyWin32==311` 的 lock 立刻得到 `FATAL: 过滤后仍残留 pywin32，检查过滤正则`（退出码 1）；对照组（真脚本）同一份 lock 过滤后仍是 56 行 / 0 残留。

> 与 GH Actions 的关系：这一步是 `RUN` 层，在 runner 上与你本机无关地重跑一次；上面第 4 条意味着**「在 Windows 改了 `requirements.txt` 却忘了重生成 lock」会在 CI 上以明确 FATAL 拦下**，而不是产出一个依赖漂移的镜像。

### 风险 2 —— `python-magic` 运行期需要 `libmagic1`；且 build 期依赖不留最终层

**结论：`libmagic1` 已在基底安装层装好；镜像里**没有**任何 build 期依赖残留（因为根本不需要编译器）。**

证据：

1. `Dockerfile:39-41`：`RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 tzdata && rm -rf /var/lib/apt/lists/*`（**同一条 RUN** ⇒ `apt` 索引与 `libmagic1` 不在同一层留下，最终镜像不含 `/var/lib/apt/lists/*`）。
2. 运行期可用的实证（在本机 Debian 12 复算，同为 bookworm 基线）：
   - `dpkg -l`：`libmagic-mgc 1:5.44-3`、`libmagic1:amd64 1:5.44-3` 均已安装；
   - `apt-cache depends libmagic1` ⇒ **`Depends: libmagic-mgc`**（`--no-install-recommends` 也会带上这个硬依赖，故不会「装了却缺数据库文件」）；
   - `apt-cache policy libmagic1` ⇒ 候选版本 `1:5.44-3`，来源 `bookworm/main`，与基底同发行版（不会跨版本 ABI 错配）；
   - `ldconfig -p | grep magic` ⇒ `libmagic.so.1 => /lib/x86_64-linux-gnu/libmagic.so.1`；
   - `ctypes.util.find_library('magic')` ⇒ `libmagic.so.1`；`magic.version()` ⇒ `544`；
   - `magic.from_buffer(b'%PDF-1.4', mime=True)` ⇒ `application/pdf`（**这正是需求里点名的那次实测**）。
3. 当前代码尚未 `import magic`（`app/` + `scripts/` 全仓 `grep -rn "import magic"` **0 命中**），所以这一层是「为已钉版依赖准备运行时」，不会因为未使用而报错。
4. 无 build 期依赖残留的三条依据：① `--only-binary=:all:` 干跑显示 45 个包全部有 wheel ⇒ 不需要 `gcc`/`python3-dev`，Dockerfile 里也确实没有装；② `PIP_NO_CACHE_DIR=1`（`Dockerfile:29`）+ `pip install --no-cache-dir`（`:68`）⇒ 不留 wheel 缓存；③ `apt` 安装与 `rm -rf /var/lib/apt/lists/*` 在同一层。
5. 已知副作用（合理）：基底不含编译器 ⇒ 将来若有人往 `requirements.lock` 里加入**没有 wheel** 的包，构建会在 pip 阶段直接失败（fail-fast，而不是悄悄编译出一个巨大的镜像）。这属于**期望行为**，已在 `Dockerfile:16-19` 注释中写明基底约束。

### 风险 3 —— 运行时目录可写性（非 root）

**结论：只需要 `uploads/` 与 `uploads/temp/`（后者即 `TEMP_FOLDER`）两个目录；`instance/` 是防御性创建；二者在镜像内自建且属主为 `app`。** 已用非 root 实跑证明「不 chown 就 500/PermissionError」。

证据（口径：从源码取真实路径，不猜）：

1. `config.py:3` `basedir = os.path.abspath(os.path.dirname(__file__))` ⇒ `/app`；`config.py:24` `UPLOAD_FOLDER = os.path.join(basedir, 'uploads')` ⇒ **`/app/uploads`**；`config.py:29` `init_app()` 内 `os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)`。
2. `app/__init__.py:178` 再 `makedirs` 一次；`:181-183` 建 `os.path.join(UPLOAD_FOLDER, 'temp')` 并写入 `app.config['TEMP_FOLDER']` ⇒ **`/app/uploads/temp`**。导入端点（`app/main/routes.py` 的 8 处 `file.save(current_app.config['TEMP_FOLDER'] ...)`）落在这里。
3. 全仓 `grep -rn "instance_path"` **0 命中**；没有任何 `logging.FileHandler` 写 `logs/`。另有 4 处落盘走系统临时目录（`app/main/routes.py:5485/5574` 用 `tempfile.gettempdir()`、`:5682/5697` 用 `tempfile.mkdtemp()`），都在 `/tmp`，非 root 可写。
4. 镜像侧：`Dockerfile:83-88` 建 `/app/uploads/temp`、`/app/instance`，`chmod 755`，`chown -R app:app /app`。
5. **非 root 实跑复算**：把 `app/`、`main.py`、`config.py`、`migrations/`、`docker/`、`scripts/` 复制到 `/tmp/imgsim/app`，`chmod 755` 后 `chown -R 10001:10001`，用
   `setpriv --reuid 10001 --regid 10001 --clear-groups /opt/wage-venv/bin/python -m gunicorn -c docker/gunicorn.conf.py main:app`
   （`DATABASE_URL=sqlite:////tmp/probe/app.db` 指向**副本库**、`SEED_SQLITE_PATH` 指向不存在路径、`PORT=5099`）⇒ 启动成功、`GET /auth/login` **200**、`HEALTHCHECK` 那一行原样执行 **exit 0**、向 `uploads/temp/x` 写入成功（文件属主 uid=10001）。
6. **反向对照（证明 `chown` 真有必要）**：把 `uploads/temp` 改回 `root:root 755`，同样非 root 跑 ⇒ `PermissionError: [Errno 13] Permission denied`。
7. 附带证据：该次启动**没有**在 `uploads/`、`instance/` 或任何其他位置新增文件（`find -newer` 为空）⇒ `PYTHONDONTWRITEBYTECODE=1` 生效，没有隐藏写点。

### 风险 4 —— 真实数据库绝不能进镜像

**结论：镜像内不存在任何真实数据；`.dockerignore` 覆盖全部数据库文件名变体（本次补了两处漏网）；容器内数据库的正确落法是环境变量 + 挂卷 + 首次启动自愈建表。**

证据：

1. 默认库口径：`config.py:6-12` `_normalize_database_url()` 在 `DATABASE_URL` 为空时回退 `'sqlite:///' + os.path.join(basedir, 'app.db')` ⇒ `/app/app.db`（**这就是非 root + 忘挂卷时最危险的一条路径，`docker/entrypoint.sh:14-23` 会在启动前直接 FATAL 拦死**）。
2. 仓库内 DB 全清单（`find` 全深度）：`app.db`、`app.db.bak-20260811_133143`、`app.db.bak-20261009_004428/33/03/25`、`app.db.bak-rf1-20261009_033829`、`app.db.evidence-ALLOY-IMPORT-02-20261009_004539`（均 2 531 328 B）、`instance/app.db`（0 B）、`@eaDir/app.db.*@SynoEAStream` ×5，以及 **`app/data.sqlite`（49 152 B，git 已跟踪，7 张表，含 `alembic_version`/`user`/`audit_log` 等非空表）**。
3. 覆盖性验证（`.dockerignore` 改后语义模拟）：`app.db`、`app/data.sqlite`、`uploads/`、`instance/` 在构建上下文中的命中数 **全部为 0**。本次新增的 `*.sqlite`、`**/*.db*`、`**/*.sqlite*`（`.dockerignore:50-53`）正是为了兜住 `app/data.sqlite` 这类**嵌套**文件 —— 裸 `*.db` 只匹配上下文根那一层（改前实测 `app/data.sqlite` 确实漏进上下文）。
4. `app/data.sqlite` 的性质：全仓（除 `test-reports-2026-10/` 内的历史快照）`grep -rn "data.sqlite"` **0 命中** ⇒ 孤儿文件，无任何代码引用；不能靠它做容器首启自举。
5. 自举种子路径：`app/db_bootstrap.py:78-82` `seed_path_for(app)` ⇒ `SEED_SQLITE_PATH` 或 `<dirname(app.root_path)>/seed.db` ⇒ `/app/seed.db`；该文件**在仓库里不存在**，`bootstrap_if_empty()` 在 `:92` 判 `isfile` 后直接 return ⇒ **自举实际处于关闭态**（`scripts/check_db_bootstrap.py:69-71` 的真种子来自 `shutil.copy2(ROOT/'app.db', seed)`，同样不参与镜像）。
6. 建表口径（写进了 `Dockerfile:114-125`）：`app/__init__.py:239-247` 在 `create_app()` 内 `with app.app_context(): _ensure_schema(app)`，即 `db.create_all()`（`app/__init__.py:107`）+ `_ENSURED_COLUMNS`（`:21`）的启动自愈 ⇒ **空库首次启动自动建表**。**禁止 `flask db migrate`**（31 张表不在迁移历史里，自动生成迁移会与线上库冲突）；老库/新库统一 `flask db stamp p1nonctarget`，容器内可 `docker compose exec app flask db stamp p1nonctarget`（`FLASK_APP=main:app` 已就位）。
7. 真实库未被触碰：操作前后真实 `app.db` 的 `sha256 = b4fb980c5d1b25b3c3a0eadc12ecf01c75b36ebd213b109e5dd190c617eeaabe` **不变**；所有起服务/自举复算都指向 `/tmp` 下的副本库。

### 风险 5 —— WSGI 入口与端口

**结论：入口是 `main:app`，端口默认 5000；`Dockerfile` / `docker/gunicorn.conf.py` / `docker/entrypoint.sh` / `main.py` 四者自洽，且已用真跑复算验证。**

证据：

1. 入口事实源：`main.py` 只有 `from app import create_app` + `app = create_app()`；`wsgi.py` 同构同义（**仓库无 `run.py`**）。⇒ gunicorn 目标是 **`main:app`**，与 `Dockerfile:131` 的 `CMD ["gunicorn", "-c", "docker/gunicorn.conf.py", "main:app"]` 完全一致（本次把 `ENV FLASK_APP` 也改成 `main:app`，消除「CMD 用 `main:app`、CLI 用 `main.py`」的不一致）。
2. 端口事实源：`config.py` **没有**端口配置项；`main.py` 的 `if __name__ == '__main__':` 分支用 5000；`docker/gunicorn.conf.py` `bind = '0.0.0.0:%d' % _int_env('PORT', 5000)`；`Dockerfile:101` `EXPOSE 5000`；`HEALTHCHECK` 读 `os.environ.get('PORT','5000')`。**四处同为 5000**，且都可以用 `PORT` 覆盖（`docker run -e PORT=8080 -p 8080:8080` 时健康检查会跟着走，不会探错口）。
3. gunicorn 配置自洽性：`workers=_int_env('WEB_CONCURRENCY',2)`、`timeout=_int_env('GUNICORN_TIMEOUT',120)`、`graceful_timeout=30`、`keepalive=5`、`accesslog=errorlog='-'`（⇒ 日志进 `docker logs`，与 `PYTHONUNBUFFERED=1` 配合才有实时性）、`forwarded_allow_ips` 仅在显式设置时才写（避免在无反代时信任伪造的 `X-Forwarded-For`）。
4. 真跑复算：用仓库自带配置起真实 gunicorn（`python -m gunicorn -c docker/gunicorn.conf.py main:app`，Python 3.11.2 + lock 钉版，`DATABASE_URL` 指副本库）⇒ 正常启动并响应（结果见风险 6）。非 root（uid 10001）下同样启动成功（见风险 3 第 5 条）。
5. `docker/entrypoint.sh` 不设 `PORT`/不覆盖 CMD，只做 `exec "$@"`（`:31`），因此 `docker run` 时传入的 CMD 参数仍然生效（`$@` 语义正确）。

### 风险 6 —— HEALTHCHECK 探针必须真实存在且无需登录

**结论：探针 `/auth/login` 已核实存在、匿名可访问（200），超时/重试/`--start-period` 齐备；`/health` 与 `/login` 都**不存在**（会永久 unhealthy）。**

证据：

1. 路由事实源：`app/auth/routes.py:7-9` 同时注册 `@bp.route('/login')` 与 `@bp.route('/')` → `def login()`；`app/__init__.py:251` `register_blueprint(auth_bp, url_prefix='/auth')` ⇒ 真实路径 **`/auth/login`**。
2. 实测（本地起真 gunicorn，`curl -o /dev/null -w '%{http_code}'`）：

   | 路径 | 结果 | 说明 |
   | --- | --- | --- |
   | `/auth/login` | **200** | 无登录态也可访问（登录页本身）⇒ 可作探针 |
   | `/login` | 404 | 少了 `/auth` 前缀 |
   | `/health` | 404 | **本项目没有该路由**，凭空写它会让容器永远 unhealthy |
   | `/` | 302 → `Location: /auth/?next=http://127.0.0.1:5099/` | 未登录被弹登录页并带 `next`（不是 `/auth/login`） |

3. 探针参数（`Dockerfile:112`）：`--interval=30s --timeout=5s --start-period=30s --retries=3`；命令内 `urllib.request.urlopen(..., timeout=4)`。**内层 4s < 外层 5s** 是有意的：保证超时由探针自己抛异常退出（可读的 traceback），而不是被 docker 强杀成「超时且无输出」。`--start-period=30s` 给 `create_app()` 的启动自愈（`db.create_all()` + `_ensure_schema()`）留出时间，避免冷启动被判 unhealthy 触发重启风暴。
4. 探针命令原样执行（真 gunicorn + 副本库）⇒ **exit 0**；非 root 下同样 exit 0（风险 3 第 5 条）。
5. 用 Python 标准库而非 `curl`/`wget`：基底注释断言 slim 镜像不含这两个工具。**未在本容器独立验证**（无 docker 拉取镜像），但用 stdlib 在两种情况下都成立（`python` 一定在），属保守选择。

### 风险 7 —— 多架构 / 缓存 / 基底 tag

**结论：基底用明确 tag（非 `latest`）、Buildx + GHA 缓存已就位、**保持单架构 `linux/amd64`**；arm64 技术上可行（全部 wheel 有 aarch64 版本）但要以模拟构建的时长与双份缓存为代价。**

证据：

1. 基底：`Dockerfile:20` `FROM python:3.11-slim-bookworm` —— 明确 tag，不用 `latest`。注意它是**可变 tag**（3.11.x 补丁版本会前进），这是有意取舍：能在 CI 里自动吃到 Python 安全补丁；若需要位级可复现，可改成 `python:3.11.9-slim-bookworm` 或 `@sha256:…`，代价是必须有人定期手动升级。**当前不建议钉 digest**（钉死后安全更新会被静默跳过）。
2. 缓存：workflow 里 `docker/setup-buildx-action@v3` + `cache-from: type=gha` + `cache-to: type=gha,mode=max`（`:102-103` 与 `:129-130`）。依赖层（`COPY requirements.txt requirements.lock` + `pip install`）在 `COPY . .` **之前**，所以改源码不会让 45 个包的安装层失效 —— 这是 CI 用时的关键。
3. 多架构可行性（已实测）：用**完整 aarch64 标签阶梯**干跑解析（`--platform manylinux_2_17/24/25/26/27/28/34/35/36_aarch64` + `manylinux2014_aarch64` + `linux_aarch64`，`--python-version 3.11 --only-binary=:all:`）⇒ `Would install … numpy-2.0.2 … pandas-2.3.3 … greenlet-3.2.4 … psycopg2-binary-2.9.12 …`，**45 个包在 arm64 上同样全部命中 wheel**。
4. 为什么仍然只推 amd64：① GitHub 托管 runner 里 `ubuntu-latest` 只有 x86_64，arm64 要靠 QEMU 模拟，构建时长与不稳定度显著上升（本项目部署目标为 x86 服务器，无 arm64 需求）；② 多架构会同时占用两份 GHA 缓存（`mode=max`）并让 push 体积翻倍，逼近 Docker Hub 免费账号的拉取/存储配额。
5. 将来要开：把两处 `platforms: linux/amd64` 改成 `platforms: linux/amd64,linux/arm64` 即可（buildx 已就位）；届时建议改用原生 arm64 runner（如 `ubuntu-24.04-arm`）而不是 QEMU 模拟。
6. ⚠ 探测方法学（避免踩同一个坑）：pip 23.0.1 的 `--platform` 是**精确标签过滤**，不会向下展开 PEP600 阶梯。`--platform manylinux2014_x86_64` 会报 `ERROR: Could not find a version that satisfies the requirement pandas==2.3.3`（**假阳性**，pandas 2.3.3 的 cp311 wheel 只带 `manylinux_2_24_x86_64`/`manylinux_2_28_x86_64` 标签）；给 `manylinux_2_36_x86_64` 时连只带 `manylinux_2_17` 标签的 greenlet 都找不到。**判断 wheel 可得性时要么不给 `--platform`（用宿主平台），要么把整条阶梯都传进去。**
7. 由此推出的硬约束：基底 **glibc ≥ 2.28**（`manylinux_2_28` 是 pandas wheel 的最高要求）。bookworm = 2.36 ✓、bullseye = 2.31 ✓；Alpine(musl) 或更老基底会失去 wheel。

### 风险 8 —— `.github/workflows/` 现状与发布流水线

**结论：改造前**没有 PR 触发**（改动只有合进 `main` 后才会第一次被构建验证），也没有顶层 `permissions` 与 `concurrency`；现已补齐，并新增 PR 专用「只构建」job。`main` 上仍保留 `gate`（report-only 门禁）与 `build-and-push`（构建 + 推送）。**

证据（`yaml.safe_load` 真解析后的结构，工具：`PYTHONPATH=/tmp/pyyaml /opt/wage-venv/bin/python`）：

```
顶层键: ['name', True, 'permissions', 'concurrency', 'env', 'jobs']   # True 即 YAML 1.1 的 `on:`
触发: {"push": {"branches": ["main"]}, "pull_request": {"branches": ["main"]}, "workflow_dispatch": null}
permissions: {'contents': 'read'}
concurrency: {'group': 'docker-publish-${{ github.workflow }}-${{ github.ref }}', 'cancel-in-progress': False}
JOB gate             if=None                                   needs=None cont=True  steps=7
JOB build-and-push   if="github.event_name != 'pull_request'"  needs=None cont=None  steps=4
JOB build-check      if="github.event_name == 'pull_request'"  needs=None cont=None  steps=3
build-and-push push = True  | tags = ${{ env.IMAGE_NAME }}:latest + ${{ env.IMAGE_NAME }}:${{ github.sha }}
build-check    push = False | 含 login 步骤? False（PR 不需要 Secret，fork PR 也能过）
```

1. **触发条件**：`push → main`（构建 + 推送）、`pull_request → main`（只构建）、`workflow_dispatch`（手动，等同 push 路径）。
2. **权限**：顶层 `permissions: contents: read`；两个构建 job 各自再声明 `contents: read`。推送镜像靠 Docker Hub Secrets，与 `GITHUB_TOKEN` 权限无关。**不需要** `packages: write`（那是推 GHCR 才要的）。
3. **镜像名与 tag 策略**：`IMAGE_NAME=zerotwice/myerp`；push 路径打 `:latest` **和** `:${{ github.sha }}` 两个 tag（`sha` 用于可追溯回滚与固定部署，`latest` 供默认拉取）；PR 路径只计算 `:pr-<sha>` 但**不推送**。仅 main 推送 ⇒ 不存在「PR 覆盖 `latest`」的窗口。
4. **缓存**：`cache-from/to: type=gha`（`mode=max`），跨 run 复用依赖层。
5. **`gate` job 保持不变（仍 report-only）**：它跑 `test-reports-2026-10/harness/ci_gates.py --phase first --json …` 与 `ci_lint.py --phase first`，`continue-on-error: true` 且 `build-and-push` **不** `needs` 它 ⇒ 门禁失败不会拦住镜像发布。这不是遗漏，是仓内 `ci_lint.py` phase=first 的**硬判据**（见 §4.1），改成阻塞会直接把门禁自己弄红。
6. 需要 GitHub 侧配置的 Secrets（**只有两个**）：

   | Secret | 内容 | 说明 |
   | --- | --- | --- |
   | `DOCKERHUB_USERNAME` | Docker Hub 用户名（命名空间应与 `zerotwice` 匹配，或用有该仓库写权限的账号） | `docker/login-action` 的 `username` |
   | `DOCKERHUB_TOKEN` | Docker Hub **Personal Access Token**，权限至少 **Read & Write** | 不要用账号密码；PAT 可单独吊销 |

   配置位置：仓库 → Settings → Secrets and variables → Actions → New repository secret。fork PR **读不到** Secrets —— 这正是 `build-check` 故意不登录的原因。
7. 流水线之外、但**必须手工做一次**的一件事：在 Docker Hub 上**先把 `zerotwice/myerp` 建成 Private 仓库**。Docker Hub 在首次 `push` 时会自动创建不存在的仓库，而自动创建的仓库**默认是 Public** —— 那会把整个 ERP 镜像（含全部模板/业务代码）公开出去。见 §3 第 2 条。

---

## 3. 首次跑流水线：最可能出问题的三个位置 + 排查方法

### ① 第 1 位：Docker Hub 登录 / 推送被拒（会红）

**症状与日志指纹**（`docker/login-action@v3` 或 `build-push-action@v6` 步骤）：

| 日志 | 根因 | 处理 |
| --- | --- | --- |
| `Error: Username and password required` | 两个 Secret 至少有一个人是空的 / 名字拼错 | 逐字符核对 `DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN`（**大小写敏感**）；Secret 在 workflow 里必须写成 `${{ secrets.XXX }}`，写成 `${{ env.XXX }}` 拿不到 |
| `unauthorized: incorrect username or password` | `DOCKERHUB_USERNAME` 与 token 不属于同一账号，或 token 已被吊销 | 到 Docker Hub → Account settings → Personal access tokens 重新生成；确认 token 的 **Access permissions** 至少 `Read & Write` |
| `denied: requested access to the resource is denied` | 登录成功但**没权限推该命名空间** | `zerotwice` 是个人命名空间时，token 必须属于该账号；是组织时，token 所有者必须是该 org 的 member 且角色可写 |

**排查配方**（不需要 docker CLI，用 token 直接换 JWT 即可判定凭据本身是否有效）：

```bash
# 用同一个 token 换 JWT：返回 token 字段 = 凭据有效；401 = token/用户名有问题
curl -sS -H 'Content-Type: application/json' \
  -d '{"username":"<DOCKERHUB_USERNAME>","password":"<DOCKERHUB_TOKEN>"}' \
  https://hub.docker.com/v2/users/login/
```

（本容器实测：`https://hub.docker.com/v2/...` 在此环境**不可达/无响应**，该配方未能在此验证 —— 请在能上网的机器或 runner 上执行。pypi.org 在本容器可达，见 §4。）

### ② 第 2 位（不会红，但更严重）：首次 push 把仓库静默建成 **Public**

Docker Hub 对不存在的仓库执行 `push` 时会**自动创建**，且自动创建的仓库默认 Public。流水线会显示全绿，但「推送到私有 Docker Hub」的需求已经失败，且源码/模板全部公开可拉。

**排查**：跑完第一次后确认可见性 —— Docker Hub 网页 → 该仓库 → 右上角应显示 **Private**；或查 API：

```bash
curl -sS https://hub.docker.com/v2/repositories/zerotwice/myerp/ | grep -o '"is_private":[a-z]*'
# 期望 "is_private":true
```

**预防**：先在 Docker Hub → Create repository → Name=`zerotwice/myerp` → **Visibility=Private**，再跑流水线；组织账号可同时把 org 的默认仓库可见性改成 Private。

### ③ 第 3 位：依赖安装层（会红，且失败点明确）

`Dockerfile:52-69` 是唯一一处「会主动 fail-fast」的构建步骤，报错信息自带定位：

| 日志指纹 | 根因 | 处理 |
| --- | --- | --- |
| `FATAL: requirements.txt sha256=… 与 requirements.lock 头部 … 不一致` | 有人改了 `requirements.txt` 没重新生成 lock（**最常见的 CI 红**，尤其在 Windows 上改依赖时） | 在仓库根跑 `python -B scripts/check_doc_claims.py --write-lock` 后提交 |
| `FATAL: 过滤后仍残留 pywin32，检查过滤正则` | 过滤正则被人改坏（丢了 `-i`/锚点） | 恢复 `Dockerfile:53` 的正则；已用人为退化实验证明这道守卫生效（§2 风险 1 第 5 条） |
| `ERROR: Could not find a version that satisfies the requirement <pkg>==<ver>` | 钉版在 PyPI 上被 yank；或**基底被换成了没有对应 wheel 的平台**（见 §2 风险 7 第 6/7 条） | 核对是否改了 `FROM`；若确被 yank，走 `--write-lock` 流程升级钉版 |
| `E: Unable to locate package libmagic1` / apt 404 | runner 上 apt 源瞬时不可达或索引过期 | 直接 Re-run；持续失败则检查是否有自建 apt 镜像源设置 |
| 构建整体超时 | 网络慢（首次拉基底 + 45 个 wheel） | 已设 `timeout-minutes: 30`；Re-run 通常命中 GHA 缓存后大幅加速 |

**候补第 4 位**：基础镜像拉取被限流（`failed to resolve source metadata` / `429 Too Many Requests`）。首次拉 `python:3.11-slim-bookworm` 是匿名请求，runner 出口 IP 共享时偶发；Re-run 即可，持续复现可在 buildx 前置一层自建 registry mirror。

---

## 4. 验证证据清单（可复算）

> 所有命令都在仓库根 `/root/code/MyERP` 执行；解释器 `/opt/wage-venv/bin/python`（Python 3.11.2）。**本容器无 docker ⇒ 没有任何一条是 `docker build`**。

| # | 验证项 | 命令（口径） | 结果 |
| --- | --- | --- | --- |
| 1 | workflow 结构（真 YAML 解析） | `PYTHONPATH=/tmp/pyyaml /opt/wage-venv/bin/python -B test-reports-2026-10/harness/ci_lint.py --phase first` | **exit 0**，19/19 项通过，`yaml_validator=yaml.safe_load (PyYAML 6.0.3)` |
| 2 | workflow 结构（无 PyYAML 兜底路径） | 同上但不设 `PYTHONPATH` | **exit 0**，19/19 项通过，`yaml_validator=subset-lint` |
| 3 | Dockerfile 里那段 `RUN` 原样复算 | `awk` 抽出 `Dockerfile:52-69` → `/tmp/rbsim/block.sh`，在 `/tmp/rbsim/work`（真 `requirements.txt`+`requirements.lock`，`pip` 用 stub）`sh -c` 执行 | `OK: … sha256 一致（4BDA7936…）`，exit 0；stub 记录 `install --no-cache-dir -r /tmp/requirements.lock.linux`；过滤后 **56 行 / pywin32 0 命中**；临时文件已清理 |
| 4 | sha256 闸门反向测试 | 同上 + `printf '\n' >> requirements.txt` | `FATAL: … 与 … 不一致`，**exit 1**，stub 调用记录**未生成** ⇒ `pip` 未执行 |
| 5 | 残留守卫活性 | `sed 's/grep -viE/grep -vE/'` 造退化版 + lock 追加 `PyWin32==311` | `FATAL: 过滤后仍残留 pywin32，检查过滤正则`，exit 1；对照组（真脚本）56 行 / 0 残留 |
| 6 | 依赖 wheel 可得性（x86_64） | `pip install --dry-run --ignore-installed --only-binary=:all: -r <过滤后 lock>`（宿主平台 glibc2.36/cp311） | `Would install …` **45 包全部 wheel**，无编译器 |
| 7 | 依赖 wheel 可得性（arm64） | 同命令 + 完整 aarch64 阶梯 `--platform` | 同样 45 包全部命中 wheel |
| 8 | `.dockerignore` 语义审计 | 自写 `moby/patternmatcher` 等价实现 `/tmp/di_audit.py`（改前用 `HEAD` 版忽略文件，改后用工作区版） | 370→**298** 文件、20.58→**18.56** MiB、新排除 72 个、**新增入上下文 0**；`app.db`/`app/data.sqlite`/`uploads/`/`instance/`/`docs/`/`test-reports-2026-10/`/`__pycache__` 命中 **0** |
| 9 | WSGI/健康检查真跑（root） | `python -m gunicorn -c docker/gunicorn.conf.py main:app`（`DATABASE_URL` 指副本库、`PORT=5099`） | `/auth/login` **200**、`/login` **404**、`/health` **404**、`/` **302**→`/auth/?next=…`；HEALTHCHECK 那行 **exit 0** |
| 10 | 非 root 复算 | `/tmp/imgsim/app`（`chown -R 10001:10001`）+ `setpriv --reuid 10001 --regid 10001 --clear-groups …` | `/auth/login` **200**、HEALTHCHECK **exit 0**、写 `uploads/temp/x` 成功；`find -newer` 为空（无隐藏写点） |
| 11 | `chown` 必要性对照 | 同上但 `uploads/temp` 保持 `root:root 755` | `PermissionError: [Errno 13] Permission denied` |
| 12 | entrypoint fail-fast 矩阵 | `sh docker/entrypoint.sh echo REACHED` × 5 组环境 | 无 `DATABASE_URL` → **FATAL/exit 1**；`ALLOW_SQLITE=1` → WARN/继续；无 `SECRET_KEY` → WARN/继续；`SECRET_KEY=dev` → WARN/继续；全齐 → 无 WARN/继续 |
| 13 | 真实库未被触碰 | `sha256sum app.db` 前后对比 | `b4fb980c5d1b25b3c3a0eadc12ecf01c75b36ebd213b109e5dd190c617eeaabe` **不变** |

**未验证项（如实登记）**：① 没有真正执行 `docker build` / `docker push`（本容器无 docker，也无 Docker Hub 凭据）；② arm64 只是**依赖解析**可行，未做真实 arm64 构建；③ `HEALTHCHECK` 在真实容器里的调度行为（interval/start-period 的实际生效）未观测；④ 「slim 基底无 curl/wget」沿用既有注释断言，未在本容器验证（探针改用 stdlib 后该断言不影响正确性）；⑤ Docker Hub API 在本容器不可达 ⇒ §3 的两条 curl 配方未在此环境跑通。

### 4.1 与仓内 CI 门禁的关系（为什么不加 `needs: gate`）

`test-reports-2026-10/harness/ci_lint.py` 对 workflow 有硬判据（`ci_lint.py:180-183`、`:197-200`），phase=first 时要求：

- `build-and-push` **不得**出现 `needs`（否则 L-W4 失败）；
- `gate` 必须是 `continue-on-error: true`（否则 L-W5 失败）。

所以本次改动**刻意不引入 `needs: gate`**：gate 是 report-only 的观测位（A-63 第二步才切阻塞）。同时 `ci_lint.py` 走 subset-lint 兜底时会校验「所有行缩进为偶数」，本次新增内容（含 `concurrency`、`if:`、新 job）已按 2 空格步进书写，两条路径（PyYAML / 无 PyYAML）实测均 19/19 通过（§4 第 1、2 项）。

---

## 5. 需要人工在 GitHub / Docker Hub 侧做的事（一次即可）

1. **Docker Hub**：创建 **Private** 仓库 `zerotwice/myerp`（务必先建，理由见 §3 ②）。
2. **Docker Hub**：Account settings → Personal access tokens → 新建 token，权限 **Read & Write**。
3. **GitHub 仓库 → Settings → Secrets and variables → Actions**：新增 `DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN`。
4. **GitHub 仓库 → Settings → Branches**：给 `main` 加保护规则，要求 PR 且 **`build-check` 通过**才能合并 —— 这是「每次 push 前保证 Dockerfile 可被自动构筑」的制度化落地（若团队直接向 `main` 直推，则只能事后发现，见 §6 局限）。
5. （可选）**Settings → Actions → General → Workflow permissions**：保持默认只读即可，workflow 已显式声明 `permissions: contents: read`。

## 6. 局限与回滚

- **局限**：`build-check` 只在 **PR 到 main** 时运行。若绕过 PR 直接 push `main`，则 Dockerfile 的问题仍会推迟到 push 之后的 `build-and-push` 才暴露（此时 `main` 上已有一个可能构建失败的提交，但**不会推错镜像**：构建失败即不推送）。要彻底前置，请启用 §5 第 4 条的分支保护。
- **回滚**：三个文件都是纯增量/注释级改动，`git revert` 单个 commit 即可；若只想临时关掉 PR 构建，删掉 `.github/workflows/docker-deploy.yml` 的 `pull_request:` 块（`build-check` 会自动变为永不触发，无副作用）。
- 本次**未改动** `docker/entrypoint.sh` 与 `docker/gunicorn.conf.py`（复核为自洽，见 §2 风险 5/6），也未改动 `app/**`、`scripts/**`、`test-reports-2026-10/**`。
