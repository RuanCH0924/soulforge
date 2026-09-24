# 更新日志

本文件记录 Soulforge 的版本演进。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)（SemVer）。

> **版本号唯一事实源**：[backend/app/__init__.py](backend/app/__init__.py) 的 `__version__`。
> 下游取值点：响应包装 `meta.version`、OpenAPI 版本、`GET /api/health`、
> 导出包 `MANIFEST.json` 的 `soulforge_version`（均由代码引用该常量，不写死）；
> `backend/pyproject.toml` 与 `frontend/package.json` 为静态字段，需手工同步，
> 由 [backend/tests/test_version.py](backend/tests/test_version.py) 自动校验防漂移。

## [0.5.0] - 2026-09-24

> **0.5.0 是统一版本基线**（2026-09-22 建立；建立时那批内容见本节末「0.5.0 基线」）。
> 2026-09-23 ~ 09-24 的交付**继续计入同一版本，不另起版本号**；尚未打 `v0.5.0` tag。

### 新增

- **两类预设的边界收口 + 日志标准化页内预设管理（M11 × M15）**：把「供大模型归并工作日志」与
  「供主工作台加载」两类文档预设彻底分开，消除「这个预设到底在哪用、该去哪改」的认知盲区。
  - **判据**：`target_file_type = WORKLOG` 即「专供大模型处理工作日志」，不新增开关字段
    （常量 `preset_service.DAILY_PRESET_TYPE`）
  - **界面收口**：设置页「文档预设」与主工作台「应用预设 / AI 整理」统一取
    `GET /api/presets?scope=workbench`（过滤在后端做，前端不自己判断）；设置页新建预设的类型下拉
    不再提供 WORKLOG，并写明「请在业务工具 → 日志标准化界面查看与编辑」；列表为空时给出同款指引
  - **M15 界面新增**：预设信息栏（徽章「大模型专用」+ 预设名 + 版本 + 来源 +「查看 / 编辑」+ 边界说明）
    与页内编辑器（用途说明 / 模板文档（YAML 规则 + 章节骨架）/ 风格与内容规则三类 ——
    比设置页表单多出 `style_rules`，那正是注入大模型 prompt 的弱规则）；保存走 `PUT /api/presets/{id}`
    （version +1 + 版本快照），**下一个新批次即用新规则**（已生成的计划不重算，逐日确认页信息条
    新增 `预设 v{N}` 如实标注批次绑定的版本）
  - **API 新增**：`GET /api/presets` 的 `scope` 参数（`all` 缺省 / `workbench`，非法值 → `400`）；
    预设响应新增 `is_builtin`（是否随版本分发的内置预设，UI 展示「来源」用）
- **内置预设「工作日志日标准化」（`preset-wlog-daily-std`）**：M15「工作日志标准化」的规则载体（P0）。
  模板文档定义含序号的必填章节（`section_order: strict`；现为 一、今日概览 / 二、关键事件 / 三、关键决策 /
  四、待办事项 / 五、明日计划），`style_rules` 承载外部 skill 的语义规则（高价值保留清单 / 低价值删除清单 /
  客观改写要求 / 默认不脱敏 / 按时间倒序归档）。P3 后已把原「工作日志汇总」并入本条，WORKLOG 只留这一个预设。
- **内置预设退役机制（`presets.retired_at`）**：内置预设随版本下线时写 `retired_at`，
  `GET /api/presets` 不再返回它，但**行保留**、按 id 仍可取——否则历史上引用它的批次 / AI 任务读取会 404。
  当前退役项：`preset-wlog-summary`「工作日志汇总」（已并入 `preset-wlog-daily-std`）。
- **「本日无可归档内容」出口（M15）**：当天全是噪音（心跳 / 状态轮询 / 无结论的调试流水 / 重复失败重试）时，
  模型现在可以**判定不产出日文件**，而不是把噪音包装成一篇「看起来合规」的日志。
  - prompt 的【输出】改为两种情形：情形一正常输出文档；情形二只回一行 `无可归档内容：<一句话理由>`，
    并强调「只要还有一条真实的事实 / 决策 / 待办 / 可复用数据，就必须走情形一」
  - 识别从严（`parse_empty_verdict()`）：整段输出 ≤ 3 行、无标题/列表/表格/引用结构、首个非空行命中哨兵
    才算空判定；**非命中一律当普通输出交给强规则**，正常文档里出现这句话不会被误判
  - 逐日状态新增 `empty`（不算失败、不计入 `days_delivered`），`daily_run_items` 新增 `empty_reason` 列；
    验收报告对空日只核对「碎片已清」，全批空日且无碎片 → 批次状态 `empty`
- **M15 单日归并服务层（P1，无 UI）**：把同一天的多个 `memory/` 来源归并成 1 篇标准工作日志，三个模块：
  - `DailySourceScanner`（`services/daily_source_scanner.py`）：只扫 `memory/` **顶层**，
    按文件名分 A（`YYYY-MM-DD.md`）/ B（`YYYY-MM-DD-HHMM.md`，含 `-HHMM-2` 去重后缀）/
    C（`YYYY-MM-DD-<topic>.md`）三类，按日分组、排出待删碎片、并标出「单来源但质量差」
    （体积 / 心跳流水 / 夹带元数据壳三种确定性判据）
  - `DailyPreprocessor`（`services/daily_preprocessor.py`）：12 条**确定性**剥壳规则（会话键 /
    两类 untrusted metadata / 引用壳 / 排队消息 / dreaming 统计壳 / 纯 `HEARTBEAT_OK` / 过程过渡语 /
    BOM·换行·空白归一），**零 token**，不依赖模型自觉；`detect_residual_shells()` 可终检「残留 = 0」
  - `DailyMergeService`（`services/daily_merge_service.py`）：组装 prompt（格式化规则 + `style_rules` +
    骨架 + 带优先级的来源）→ LLM → `sanitize()` → `FormatValidator` 强规则校验/机械修正；
    单来源超 24KB 自动分块摘要、块数超 6 或归并 prompt 超 160KB 则转人工复核（新增错误码
    `DAILY_SOURCE_TOO_LARGE`）；**只出 `DailyMergePlan`，不写盘、不删碎片**（写入与删除属 P2）
  与既有 M13 单文件 AI 整理完全隔离：`ai_jobs` 保持单文件语义不变，批次表与 UI 属 P2。
- **M15 批次与 UI（P2）**：把 P1 的「单日归并」变成可确认、可审计的批次流程 ——
  - 数据层新增 `daily_runs` / `daily_run_items` 两表（**不复用 `ai_jobs`**，避免污染单文件状态机；
    schema 与约束见 [docs/DATA-MODEL.md](docs/DATA-MODEL.md) 2.9）；
    `config.toml` 新增 `[daily_standardizer]` 段（`max_days_per_run` / `token_budget` /
    `provider_id` / `dry_run_only`，**无定时字段**）
  - `DailyRunService`（`services/daily_run_service.py`）：创建批次走**幂等键**
    `sha256(agent_id + 范围 + preset + provider + 有序来源 SHA-256 集合)`，同键重复提交直接复用
    （`reused=true`）不重复烧 token；后台**逐日生成**（单日失败不中断整批），
    单批天数上限与 token 预算越限即中止
  - **确认执行零污染**：`apply()` 是唯一写盘入口且只接受 `awaiting_confirm`；
    先对**全部目标日**做批次级预检 —— SHA-256 乐观锁（冲突抛 `409`，覆盖「另一批次抢先确认」与
    「计划后被外部改动」）+ 写前验收（强规则 + 12 类残留壳检测）—— **任一日不过就整批不写**；
    写入走 `FileManager`（自动备份 + 审计 `daily_apply`），碎片删除走 `send2trash`，
    删失败标 `partially_applied` 且**不回滚日文件**
  - **验收报告**（`build_report()`）：对磁盘上的真实文件核对 5 项（单文件 / 命名 / 章节 / 无残留壳 /
    碎片已清），只读、可重复跑；不通过则批次标 `needs_review`
  - API：`/api/daily-runs` 6 个端点（创建 / 列表 / 详情 / 应用 / 拒绝 / 跳过 / 报告，见
    [docs/API.md](docs/API.md) 3.15）；新增错误码 `DAILY_RUN_NOT_FOUND`（404）/
    `DAILY_RUN_STATUS`（409）/ `DAILY_RUN_DISABLED`（403，全局 dry-run 开关）
  - 前端：业务工具页新增「日志标准化」tab（`components/DailyStandardizerPanel.tsx`）——
    参数 → 逐日确认（**默认全部不勾选**；逐日来源 A/B/C 与剥壳体积、拟删碎片、强规则报告、
    diff 可视化预览 + 原始差异）→ 验收报告；生成中 1.5s 轮询。
    技能预设的每个选项在**名称下方显示一行功能简介**（文案取后端 `presets.description`，
    前端不硬编码，用户自建预设同样生效；未填说明时显示「（该预设未填写说明）」）
  - 测试：新增 `tests/test_daily_runs.py` 17 个用例（完整流程 / 备份审计 / 幂等复用 / 乐观锁 409 /
    二次 apply 409 / 路径穿越 403 / 非法日期 400 / 写前验收不过零污染 / 碎片删失败 partial /
    跳过 / 拒绝 / 空范围 / 天数上限 / 预算中止 / dry-run 403），每步都核对磁盘真实状态
- **M15 规则投递形态与效率对比台（P3）**：`DailyMergeService` 支持三种规则投递形态并通过
  `plan_day(..., delivery=...)` 切换 —— `doc_full`（规则 + 模板全文进 user prompt，默认，即 P1/P2 现状）、
  `trimmed`（按当日来源类型裁剪规则与模板骨架）、`system_embedded`（规则全文进 system prompt）；
  三形态的「任务 / 目标 / 来源 / 输出要求」逐字一致，保证对比可归因（有单测守着）。
  新增 `backend/daily_form_bench.py` 对比台：固定样本集 × 三形态 × N 次重复，记录 token / 耗时 /
  输出一致性方差 / 强规则通过率 / 规则改动生效延迟，带 token 预算硬中止，且只在
  `index.db` 副本上跑（不改真实库、不写 workspace）。实测结论见
  [docs/M15-EFFICIENCY-REPORT.md](docs/M15-EFFICIENCY-REPORT.md)。
- **M15 默认规则投递形态改为 `system_embedded`（P3 实测定稿）**：规则全文改为注入 **system prompt**，
  user prompt 只留任务与来源。27 次真实调用（3 样本日 × 3 形态 × 3 重复）实测：输出 token −9.7%、
  单日耗时 −13.3%（26.6s → 23.1s）、三次重复的输出一致性 0.442 → 0.518、强规则通过率持平 100%。
  另两种形态保留在代码里供复测对照：`doc_full` 为原行为，`trimmed`（按来源裁剪）实测
  「省输入但多输出、耗时最高、掉过一次强规则」，不采用。

### 变更

- **M15 空日的磁盘语义（重要）**：判定「无可归档内容」的日期**不产出 `memory/YYYY-MM-DD.md`**，
  只清理 B/C 碎片（走回收站），**已有的同名主文件保持不动**——`YYYY-MM-DD.md` 是 OpenClaw 系统
  自动生成的日文件，删它等于让模型的一次判断产生不可逆后果，因此不在自动化范围内。
  空日的乐观锁改用**逐个碎片比对 SHA-256**（该日不写目标文件，锁不该锁在它上面），碎片被改动同样
  抛 `409` 且整批不写；审计动作 `daily_empty_content`。
  `POST /api/daily-runs/{id}/apply` 的响应新增 `no_content[]` 字段（语义：**未产出日文件，仅清理碎片**）。
  前端按钮「写入选中 / 全部写入」→「执行选中 / 全部执行」，确认弹窗**逐日标注动作**——
  空日执行的不是「写入」，按钮文案若仍叫「写入」就是谎报动作。
- **WORKLOG 预设合并为一个（修正并列选项带来的语义歧义）**：原「工作日志汇总」
  （`preset-wlog-summary`）与「工作日志日标准化」（`preset-wlog-daily-std`）本质是同一件事的两种口径
  ——**整理单个已存在的日文件** vs **把同一天的多份来源归并成 1 份并清理碎片**。
  两条说明文案都只讲「做什么」、都没讲「什么时候该用哪个」，并列在预设列表里只会让人两头都不敢选。
  现把汇总的归档顺序规则与「明日计划」章节并入日标准化（章节 4 → 5 条，
  `sections_json` 与 `template_md` 同步），旧预设退役隐藏。`DailyRunCreate.preset_id` 的默认值与
  M15 前端默认预设不变（本就是 `preset-wlog-daily-std`），**未改任何 API 契约**。
- **存量安装的内置预设「刷新 / 退役」迁移**：`seed_builtins()` 在存量分支（`presets` 表非空）新增两步，
  判据是**内容锚点表**——`BUILTIN_PRESETS_REFRESHED` / `BUILTIN_PRESETS_RETIRED` 各自记着该预设
  上一版发布时的定义，只有库中内容仍与锚点**逐字段一致**（说明用户从没改过）才执行：
  - 内容有更新 → 覆盖为新定义 + `version` 自增 + 留版本快照（本次：日标准化预设拿到 5 章节与新文案）
  - 已下线 → 写 `retired_at` 隐藏（本次：工作日志汇总）
  用户编辑过的预设一律不动——那是用户自己的资产，不替用户做覆盖或隐藏的决定。
  此前内置预设的任何改动只能影响全新安装，老机器永远拿不到修订。
- **M15 逐日归并的 prompt 结构变化**（仅影响工作日志标准化批次，M13 AI 整理与应用预设不受影响）：
  规则块从 user prompt 移到 system prompt。对同一批次而言 system prompt 恒定不变，
  对支持 prompt 缓存的服务商可命中前缀缓存（本轮未量化）。规则来源与优先级完全不变——
  仍然只读 `preset.style_rules` 与 `template_md`，改预设下一次调用即生效（实测：无需重启、无需发版）。

### 修复

- **写前验收把「编码·空白归一」误判成残留壳，合格文档被判 `blocked`**：`detect_residual_shells()`
  此前遍历全部 12 条预处理规则，而 M11「编码与换行归一」/ M12「空白归一」是收尾归一动作
  （对任何文档都会命中）—— 实测一份完全合规的 5 章节文档只要结尾带换行，就会返回 `['M12']`，
  于是该天被判「仍残留低价值元数据壳」而拒绝写入（同一 bug 也让验收报告的「无残留壳」列误报）。
  现按 `PreprocessRule.is_shell` 把规则分成**真壳（M01~M10）**与**归一（M11/M12）**，
  残留检测只看 `SHELL_RULES`；报错文案改用规则名（新增 `describe_shells()`），
  不再把 `M12` 这类内部编号直接抛给用户。
- **输出被 `max_tokens` 截断却报成「强规则未通过」**：`LLMClient` 此前从不读响应的
  `finish_reason`（Anthropic 为 `stop_reason`），模型写了一半被截断时只剩「章节缺失」这类结论，
  用户按「格式问题」方向反复重跑永远修不好。现 `LLMResponse` 记录 `finish_reason` 并提供
  `truncated` 判定；`chat()` 检测到截断时**自动以翻倍预算重试一次**（封顶 32768），
  仍截断则抛新增的 `LLMOutputTruncatedError`（`422` / `LLM_OUTPUT_TRUNCATED`），
  消息直接给出「到设置 → LLM Provider 调大该 provider 的 `max_tokens`」的解法。
  影响面覆盖 M15 批次日归并、M13 AI 整理与 `POST /api/llm/chat`。
- **`forbid_raw_html` 把占位符误判为原始 HTML（会拦死整天写入）**：该规则此前用
  `<([a-zA-Z][a-zA-Z0-9-]*)(\s|/?>)` 匹配，任何 `<单词>` 都算违规。而真实工作日志里
  常出现 `` `session:<id>` ``、`` `cron:<jobId>` `` 这类枚举取值与占位符（尤其写在行内代码里），
  于是整天的归并结果被判「含原始 HTML」——该规则**没有机械修正手段**，直接导致该天无法写入。
  现改为：只认**真实会渲染的 HTML 标签名**（内置标签白名单），并跳过行内代码跨度
  （围栏代码块此前已跳过）。`<br/>` / `<div>` / `<IMG src=a>` / `</span>` 之类仍会被拦。
  影响面同时覆盖 M15 归并、M13 AI 整理与应用预设（共用同一个校验器）。
- **`sanitize()` 漏剥推理模型的思考块**：MiniMax / DeepSeek / Qwen 等推理模型会把思考过程包在
  `<think>…</think>` 里，而此前的净化只靠中文前言特征词（「让我」「以下是」…）判定，
  思考内容是英文时匹配不上 → `<think>` 残留在正文里，触发 `forbid_raw_html` 把一次成功的归并
  误判为强规则失败。现按标签显式剥离思考块（`think` / `thinking` / `reasoning` / `scratchpad` /
  `analysis`），且只在「整段输出以思考块开头」时才剥（正文里作为示例出现的标签不受影响），
  未闭合的块（被 max_tokens 截断）不剥、留给强规则如实报错。
- **`FormatValidator` 对 Markdown 表格的假阳性**：表格的相邻行（表头 / 分隔行 / 数据行）此前会被判为
  「段落间缺空行」（`FMT-PARAGRAPH-BLANK`），更严重的是 `auto_fix` 会在表格行之间插入空行、把表格改坏。
  现按块级元素处理表格行：既不误报、也不改写。M15 的「关键决策」章节正是表格，该问题会直接挡住此功能。
- **AI 整理的 prompt 未注入 `preset.style_rules`**：`_build_prompt()` 此前只注入 `template_md`，
  预设的「风格与内容规则」只存库、从未进入 prompt，与 [DEVELOPMENT.md](docs/DEVELOPMENT.md) 模块 M13
  的声明不符；现新增【风格与内容规则】段逐条注入，并同步任务步骤说明。
- **新增内置预设进不了存量安装**：`seed_builtins()` 原先「仅当 `presets` 表为空」才播种，
  表非空的存量安装永远看不到后加的内置预设（第 5 条内置预设因此不可见）。现改为
  「首次空表全量播种 + 存量只补种 append-only 白名单 `BUILTIN_PRESETS_ADDED`」，
  历史内置预设不进白名单（用户删掉的不复活）；补种时写入 v1 版本快照，该快照同时充当
  「已补种」标记——用户日后删掉它，重启不会再塞回来。
- **统计面板的 lint 警告数恒为 0，与检查报告的实测条数冲突**：该数字此前取索引列
  `files.lint_warnings` 求和，而该列从不被扫描填充（`FileInfo.lint_warnings` 恒为默认 0），
  所以永远是 0——即「谎报无问题」。现 `/api/stats` 不再返回该字段，UI 的 lint 计数统一取自
  `GET /api/lint/all`，与「检查报告」**同源同口径**（按报告中列出的条数计，含 error 级）：
  统计面板卡片在打开/点「刷新」时实时重算（该调用要全量扫一遍，大库约 1~2 分钟，
  因此**卡片不阻塞**：其余 7 张指标先出，lint 卡片先显示「…」再填数字），
  状态栏警告数与 Agent 树角标同源于页面加载时的那次全量 lint；
  取不到时状态栏显示「lint 检查中…」，不再用 0 冒充「lint 无警告」。

### 文档

- 新增 [docs/MEMORY-DAILY-STANDARDIZER-PLAN.md](docs/MEMORY-DAILY-STANDARDIZER-PLAN.md)——M15「工作日志标准化」开发方案
  （方案选型结论、需求/选型/架构/流程/测试/部署六模块、排期与量化验收标准）；
  [ROADMAP.md](docs/ROADMAP.md) 版本规划新增 M15 里程碑，[DEVELOPMENT.md](docs/DEVELOPMENT.md) 模块矩阵同步登记。
- 内置预设数量的相关表述同步更新（ROADMAP 内置预设表、DATA-MODEL 内置预设 id 列表）——
  M15 时 4 → 5，预设收口后 5 → 4（退役项单列说明）。
- 文案统一：命令面板与统计面板标题「统计仪表盘」→「统计面板」，与数据中心 tab 一致；
  [UI-SPECS.md](docs/UI-SPECS.md) 文案规范新增两条约束——「同一指标只能有一个数据源与一个口径」
  （实时指标不得从索引推测，取不到时不得用 0 冒充无问题）与「同一界面元素的命名跨入口一致」，
  并把 lint 计数数据源、统计面板命名登记进第十一节一致性核对表。
- [MEMORY-DAILY-STANDARDIZER-PLAN.md](docs/MEMORY-DAILY-STANDARDIZER-PLAN.md) 升至 v1.4：
  §5.1 模块拆解标注 P1 已交付项、§6.2 注明 P1 覆盖第 2~5 步、§7.1 列出 P1 测试清单、
  §9.1 P1 打 ✅，附录 A 补 5 条实测边界（只扫顶层 / `-HHMM-2` 归 B / 真实日历日 / 必须补零 / 大小写不敏感），
  新增**附录 C**（预处理 12 条规则清单 + 6 个阈值常量）。
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) 新增「模块 M15：工作日志标准化（P1 已交付 · 服务层）」，
  写清三个服务文件、强/弱规则分层与三条易踩坑边界；模块矩阵 M15 状态更新为「P0 与 P1 已交付」。
- [MEMORY-DAILY-STANDARDIZER-PLAN.md](docs/MEMORY-DAILY-STANDARDIZER-PLAN.md) 升至 v1.5：
  §5.1 模块拆解标 P2 已交付（`DailyRunService`）、§5.3 补齐两表真实字段与逐日状态机、
  §6.2 注明 P2 覆盖第 1 / 6 / 7 / 8 步并修正幂等键口径、§7.1 加 P2 测试清单（基线 270）、
  §8.1 补 `dry_run_only` 与各默认值、§9.1 P2 打 ✅，新增**附录 D**
  （批次状态机 / 逐日状态 / 6 个端点 / 前端三阶段流程）。
- [DEVELOPMENT.md](docs/DEVELOPMENT.md)「模块 M15」小节改写为 P2 版：补 `DailyRunService` / API /
  前端面板三行与第四条边界（批量 apply 是「全或无」），并说明与 M13 的隔离；
  模块矩阵 M15 状态更新为「P0 / P1 / P2 已交付」。
- [API.md](docs/API.md) 新增 §3.15「工作日志标准化（M15 · P2）」——7 个端点（含 5 个 /apply 等子路径）
  的请求/响应/错误码，并把 `daily_standardizer` 段加进 `PUT /api/config` 示例。
- [DATA-MODEL.md](docs/DATA-MODEL.md) 新增 §2.9（`daily_runs` / `daily_run_items` 建表 SQL 与约束），
  §七 `config.toml` 示例补 `[daily_standardizer]`，§八表数量 8 → 10。
- [ROADMAP.md](docs/ROADMAP.md) §2.6 标题改为「P0 / P1 / P2 已交付」，新增 P2 已交付清单 6 条，
  下一步指向 P3 效率验证。
- [UI-SPECS.md](docs/UI-SPECS.md) 升至 v1.10：业务工具页 tab 数 4 → 5、§4.3 面板清单补
  `DailyStandardizerPanel`、新增 §5.7「日志标准化」交互规范（三阶段 + 5 条硬约束），
  一致性核对表新增 3 行（tab 数 / 默认勾选数 0 / 轮询 1500ms）。
- 新增 [docs/M15-EFFICIENCY-REPORT.md](docs/M15-EFFICIENCY-REPORT.md)——P3 效率对比报告：
  三形态定义（含形态②的裁剪口径与 6 条 `style_rules` 的归类依据）、方法与护栏、
  成本 / 耗时 / 稳定性 / 合规率实测表、默认形态定稿理由、两个实测缺陷的定位与验证、
  局限与复测命令。
- [MEMORY-DAILY-STANDARDIZER-PLAN.md](docs/MEMORY-DAILY-STANDARDIZER-PLAN.md) 升至 v1.6：
  §7.2 改写为实测结论、§9.1 P3 打 ✅、新增**附录 E 运维手册**（灰度 / 分批 / 规则迭代生效成本 /
  成本预算 / 8 类故障处置 / 数据回退）。
- [ROADMAP.md](docs/ROADMAP.md) §2.6 标题改为「P0 / P1 / P2 / P3 已交付」，新增 P3 已交付清单 6 条；
  [DEVELOPMENT.md](docs/DEVELOPMENT.md) 模块 M15 补「规则投递形态」表、对比台与
  「两个实测踩坑（已修，勿回归）」小节。
- 预设收口的相关文档同步：[ROADMAP.md](docs/ROADMAP.md) §2.5 内置预设表删掉「工作日志汇总」并注明退役去向、
  §2.6 标题加「+ 预设收口」并新增「P3 后补记」清单 4 条；
  [MEMORY-DAILY-STANDARDIZER-PLAN.md](docs/MEMORY-DAILY-STANDARDIZER-PLAN.md) 升至 v1.7
  （§3.3 / §6.1 的「两个预设分工」改写为「已收口」+ 迁移机制说明，§9.1 增「P3 后补记」行，
  章节契约 4 → 5 章节、回归基线 289）；
  [DEVELOPMENT.md](docs/DEVELOPMENT.md) 模块 M15 新增「WORKLOG 预设只有一个（勿再新增并列项）」小节；
  [DATA-MODEL.md](docs/DATA-MODEL.md) §2.5 建表 SQL 补 `retired_at`、约束段补三件事的播种规则；
  [UI-SPECS.md](docs/UI-SPECS.md) 升至 v1.11（§5.7 硬约束新增「同一用途不出现两个并列选项」）；
  [API.md](docs/API.md) §3.10 列表示例改用现存预设。
- 空日决策的相关文档同步：[MEMORY-DAILY-STANDARDIZER-PLAN.md](docs/MEMORY-DAILY-STANDARDIZER-PLAN.md) 升至 v1.8
  （新增 §6.3「本日无可归档内容的判定」含**主文件定义**、§9.2 增 2 条验收标准、附录 D.2 补 `empty` 状态、
  §6.2 第 5 步补判定顺序）；
  [DEVELOPMENT.md](docs/DEVELOPMENT.md) 模块 M15 新增「『本日无可归档内容』出口（勿改成"必须产出"）」；
  [DATA-MODEL.md](docs/DATA-MODEL.md) §2.9 补 `empty_reason` 列与 `empty` 状态；
  [API.md](docs/API.md) §3.15 补 `empty_reason` / `empty` / `no_content` 与空日的乐观锁口径；
  [UI-SPECS.md](docs/UI-SPECS.md) 升至 v1.12（§5.7 新增 4 条硬约束 + 一致性核对表 2 行）。
- 失败归因修正的相关文档同步：
  [MEMORY-DAILY-STANDARDIZER-PLAN.md](docs/MEMORY-DAILY-STANDARDIZER-PLAN.md) 升至 v1.9
  （§9.2 新增第 12 条验收标准「失败归因必须如实」、§9.1 追加「归因修正」后补记、残留壳口径由
  「12 类」改写为「真壳 M01~M10」）；[UI-SPECS.md](docs/UI-SPECS.md) 升至 v1.13（§5.7 新增
  「截断不等于内容不合规」「残留壳文案不暴露内部编号」+ 一致性核对表 2 行）；
  [API.md](docs/API.md) 错误码清单补 `LLM_OUTPUT_TRUNCATED`；
  [DEVELOPMENT.md](docs/DEVELOPMENT.md) 预处理器行改写为「真壳 M01~M10 + 归一 M11/M12 +
  `SHELL_RULES`/`describe_shells()`」；[ROADMAP.md](docs/ROADMAP.md) §2.6 追加「归因修正」后补记。
- 两类预设边界与页内预设管理的相关文档同步：
  [DEVELOPMENT.md](docs/DEVELOPMENT.md) 模块 M11 新增「两类预设的边界」表 + 关键护栏更正
  （内置预设同等可编辑可删除、改预设不重算已生成计划）；
  [ARCHITECTURE.md](docs/ARCHITECTURE.md) 新增 **3.12 M15 模块设计**（四个服务 / 强·弱规则分层 /
  零污染写入 / 空日出口 / 失败归因 / 状态机 / 规则载体），并修正 3.8 预设段与架构树中过时的
  「系统预设不可删 / 只能改 description + style_rules」；[API.md](docs/API.md) §3.10 补 `scope`
  查询参数与 `is_builtin` 字段（并修正示例里 `is_system` 取值）；
  [DATA-MODEL.md](docs/DATA-MODEL.md) 纠正 `is_system` 语义（历史字段恒为 0）、补 `is_builtin`
  为派生字段与两类预设边界；[UI-SPECS.md](docs/UI-SPECS.md) 升至 v1.14（§5.1 + §5.7 新增 3 条硬约束、
  一致性核对表 5 行）；[ROADMAP.md](docs/ROADMAP.md) §2.6 追加「预设边界」后补记、M11 验收清单
  更正（预设可删 + scope 边界）；README / README.zh-CN 补 M15 功能条目、路线图 M15 行与
  `/api/daily-runs` 端点说明。
- **本文件（CHANGELOG）的版本段归属**：`0.5.0` 未打 tag 前的交付统一累计在 `[0.5.0]` 条目下——
  取消 `[未发布]` 占位，2026-09-22 的基线内容降为条目末的「0.5.0 基线」子节；
  「发版流程」补一条约定（打 tag 前的交付直接追加到当前版本条目，不另起版本号）。

### 0.5.0 基线（2026-09-22 建立）

首个统一版本基线。建立时**不新增业务功能**，目标是**收口现状、建立版本链路、清理过时文档**。

#### 新增

- **lint 规则清单可视化**：此前用户只能看到「某行违规」，看不到「一共在检查什么」——8 条内置规则的说明
  只写死在源码与文档里。现在给规则类补 `scope`（单个文件 / 整个 Agent）与 `description` 字段，
  新增 `GET /api/lint/rules` 下发规则目录，前端在**数据中心 → 检查报告**顶部渲染可折叠的「检查规则（N 条）」表
  （默认收起，**无警告时自动展开**）；编辑器「检查」面板头部提供「查看规则」按钮直接跳到该 tab，
  系统配置的 Lint 开关下方给出同一指引——规则文案只存在一处（后端），不再出现多份副本。
- **「设为预设」**：编辑器工具栏新增按钮，把当前文档直接存为**文档预设**（结构模板）。
  弹窗内填写参数——预设名称、适用文件类型、用途说明、章节标题层级、必填章节勾选
  （由文档标题实时扫描得出，跳过围栏代码块）、是否严格要求章节顺序、是否要求 YAML frontmatter；
  后端 `POST /api/presets/from-document` 以文档内容作模板正文并生成带 YAML 规则 frontmatter 的模板，
  保存后可在「系统配置 → 文档预设」查看、编辑版本与回溯，并直接用于「应用预设 / AI 整理」。
- **版本号链路**：以后端 `app/__init__.py` 的 `__version__` 作为唯一事实源，
  `Meta.version`、导出 `MANIFEST.json` 的 `soulforge_version` 改为引用该常量，不再各自写死；
  `pyproject.toml` / `package.json` 两个静态字段由新增的 `tests/test_version.py` 校验防漂移。
- **版本可见性**：前端启动时读取 `GET /api/health`，在状态栏右下角显示后端版本号。
- 新增本文件（CHANGELOG），并明确发版流程。

#### 修复

- **AI 整理输出夹带对话内容**：模型常在被整理的文档正文前输出一段「思考过程 / 格式化规则复述」
  （如「让我仔细分析这个任务：…」），此前这类文本不构成格式违规、会原样进入 diff 预览与写入。
  现在在格式校验之前新增**输出净化**：剥离正文之前的对话性前言（仅在具备明显对话特征时触发，
  不会误删文档自身的开头段落），并去除模型给整篇文档加的外层代码围栏；
  系统提示与用户提示同步强化「第一行直接进入正文、禁止思考过程与围栏包裹」。

#### 变更

- `GET /api/health` 响应改为全站统一的 `{data, meta}` 包装（此前直接返回裸对象，与文档约定不一致）。
- `frontend/package.json` 版本号对齐为 `0.5.0`。
- **编辑器工具栏**：取消「整理 ▾」下拉，「应用预设 / AI 整理 / 导出文件」平铺为一级按钮（少一层点击）。
- **按钮文案统一收敛到 4 个汉字以内**：新增全局文案约束（写入 `docs/UI-SPECS.md` 第十节），
  并据此修改 11 处超长按钮——编辑器「导出当前文件」→「导出文件」、对比「忽略格式噪声」→「忽略噪声」、
  历史「回滚到此版本」→「回滚版本」、预设「回溯到此版本」→「回溯版本」、同步「生成同步计划」→「生成计划」、
  「执行同步（N 个文件）」→「执行同步」（计数移入悬浮提示）、超同步「保存同步范围」→「保存范围」、
  设置「管理 LLM Provider（AI 模型接入）」→「管理模型」、「保存为预设」→「保存预设」、
  数据中心 tab「统计仪表盘」→「统计面板」与「健康检查报告」→「检查报告」；
  被截掉的完整含义全部移到 `title` 悬浮提示。
- **编辑器工具栏折行**：由「单行横向滚动」改为「按行折行」——此前窄窗口 / 多窗口平铺时按钮会被推到可视区外，而滚动条被隐藏、用户无任何提示；
  现在按钮不收缩、不裁切，空间不足即折行，工具栏高度自适应；窗口宽度 < 780px 时隐藏 `Ctrl+B / Ctrl+I / Ctrl+S` 快捷键提示以优先保证动作按钮可见。

#### 移除

- 模板系统（M9）与导入能力早在 `912740b` 已移除，本次在文档中同步清理其残留描述。
- 删除 3 份过时文档：`docs/ui-theme-research.md`（结论未落地且与现设计冲突）、
  `docs/AGENT-PLAN.md`（未实现草案）、`docs/TEMPLATE-FORMAT-TEST-REPORT.md`（一次性测试报告）。

#### 文档

- 修正各文档中与实现不符的内容：数据目录路径（`~/.soulforge` → `<项目根>/.soulforge`）、
  已不存在的接口与依赖（`/api/search/agents`、TanStack Query、shadcn/ui、Alembic 等）、
  缺失的数据表与列（`preset_versions`、`presets.template_md`）、README 失效链接。

#### 本基线已交付能力（此前各版本累积）

- **Phase 1 · MVP**：Agent 自动发现、文件浏览与编辑（Monaco）、跨 Agent 全文搜索（ripgrep）、
  Diff 对比、跨 Agent 同步（plan + confirm 两步）、Prompt Pack 导出（`.tar.gz` + SHA-256 manifest）、
  自动备份与回滚（30 天保留）、Lint 8 条规则、统计仪表盘与审计日志。
- **Phase 2 · UI 优化**：侧边导航四页面（工作台 / 业务工具 / 数据中心 / 系统配置）、
  命令面板（`Ctrl+K`）、多文档横向平铺编辑（最多 3 窗口）、CORE 分类浏览模式、
  四档响应式断点、深浅双主题、草稿保护与会话恢复。
- **Phase 2.5 · AI Editor**：文档预设（Markdown 模板 + 规则解析 + 格式校验/自动修正）、
  LLM Provider 接入（OpenAI / Anthropic 协议，API key Fernet 加密 + 热加载）、
  AI 自动整理（生成 → diff 确认 → 写入，输出强制过格式校验与 lint）。
- **超级同步**：独立守护进程，多个 Agent 同名核心文档秒级同步，UI 矩阵配置 / 运行状态 / 日志检索导出。

## 历史沿革（0.5.0 之前未单独打版本号，按提交归档）

| 日期 | 提交 | 内容 |
|---|---|---|
| 2026-08-11 | `097efca` | 初始提交：项目骨架 |
| 2026-08-11 | `a30e047` | 从公开仓库移除个人与私有 Agent 模板信息 |
| 2026-08-12 | `0c72fca` | 新增 memory / 其他文件的显示配置开关 |
| 2026-08-12 | `41ef470` | Phase 2.5 AI 编辑器套件 + 页面化 UI 重构 |
| 2026-08-12 | `a9be812` | 编辑器工具栏移至编辑器上方，修正边框样式 |
| 2026-08-21 | `c6b2c02` | CORE 分类浏览模式与切换控件 |
| 2026-08-26 | `1b39d77` | 多文档横向平铺编辑窗口 |
| 2026-09-10 | `d213126` | M 系列 UI 优化与布局重构（M-01~M-08） |
| 2026-09-13 | `912740b` | 新增超级同步；移除模板系统与导入能力 |
| 2026-09-13 | `b692237` | Linux / macOS 一键启动脚本与跨平台文档 |

## 发版流程

> 约定：**未打 tag 之前**的交付直接追加到当前版本条目下（不新开版本号、不留 `[未发布]` 占位），
> 发布时再补 `git tag v<版本>`。`0.5.0` 即此形态——基线建立于 2026-09-22，之后的交付持续累计在同一版本内。

1. 修改 [backend/app/__init__.py](backend/app/__init__.py) 的 `__version__`；
2. 同步 [backend/pyproject.toml](backend/pyproject.toml) 的 `project.version`
   与 [frontend/package.json](frontend/package.json) 的 `version`（均为 npm / 打包器要求的静态字段）；
3. 在本文件追加对应版本条目（新增 / 变更 / 移除 / 修复）；
4. 同步版本号到 [README.md](README.md)、[README.zh-CN.md](README.zh-CN.md) 的版本徽标；
5. 运行 `pytest`（在 `backend/` 下）确认 `tests/test_version.py` 校验通过；
6. 打标签：`git tag v<版本>` 并推送（`git push origin v<版本>`）。

### 版本号规则

| 位 | 何时递增 | 示例 |
|---|---|---|
| MAJOR | 不兼容的对外变更（如 REST API 破坏性调整、数据模型不兼容迁移） | `1.0.0` |
| MINOR | 向后兼容的功能新增 | `0.5.0` → `0.6.0` |
| PATCH | 向后兼容的缺陷修复 | `0.6.0` → `0.6.1` |
