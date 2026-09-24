# Soulforge — 落地路径

> 配套主文档 [DEVELOPMENT.md](DEVELOPMENT.md) 的落地路径章节。
> 本文档按 **Phase** 组织，每个 Phase 有明确目标、验收清单、回退方案。

---

## 一、版本规划总览

| Phase | 范围 | 状态 |
|---|---|---|
| **Phase 1 · MVP** | 浏览 + 编辑 + 备份 + lint + 同步 + 导出 | ✅ 已完成 |
| **Phase 2 · UI 优化** | 页面交互美观、编辑器体验、视觉一致性 | ✅ 已完成 |
| **Phase 2.5 · AI Editor** | 模板预设 + Agent 大模型接入 + AI 文档整理 | ✅ 已完成 |
| **超级同步** | 多 Agent 同名核心文档秒级实时同步（独立守护脚本 + UI 矩阵配置 / 状态 / 日志） | ✅ 已完成 |
| **M15 · 工作日志标准化** | `memory/` 日文件归并（每天 1 个 `YYYY-MM-DD.md` + 元数据清洗 + 碎片删除），手动批次 + 确认 | ✅ 已交付（P0 / P1 / P2 / P3 + 预设收口 / 空日决策 / 归因修正 / 预设边界；见 [MEMORY-DAILY-STANDARDIZER-PLAN.md](MEMORY-DAILY-STANDARDIZER-PLAN.md) 与 [M15-EFFICIENCY-REPORT.md](M15-EFFICIENCY-REPORT.md)） |
| **Phase 3 · 远期** | 团队协作 / 云端同步 / 第三方插件 | 📋 规划 |

> 统一版本基线自 **v0.5.0** 起，版本历史与发版流程见 [CHANGELOG.md](../CHANGELOG.md)。
> Phase 1 的完整历程见 [附录 A](#附录-a--phase-1-mvp-回顾)。

---

## 二、Phase 2.5 AI Editor（已交付）

### 2.1 阶段目标

> 让老板的 **OpenClaw 灵魂文档** 和 **memory/ 工作日志** 都能按统一格式规范化，
> 通过 AI Agent 自动整理，**保证所有文档结构一致、章节齐全、风格统一**。

### 2.2 三步走规划

```
Step 1 ──► Step 2 ──► Step 3
模板预设     Agent 接入     AI 自动整理
（静态）     （能力）       （应用）
```

| Step | 范围 | 验收标准 | 估时 |
|---|---|---|---|
| **Step 1：模板预设** | 保存文档格式预设（SOUL/AGENTS/MEMORY/user/工作日志等），可在 UI 选择 + 应用 | 4 个内置预设（SOUL/AGENTS/MEMORY/工作日志）+ 用户可新建/编辑预设 | 1 周 |
| **Step 2：Agent 接入** | 接入 LLM 大模型（OpenAI 兼容协议），支持多 provider（OpenAI / Anthropic / 本地 Ollama） | 至少一个 provider 跑通 + 后端配置可热加载 | 1 周 |
| **Step 3：AI 自动整理** | 选定预设 + 选定文件 → AI Agent 按预设重写文档 → 生成 diff → 老板确认后写入 | E2E 流程跑通：对一个 Agent 的 MEMORY.md 应用"工作日志汇总"预设 | 2 周 |

### 2.3 Step 1 详细拆解：模板预设系统

#### 目标

> 把"SOUL.md 应该有哪几章、MEMORY.md 应该按什么格式"这件事**结构化、可复用、可版本化**。

#### 数据模型

新增 `presets` 表：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | text PK | UUID |
| `name` | text | 预设名（如 "SOUL.md 标准结构"） |
| `target_file_type` | text | 适用文件类型（SOUL/AGENTS/MEMORY/USER/IDENTITY/TOOLS/WORKLOG/ANY） |
| `description` | text | 用途说明 |
| `sections_json` | text | 章节列表（JSON），每个章节 = `{title, required, order, hint}` |
| `frontmatter_json` | text | YAML frontmatter 模板（JSON），每个字段 = `{key, required, default}` |
| `style_rules` | text | 风格规则（Markdown 规范、emoji 禁令、口语化禁令等） |
| `created_at` / `updated_at` | text | 时间戳 |
| `version` | integer | 预设版本（老板可迭代升级） |

#### 内置预设（v1）

| 预设名 | target_file_type | 适用场景 |
|---|---|---|
| `SOUL 标准结构` | SOUL | 新建/重整 SOUL.md（核心行为准则、学习连续性、核心边界） |
| `AGENTS 标准结构` | AGENTS | 新建/重整 AGENTS.md（启动流程、记忆、工具、群聊、安全） |
| `MEMORY 标准结构` | MEMORY | 重整长期记忆（重要决定、经验教训、待办） |
| `工作日志日标准化` | WORKLOG | 把同一天的多份来源（日文件 / session 导出 / 主题碎片）归并成 1 份 `YYYY-MM-DD.md` + 清理碎片；也可整理单份日文件——M15 新增，见本文 2.6 节 |

> 原内置预设 `工作日志汇总`（`preset-wlog-summary`）已**退役并合并**进 `工作日志日标准化`：两者是同一件事的
> 两种口径（单文件整理 vs 逐日归并），并列成两个选项会让用户无法判断该选哪个。它的归档顺序规则与
> 「明日计划」章节已并入，WORKLOG 类型只保留一个预设。退役机制见 2.6 节。

#### UI 入口

- 顶部菜单 → 「预设」 → 列表 + 新建/编辑/删除
- 文件编辑页 → 「应用预设」按钮 → 选预设 → 生成 diff 预览 → 老板确认 → 写入

#### API 端点

| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/api/presets` | 列出全部预设（系统 + 用户自定义） |
| `POST` | `/api/presets` | 创建新预设 |
| `GET` | `/api/presets/{id}` | 查看预设详情 |
| `PUT` | `/api/presets/{id}` | 编辑预设（version 自增） |
| `DELETE` | `/api/presets/{id}` | 删除预设（内置预设也可删；删后重启不会重建） |
| `POST` | `/api/presets/{id}/apply` | 应用预设到指定 Agent + 文件（返回 diff plan） |
| `POST` | `/api/presets/{id}/apply/execute` | 执行应用（写入文件，自动备份） |

#### 验收清单

1. ✅ 顶部菜单有「预设」入口
2. ✅ 系统提供 4 个内置预设（含 M15 的 `工作日志日标准化`，见 2.6 节）
3. ✅ 用户可新建/编辑/删除自己的预设
4. ✅ 预设编辑器支持 JSON 或可视化拖拽两种模式
5. ✅ 文件编辑页有「应用预设」按钮
6. ✅ 应用预设走 plan + execute 两步，绝不直接覆盖
7. ✅ 内置预设与用户预设**同等可编辑、可删除**（播种时 `is_system=0`）；被用户改过的内置预设不会被升级覆盖
8. ✅ 两类预设边界（2026-09-24 收口）：`WORKLOG` 类 = 大模型专用，不出现在文档预设页与主工作台；
   两侧取用方式 `scope=workbench` / `target_file_type=WORKLOG`，且日志预设可在日志标准化界面内直接编辑（见 2.6 节）

---

### 2.4 Step 2 详细拆解：Agent 大模型接入

#### 目标

> 让 Soulforge 后端能调用任意 **OpenAI 兼容协议**的 LLM，
> 支持多 provider 配置（OpenAI / Anthropic / DeepSeek / Ollama / 其他），
> 配置变更可热加载（不需要重启服务）。

#### 数据模型

新增 `llm_providers` 表：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | text PK | provider 名（如 "openai-main" / "ollama-local"） |
| `base_url` | text | API 端点 |
| `api_key` | text | 密钥（**加密存储**） |
| `model` | text | 模型名（gpt-4 / claude-sonnet / qwen2.5 / llama3） |
| `protocol` | text | `openai-completions` / `anthropic-messages` |
| `enabled` | integer | 是否启用 |
| `max_tokens` | integer | 单次最大 token |
| `temperature` | real | 默认温度 |
| `timeout_seconds` | integer | 超时 |
| `created_at` / `updated_at` | text | 时间戳 |

#### 配置加载机制

```
[Soulforge 启动]
  ↓
读 .soulforge/config.toml → llm_providers 段
  ↓
注册到内存 LLMRegistry
  ↓
[文件变更 / PUT /api/config]
  ↓
热加载：diff 新旧 → 增量注册/失效 → 不重启
```

#### UI 入口

- 设置 → 「LLM Provider」 → 列表 + 新增/编辑/删除
- 「测试连通性」按钮（发一条 "ping" 看是否返回）

#### API 端点

| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/api/llm/providers` | 列出所有 provider |
| `POST` | `/api/llm/providers` | 新增 provider |
| `PUT` | `/api/llm/providers/{id}` | 编辑 provider（**key 留空 = 保留旧 key**） |
| `DELETE` | `/api/llm/providers/{id}` | 删除 provider |
| `POST` | `/api/llm/providers/{id}/test` | 测试连通性 |
| `POST` | `/api/llm/chat` | 通用 chat 端点（内部用） |

#### 安全护栏

- API key **加密存储**（Fernet，对称加密，密钥来自 `SOULFORGE_SECRET` 或首次启动生成）
- API key 在 UI 上**永远显示掩码**（`sk-****...****`）
- API key 不进 git（`.gitignore` 加 `.soulforge/secrets/`，备份也排除）
- 配置中心 UI 有「泄露检测」按钮：扫描日志/审计里是否泄露过明文 key

#### 验收清单

1. ✅ 设置里有「LLM Provider」管理页
2. ✅ 至少能跑通 OpenAI / Anthropic / Ollama 三个协议
3. ✅ 修改配置后**不重启**就生效
4. ✅ API key 在 UI 永远显示掩码
5. ✅ 「测试连通性」按钮能用
6. ✅ 删除 provider 会拒绝有关联 ai_job 的删除（避免历史断链）

---

### 2.5 Step 3 详细拆解：AI 自动整理

#### 目标

> 老板选一个预设 + 选一个文件 + 选一个 LLM provider →
> AI Agent 按预设重写文档 → 生成 diff plan → 老板确认 → 写入。

#### 数据模型

新增 `ai_jobs` 表：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | text PK | UUID |
| `agent_id` | text | 目标 Agent |
| `file_path` | text | 目标文件路径 |
| `preset_id` | text | 使用的预设 |
| `provider_id` | text | 使用的 LLM provider |
| `status` | text | `pending` / `running` / `awaiting_confirm` / `applied` / `rejected` / `failed` |
| `input_snapshot` | text | 原始内容快照 |
| `output_content` | text | AI 输出（待确认内容） |
| `diff_plan_json` | text | 生成的 diff plan |
| `error` | text | 失败原因 |
| `created_at` / `updated_at` / `finished_at` | text | 时间戳 |

#### 完整流程

```
[老板选文件 + 选预设 + 选 provider]
  ↓
POST /api/ai/jobs  (status: pending)
  ↓
后台异步执行
  ↓
1) 读取原文件 → 快照
2) 构造 prompt：原文件 + 预设 + 老板可选的额外指令
3) 调 LLM → 拿到新内容
4) 计算 unified diff → diff_plan
5) status: awaiting_confirm
  ↓
[UI 弹出 diff plan，老板预览]
  ↓
POST /api/ai/jobs/{id}/apply   → status: applied（写入文件 + 自动备份 + 审计）
POST /api/ai/jobs/{id}/reject  → status: rejected（不写入）
  ↓
[失败处理]
status: failed + error 字段
```

#### UI 设计

- 文件编辑页 → 「AI 整理」按钮 → 弹出向导：
  1. 选预设（默认按文件类型过滤）
  2. 选 provider（默认按上次使用）
  3. 可选：附加指令（"把 SOUL.md 里关于群聊的章节合并"）
  4. 「生成」按钮 → 后台任务
- 异步任务跑完后，右下角弹通知 → 点击进入 diff plan 预览页
- Diff plan 页：左右 diff（前端 `DiffView`）+ 「应用」/「拒绝」按钮 + 「重新生成」按钮（带新指令）

#### 安全护栏

- AI 输出**绝不直接覆盖原文件**，必须经过老板 diff 确认
- AI 输出必须通过 lint 检查，违规拒绝写入
- 大文件（> 30KB）拒绝 AI 整理（token 成本 + 质量风险）
- API key 审计：每次调用记录 provider + token 消耗（成本追踪）
- 单文件 AI 调用**默认单次**（老板可点「再来一次」），不自动循环

#### 验收清单

1. ✅ 文件编辑页有「AI 整理」按钮
2. ✅ 向导流程 4 步走（选预设/选 provider/附加指令/生成）
3. ✅ 异步任务跑完后有通知
4. ✅ diff plan 预览页可视化 diff
5. ✅ 应用/拒绝按钮可点
6. ✅ 「重新生成」按钮可带新指令
7. ✅ AI 输出过 lint 才能写入
8. ✅ 大文件 > 30KB 自动拒绝
9. ✅ 调用记录写审计日志

---

### 2.6 M15 · 工作日志标准化（P0 / P1 / P2 / P3 已交付 + 预设收口 + 空日决策 + 归因修正 + 预设边界）

> 完整方案见 [MEMORY-DAILY-STANDARDIZER-PLAN.md](MEMORY-DAILY-STANDARDIZER-PLAN.md)，
> 效率实测见 [M15-EFFICIENCY-REPORT.md](M15-EFFICIENCY-REPORT.md)。
> 本节只记录里程碑定位、已确认的范围边界与阶段进度。

**已交付（P0 · 2026-09-23）**：

1. AI 整理任务的 prompt 接通 `preset.style_rules`（【风格与内容规则】段）——
   此前只存库未注入，属文档↔实现漂移，已修正
2. 新增第 5 条内置预设 `preset-wlog-daily-std`「工作日志日标准化」：
   模板文档定义 4 个含序号的必填章节（一、今日概览 / 二、关键事件 / 三、关键决策 / 四、待办事项，
   `section_order: strict`），`style_rules` 承载 skill 的语义规则（保留清单 / 删除清单 / 客观改写 / 默认不脱敏）
3. 修复 `FormatValidator` 对 Markdown 表格的假阳性：表格行按块级元素处理，不再被判「段落间缺空行」，
   `auto_fix` 也不会再往表格行之间插空行（此前会把表格改坏，而「关键决策」章节正是表格）
4. `seed_builtins()` 支持**存量安装补种新增内置预设**：首次空表全量播种，表非空时只补种
   append-only 白名单 `BUILTIN_PRESETS_ADDED`（本版本 = `preset-wlog-daily-std`）；
   历史内置预设不进白名单，用户已删除的不会被复活。补种时写 v1 版本快照，该快照同时充当
   「已补种」标记——用户日后删掉它，重启不会再塞回来。
   （此前「仅表为空才播种」导致第 5 条内置预设进不了存量安装，P0 交付物不可见）

**已交付（P1 · 2026-09-24）**：

1. **A/B/C 分类器**（`DailySourceScanner`）：只扫 `memory/` **顶层**，按文件名分三类
   （`YYYY-MM-DD.md` / `YYYY-MM-DD-HHMM.md`（含 `-HHMM-2` 去重后缀）/ `YYYY-MM-DD-<topic>.md`），
   按日分组、排出碎片清单、标出「单来源但质量差」；非补零日期、非法日期、子目录与 dreaming 一律排除
2. **12 条确定性预处理器**（`DailyPreprocessor`）：剥会话键 / 两类 untrusted metadata / 引用壳 /
   排队消息 / dreaming 统计壳 / 纯 `HEARTBEAT_OK` / 过程过渡语，并做 BOM、换行、空白归一 ——
   **零 token**，且 `detect_residual_shells()` 可对任意文本终检「残留 = 0」
   （口径 = 真壳规则 M01~M10；M11/M12 是编码·空白归一，对任何文档都会命中，不算残留）
3. **单日「多来源 → 1 文件」归并**（`DailyMergeService`）：组装 prompt（模板规则 + `style_rules` +
   骨架 + 带优先级的来源）→ LLM → `sanitize()` → `FormatValidator` 强规则校验/机械修正；
   超限来源分块摘要（token 全量记账），仍超限则转人工复核；**只出计划，不写盘、不删碎片**
4. 测试：分类器与预处理器单测 100%，集成测试覆盖 4 个场景（单 A 文件 / 单 session 导出 /
   主文件+主题文件 / 同日 3 碎片）；`pytest` 基线 253 passed / 1 skipped

**已交付（P2 · 2026-09-24）**：

1. **批次编排**（`DailyRunService`）：独立两表 `daily_runs` / `daily_run_items`（不复用 `ai_jobs`）；
   幂等键 = `sha256(agent_id + 范围 + preset + provider + 有序来源 SHA-256 集合)`，同键重复提交直接复用
   （`reused=true`），不产生第二次 LLM 调用；护栏有单批天数上限（`max_days_per_run`）与 token 预算
   （`token_budget`，越限中止且不写任何文件）
2. **确认执行**：`apply()` 是唯一写盘入口，且只接受 `awaiting_confirm`；先对**全部目标日**做批次级预检
   —— 乐观锁（`source_hashes_json` 的 SHA-256 比对，冲突抛 `409`）与写前验收（强规则 + 12 类残留壳）
   —— **任一日不过就整批不写**；写入走 `FileManager`（自动备份 + 审计 `daily_apply`），
   碎片删除走 `send2trash`，删失败标 `partially_applied` 且**不回滚日文件**
3. **验收报告**（`build_report()`）：对磁盘上的**真实文件**核对 5 项（单文件 / 命名 / 章节 / 无残留壳 /
   碎片已清），只读可重复跑；不通过则批次标 `needs_review`
4. **API**：`/api/daily-runs` 6 个端点（创建 / 列表 / 详情 / 应用 / 拒绝 / 跳过 / 报告）；
   新增错误码 `DAILY_RUN_NOT_FOUND`（404）/ `DAILY_RUN_STATUS`（409）/ `DAILY_RUN_DISABLED`（403）
5. **前端**：Tools 页「日志标准化」tab（`DailyStandardizerPanel.tsx`）—— 参数 → 逐日确认
   （**默认全部不勾选**，逐日来源 A/B/C 与剥壳体积、拟删碎片、强规则报告、diff 预览）→ 验收报告
6. 测试：新增 `test_daily_runs.py` 17 个用例（完整流程 / 幂等复用 / 乐观锁 409 / 路径穿越 403 /
   写前验收不过零污染 / 碎片删失败 partial / 预算中止 / 跳过与拒绝 / 空范围 / 天数上限 / dry-run 开关）；
   `pytest` 基线 **270 passed / 1 skipped**

**已交付（P3 · 2026-09-24）**：

1. **三种规则投递形态可切换**（`DailyMergeService.plan_day(..., delivery=...)`）：
   `doc_full`（P1/P2 行为，对照基线）/ `trimmed`（按当日来源类型裁剪规则 + 只给章节骨架）/
   `system_embedded`（规则全文进 system prompt）；三形态的「任务 / 目标 / 来源 / 输出要求」逐字一致，
   结论可归因到形态本身（有单测守着）
2. **对比台** `backend/daily_form_bench.py`：固定样本集 × 三形态 × N 次重复，27 次真实调用，
   记录 token / 耗时 / 输出一致性 / 强规则通过率 / 规则改动生效延迟，带 token 预算硬中止；
   只在 `index.db` 副本上跑，不写 workspace、不改真实库
3. **默认形态定稿 = `system_embedded`**：输出 token −9.7%、单日耗时 −13.3%、
   三次输出一致性 0.442 → 0.518、强规则通过率持平 100%；
   `trimmed` 省输入但输出更长、耗时最高、掉过一次强规则 → 不采用（留作复测对照）
4. **运维手册**（方案附录 E）：灰度开关、按范围分批、逐日确认、规则迭代生效成本表、成本预算、
   8 类故障处置、数据回退
5. **修掉两个实测拦死写入的缺陷**：`forbid_raw_html` 把 `` `session:<id>` `` 这类占位符误判为
   HTML（该规则无机械修正 → 整天无法写入）；`sanitize()` 漏剥推理模型的 `<think>` 思考块
   （27/27 次调用都带思考块，英文思考内容匹配不上中文前言特征词 → 成功归并被误判为失败）
6. 测试：`pytest` 基线 **285 passed / 1 skipped**（286 收集）

**已交付（P3 后补记 · 2026-09-24 · 预设收口）**：

1. **WORKLOG 预设合并为一个**：原「工作日志汇总」（`preset-wlog-summary`）与「工作日志日标准化」
   （`preset-wlog-daily-std`）是同一件事的两种口径（**单文件整理 vs 逐日归并**），并列成两个选项
   让用户无法判断该选哪个（两条说明文案都只讲「做什么」，没讲「什么时候用哪个」）。
   现把汇总的归档顺序规则与「明日计划」章节并入日标准化 → 章节扩为 5 条
   （一、今日概览 / 二、关键事件 / 三、关键决策 / 四、待办事项 / **五、明日计划**），
   `sections_json` 与 `template_md` 同步更新
2. **内置预设退役机制**：`presets` 表新增 `retired_at`（非空即退役）。退役的预设
   `list()` 不返回，但**行保留**、`get()` 仍可取——否则历史批次 / AI 任务按 id 读取会 404
3. **存量安装的「刷新 / 退役」迁移**（两张内容锚点表，`preset_service.py`）：
   ① `BUILTIN_PRESETS_REFRESHED`（内容有更新 → 覆盖为新定义 + `version` 自增 + 留快照，
   如本次的日标准化预设）② `BUILTIN_PRESETS_RETIRED`（已下线 → 写 `retired_at`，如本次的汇总预设）。
   判据统一为「库中内容是否仍逐字段等于上一版发布的内置定义」——**用户改过的一律不动**
   （那是用户自己的资产）；此前内置预设的修订只能影响全新安装，老机器永远拿不到
4. 测试：新增 4 个用例（刷新生效 / 用户改过不覆盖 / 退役隐藏但可取 / 用户改过的退役预设保留可见）；
   `pytest` 基线 **289 passed / 1 skipped**（290 收集）

**已交付（P3 后补记 · 2026-09-24 · 空日决策）**：

1. **问题**：prompt 写死「第一行必须是 `# 工作日志 - <date>`」+ 强规则强制必填章节齐全 ——
   模型**没有合法出口**，当天全是噪音（心跳 / 状态轮询 / 无结论的调试流水 / 重复失败重试）时
   只能把这些内容包装成一篇「看起来合规」的日志，即**凑数**
2. **改法**：给模型第二个合法出口——只回一行 `无可归档内容：<一句话理由>`；命中则该日
   **不产出日文件**（`item_status=empty`），B/C 碎片照常列入待清理（走回收站 + 人工确认），
   **A 类主文件 `memory/YYYY-MM-DD.md` 保持不动**。识别从严（`parse_empty_verdict()`：
   >3 行 / 含标题列表表格引用 / 首行不是哨兵 → 一律当普通输出交给强规则），
   正常文档里出现这句话不会被误判
3. **状态与验收**：新增逐日状态 `empty`（不算失败、不计入已交付）；`daily_run_items.empty_reason`
   列存理由；空日的乐观锁改为**逐个碎片比对 SHA-256**；验收报告对空日只核对「碎片已清」；
   全批都是空日且无碎片 → 批次状态 `empty`
4. **主文件定义（与老板确认）**：A 类 = `memory/YYYY-MM-DD.md` **精确命名**（OpenClaw 系统自动
   生成的日文件）；`-HHMM` / `-<topic>` 等其它命名都只是碎片——扫描器按纯正则判定，不做模糊匹配
5. 测试：新增 16 个用例（哨兵识别 10 个参数化 + prompt 出口 + 计划形态 + 空日写盘/无碎片/混合批次/
   碎片乐观锁）；`pytest` 基线 **305 passed / 1 skipped**（306 收集）

**已交付（P3 后补记 · 2026-09-24 · 归因修正）**：

> 由一起真实批次失败排查（2026-09-24 17:46 批次）定位出两个缺陷：**被截断**与**误判残留**。

1. **残留壳口径收窄到真壳规则**：`detect_residual_shells()` 此前遍历全部 12 条预处理规则，
   而 M11「编码与换行归一」/ M12「空白归一」是收尾归一（任何文档都会命中）——
   实测一份合规的 5 章节文档只要结尾带换行就返回 `['M12']`，于是该天被判「仍残留低价值元数据壳」
   而**拒绝写入**（同一 bug 也让验收报告的「无残留壳」列误报）。
   现按 `PreprocessRule.is_shell` 分成真壳（M01~M10）与归一（M11/M12），残留检测只看 `SHELL_RULES`；
   报错文案改用规则名（`describe_shells()`），不再把 `M12` 这类内部编号抛给用户
2. **输出截断如实归因 + 自动重试**：`LLMClient` 此前从不读响应的 `finish_reason`
   （Anthropic 为 `stop_reason`）—— 模型写了一半被 `max_tokens` 截断时只剩「章节缺失」这类结论，
   用户按「格式问题」方向反复重跑永远修不好（违反 UI-SPECS「不得谎报失败原因」）。
   现 `LLMResponse` 记录 `finish_reason` 并提供 `truncated` 判定；`chat()` 检测到截断时
   **自动以翻倍预算重试一次**（封顶 32768），仍截断则抛新增的 `LLMOutputTruncatedError`
   （`422` / `LLM_OUTPUT_TRUNCATED`），消息直接给出「到设置 → LLM Provider 调大该 provider
   的 `max_tokens`」的解法；影响面覆盖 M15 归并、M13 AI 整理与 `POST /api/llm/chat`
3. 测试：新增 7 个用例（合规文档带尾换行的回归反例 / 真壳仍检出 / `is_shell` 目录 /
   `finish_reason` 判定矩阵 / 重试预算 [64,128] / 持续截断抛错 / API 映射 422）；
   `pytest` 基线 **312 passed / 1 skipped**（313 收集）

**已交付（P3 后补记 · 2026-09-24 · 预设边界）**：

> 诉求：消除「当前生效的预设从哪来、该去哪改」的认知盲区——此前日志预设同时出现在
> 设置页「文档预设」与主工作台「应用预设」里，两类预设混在一起。

1. **判据与过滤**：`target_file_type = WORKLOG` 即「专供大模型处理工作日志」（`DAILY_PRESET_TYPE`，
   不加开关字段）；`GET /api/presets` 新增 `scope`（`all` / `workbench`，非法值 400），
   设置页「文档预设」与主工作台「应用预设 / AI 整理」统一取 `scope=workbench` → 不再出现日志预设；
   设置页新建预设的类型下拉也不再提供 WORKLOG，并注明去「业务工具 → 日志标准化」管理
2. **M15 界面新增预设信息栏**：徽章「大模型专用」+ 预设名 + 版本 + 来源（`is_builtin` ? 内置预设 : 用户自建）
   +「查看 / 编辑」+ 边界说明（专供大模型、不在别处出现、改完重新生成批次生效）
3. **M15 页内预设编辑器**（`DailyPresetEditor.tsx`）：可改用途说明 / 模板文档（YAML 规则 + 章节骨架）/
   风格与内容规则（`style_rules` 逐行）——比设置页表单多出第三项，那正是注入 prompt 的弱规则；
   保存走 `PUT /api/presets/{id}`（version +1 + 版本快照），**新批次即用新规则**
   （已生成的计划不重算；逐日确认页信息条补 `预设 v{N}` 如实标注批次绑定的版本）
4. 预设响应新增 `is_builtin`（是否随版本分发的内置预设）；顺带修正若干过时描述
   （「系统预设不可删 / 仅可改 description + style_rules」与实现不符——内置预设播种即 `is_system=0`，
   与用户预设同等可编辑可删除）
5. 测试：新增 4 个用例（workbench 排除内置日志预设 / 用户自建 WORKLOG 同样排除 / 非法 scope 400 /
   `is_builtin` 来源标识）；`pytest` 基线 **316 passed / 1 skipped**（317 收集）；
   前端 `npm run build` 通过，浏览器实测 4 步（信息栏标识 / 页内编辑保存并刷新版本 / 文档预设页排除 /
   主工作台应用预设排除）全部符合预期

**目标**：把指定 Agent `memory/` 下某段日期范围的工作日志整理成**每天恰好 1 个 `YYYY-MM-DD.md`**，
剥离 session 元数据壳与对话腔噪音，保留关键事实、决策与待办。

**与 Phase 2.5 的关系**：复用既有 AI Editor 机器（文档预设 + 版本历史 + LLM provider + plan/diff 确认 + 备份审计），
新增的是**批次级编排**（同日 N 来源 → 1 文件 + 碎片删除），不改动既有单文件整理路径。

**已确认的范围边界**（2026-09-23 决策）：

| # | 决策 |
|---|---|
| 1 | 不实现 session corpus / dreaming（外部来源），不引入外部来源目录 |
| 2 | 触发方式：手动一键 + 批次确认（不做定时调度） |
| 3 | 批次粒度：一次只处理一个 Agent 的 `memory/` 目录（`agent_id` 必填） |
| 4 | 碎片归档后删除、不留痕；输出内容中不写来源信息 |

**交付阶段**：P0 地基（接通 `style_rules` 到 prompt + skill 落成预设）→ P1 单日归并 → P2 批次与 UI → P3 效率对比。

**验收门**：每天 1 文件 / 命名合规 / 5 章节齐全 = 100%（分母排除模型判定「无可归档内容」的日子）；
低价值元数据**壳**残留 = 0（口径 = 真壳规则 M01~M10；M11/M12 是编码·空白归一，对任何文档都会命中，不计入）；
关键事实保留率 ≥ 95%；碎片删除 100%（经回收站可恢复）；失败批次零污染；
**失败归因如实**（输出被 `max_tokens` 截断必须报配额不足而非「格式违规」）；既有功能零回归。

---

## 三、Phase 2 · UI 优化（已交付）

### 3.1 目标

> 提升页面交互和美观度，让老板用得更顺手。

### 3.2 任务清单

| 优先级 | 任务 | 说明 |
|---|---|---|
| 高 | 顶部状态条加实时指示 | 连接状态 / 索引文件数 / 上次扫描时间 |
| 高 | 文件树加折叠 + 搜索 | 支持 `/` 快捷键聚焦搜索框 |
| 高 | 编辑器加字体大小调节 | Ctrl +/- 缩放 |
| 中 | 主题切换 | 浅色 / 深色 / 跟随系统 |
| 中 | diff 页加并排/上下两种模式 | 默认并排，可切上下 |
| 中 | toast 通知加分类 | success / warning / error 三色 |
| 低 | 加载动画统一 | spinner / skeleton |
| 低 | 键盘快捷键文档 | `/` 搜索 / `Ctrl+S` 保存 / `Ctrl+K` 命令面板 |

### 3.3 验收清单

1. ✅ 所有交互在 ≥1280px 屏幕上视觉一致
2. ✅ 顶部状态条实时更新（≤ 5s 延迟）
3. ✅ 主题切换记忆（localStorage）
4. ✅ 快捷键 Ctrl+S 保存不刷新页面

---

## 四、Phase 3 · 远期规划

| 优化 | 优先级 | 说明 |
|---|---|---|
| 多用户 / 鉴权 | 低 | 单人本地用不到 |
| 云端同步 | 低 | 隐私敏感 |
| WebSocket 实时同步 | 低 | 单老板规模不需要 |
| 第三方 lint 规则插件 | 中 | 跟模板贡献一起做 |
| 第三方预设贡献 | 中 | GitHub PR 形式 |
| 跨框架适配 | 中 | OpenClaw → LangGraph / AutoGen |
| AI 整理的「规则库」 | 中 | 把老板常用的整理规则沉淀成可复用 preset |
| AI 整理的「批量模式」 | 低 | 一次对多个文件应用同一预设 |

---

## 五、风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| LLM 输出质量不稳定 | AI 整理结果难用 | 强制走 diff 确认，不自动写入 |
| LLM API 成本失控 | 月账单爆炸 | 审计日志记录 token 消耗 + 单文件单次默认 |
| 预设被滥用 | 老板的预设被批量改坏 | 预设按 Agent 隔离，跨 Agent 应用走 plan + confirm |
| API key 泄露 | 严重安全事件 | 加密存储 + UI 掩码 + 泄露检测 |
| 大文件 token 超限 | AI 调用失败 | > 30KB 自动拒绝，强制文件拆分 |
| OpenClaw workspace 路径变更 | 数据全丢 | AgentDiscovery 自动发现 + 软链 |
| 误操作删了整个 workspace | 全部 Agent 失效 | Soulforge 永不删 workspace 根目录 |

---

## 六、给 AI 编程助手（Trae）的开发节奏建议

> Phase 2.5 已按本节节奏交付，保留作为方法参考。

### 6.1 Phase 2.5 的工作流

1. **Step 1 优先**：先把 presets 数据模型 + 4 个内置预设 + 基础 CRUD 跑通
2. **Step 2 接 provider**：先跑通 OpenAI 一个协议，再补 Anthropic / Ollama
3. **Step 3 做端到端**：选 SOUL.md + 内置 preset + OpenAI → diff 确认 → 写入，跑通最小闭环
4. **每步完成就跑验收清单**：老板逐项点 ✓

### 6.2 别做的事

- ❌ Step 1 不要做 AI 调用（先把数据层跑通）
- ❌ Step 2 不要做 Anthropic 协议（先跑通 OpenAI，再扩展）
- ❌ Step 3 不要做自动写入（必须老板确认）
- ❌ 不要在 Phase 2.5 做 WebSocket / 云端同步 / 多用户
- ❌ 不要把 API key 落 git

### 6.3 老板验收节点

| 节点 | 验收人 | 验收内容 |
|---|---|---|
| Step 1 结束 | 老板 | 4 个内置预设 + CRUD + 应用流程 |
| Step 2 结束 | 老板 | LLM Provider 管理 + 热加载 |
| Step 3 结束 | 老板 | AI 整理 E2E 流程（生成→diff→确认→写入） |
| Phase 2 UI 结束 | 老板 | UI 优化 9 项验收清单 |

---

## 七、上线计划

### 7.1 当前状态（v0.5.0 基线）

> **版本约定**：`0.5.0` 是统一版本基线，**尚未打 tag**；之后的交付（M15 全部阶段与其后补记等）
> 继续累计在同一版本条目内，不另起版本号（见 [CHANGELOG.md](../CHANGELOG.md) 的「发版流程」约定）。

- [x] README 补充 AI Editor / 超级同步章节（2026-09-24 补 M15 工作日志标准化）
- [x] 建立统一版本号链路（`backend/app/__init__.py` + [CHANGELOG.md](../CHANGELOG.md)）
- [ ] 在 GitHub 打标签并发 Release（`git tag v0.5.0`）
- [ ] 录 1 个 5 分钟 AI Editor 演示视频
- [ ] 写迁移指南（老版本 → v0.5.0：数据库会自动补列，无需手工迁移）

### 7.2 Phase 3 完成后再规划发布节奏

Phase 3 尚未启动，届时再确定版本号与发布窗口。

### 7.3 GitHub 仓库结构（不变）

```
soulforge/
├── README.md
├── LICENSE (MIT)
├── docs/
├── backend/
├── frontend/
├── tests/
└── .github/
```

---

## 八、长期愿景

> Soulforge 不再只是 OpenClaw 内部工具，而是「任何 LLM Agent system-prompt 文件」的通用管理器 + AI 文档整理助手。
> 形成一个跨框架的 prompt 工程 + AI 文档工程生态。

但**先专注 Phase 2.5 三步走**，跑通再说。

---

## 附录 A · Phase 1 MVP 回顾

> 保留 Phase 1 的落地路径作为历史存档（当时未打独立版本号）。

### A.1 Phase 1 里程碑节奏

> 当时未打独立版本号，按交付顺序记录；统一版本基线自 v0.5.0 起。

| 里程碑 | 范围 | 周期 | 状态 |
|---|---|---|---|
| M1 骨架 | 浏览 + 编辑 + 备份 + lint | 2 周 | ✅ 已交付 |
| M2 检索 | 搜索 + diff | 1 周 | ✅ 已交付 |
| M3 协同 | 跨 Agent 同步 + 导出 | 1 周 | ✅ 已交付 |
| M4 观测 | 统计 + 审计日志 UI | 1 周 | ✅ 已交付 |

### A.2 Phase 1 模块矩阵

| 模块 | 交付物 | 状态 |
|---|---|---|
| M1 Agent 管理 | `GET/POST /api/agents` + Agent 树 UI | ✅ |
| M2 文件浏览/编辑 | Monaco 编辑器 + 自动备份 | ✅ |
| M3 跨 Agent 搜索 | ripgrep 后端 + Cmd+K UI | ✅ |
| M4 Diff 对比 | 自研归一化 diff + 双 Agent 对比 + 历史对比 | ✅ |
| M5 跨 Agent 同步 | plan + execute 两步流程 | ✅ |
| M6 导出 | `.tar.gz` + manifest（导入能力已移除） | ✅ |
| M7 备份/回滚 | 自动备份 + 30 天保留 + 一键回滚 | ✅ |
| M8 Lint | 8 条规则 + 健康检查 UI | ✅ |
| M9 模板系统 | 4 个内置模板 + 应用到新 Agent（已移除） | ❌ |
| M10 统计/仪表盘 | 仪表盘 API + UI + 审计日志 | ✅ |

### A.3 Phase 1 关键决策（保留供 Phase 2.5 参考）

- **单进程部署**：FastAPI 同时 serve React build + API
- **本地零配置**：默认端口 8848，127.0.0.1，不暴露公网
- **备份外置**：`.soulforge/backups/`，不污染 workspace
- **审计日志**：所有写操作进 `audit_log` 表
- **lint 不强制拦截**：只警告，除非老板开启「严格模式」

---

*最后更新：2026-09-24 · M15（工作日志标准化）P0 / P1 / P2 / P3 全部交付（扫描分类 → 单日归并 → 批次编排 / 确认执行 / 验收报告 / 前端 tab → 规则投递形态效率对比与运维手册），并完成预设收口（WORKLOG 预设合并为一个 + 存量安装刷新/退役迁移）、空日决策（全天无内容时不产出日文件，不再硬凑）、归因修正（残留壳口径收窄到真壳 M01~M10 + 输出截断如实归因与自动重试）与预设边界（日志预设只在日志标准化界面可见可编辑，文档预设页与主工作台按 `scope=workbench` 排除）；Phase 1 / 2 / 2.5 与超级同步均已交付。当前版本基线 **0.5.0**（未打 tag，交付持续累计）*