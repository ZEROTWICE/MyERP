# 子智能体 / AgentTeams 成员模型路由（现行版 · 2026-10-11 修订：引入 p1234 三线制）

> 本件是 `/root/.dsh/profiles/web/cordis.patch.yml` 的 `system-prompt.personaSuffix` 里那 6 条约束的**仓库内同步副本**，
> 改动 profile 后请把本件一并更新（两边必须逐字一致）。机器可执行实现 = `/root/.dsh/quota-check/route.mjs`。

## 一、规则正文（逐字）

```
子智能体约束（派发 subagent / AgentTeams 成员前必须遵守；写在系统提示里，不受上下文压缩影响）：
1. 写代码的子智能体走【代码线】，最多 1 个并发：优先 provider=zai-coding-cn, model=glm-5.3（code plan）；仅当该 plan 的 5 小时额度**已激活且已用 >10%** 或周额度**已激活且已用 >90%** 时，才落 provider=p1234, model=cn:glm-5.3。**注意**：窗口读数显示 0 且 resetsAt 为空**不代表 plan 不可用**（实测：该读数下 plan 仍可用）⇒ 不得因「窗口未激活」而放弃 code plan。
2. 其余一切子智能体走【非代码线】，最多 1 个并发：优先 provider=volcengine-code, model=deepseek-v4-1-flash-260910（火山方舟_code）；仅当该 plan 的 5 小时额度**已激活且已用 >10%** 或周额度**已激活且已用 >90%** 时，才落 provider=deepseek-official, model=deepseek-flash。**注意**：其 5h 窗口常态读 0 且 resetsAt 为空，**不代表 plan 不可用**（2026-10-12 探针实测：该读数下 volcengine-code 正常执行 bash 任务）⇒ 不得因「5h 窗口未激活」而放弃它。
3. 【规划线】复杂问题、规划、拆解等任务（recon / 方案设计 / 任务拆解 / 架构评审），最多 1 个并发：固定 provider=p1234, model=cn:kimi-k3-1。它不占代码线与非代码线的额度，可与两者并行。判「规划」的口径：产物是方案/清单/拆解表，不是可直接跑的代码；若是「既想又写」的混合任务，按写代码走代码线。
4. 三条线【并行】、互不排斥（代码线 1 个 + 非代码线 1 个 + 规划线 1 个可同时跑）；同一线内超出的并发：代码线落 provider=p1234, model=cn:glm-5.3；非代码线落 provider=deepseek-official, model=deepseek-flash；规划线落 provider=p1234, model=cn:glm-5.3。
5. reasoning_effort 一律显式传 max。
6. 派单前先生成路由表：node /root/.dsh/quota-check/route.mjs（取额度 + 按上面的阈值算推荐路由）。本约束没有自动执行层：subagent 与 AgentTeams 都不会自己读额度或按本表选路 ⇒ 路由一律由主会话在派单时显式写入（实测：不传 provider/model 的子智能体落 agent-default-model = deepseek-official/deepseek-flash，而非主会话路由；传了就落指定位）。AgentTeams 成员必须在计划里逐个显式声明 provider/model/reasoning_effort=max，否则该成员落配置文件默认路由；running 团队的成员路由不可改，选错只能重建队。
```

## 二、为什么这么写（来自实测，不是偏好）

| 事实 | 证据 |
|---|---|
| `percent=0` **不等于**「额度充裕」，它可能是「窗口未激活」 | 成本台账 `planSamples`：`zai` 的 5h 窗口 66 条样本里 **27 条**为 `p=0` 且 `resetsAt=""`；最近一次非零样本 `p=39 / r=2026-10-11T00:05:10Z`。故 `plan-ok` 必须先判 `resetsAt` 非空 |
| 窗口读数 0/空**不代表 plan 不可用** | 2026-10-11 订正：`zai-coding-cn` 的 5h 读数为 0/空时 plan 依然可用（10-10 台账 256 calls；10-11 该 plan 在窗口读数恒 0/空的情况下仍被派过）⇒ 只按「已激活且超阈」才回落 |
| 不设 5h 阈值会把并发塞进快要触顶的 code plan | 用户实测：code plan 5h 限额不多，>10% 后可能不足以支撑子智能体完成任务 ⇒ 必须回落 |
| 周额度同样会触顶 | 用户实测：周额度也可经插件读取 ⇒ 已并入判据（>90% 不再用 code plan） |
| 三条线是并行而非先后 | 用户口径（2026-10-11）：代码线先占 `zai-coding-cn`、其余落 `p1234/cn:glm-5.3`；非代码线先占 `volcengine-code`、其余落 `deepseek-official`；规划线固定 `p1234/cn:kimi-k3-1`；三条线互不排斥 |
| 路由必须在**派单时**定死 | 实测两次：running 团队的 roster 不可改（错误原文 `a running team only permits update_task edits to pending, never-started tasks; roster and removal edits require a staged plan`） |
| 不传 provider/model ≠ 继承主会话路由 | 2026-10-11 实测：不传参派出的子智能体在成本台账里落 `deepseek-official:deepseek-flash`（+3 次调用）= 配置文件 `agent-default-model`，而非主会话路由；显式传了就落指定位 ⇒ 写什么落什么 |
| 子智能体被「自动停止」= 单次激活输出达 provider `maxTokens` | DSH 源码 `dsh-subagent/lib/index.js:618`：`case "max-tokens": return "<subject> ran out of room before it finished."`；`reasoning_effort=max` 的推理 token 与正文共享该预算 ⇒ 读大件后写长报告最容易触顶 |
| `p1234` 不查额度 | 用户口径：p1234 为代理路由（聚合上游），没有可读的 plan 额度接口 ⇒ 规划线与代码回落**固定路由、不判窗口**（`route.mjs` 里 usage 记 `n/a`） |
| 非代码线 5h 窗口「未激活」同样**不代表**不可用 | 2026-10-12 探针：刻意按旧规则该回落时，直接派 `volcengine-code/deepseek-v4-1-flash-260910` 执行 bash 探针任务 ⇒ 正常执行并回报（`VC-PROBE-OK` + UTC 时间）；同批读数 volcengine 周窗口活（0% / resetsAt 10-18）、月额度 28.7%。故删除旧规则「或 5h 窗口未激活 ⇒ 落 deepseek-official」，与规则 1 同口径（只按「已激活且超阈」回落，周>90% 仍守） |

## 三、自查

```bash
node /root/.dsh/quota-check/route.mjs --selftest   # 10 例判据矩阵（含边界 10% / 90% 与两侧窗口未激活）
node /root/.dsh/quota-check/route.mjs             # 取真实额度并打印推荐路由表（三条线）
```

## 四、已知遗留

- `zai-coding-cn` 与 `zai` 用的是**同一个**额度 endpoint（`open.bigmodel.cn/.../quota/limit`），实测两者四个窗口数字逐位相同；
  若两者实为**账户级**读数，则规则 1 的判据读的是与 plan 无关的数 —— 尚未证伪，按「保守取更严者」处理。
  （2026-10-11 修订后：代码线**回落**已改走 `p1234/cn:glm-5.3`，`zai` 仅在「code plan 不可用且 p1234 也不可用」的人工兜底场景出现，不再出现在自动路由表。）
- 成本台账 `planSamples` 只采样了 `['volcengine','zai']` 两个键，没有单独的 `zai-coding-cn` 键；本件按同一读数评估 code plan。
- `p1234` 没有额度接口，规则 3 的规划线与规则 1/4 的 `p1234` 回落是**无条件固定路由**；若 p1234 上游本身不可用，路由表不会自动发现 —— 需要人工兜底（先派一个轻量探针验证）。
- 「规划」与「写代码」的边界靠主会话判断（产物是不是可直接跑的代码）；判错只会错配模型，不会破坏功能，按保守口径（混合任务走代码线）处理。
