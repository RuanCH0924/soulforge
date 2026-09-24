# Soulforge — 工作日志标准化（M15）开发方案

> 配套文档：[DEVELOPMENT.md](DEVELOPMENT.md)（模块矩阵）、[ROADMAP.md](ROADMAP.md)（版本规划）、[UI-SPECS.md](UI-SPECS.md)（交互规范）。
> 规则来源：外部 skill `memory-daily-standardizer`（`.trae/skills/memory-daily-standardizer/SKILL.md`，创建于 2026-07-03）。
> 适用范围：指定 Agent 工作空间下 `memory/` 目录的**每日工作日志**整理。
> 状态：**P0 / P1 / P2 / P3 已交付**，预设已收口（WORKLOG 只保留 `preset-wlog-daily-std` 一个），
> 并支持模型决策「本日无可归档内容」（不产出日文件，见 6.3）。

### 修订记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-23 | 初版：方案选型（skill 文档化 + 流程代码化）、需求/选型/架构/流程/测试/部署六模块、排期与验收标准 |
| v1.1 | 2026-09-23 | 按已确认决策收敛范围：移除 corpus / dreaming（D、E 两类）与外部来源；触发方式定为手动批次（不做定时）；批次粒度为单 Agent；碎片删除不留痕、输出不写来源 |
| v1.2 | 2026-09-23 | **P0 已交付**：新增内置预设「工作日志日标准化」、AI 整理 prompt 接通 `style_rules`；补充 P0 前置改造第 3 项（修复 `FormatValidator` 表格假阳性——实测确认「关键决策」表格会被误判并遭 `auto_fix` 插空行破坏，是 P0 的阻塞项） |
| v1.3 | 2026-09-23 | 补 P0 前置改造第 4 项：`seed_builtins()` 改为「首次空表全量 + 存量只补种 `BUILTIN_PRESETS_ADDED` 白名单」，修掉「新增内置预设进不了存量安装、P0 交付物不可见」的缺口 |
| v1.4 | 2026-09-24 | **P1 已交付**：A/B/C 分类器（`DailySourceScanner`）+ 12 条确定性预处理器（`DailyPreprocessor`）+ 单日「多来源 → 1 文件」归并（`DailyMergeService`），含 4 个场景集成测试；补充两条实测定下的边界（只扫 `memory/` 顶层、`YYYY-MM-DD-HHMM-2` 归 B）与附录 C（预处理 12 规则清单） |
| v1.5 | 2026-09-24 | **P2 已交付**：批次表 `daily_runs` / `daily_run_items` + `DailyRunService`（幂等键 / 天数与 token 上限 / 后台逐日生成 / 批次级写前预检 / 乐观锁 / 碎片清理 / 验收报告）+ 6 个 API 端点 + Tools 页「日志标准化」tab（三阶段：参数 → 逐日确认 → 验收报告）；新增附录 D（批次状态机与 API 契约）。批量 apply 的语义在此定型：**任一天不过写前预检 → 整批不写** |
| v1.6 | 2026-09-24 | **P3 已交付**：三种规则投递形态（`doc_full` / `trimmed` / `system_embedded`）+ 对比台 `backend/daily_form_bench.py`，实测报告见 [M15-EFFICIENCY-REPORT.md](M15-EFFICIENCY-REPORT.md)；默认形态定稿；新增附录 E（运维手册）。**同时修掉两个实测拦死写入的缺陷**：`forbid_raw_html` 把 `` `session:<id>` `` 这类占位符误判为 HTML；`sanitize()` 漏剥推理模型的 `<think>` 思考块 |
| v1.7 | 2026-09-24 | **预设收口（P3 后补记）**：`preset-wlog-summary`「工作日志汇总」并入 `preset-wlog-daily-std`（章节扩为 5 条，新增「五、明日计划」；补「按时间倒序归档」规则），WORKLOG 类型只保留一个预设——两个并列选项的语义歧义（单文件整理 vs 逐日归并）就此消除；`presets` 表加 `retired_at`，存量安装走「刷新 / 退役」内容锚点迁移（用户改过的一律不动） |
| v1.8 | 2026-09-24 | **「本日无可归档内容」出口**：此前 prompt 写死 H1 + 强规则强制章节齐全，模型没有合法出口，全天噪音的日子只能凑数。现给模型第二个合法出口（只回一行 `无可归档内容：<理由>`），命中则**不产出日文件**，只清 B/C 碎片、**A 类主文件 `YYYY-MM-DD.md` 保持不动**；新增逐日状态 `empty`、`daily_run_items.empty_reason` 列，验收报告对空日只核对「碎片已清」。新增 §6.3 与 3 条验收标准。另明确**主文件定义** = `memory/YYYY-MM-DD.md` 精确命名（系统自动生成的日文件） |
| v1.9 | 2026-09-24 | **失败归因修正（P3 后补记）**：排查 17:46 批次失败时确认两个缺陷——① `detect_residual_shells()` 把 M11/M12「编码·空白归一」也当壳检测，导致**任何合规文档只要结尾带换行就被判「有残留」**（写前验收误拦 + 验收报告 `no_residue` 误报），现口径收窄到真壳规则 `SHELL_RULES`（M01~M10），报错改用规则名（`describe_shells()`）；② `LLMClient` 从不读 `finish_reason`，输出被 `max_tokens` 截断时被报成「强规则未通过」（谎报失败原因），现截断自动重试 1 次（预算翻倍、封顶 32768），仍截断则抛 `LLMOutputTruncatedError`（`422` / `LLM_OUTPUT_TRUNCATED`）并提示调大 provider 的 `max_tokens`。§9.2 新增第 12 条验收标准 |
| v1.10 | 2026-09-24 | **预设边界与页内管理（P3 后补记）**：日志标准化预设与主工作台文档预设彻底分开——判据 `target_file_type=WORKLOG`；M15 界面新增预设信息栏（徽章「大模型专用」+ 版本 + 来源 +「查看 / 编辑」）与页内编辑器（用途说明 / 模板文档 / 风格与内容规则三类，比设置页表单多出 `style_rules`），保存即 version+1、新批次生效；设置页「文档预设」与主工作台「应用预设 / AI 整理」改取 `?scope=workbench`，不再出现日志预设 |

---

## 一、背景与目标

### 1.1 问题

OpenClaw Agent 的工作空间里，`memory/` 目录长期存在三类碎片：

- 同一天既有标准日文件，又有带时间戳或主题后缀的 session 导出（如 `2026-05-20-1415.md`、`2026-05-06-feishu-card-timeout.md`）
- session 导出里夹着大量对后续检索无价值的元数据壳（`Session Key`、`Conversation info (untrusted metadata)` 整段 JSON、`Sender` JSON、`Queued messages while agent was busy` 等）
- 内容里混有对话腔噪音（"让我检查一下""喵呜～"）与重复流水（轮询、失败重试、HEARTBEAT_OK）

结果是：**同一天读出多个文件**、**信息密度低**，后续做月度归纳与全文检索都不稳定。

### 1.2 目标

把指定 Agent `memory/` 下某段日期范围的工作日志，整理成**每天恰好 1 个 `YYYY-MM-DD.md`** 的标准结构，并保证：

1. 每个日期只保留 1 个标准文件
2. 同日碎片文件整理后被删除
3. 内容是「工作日志 / 关键信息」形态，不保留大段低价值元数据
4. 后续可直接用于月度归纳、检索、对比

### 1.3 规则来源的三层拆解

外部 skill 的规范可拆成三层，本方案的架构完全对应这三层：

| 层 | 内容 | 性质 | 承载方式 |
|---|---|---|---|
| **产物契约** | 每天 1 个 `YYYY-MM-DD.md`；H1 为 `# 工作日志 - YYYY-MM-DD`；固定 5 章节（今日概览 / 关键事件 / 关键决策 / 待办事项 / 明日计划）；碎片整理后删除。**例外**：全天无可归档内容时由模型判定，该日不产出文件（见 6.3） | 可机械校验 | `TemplateRules` + `FormatValidator`（**强规则**） |
| **语义规则** | A–C 类来源识别与优先级；高价值清单；低价值删除清单；只留结论不留过程；对话腔改写为客观记录 | 需 LLM + 人工确认 | 技能文档正文 + `style_rules`（**弱规则**） |
| **默认原则** | **默认不做脱敏**（仅用户明确要求时才处理）；目标是"有用"而非"最短" | 硬约束 | 写入技能文档 + UI 明示 |

---

## 二、范围与边界

### 2.1 已确认的决策（来自需求方）

| # | 决策 | 影响 |
|---|---|---|
| 1 | **忽略 corpus / dreaming 相关内容**（SKILL.md 的 D、E 两类不实现），不引入外部来源目录 | 来源从 5 类收缩为 3 类；**删除「缺失补齐」整块能力**；不需要扩展文件扫描域 |
| 2 | **只做「手动一键 + 批次确认」**，不做定时调度 | 不引入 Scheduler；无 `interval_hours` 配置；交互固定为「选范围 → 出计划 → 确认 → 执行」 |
| 3 | **范围是全部 Agent，但一次只处理一个 Agent 的 `memory/` 目录** | 批次参数 `agent_id` 必填；不提供「全部 Agent」批量；预设与 provider 无需按 Agent 隔离 |
| 4 | **归档后删除原文件，可以不留痕；不要求在合并内容中写明来源** | 碎片直接 `send2trash`，不做批次归档副本；输出模板去掉全部来源引用行 |

### 2.2 纳入范围（In Scope）

- 指定 Agent `memory/` 下日文件名模式（`YYYY-MM-DD.md` / `YYYY-MM-DD-HHMM.md` / `YYYY-MM-DD-<topic>.md`）的扫描与分类
- 低价值元数据壳的**确定性预处理剥离**（不进 prompt，零 token）
- 同日多来源 → 1 个标准日文件的 LLM 归并
- 碎片文件删除（经系统回收站）
- 批次级计划 / 差异确认 / 执行 / 验收报告
- skill 规则作为**版本化文档**管理（可编辑、可回溯）

### 2.3 明确不做（Out of Scope）

| 不做项 | 理由 |
|---|---|
| session corpus（`.txt`）读取与反建日文件 | 需求方明确忽略；且来源可能在 workspace 之外，需要额外的路径白名单与只读保证 |
| dreaming 产物提炼 | 同上 |
| 定时 / 无人值守自动整理 | 需求方明确只要手动批次 |
| 敏感信息脱敏 | skill 明确「默认不脱敏」，仅在用户显式勾选时处理 |
| `memory/` 下长期记忆类文件（如 `lessons.md`、`<topic>.md`）的改写 | 不属于「每日工作日志」；分类器必须显式排除 |
| 跨 Agent 一致性比对、月度归纳 | 属其它能力（lint 的 drift 规则、`memory-summarize` skill 领域） |

---

## 三、技术选型

### 3.1 待评估的两个方案

- **方案一**：skill 定义为独立显式文档，配置大模型在每次执行整理任务时加载该文档
- **方案二**：把 skill 的业务规则、整理要求、标准工作流直接嵌入功能逻辑与大模型的系统提示词

### 3.2 对比

| 评估维度 | 方案一（独立文档，任务时加载） | 方案二（内嵌逻辑与系统提示词） |
|---|---|---|
| 规则可迭代性 | ✅ 改文档即生效，无需发版 | ❌ 每次调整都要改代码 + 发版 + 重启 |
| 可追溯 / 审计 | ✅ 文档可版本化、可 diff、可回溯（现有 `preset_versions` 直接可用） | ❌ 规则藏在代码里，无法还原历史批次用的是哪版规则 |
| Prompt 体积 / 成本 | ✅ 可按来源类型**裁剪注入**（C 类主题文件只需"事件提炼"段） | ❌ 常驻 system prompt，每轮都付全量 token，随规则增长持续膨胀 |
| 输出一致性 / 可复现 | ⚠️ 中：文档改动会影响后续批次，需把版本绑定到批次 | ✅ 高：同一版本行为固定 |
| 实现复杂度 | ✅ 低：`AIJobService._build_prompt()` 已经在注入 `preset.template_md` | ⚠️ 需重构提示词层，且与既有预设机制功能重复 |
| 与既有系统契合 | ✅ 与 M11 文档预设 + 版本历史 + UI 编辑完全同构 | ❌ 形成第二套规则源，与预设机制冲突 |
| 可扩展（多 skill） | ✅ 一个 skill = 一条预设记录，天然多套并存 | ❌ 系统提示词只有一份，多 skill 互相打架 |

### 3.3 选型结论

**选方案一**，并明确两条边界：

1. **规则放文档**：SKILL.md 落成一条版本化文档预设（`target_file_type = WORKLOG`，与
   `preset-wlog-daily-std` 及前端「按文件名推断适用类型」的口径一致——原先与此并列的
   `preset-wlog-summary` 已于 P3 后并入本条，见 6.1 第 2 点），采用
   **任务前由代码注入 prompt** 的形态——而非让模型自主调工具读取文件（那会多一轮 tool call 并把全文 token 翻倍）。
2. **流程放代码**：扫描、分类、预处理、按天归并、碎片删除、验收全部是确定性逻辑，不进 prompt。
   它们要幂等、要审计、要能失败重试，交给模型只会引入不确定性。

**方案二仅在一个子场景成立**：把"输出契约"编译成 `TemplateRules` 交给 `FormatValidator` 强制执行——
这是方案一的组成部分，不是替代方案。

### 3.4 既有能力盘点与缺口

| 能力 | 现状 | 结论 |
|---|---|---|
| LLM 多 provider + 热加载 + key 加密 + 连通性测试 | 已有（M12） | 直接复用 |
| 预设 CRUD + 版本历史 + 回溯 | 已有（M11，`presets` + `preset_versions`） | 直接复用为「技能文档管理」 |
| 模板规则解析 + 格式校验/机械修正 | 已有（`template_rules` + `FormatValidator`） | 直接复用为**强规则**层 |
| 写前自动备份 + 审计 + `send2trash` + `_safe_join` | 已有（`FileManager`） | 直接复用 |
| plan → diff → 确认 → 执行 两步流 | 已有（`ApplyPresetModal` / `AIJobService`） | 复用交互与数据形态 |
| **`style_rules` 接入 prompt** | ❌ `_build_prompt()` 只注入 `template_md`，**完全没用到 `style_rules`**，与 [DEVELOPMENT.md](DEVELOPMENT.md) 模块 M13 章节的声明不符 | **必须补**（既有文档↔实现漂移，也是本方案的必需品） |
| **批次级编排** | ❌ `AIJobService.execute()` 是单文件读 → 单文件写，不支持「同日 N 来源 → 1 文件」+ 碎片删除 | 新增编排层，不改动既有单文件路径 |
| **单来源体积处理** | ⚠️ 单文件 30KB 上限（`AI_FILE_SIZE_LIMIT`）；单日 session 导出可能超限 | 新增分块摘要 / 转人工复核兜底 |
| **重命名 / 移动文件** | ❌ 无此 API | **本方案不需要**：归并 = 写目标文件 + 删除碎片，无重命名动作 |

---

## 四、需求分析

| 诉求 | 具体要求 | 验收口径 |
|---|---|---|
| **格式标准化** | 每天恰好 1 个 `YYYY-MM-DD.md`；H1 为 `# 工作日志 - YYYY-MM-DD`；5 章节齐全且顺序正确 | 100%；不出现空章节凑数；**全天无内容的日子不产出文件**（模型判定，需给理由） |
| **内容分类** | 来源自动分 A / B / C 三类（见附录 A），排除长期记忆文件 | 分类准确率 100%（纯正则，不允许模糊） |
| **去重合并** | 同日多来源合并为 1；跨来源重复事件只保留信息量最大的一条；不丢失任一方独有事实 | 关键事实保留率 ≥ 95% |
| **关键信息提取** | 保留：明确问题与根因 / 修复方案与结果 / 用户做出的选择 / 配置项含义与变更 / 模型·工具·技能·cron 行为 / 安全审计结果 / 可复用数据（余额、盘中收盘、日报）/ 文档与文件产出 / 未决问题与待办 | 高价值项缺失需人工复核 |
| **噪音剥离** | 删除：`Session Key`·`Session ID`·`Source` / `Conversation info (untrusted metadata)` JSON / `Sender (untrusted metadata)` JSON / `Reply target of current user message` 壳 / `Queued messages while agent was busy` / 重复的"让我检查一下"类过渡语 / 单纯重复的 `HEARTBEAT_OK`；只留结论不留过程；对话腔改写为客观记录 | 低价值元数据壳残留 = 0（口径 = 真壳规则 M01~M10；M11/M12 是编码·空白归一，不算残留，见 9.2 第 4 条） |
| **归档存储** | 碎片文件整理成功后删除（经系统回收站，可恢复）；不保留额外归档副本 | 删除成功率 100% |
| **来源标注** | 输出内容中**不写来源**（无"整合自 / 来源 / 原始文件位置"等行） | 输出中来源元信息行 = 0 |
| **安全前提** | **默认不脱敏**；整理前备份；写入前必须 diff 确认 | 行为一致；写操作 100% 有备份与审计 |

---

## 五、系统架构设计

### 5.1 模块拆解

> **P1 已交付**：日志扫描（分类部分）、来源预处理、单日归并三个模块（见下方 ✅ 标注）。
> ⏳ 标注的部分属 P2（批次编排 / 写入 / 碎片删除 / 验收报告）。

```
┌─ 日志扫描模块 LogScanner ✅ DailySourceScanner ─────────┐
│ 扫指定 Agent 的 memory/ 顶层 *.md                      │
│ 按日文件名模式分类 A / B / C；按日期分组               │
│ 识别「同日多来源」与「单来源但内容质量差」             │
└────────────────────┬──────────────────────────────────┘
                     ↓
┌─ 来源预处理模块 Preprocessor ✅ 确定性，零 token ─────┐
│ 剥元数据壳（12 条规则，见附录 C）；换行与 BOM 归一；   │
│ 体积统计与超限分块                                     │
└────────────────────┬──────────────────────────────────┘
                     ↓
┌─ 技能文档管理模块 SkillDocManager ✅ 复用 M11 预设 ────┐
│ skill 文档 = 版本化预设：                              │
│   template_md  → 输出骨架（强规则，供 FormatValidator）│
│   style_rules  → 语义规则（弱规则，供 prompt）         │
│ 批次记录所用预设版本，保证可回溯（⏳ 批次表属 P2）     │
└────────────────────┬──────────────────────────────────┘
                     ↓
┌─ 大模型调用模块 LLMOrchestrator ✅ DailyMergeService ─┐
│ 按来源类型裁剪注入规则 → 组装 prompt → 调 provider     │
│ → sanitize() 剥离思考过程 → FormatValidator 校验/修正 │
│ → token 记账与预算控制（⏳ 批次级预算硬中止属 P2）     │
└────────────────────┬──────────────────────────────────┘
                     ↓
┌─ 整理执行模块 MergeExecutor ✅ P2（`DailyRunService`）─┐
│ 按天归并 → 生成 diff plan（新内容 + 拟删碎片清单）      │
│ → 人工逐日确认 → 写入（备份 + 审计 + SHA-256 乐观锁）  │
└────────────────────┬──────────────────────────────────┘
                     ↓
┌─ 碎片清理模块 FragmentCleaner ✅ P2 ───────────────────┐
│ 已确认的碎片文件走 send2trash 删除（可恢复）            │
└────────────────────┬──────────────────────────────────┘
                     ↓
┌─ 验收报告模块 Verifier ✅ P2（`build_report()`）───────┐
│ 每天 1 文件 / 命名合规 / 章节完整 / 元数据壳残留 = 0   │
│ → 出报告；不通过则批次标记 needs_review，不写入        │
└───────────────────────────────────────────────────────┘
```

**P1 的交付形态**：`DailyMergeService.plan_day()` 返回 `DailyMergePlan`（目标路径 + 归并内容 +
强规则校验报告 + lint 警告 + 拟删碎片清单 + token 成本 + 备注），**只读不写**——
它就是 P2 落库 `daily_run_items` 的载荷形状。

**P2 的交付形态**：`DailyRunService` 把 `plan_day()` 逐日跑成可确认的批次——计划先落库（`planned` →
`awaiting_confirm`），人逐个 diff 确认后才 `apply()` 写入并清理碎片，最后出验收报告。
**批量 apply 的守门语义**：`apply()` 先对全部目标日做**批次级预检**（写前验收 + 乐观锁），
只要有一天不过就**整批不写**（冲突抛 `409`、验收不过标 `blocked`），杜绝"写一半"。

### 5.2 规则分层（本方案的核心机制）

| 层 | 内容 | 执行者 | 不通过时 |
|---|---|---|---|
| **强规则** | H1 格式、5 章节与顺序、命名 `YYYY-MM-DD.md`、禁空章节 | `TemplateRules` + `FormatValidator` 机械校验与修正 | **拦截写入** |
| **弱规则** | 保留什么 / 删什么 / 改写风格 / 去重合并 / 默认不脱敏 | 技能文档正文 + `style_rules` → LLM | 进 diff 人工确认 + 验收指标评估 |

### 5.3 数据模型（新增两张表）

| 表 | 关键字段 | 说明 |
|---|---|---|
| `daily_runs` | `id` / `agent_id` / `date_from` / `date_to` / `preset_id` / `preset_version` / `provider_id` / `status` / `idempotency_key` / `days_total` / `token_budget` / `tokens_used` / `cost_estimate_usd` / `error` / `created_at` / `finished_at` | 批次（状态机：`planned` → `awaiting_confirm` → `applied` / `partially_applied` / `needs_review`；另有 `rejected` / `failed` / `empty`） |
| `daily_run_items` | `run_id` / `date` / `target_path` / `source_hashes_json` / `sources_json` / `fragments_json` / `output_content` / `unified_diff` / `format_report_json` / `lint_warnings_json` / `notes_json` / `empty_reason` / `decision`（pending/applied/skipped）/ `item_status` / `backup_id` / 逐日 token 与成本 | 批次的逐日条目（`item_status`：`pending` / `planned` / `failed` / `blocked` / `applied` / `partially_applied` / `empty` / `skipped`） |

设计要点：`ai_jobs` 保持"单文件"语义不变，批次不复用该表，避免污染既有状态机。
完整字段与索引见 [DATA-MODEL.md](DATA-MODEL.md) 2.9；状态流转与 API 契约见本文附录 D。

---

## 六、详细实现流程

### 6.1 前置改造（P0 · ✅ 已交付 2026-09-23）

1. ✅ **接通 `style_rules` 到 prompt**：在 `AIJobService._build_prompt()` 新增【风格与内容规则】段，
   把 `preset.style_rules`（列表）逐条注入。这是让「skill 文档化」真正成立的最小改动，
   同时修掉既有文档↔实现漂移。
2. ✅ **把 SKILL.md 落成预设**（`target_file_type = WORKLOG`）：
   - `template_md`：`schema: soulforge.template/v1` + `target_file_type: WORKLOG` +
     `structure.required_sections`（一、今日概览 / 二、关键事件 / 三、关键决策 / 四、待办事项 / 五、明日计划）
     + `section_order: strict` + 正文骨架（见附录 B）
   - `style_rules`：语义规则清单（高价值保留项 / 低价值删除项 / 客观改写要求 / **默认不脱敏** / 按时间倒序归档）
   - 以内置预设 `preset-wlog-daily-std`「工作日志日标准化」落地（走 `seed_builtins()`），
     因而天然具备版本、回溯、UI 编辑能力

   > **与既有内置预设的关系（已收口）**：项目原有 `preset-wlog-summary`「工作日志汇总」
   > （章节为 今日概览 / 关键决策 / 待办与风险 / 明日计划），面向"按时间倒序归档、提取关键决策"。
   > 它与本预设本质是同一件事的两种口径（**单文件整理 vs 逐日归并**），并列成两个选项会让用户
   > 无法判断该选哪个。现已把它的归档顺序规则与「明日计划」章节**并入本预设**
   > （章节扩为 5 条，`sections_json` 与 `template_md` 同步），WORKLOG 类型只保留一个预设；
   > 旧 id 走「内置预设退役」机制隐藏（见 9.1 P3 后补记）。
   >
   > 实现要点：`BUILTIN_PRESETS_REFRESHED` / `BUILTIN_PRESETS_RETIRED` 两张**内容锚点表**
   > （id → 上一版发布时的定义）决定存量机器上「升级」还是「下线」——库中内容仍与锚点逐字段一致
   > （= 用户没改过）才动，用户改过的一律保留可见。
3. ✅ **修复 `FormatValidator` 的表格假阳性（P0 阻塞项，原方案遗漏）**：
   实测确认表格的相邻行会被判「段落间缺空行」（`FMT-PARAGRAPH-BLANK`），且 `auto_fix` 会在表格行之间
   插入空行、把表格改坏——而附录 B 的「关键决策」章节正是表格，不修则强规则必然拦截每一次有效输出。
   现把表格行按块级元素处理：既不误报、也不改写。
4. ✅ **让新增内置预设进入存量安装（P0 交付物可见性，原方案遗漏）**：
   `seed_builtins()` 原先「仅当 `presets` 表为空」才播种，而存量安装的表非空 →
   新增的内置预设**不会出现**，P0 交付物在用户机器上不可见。现改为：
   - 首次启动（表为空）→ 全量播种；
   - 存量安装（表非空）→ 只补种 `BUILTIN_PRESETS_ADDED`（**append-only 白名单**，
     本版本 = `preset-wlog-daily-std`）。历史内置预设不进白名单：
     用户可能已主动删除，升级时塞回来属于数据污染；
   - 补种时写入 v1 版本快照，**该快照同时充当「已补种」标记**——
     用户日后删掉它，启动流程不会再塞回来（删除即视为已知悉并拒绝）。
   实测（用真实 `index.db` 副本）：4 → 5 条，仅新增 `preset-wlog-daily-std`，
   用户已删的 3 条内置预设未被复活；重复执行幂等。
   - 后续（v1.7 预设收口）在存量分支又加了两件事：`BUILTIN_PRESETS_REFRESHED`（内容有更新 → 覆盖为新定义）
     与 `BUILTIN_PRESETS_RETIRED`（已下线 → 写 `retired_at` 隐藏），判据同为「库中内容是否仍等于
     上一版发布的内置定义」——用户改过就不动。

### 6.2 运行流程（8 步）

| 步 | 动作 | 失败处理 |
|---|---|---|
| 1 | 用户在「业务工具 → 日志标准化」选 Agent + 日期范围（月份或区间）+ provider + 技能预设 → 创建批次（`planned`） | 参数校验 `400`、路径穿越 `403`、超单批天数上限 `400` |
| 2 | 扫描该 Agent `memory/` 下日文件，分类 A/B/C，按日期分组，标出同日多来源 | 无来源 → 批次 `empty` 结束 |
| 3 | 预处理：剥元数据壳、归一换行与 BOM、统计体积；超限来源分块摘要 | 仍超限 → 该日 `failed`，转人工复核 |
| 4 | 逐日组装 prompt：按来源类型裁剪注入规则子集 + 骨架 + 目标内容 | token 预估超预算 → 中止并告警 |
| 5 | 调 LLM → `sanitize()` 剥思考过程 → **先判是否「无可归档内容」** → 否则 `FormatValidator.validate_and_fix()` 强规则修正 | 强规则不过 → 该日 `failed`，不写入；判定无可归档内容 → 该日 `empty`（不产出日文件） |
| 6 | 产出 diff plan：每日 1 条 = 归并后的新内容 + 拟删除碎片清单 | — |
| 7 | 人工逐日确认（可整批确认 / 跳过某日）→ 写入日文件（自动备份 + 审计 + 乐观锁）→ 删除碎片 | 文件被外部改动 → `409`（整批不写） |
| 8 | 跑 Verifier 出验收报告，写审计日志；批次标记 `applied` | 验收不通过 → 标 `needs_review`（已写入的日文件不回滚） |

**幂等设计**：批次键 `idempotency_key = sha256(agent_id + date_from + date_to + preset_id + provider_id + 有序来源清单 sha256 集合)`；
同键重复提交直接返回既有批次（`reused=true`），不产生第二次 LLM 调用。

> **P1 覆盖范围（已交付）**：上表第 2~5 步已实现（分类 → 预处理 → 组装 prompt → 调 LLM → 强规则校验），
> 产出 `DailyMergePlan`（含拟删碎片清单）但**不落库、不写盘、不删碎片**。
>
> **P2 覆盖范围（已交付）**：第 1 / 6 / 7 / 8 步落地为 `DailyRunService` —— 批次创建与幂等复用、
> 逐日计划持久化、批次级写前预检（乐观锁 + 写前验收）、写入与碎片清理、验收报告；
> 前端为 Tools 页「日志标准化」tab。剩余第 4 步的**预算预估**（`token_budget` 为空时不做预估，
> 只在实跑中按已用量中止）留待 P3 与效率对比一并处理。

### 6.3 「本日无可归档内容」的判定（v1.8 · 预设收口后补记）

**问题**：此前 prompt 写死「第一行必须是 `# 工作日志 - <date>`」，而 `FormatValidator` 又强制必填章节
齐全——两处夹击之下模型**没有任何合法出口**。当天如果全是噪音（心跳 / 状态轮询 / 无结论的调试流水 /
重复失败重试），它只能把这些内容包装成一篇「看起来合规」的日志，也就是**凑数**。

**改法**：给模型第二个合法出口，让它自己决策这一天是否值得产出。

| 环节 | 口径 |
|---|---|
| 输出契约 | 【输出】只允许两种情形：**情形一**正常输出文档；**情形二**只回一行 `无可归档内容：<一句话理由>` |
| 判定从严 | prompt 里明确：只要还有一条真实的事实 / 决策 / 待办 / 可复用数据，就必须走情形一 |
| 机械识别 | `parse_empty_verdict()`：整段输出 ≤ 3 行、无标题/列表/表格/引用结构、首个非空行以「无可归档内容」开头才算命中——**非命中一律当普通输出交给强规则**（宁可多校验，也不误判正常文档） |
| 磁盘动作 | **不产出日文件**；B/C 碎片照常列入待清理（走回收站，需人工确认）；**A 类主文件不动** |
| 状态与计数 | 该日 `item_status=empty`（不算失败、不计入 `days_delivered`）；验收报告对空日只核对「碎片已清」 |
| 主文件定义 | A 类 = **`memory/YYYY-MM-DD.md` 精确命名**（OpenClaw 系统自动生成的日文件）。其它命名（`-HHMM` / `-<topic>`）都是碎片，不是主文件——扫描器按纯正则判定，不做模糊匹配 |

> **为什么不自动删除空日的主文件**：`YYYY-MM-DD.md` 是系统的日文件，删除它等于让模型的一次判断
> 产生不可逆后果；而 B/C 碎片本来就是「归并后应当消失」的中间产物。因此空日只清碎片，主文件保留，
> 由用户看到「无可归档内容」的判定与理由后自行处置。

---

## 七、测试验证方案

### 7.1 分层测试

| 层 | 用例 | 通过标准 |
|---|---|---|
| 单元 · 分类器 | A/B/C 三类各 3 个样本 + 反例（`memory/lessons.md`、`memory/2026-5-6.md`、`memory/README.md`） | 命中与排除均 100% 正确 |
| 单元 · 预处理器 | 12 类元数据各 1 样本 + 混合样本 + **正文中合法 JSON 示例** + 回归反例（完全合规的 5 章节文档带尾换行 → 残留 = 0，M11/M12 不计入） | 剥壳后残留 = 0；且不误删正文合法内容 |
| 单元 · 规则解析 | 技能预设 → `TemplateRules` | 5 章节 + `strict` 顺序解析正确 |
| 集成 · 场景 | ① 单个已精简的日文件（可直接保留，仅规范标题）② 单个 session 导出（剥壳 → 改写 → 命名归并）③ 主文件 + 主题文件（合并为新的关键事件小节）四 同日 3 个碎片 | 每场景产出 1 个合规日文件，碎片被删除，原内容关键事实无丢失 |
| 端到端 | 取 1 个真实 Agent 的整月 `memory/`，在 `SOULFORGE_DATA_DIR` 隔离环境下跑 | 满足 §9.2 全部量化标准 |
| 质量评估 | 以人工整理过的历史日文件作 golden set 比对 | 5 章节完整率 100%；关键事实保留率 ≥ 95% |
| 回归 | 既有 `pytest` 全量 + `npm run build` | 零回归（空日决策交付后基线 **305 passed / 1 skipped**（306 收集）；构建退出码 0） |

**已交付的测试**（全部绿）：

| 文件 | 覆盖 |
|---|---|
| `backend/tests/test_daily_scanner.py` | 分类器：A/B/C 各 3 样本 + 8 个反例（`lessons.md` / `2026-5-6.md` / `2026-13-45.md` / `2026-02-30.md` / 非开头日期 / 非 .md …）；分组与优先级；排除子目录与 dreaming；质量标记；范围校验 |
| `backend/tests/test_daily_preprocessor.py` | 12 条规则各 1 样本（并断言残留片段消失）+ 混合样本（`detect_residual_shells() == []`）+ 3 个误删反例（正文合法 JSON / 无标题引导的引用块 / 句中出现过渡语或 HEARTBEAT_OK）+ **M11/M12 误报回归**（合规文档带尾换行仍为 `[]`、真壳仍检出）+ 体积统计 |
| `backend/tests/test_daily_merge.py` | 4 个场景（单 A / 单 session / 主+主题 / 同日 3 碎片）+ 只读护栏（原文件与目标文件都没被动过）+ 超限分块摘要（token 全量记账）+ 块数超上限转人工复核 + 无来源日期报错 |
| `backend/tests/test_daily_runs.py` | P2 批次：完整流程（创建 → 生成 → 确认 → 写入 + 删碎片 → 验收）/ 备份与审计 / 幂等复用 / 乐观锁 `409` / 二次 apply `409` / 3 个路径穿越参数化 `403` / 非法日期 `400` / 写前验收不过 → `blocked` 且零污染 / 碎片删失败 → `partially_applied` 且不回滚 / 跳过 / 拒绝 / 空范围 / 天数上限 / token 预算中止 / `dry_run_only` `403`（每步都核对磁盘真实状态，LLM 全部 mock） |

### 7.2 两种部署方案的效率对比（✅ 已交付 2026-09-24）

> 完整实测报告：[M15-EFFICIENCY-REPORT.md](M15-EFFICIENCY-REPORT.md)。
> 对比台：`backend/daily_form_bench.py`（3 样本日 × 3 形态 × 3 次重复 = 27 次真实调用，带 token 预算硬中止）。

| 形态 | 说明 | 实测结论 |
|---|---|---|
| ① `doc_full` · 文档注入（全量） | 规则 + 模板全文进 user prompt | 对照基线 |
| ② `trimmed` · 按来源裁剪注入 | 只注入该来源类型相关的规则子集 + 章节骨架 | 省输入 10.5% 但**输出更长（+13.3%）**、耗时最高、掉过一次强规则 → 不采用 |
| ③ `system_embedded` · 内嵌 system prompt | 规则全文进 system prompt | **定为默认**：输出 token −9.7%、单日耗时 −13.3%、三次输出一致性 0.442 → 0.518，合规率持平 |

记录指标：输入 / 输出 token、单日耗时、整月总耗时（132 天外推 58.5 / 63.6 / 50.8 分钟）、
**同一样本重复 3 次的输出一致性方差**（0.347 / 0.378 / 0.309 CV）、
**改一条规则后的生效成本**（三形态一致：改预设下一次调用即生效，无需重启、无需发版）。

### 7.3 安全与破坏性测试

- 路径穿越：构造 `../../etc/passwd` 类日期参数 → 必须 `403`
- 并发写：同一天两个批次同时确认 → 第二个必须 `409`
- 删除保护：碎片删除失败（文件被占用）→ 批次标 `partially_applied`，日文件保留不回滚
- 预算越限：`token_budget` 触发 → 批次中止且不写入任何文件

---

## 八、部署运维方案

### 8.1 上线步骤

1. **数据库**：新增 `daily_runs` / `daily_run_items` 两表（沿用既有"启动自动补表"机制，无需手工迁移）
2. **配置**：`config.toml` 新增 `[daily_standardizer]` 段——
   `max_days_per_run`（单批天数上限，默认 31）/ `token_budget`（单批 token 预算，默认 200000，`0` = 不限）/
   `provider_id`（默认 provider）/ `dry_run_only`（全局"只出计划"开关，默认 `false`）。
   **不含定时相关字段**（触发方式为手动批次）
3. **导入技能预设**：把 SKILL.md 落成预设（`PresetService.create`），成为可版本化、可编辑、可回溯的普通预设
4. **灰度**：先以 **dry-run**（只出计划、不写入、不删除）模式跑若干批次，人工核对无误后再开启执行
   （对应 `[daily_standardizer].dry_run_only = true`；开启时 `apply` 直接返回 `403 DAILY_RUN_DISABLED`）

### 8.2 日常维护

- **规则迭代**：改技能预设 → `version + 1` → 需要时可回溯到任一历史版本；批次记录所用版本号
- **成本监控**：每批次 token 消耗与耗时进审计日志，按周看趋势
- **provider 切换**：热加载，无需重启

### 8.3 备份策略

| 层 | 措施 | 说明 |
|---|---|---|
| 写入前 | 自动备份目标日文件（`backup.retention_days`，默认 30 天） | 项目既有护栏，防误写；与"是否留痕"无关 |
| 删除时 | 碎片走 `send2trash`，进系统回收站 | 可人工恢复；不额外做批次归档副本（已确认不留痕） |
| 批次级 | 不生成快照 | 按决策 4 取消 |

### 8.4 异常告警

| 场景 | 处理 |
|---|---|
| 批次失败 / 超时 | loguru 分级日志 + 审计记录 + 批次列表红标 |
| token 超预算 | 立即中止该批次，不写入任何文件，前端 Toast 提示 |
| 强规则校验不过 | 该日标 `failed`，写审计，不写入 |
| 碎片删除失败 | 批次标 `partially_applied`，保留日文件，提示手工清理 |
| 预留扩展 | webhook 出口（可选，默认关闭） |

### 8.5 企业级护栏

- 单批天数与来源数上限，防失控
- token 预算越限即中止（不做"打满预算继续跑"）
- 所有写操作必经备份 + 审计 + SHA-256 乐观锁
- 路径全程过 `_safe_join`
- **默认不脱敏**；若用户在 UI 显式勾选脱敏，则在批次报告中标注"本批已脱敏"

---

## 九、排期与质量验收标准

### 9.1 排期（按交付顺序与依赖；规模沿用项目惯例 S / M / L）

| 阶段 | 内容 | 规模 | 依赖 | 验收门 |
|---|---|---|---|---|
| **P0 · 地基** ✅ | 接通 `style_rules` 到 prompt（修漂移）+ SKILL.md 落成预设 + 修 `FormatValidator` 表格假阳性 | S | — | 单元测试 + 既有 `pytest` 全绿；预设可在 UI 编辑并回溯 —— **已交付 2026-09-23** |
| **P1 · 单日归并** ✅ | A/B/C 分类器 + 元数据预处理器 + 单日「多来源 → 1 文件」 | L | P0 | 集成测试覆盖 4 个场景；分类器与预处理器单测 100% —— **已交付 2026-09-24**（服务层，无 UI） |
| **P2 · 批次与 UI** ✅ | 批次编排（单 Agent）+ plan/diff 确认 + 碎片删除 + 验收报告 + Tools 页「日志标准化」tab | M | P1 | 整月真实样本 dry-run 跑通；并发与路径穿越测试通过 —— **已交付 2026-09-24** |
| **P3 · 效率验证** ✅ | 三形态效率对比报告 + 默认形态定稿 + 运维文档 | S | P2 | 产出对比报告并通过评审 —— **已交付 2026-09-24**（报告：[M15-EFFICIENCY-REPORT.md](M15-EFFICIENCY-REPORT.md)；默认形态 = `system_embedded`；运维手册见附录 E） |
| **P3 后补记 · 预设收口** ✅ | 把 `preset-wlog-summary`「工作日志汇总」并入 `preset-wlog-daily-std`（章节加「五、明日计划」+ 归档顺序规则），WORKLOG 只留一个预设；存量机器走「刷新 / 退役」迁移 | S | P3 | 两个选项的语义歧义消失；存量机器自动升级 + 旧预设隐藏，用户改过的预设不被覆盖 —— **已交付 2026-09-24**（`pytest` 289 passed / 1 skipped） |
| **P3 后补记 · 空日决策** ✅ | 给模型「本日无可归档内容」的合法出口（不再硬凑）；新增逐日状态 `empty` + `empty_reason`；空日不产出日文件、只清 B/C 碎片、主文件不动 | M | 预设收口 | 全噪音的日子不再被凑成日志；空日的主文件逐字未变；`pytest` 305 passed / 1 skipped —— **已交付 2026-09-24** |
| **P3 后补记 · 归因修正** ✅ | ① 残留壳口径收窄到真壳规则 `SHELL_RULES`（M01~M10），不再把 M11/M12 归一误报成残留；② `LLMClient.chat()` 读 `finish_reason`，截断时自动重试 1 次（预算翻倍、封顶 32768），仍截断则抛 `LLMOutputTruncatedError`（`422` / `LLM_OUTPUT_TRUNCATED`） | S | 空日决策 | 完全合规的 5 章节文档不再被判「有残留」；被截断的日子报的是配额不足而非格式违规；`pytest` 312 passed / 1 skipped —— **已交付 2026-09-24** |
| **P3 后补记 · 预设边界** ✅ | 两类文档预设分开：`target_file_type=WORKLOG` = 大模型日志标准化专用（只在「业务工具 → 日志标准化」可见可编辑），其余 = 主工作台加载用；新增 M15 预设信息栏（徽章「大模型专用」+ 版本 + 来源 `is_builtin` + 边界说明）与页内编辑器（说明 / 模板文档 / `style_rules` 三类），保存即 version+1、新批次生效；设置页与主工作台按 `scope=workbench` 排除日志预设 | S | 归因修正 | 界面上能确认「当前生效的是哪个预设、从哪来、去哪改」；文档预设页与主工作台不再出现日志预设；`pytest` 316 passed / 1 skipped —— **已交付 2026-09-24** |

> 工期由需求方按人力确定，本方案只给顺序与依赖。

### 9.2 质量验收标准（全部量化，达标才算交付）

1. 每天 1 个 `YYYY-MM-DD.md`：**100%**（分母排除模型判定「无可归档内容」的日子——那些天不产出文件）
2. 命名合规 `YYYY-MM-DD.md`：**100%**
3. 5 章节齐全 + 顺序正确（强规则拦截）：**100%**
4. 低价值元数据壳残留：**0**（口径 = `SHELL_RULES`，即真壳规则 M01~M10；M11/M12「编码·空白归一」对任何文档都会命中，**不计入**残留）
5. 输出中来源元信息行（整合自 / 来源 / 原始文件位置）：**0**
6. 关键事实保留率（golden set 人工核对）：**≥ 95%**
7. 碎片文件全部删除（经回收站可恢复）：**100%**；不产生额外归档副本
8. 默认不脱敏；仅显式开启时才处理：**行为一致**
9. 所有写操作均有备份 + 审计记录：**100%**
10. 失败批次零污染：强规则不过 / 预算越限 / 验收不过时**绝不写入**
11. 空日判定必须带理由，且**不删主文件**：`empty_reason` 非空；`YYYY-MM-DD.md` 内容与判定前逐字一致
12. 失败归因必须如实：模型输出被 `max_tokens` 截断（`finish_reason` = `length` / `max_tokens`）时，
    该日报 `LLM_OUTPUT_TRUNCATED` 并提示调大 provider 的 `max_tokens`，**不得**报成「强规则未通过」
    （自动重试 1 次、预算翻倍后仍截断才算失败）
13. 既有功能零回归：`pytest` 全绿、`npm run build` 退出码 0

---

## 十、风险与回退

| 风险 | 影响 | 应对 |
|---|---|---|
| LLM 归并时丢失关键事实 | 日志价值下降 | 关键事实保留率纳入验收（≥ 95%）；diff 逐日人工确认；强规则拦截结构性错误 |
| LLM 把低价值元数据又抄回输出 | 整理白做 | 预处理阶段确定性剥壳（不依赖模型）；输出验收检测真壳残留（M01~M10） |
| 输出被 `max_tokens` 截断被误判成「内容不合规」 | 用户按错误方向反复重跑，问题永远不解决 | `chat()` 读 `finish_reason`：截断自动重试 1 次（预算翻倍），仍截断抛 `LLM_OUTPUT_TRUNCATED` 并提示调大 provider 的 `max_tokens` |
| 误删非碎片文件 | 数据损失 | 分类器只命中 3 种日文件名模式 + 白名单排除；删除列表进 diff 由人确认；`send2trash` 可恢复 |
| 单日来源过大导致 token 爆炸 | 成本失控 / 调用失败 | 单批 token 预算硬中止；超限来源分块摘要或转人工复核 |
| 技能文档与实现漂移 | 规则与实际行为不符 | 文档版本化 + 批次绑定版本号；强规则部分由代码强校验，不依赖文档表述 |
| 成本高于预期 | 月费用上升 | P3 效率对比报告给出三形态成本；provider 可换低成本模型；支持跳过已整理日期 |

**回退方案**：每阶段独立提交，可按阶段 `git revert`；
数据层仅有新增两表，回退后旧表与旧接口零影响；
执行侧提供全局"关闭执行（只出计划）"开关，异常时可一键降级为 dry-run。

---

## 附录 A · 来源分类规则（A/B/C）

| 类 | 命名模式 | 特征 | 处理策略 |
|---|---|---|---|
| **A 标准日文件** | `YYYY-MM-DD.md` | 已按天命名，可能已较精简 | 作为当天**主骨架**；若已精简可只规范标题，不强制重写 |
| **B 同日 session / 时间戳** | `YYYY-MM-DD-HHMM.md` | 含 `Session Key` / `Conversation info` 等元数据；信息密度高但可读性差 | 剥壳后提炼为「关键事件」并入主文件 |
| **C 同日主题文件** | `YYYY-MM-DD-<topic>.md` | 已聚焦一个问题/时段，含关键决策与排查过程 | 提炼为「核心事件」并入主文件 |

**来源优先级**：A（主骨架）> C（关键事件）> B（补充事件）。

**排除项**：`memory/` 下不符合上述三种模式的文件（如 `lessons.md`、`<topic>.md`、`README.md`）一律不处理。

### 实现细节（P1 实测定下的边界）

| # | 规则 | 理由 |
|---|---|---|
| 1 | **只扫 `memory/` 顶层，不递归** | 实测各 Agent 的 `memory/` 下有 `archive/`、`dreaming/`、`cases/`、`contacts/`、`logs/`、`iteration/`、`.dreams/` 等子目录，都是独立语义目录（历史归档 / dreaming 产物 / 案件资料），混进来会误改文件、误删碎片；方案已明确 dreaming / corpus 不在范围内 |
| 2 | `YYYY-MM-DD-HHMM-<extra>.md` **归 B 类** | 实测存在 `2026-09-13-1623-2.md`（同分钟去重后缀），它是同一次 session 导出的多份之一，与 A 合并的语义与 B 一致 |
| 3 | 日期必须是**真实日历日** | `2026-13-45.md` / `2026-02-30.md` 这类脏文件名直接排除，不做修正 |
| 4 | 月份/日期必须**补零两位** | `2026-5-6.md` 不处理（与 skill 的命名规范一致，且避免把随手写的文件名当成日文件） |
| 5 | 大小写不敏感的 `.md` 扩展名 | Windows 实测存在 `.MD`，按同一模式处理 |

> **与 SKILL.md 的差异（以本方案为准）**：SKILL.md 的「C 类」示例里列了 `2026-05-31-1818.md`
> （纯时间戳形式）。本方案附录 A 明确 `YYYY-MM-DD-HHMM.md` 属 **B 类**——分类只影响来源优先级
> （C > B），不影响最终处理策略（两者都是「剥壳后并入主文件、随后删除」），因此以命名的客观形态为准。


---

## 附录 B · 标准输出模板

强规则部分（`template_md` 的 `structure`）：

```yaml
schema: soulforge.template/v1
name: "工作日志日标准化"
target_file_type: WORKLOG
structure:
  section_heading_level: 2
  required_sections:
    - title: 一、今日概览
    - title: 二、关键事件
    - title: 三、关键决策
    - title: 四、待办事项
  section_order: strict
elements:
  heading_style: atx
  list_style: "-"
  heading_blank_line: true
  paragraph_blank_line: true
typography:
  max_heading_level: 3
  allow_bold: true
  allow_italic: true
  forbid_emoji: true
  forbid_raw_html: true
modules:
  frontmatter: optional
```

> **实现要点（易踩坑）**：`FormatValidator._heading_at()` 对章节标题做**精确匹配**
> （要求 `标题.strip() == title`），因此序号 `一、二、三、四` 是标题的一部分，
> `required_sections` 必须写成 `一、今日概览` 而不能写成 `今日概览`——
> 否则会被判为「缺失必填章节」（`STR-MISSING-SECTION`）并触发机械补齐，产出重复章节。
> `section_heading_level: 2` 对应 skill 模板里的 `##` 章节；`max_heading_level: 3` 允许
> 「关键事件」下的 `### 事件 N` 子标题。
>
> **表格**：`FormatValidator` 已把表格行按块级元素处理——「关键决策」用表格不会被判「段落间缺空行」，
> `auto_fix` 也不会往表格行之间插空行（P0 修复项，见 §6.1 第 3 条）。
> 模板正文**不含 HTML 注释提示**：模板全文会进入 prompt，模型若照抄注释会触发 `forbid_raw_html`
> 且该规则没有机械修正手段，会导致强规则直接拦截。

骨架正文（供模型组织内容，也为 `FormatValidator` 提供结构基准）：

```markdown
# 工作日志 - YYYY-MM-DD

## 一、今日概览

- **日期**：YYYY-MM-DD
- **核心活动**：1~3 条概括当天最重要的事

## 二、关键事件

### 事件 1
- 事实 / 原因 / 结果

## 三、关键决策

| 决策项 | 内容 |
|--------|------|
| ... | ... |

## 四、待办事项

- [ ] ...
```

> 与 SKILL.md 原模板的差异：**去掉**标题下的 `> 整合方式…`、`> 原始文件位置…` 与末尾 `*整合自 N 个来源*`
> （按决策 4「不要求在合并内容中写明来源」）。当天信息确实丰富时可追加 `关键技术细节 / 关键信息` 章节，
> 但**不得为凑结构添加空章节**。

---

## 附录 C · 预处理的 12 条确定性规则（P1 已交付）

> 事实源：`backend/app/services/daily_preprocessor.py` 的 `PREPROCESS_RULES`
> （`rule_id` / `name` / `description` 三处文案只定义一次，本文档与 UI 均以此为准）。
> 这些规则在**进 prompt 之前**就删掉低价值壳，不依赖模型「自觉不抄回来」，因此零 token。

| ID | 名称 | 命中对象 | 删除范围 |
|---|---|---|---|
| M01 | 会话元数据行 | `Session Key` / `Session ID` / `Source` 键值行 | 仅该行 |
| M02 | session 标题壳 | `# Session: 2026-09-23 09:16:04 Asia/Shanghai` | 仅该行 |
| M03 | Conversation info 块 | `Conversation info (untrusted metadata)` 标题行 | 标题行 + 紧随的围栏/JSON 块 |
| M04 | Sender 块 | `Sender (untrusted metadata)` 标题行 | 标题行 + 紧随的围栏/JSON 块 |
| M05 | Reply target 上下文壳 | `Reply target of current user message` 标题行 | 标题行 + 紧随的引用块 |
| M06 | Queued messages 块 | `Queued messages while agent was busy` 标题行 | 标题行 + 紧随的列表块 |
| M07 | Possible Lasting Truths 空判 | `… : No strong candidate truths surfaced` | 仅该行 |
| M08 | dreaming 统计壳 | `Reflections` / `Themes` / `Candidate Truths` / `Theme Summary` 统计行 | 仅该行 |
| M09 | 过程过渡语行 | 整行仅为「让我检查一下」「我来看看」「任务还在运行中」这类过程话 | 仅该行 |
| M10 | 纯 HEARTBEAT_OK 行 | 整行仅为 `HEARTBEAT_OK` | 仅该行 |
| M11 | 编码与换行归一 | BOM / `CRLF` / `CR` | 归一为 `LF` + 无 BOM |
| M12 | 空白归一 | 行尾空白 / 连续空行 / 首尾空行 | 折叠 |

**保守性原则**（宁可不删，不可误删，均有单元测试反例守着）：

- M03~M06 只删「标题行 + 紧随其后的那种块」；标题行后面是普通正文时，只删标题行本身。
- 正文里合法的 ```json 代码块**没有**上述标题行引导 → 一律保留。
- M09/M10 只匹配「整行就是那句话」（容忍角色前缀 / 引号 / 加粗），**不做子串替换**。
- `detect_residual_shells(text)` 可对任意文本做终检，返回仍命中的**真壳**规则 id 列表（`SHELL_RULES` = M01~M10）——
  用于验收「低价值元数据壳残留 = 0」（P2 起还会对 LLM 输出做同一终检）。
  M11/M12「编码·换行·空白归一」不在其列：它们对任何文档都会命中（例如结尾带换行必然命中空白归一），
  计入残留会把完全合规的文档误判为不合格。报错文案用 `describe_shells()` 渲染成规则名，不暴露 `M12` 这类内部编号。

**阈值（模块常量，暂不进 `config.toml`）**：

| 常量 | 值 | 含义 |
|---|---|---|
| `CHUNK_THRESHOLD_BYTES` | 24KB | 单来源净化后仍超过此值 → 分块摘要 |
| `CHUNK_TARGET_BYTES` | 20KB | 分块目标体积（只在行边界断开） |
| `MAX_CHUNKS_PER_SOURCE` | 6 | 单来源分块上限，超过 → 抛 `DAILY_SOURCE_TOO_LARGE` 转人工复核 |
| `MAX_MERGE_PROMPT_BYTES` | 160KB | 归并 prompt 上限，超过 → 同日转人工复核 |
| `LOW_QUALITY_SIZE_BYTES` | 24KB | A 类文件判「质量差」的体积阈值 |
| `HEARTBEAT_SPAM_LINES` | 20 | A 类文件判「心跳流水」的行数阈值 |

> P2 只把**批次级**护栏（`max_days_per_run` / `token_budget` / `provider_id` / `dry_run_only`）
> 放进 `config.toml`；上表这些**单日来源阈值**仍是模块常量（改动需发版），
> 是否外置留待 P3 与效率对比一并评估。

---

## 附录 D · 批次状态机与 API 契约（P2 已交付）

> 事实源：`backend/app/services/daily_run_service.py`（状态常量）与 `backend/app/api/daily.py`（路由）；
> 表结构见 [DATA-MODEL.md](DATA-MODEL.md) 2.9，端点细节见 [API.md](API.md) 3.15。

### D.1 批次状态机

```
planned ──(后台逐日生成中)──┬─► awaiting_confirm ──┬─► applied            全部写入成功
                            │                     ├─► partially_applied  已写入但有碎片没删掉
                            │                     ├─► needs_review       写入后有日子没过验收
                            │                     └─► rejected           人拒绝 / 全部跳过
                            ├─► failed             生成阶段整批失败（无任何可确认的计划）
                            └─► empty              该范围没有需要整理的日子
```

- 只有 `awaiting_confirm` 允许 `apply()`；`apply()` 是**唯一**会写盘的入口。
- `rejected` / `applied` / `partially_applied` 为终态，不可再 `reject`。
- `needs_review` 表示「已写盘但验收有项目未达成」，供人手工处理后重跑报告。

### D.2 逐日条目状态

| 状态 | 含义 |
|---|---|
| `pending` | 还没轮到生成 |
| `planned` | 计划已生成，**可被勾选应用** |
| `failed` | 该日生成失败（LLM 报错 / 来源超限 / 强规则不过 / 预算中止） |
| `blocked` | 应用时写前验收不过 → **未写入** |
| `applied` | 已写入且碎片已清理 |
| `partially_applied` | 日文件已写，碎片删失败（**不回滚日文件**） |
| `empty` | **判定「本日无可归档内容」**（v1.8）：不产出日文件；有 B/C 碎片时可被执行（只清碎片），`decision` 落为 `applied` |
| `skipped` | 人工跳过 |

> `empty` 与 `failed` 的区别：`failed` 是「本该产出但没成」，`empty` 是「模型判定不该产出」——
> 后者是正常结论，不计入失败，也不会把批次拖成 `needs_review`。
> 当批次里所有条目都是 `empty` 且没有碎片要清时，批次状态为 `empty`（本批没有需要写入的文件）。

### D.3 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/daily-runs` | 创建批次（`202`，异步逐日生成；命中幂等键则 `reused=true` 复用） |
| `GET` | `/api/daily-runs` | 批次列表（`agent_id` / `status` / `limit`） |
| `GET` | `/api/daily-runs/{run_id}` | 批次详情（含逐日来源、diff、强规则报告、状态） |
| `POST` | `/api/daily-runs/{run_id}/apply` | 应用（`dates` 或 `apply_all`）：批次级预检 → 写入 → 删碎片 → 验收 |
| `POST` | `/api/daily-runs/{run_id}/reject` | 拒绝整批（不写任何文件） |
| `POST` | `/api/daily-runs/{run_id}/skip` | 跳过若干日 |
| `GET` | `/api/daily-runs/{run_id}/report` | 验收报告（对磁盘真实文件核对，只读可重复跑） |

**新增错误码**：`DAILY_SOURCE_TOO_LARGE`（`422`，P1）/ `DAILY_RUN_NOT_FOUND`（`404`）/
`DAILY_RUN_STATUS`（`409`）/ `DAILY_RUN_DISABLED`（`403`，全局 dry-run 开关）。

### D.4 前端（Tools 页「日志标准化」tab）

三阶段单页流程，对应 `DailyStandardizerPanel.tsx`：

1. **参数**：Agent + 日期范围 + WORKLOG 预设 + provider + 附加指令 → 生成计划；下方是该 Agent 的批次历史（可点开复核）
2. **逐日确认**：生成中按 1.5s 轮询；每日一张卡片（来源 A/B/C 与剥壳体积、拟删碎片、强规则报告、diff 预览/原始差异）。
   **默认全部不勾选**；可「写入选中 N 天」「全部写入」「跳过选中」「拒绝整批」
3. **验收报告**：5 项核对（单文件 / 命名 / 章节 / 无残留壳 / 碎片已清）+ 逐日说明，可「重新核对」

> 文案与交互规范见 [UI-SPECS.md](UI-SPECS.md) 的 M15 小节。

---

## 附录 E · 运维手册（P3 交付）

### E.1 日常运行

1. **首次使用先灰度**：`config.toml` 设 `[daily_standardizer].dry_run_only = true`，
   跑几批只出计划、逐个核对 diff；确认无误后改回 `false` 才允许写入。
2. **按范围分批跑**：建议一次一个自然月（单批上限 `max_days_per_run`，默认 31 天）；
   超过上限会被 `400` 拒绝并提示缩小范围，**不会**自动拆批。
3. **逐日确认**：默认全部不勾选；只勾选你已看过 diff 的日子。「全部写入」是显式动作。
4. **写完看验收报告**：5 项核对全绿即交付完成；有未达成项时批次标 `needs_review`，
   逐日 `details` 会写清原因（缺章节 / 有残留壳 / 碎片没删掉 / 同一天仍有多个文件）。

### E.2 规则迭代（最常做的一件事）

| 动作 | 生效成本 | 说明 |
|---|---|---|
| 改预设的 `style_rules` / `template_md` | **下一次调用即生效**，无需重启、无需发版 | 预设存 DB，`PresetService` 每次现读；改动会 `version + 1` 并留下版本快照，可回溯 |
| 改「格式化规则」frontmatter（章节 / 顺序 / 禁项） | 同上 | 强规则与 prompt 用的是同一份解析结果（`PresetService.rules_for`），不会两边漂移 |
| 改阈值常量（分块体积 / 块数上限 / 低质量判据） | 需改代码 → **需发版** | 见附录 C 的常量表；调参前先确认是「来源太大」还是「判据过严」 |
| 改 `[daily_standardizer]` 段 | 立即生效（`max_days_per_run` / `token_budget` / `provider_id` / `dry_run_only`） | 在「系统配置」页或 config.toml 改均可 |
| 换 LLM provider | 立即生效（热加载） | 设置 → LLM Provider 改完即可用；批次价格差异见效率报告 |

> 批次表记录了 `preset_version`，所以「某个批次是用哪一版规则跑的」永远可追溯。

### E.3 成本与预算

- 每批次、每日都记 token 与成本（`daily_runs.tokens_used` / `daily_run_items.total_tokens`），
  并写审计日志（`daily_run_create` / `daily_apply`）。
- 单批 `token_budget` 是**硬中止线**：越限即停止后续日期且不写入任何文件；
  已生成的计划保留可确认（改预设后重新生成更划算）。
- 成本与耗时的实测基线见 [M15-EFFICIENCY-REPORT.md](M15-EFFICIENCY-REPORT.md)；
  按天归并是**串行**的，整月耗时 = 单日均值 × 天数。

### E.4 故障处置

| 现象 | 原因 | 处置 |
|---|---|---|
| 批次 `failed`，逐日为 `failed` | LLM 报错（网络 / key / 限流）或来源超限 | 看逐日 `error`；修好 provider 后重新创建批次（修正后内容变了会生成新批次） |
| 批次 `needs_review` | 有日子 `blocked`（写前验收不过）或写入后验收未达成 | 看该日卡片与报告 `details`；改预设后重新生成，或人工改完点「重新核对」 |
| apply 返回 `409` | 目标文件在计划生成后被外部改动（含另一个批次抢先确认） | **整批未写**；重新创建批次拿新计划 |
| apply 返回 `403 DAILY_RUN_DISABLED` | 全局 `dry_run_only = true` | 按 E.1 第 1 条评估后关掉开关 |
| 某天 `partially_applied` | 日文件已写，碎片删失败（文件被占用等） | **不回滚**；手工清理残留碎片（回收站里也有副本） |
| 某天提示「净化后仍超限、已分 N 块摘要」 | 单来源 > 24KB | 正常路径，token 已全量记账；块数 > 6 会直接转人工复核 |
| 批次 `empty`（0 天） | 该范围没有「同日多来源」也没有「质量差的单来源」 | 正常；说明这段时间本来就干净 |
| 单日耗时过长 | 推理模型 + 大来源 | 换高速档模型 / 缩小范围；`token_budget` 兜底 |

### E.5 数据与回退

- 写盘前自动备份目标日文件（`backup.retention_days`，默认 30 天），可在「历史」里回滚；
  碎片删除走 `send2trash`，回收站可恢复。
- 数据层只有新增两表 `daily_runs` / `daily_run_items`，**不动既有表**：回退只需
  `git revert` + 让新表闲置，旧功能零影响。
- 批次表是 append-only 的审计性数据，不参与索引重建；`SOULFORGE_DATA_DIR` 迁移时随库一起搬。

---

*最后更新：2026-09-24 · v1.10（P0 / P1 / P2 / P3 已交付：预设落地 + style_rules 接通 + 表格假阳性修复 + 存量安装补种 + 扫描/分类/预处理/单日归并 + 批次编排/确认执行/碎片清理/验收报告/前端 tab + 规则投递形态效率对比与运维手册；P3 后补记：WORKLOG 预设收口为一个 + 存量安装的刷新/退役迁移 + 「本日无可归档内容」出口 + 残留壳口径收窄到 M01~M10 + 输出截断如实归因与自动重试 + 预设边界收口与页内预设管理）*
