# DEP-01 依赖清理登记

- **触发**：用户 m00874 —— 「现在做出修改，文件只会在Windows上测试，Docker中部署，和Jenkins无任何关系。」
- **口径**：部署面只有 Docker（`Dockerfile` / `python:3.11-slim-bookworm` → GH Actions → 私有 Docker Hub `zerotwice/myerp`）；
  Windows 只做本地测试；Jenkins 与本项目无关（`Jenkinsfile` 保留为历史件，不再计入部署路径）。
- **性质**：删除类改动（无新增抽象、无新增依赖、无新增运行时行为），仅收窄依赖面 + 修正一处门禁判据缺陷。
- **登记时点**：2026-10-10

---

## 1. 改动前 baseline（现场读数）

| 项 | 改前值 | 工具/口径 |
|---|---|---|
| `requirements.txt` 声明条数 | **23** | `grep -cv '^#\|^$' requirements.txt`（与 `52-V13-TL050607-工具链收尾.md:184` 记录一致） |
| `requirements.lock` 钉版条数 | **45** | `check_doc_claims` lock 判据层（`52-V13…:35/:60/:184/:192`） |
| `requirements.lock` 体积 / sha256 | **2002 B / `32D4911D128C23B5DAA7DAAE827555C14F3ED19A09893EF53592C234788B2D48`** | `52-V13…:44` |
| lock 生成平台 | **win32 / Python 3.9.21**（解释器 `F:\Miniconda\envs\wage\python.exe`） | lock 头 `# 平台:` |
| `check_doc_claims --selftest` | **16/16** | 判据层自检 |
| `check_doc_claims`（默认域，无 `--coverage`） | violations=**11**（全为 `evidence/harness/coverage.json` 权威源结构性缺失） | 现场实测 |
| `check_doc_claims --coverage <run 产物>` | violations=**0** | 现场实测 |

## 2. 改动文件与改后值

### 2.1 删除：`diagnose_product_edit.py`（125 行）
一次性 HTTP 诊断脚本（`import requests` / `from bs4 import BeautifulSoup`），零引用（仅 `docs/test-reports/2026-10/06-测试工具链评估.md:285,:382` 把它列为待清理项 P2-4）。
它是 `requests` + `beautifulsoup4` 在本仓的**唯一**使用者 ⇒ 删掉它，这两个声明失去存在理由。

### 2.2 `requirements.txt`：23 条声明 → **20 条**
移除 3 条声明及其小节注释：

```
- # Web请求（用于诊断工具）
- requests>=2.31.0
- beautifulsoup4>=4.12.0
- # 文件类型检测
- python-magic>=0.4.27
```

移除依据（工具 + 值）：

| 包 | 全仓引用实测 | 结论 |
|---|---|---|
| `requests` | 仅 `diagnose_product_edit.py:1` | 随脚本删除而失效 |
| `beautifulsoup4` | 仅 `diagnose_product_edit.py:3,15,92` | 同上 |
| `python-magic` | **`import magic` 全仓 0 处**；`Dockerfile:35-36` 自述「当前代码路径尚未 import magic」 | 未使用 |

**保留项及理由（不作 YAGNI 处理）**：
- `Flask-Paginate>=2023.10.24` —— 非死依赖：`app/main/routes.py:32` `from flask_paginate import Pagination`、`:5141` 唯一构造点，`app/templates/main/search/pagination.html` 消费其 `has_prev` / `prev_num` / `iter_pages()`。移除它要另写分页对象 = 净增代码，不划算。
- `numpy>=1.24.0` —— `pandas` 的传递依赖，显式声明属既有口径。

### 2.3 `requirements.lock`：45 条钉版 → **33 条**（体积 2002 B → **1642 B**，sha256 → **`621C65C45E80651356C5F6D25645C74F0243CFF51FD35DD7D140F505310BB47B`**）
用权威工具重生成（唯一写操作）：

```
/opt/wage-venv/bin/python -B scripts/check_doc_claims.py --write-lock
```

新锁头：

```
# 解释器：/opt/wage-venv/bin/python
# 平台：linux / Python 3.11.2
# requirements.txt sha256: F2CEB9799F2D899CF54992A99428C472B5584E5867ECE46BFD7A5784C4B45846
# env-exceptions: (none)
```

消失的 12 条钉版，分三类：

| 类别 | 包 | 原因 |
|---|---|---|
| 本次清理目标（7） | `requests` `beautifulsoup4` `soupsieve` `certifi` `charset-normalizer` `urllib3` `python-magic` | 声明已移除 |
| win32 专有（2） | `pywin32` `colorama` | 环境标记 `sys_platform == "win32"` 在**本平台求值为假** |
| py<3.10 回填（3） | `importlib-metadata` `tomli` `zipp` | 本平台 Python 3.11 不再需要 |

**平台口径变更（有意的）**：lock 由「win32 / Python 3.9.21 交付件」变为「linux / Python 3.11 部署件」，与唯一部署面
（`Dockerfile` 基底 `python:3.11-slim-bookworm`）同平台。这是本次改动的**目标状态**，不是副作用。
**Windows 测试面不受影响**：`requirements.txt` 中 `pywin32>=305; sys_platform == "win32"` 的标记仍在，
Windows 上按 `requirements.txt` 安装即可获得 pywin32；lock 不再承担 Windows 交付职责。

### 2.4 `Dockerfile`
1. **`:40` 去掉 `libmagic1`**：`apt-get install -y --no-install-recommends tzdata`。依据：`libmagic1` 是
   `python-magic` 的运行时依赖，声明已移除且代码从未 `import magic` ⇒ apt 包失去理由（少一个系统包、少一份攻击面）。
2. `:34-50` 注释块改写：原文称 lock「生成平台是 win32 / Python 3.9.21，因此含 pywin32==311」——改动后**该前提已假**，
   注释与硬编码的 `requirements.txt` sha（`4BDA79…`）一并更新/移除。
3. `:52-56` 的 pywin32 构建期过滤**保留**并改述为**防御**：lock 现由 Linux 生成、本不含 pywin32，但
   `requirements.txt` 仍声明 win32 标记件，一旦有人在 Windows 上重生成 lock，pywin32==311 会被烘回来且 Linux 无 wheel
   ⇒ 保留一次无条件过滤（现为空操作）作为护栏。`:57-67` 的「lock 头 sha256 ↔ 镜像内 requirements.txt」一致性校验**原样保留**。

### 2.5 `scripts/check_doc_claims.py`（门禁判据层）
改动 1 —— 生成器头串失真修正（不再断言 lock 是 Windows 交付件、不再断言 env-exceptions 里的包「未安装于 canonical env」）。

改动 2 —— **`check_lock` 的「声明依赖未进 lock」判据改为标记感知**，A-70 三步留档：

| 步骤 | 内容 |
|---|---|
| ① 改前值留档 | 原判据（`check_lock`）：对 `requirements.txt` 的**每条**声明，只要名字不在 lock 的钉版集合中就判违规，**不求值环境标记**。 |
| ② 阴性对照先红 | 该判据的缺陷是**潜伏的**：旧 lock 由 Windows 生成、内含 `pywin32==311`，判据因而恰好通过（`selftest 16/16`）。lock 改由 Linux 生成后缺陷立即显形 —— `--selftest` 变为 **15/16**，`DC-L1 真实 lock + requirements` 报 `['声明依赖未进 lock：pywin32']`。即**工具生成物被工具自己判红**。 |
| ③ 改后值 + 登记 | 判据改为：声明带环境标记且**在本平台求值为假** ⇒ 不进 lock 是**正确**的，记 WARN 放行；标记为真或无限定 ⇒ 仍必须进 lock。改后 `--selftest` 回到 **16/16**，`check_lock(真实 lock, requirements.txt)` violations=NONE。与 `build_lock_content`（生成侧本就按 `marker.evaluate(env)` 跳过）口径一致。 |

## 3. 验证证据（工具 + 口径 + 值）

| # | 验证 | 命令/口径 | 实测 |
|---|---|---|---|
| V1 | lock ↔ 声明 sha256 一致 | 复现 `Dockerfile:57-64` 的 shell 判据 | `OK: F2CEB9799F2D899CF54992A99428C472B5584E5867ECE46BFD7A5784C4B45846` |
| V2 | 依赖层过滤块可执行 | 复现 `Dockerfile:52-56`（`grep -viE pywin32` + 残留自检） | 过滤后 33 条 = 原始 33 条，残留自检未触发 |
| V3 | 门禁判据层自检 | `check_doc_claims --selftest` | **16/16 通过**（改后）／15/16（缺陷显形时）／16/16（改前 Windows lock） |
| V4 | 口径 + 依赖钉版守卫 | `check_doc_claims --coverage test-reports-2026-10/evidence/harness/ci-run-20261009-233226/coverage.json` | `lock：33 条钉版 / 环境匹配 33 条 / exception 0 条`；`RESULT: OK（violations=0）` |
| V5 | 属性/列守卫 | `check_properties.py` | `已扫描 25 个文件，模型类 74 个` → `RESULT: OK` |
| V6 | 模板守卫 | `check_templates.py --phase first` | `RESULT: OK` |
| V7 | **判据修改的阴性对照** | 在真实声明面追加 `totally-absent-pkg>=1.0`（无限定标记）后调 `check_lock` | 仍判违规：`['声明依赖未进 lock：totally-absent-pkg']` ⇒ 护栏未被削弱 |
| V8 | 判据修改的阳性对照 A | 追加 `winpkg>=1.0; sys_platform == "win32"`（本平台为假） | 违规 none（放行）+ WARN「本平台为假，不进 lock」 |
| V9 | 判据修改的阳性对照 B | 追加 `linuxpkg>=1.0; sys_platform == "linux"`（本平台为真） | 仍判违规：`['声明依赖未进 lock：linuxpkg']` ⇒ 标记为真时照样强制 |
| V10 | 代码残留引用 | `grep -rn "^import magic\|import requests\|from bs4" app/ scripts/ main.py config.py wsgi.py` | 0 命中 |
| V11 | 应用可导入回归 | `/opt/wage-venv/bin/python -B -c "import app"` | `✓ import app OK` |
| V12 | 二次生成幂等 | 连跑两次 `--write-lock` | 钉版集合稳定（33 条，仅锁头「生成时点」行变化） |

> **环境限制（如实登记）**：本容器**无 `docker` CLI**，V2 用「离线复现 `Dockerfile` 依赖层 `RUN` 块的等价 shell」替代真实
> `docker build`。真实镜像构筑证据以 push 后 GitHub Actions 的 `build-check` / `build-and-push` 作业为准；
> 该作业同时会执行 V1 的一致性门（`Dockerfile:57-64`），不一致即 fail-fast。

## 4. 未处理的相邻项（留给后续批次，此处仅登记不实施）

- **`Jenkinsfile` / `scripts/deploy.bat`**：`m00874` 已界定 Jenkins 与部署无关；`deploy.bat:153` 与 `Jenkinsfile:251`
  在上一个安全批次里改为 `pip install -r requirements.lock`（CWE-1104 修法），现 lock 已为 Linux 件 ⇒ 这两条 Windows/CI
  路径若仍被使用，应改回 `requirements.txt`（带 win32 标记）或另生成 Windows 专用 lock。**本批次未动**。
- `52-V13-TL050607-工具链收尾.md:35/:44/:60/:75/:184/:192/:217` 记有「45 条钉版 / 23 条声明 / lock 2002 B / `32D4911D…`」
  等**历史读数**。经核验它们不被 `check_doc_claims` 扫描（不在 `<!-- caliber-table -->` 块内、非 RETIRED 模式），
  按 append-only 纪律**保持原样**，以本文件作为其时效性分界。
- `PYPI_FALLBACK = {'psycopg2-binary': '2.9.12'}` 现为空转（该包已实际安装于 canonical env）；保留为安全兜底，未删。
- ponytail-audit 的其余删除项（两棵 bootstrap 死树 `app/static/bootstrap/**` + `bootstrap-5.3.3-dist/**`
  ≈163,368 行、`app/utils/excel_utils.py`、`工具/工价转换.py`、`merge_and_upgrade.py`、被跟踪的 `app.db.bak-20260811` 等）
  **不在本次范围**，待独立批次。
