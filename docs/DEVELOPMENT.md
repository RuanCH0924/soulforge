# Soulforge — 开发文档

> 本文件是写给 **AI 编程助手**（Trae / Cursor / Windsurf）阅读的完整开发说明书。
> 项目拥有者不需要懂代码，把本文档丢给 AI，它就能理解项目全貌并逐步生成代码。
> 开发方式：Vibe Coding（自然语言描述 → AI 生成代码 → 老板验收）
>
> **版本号**：唯一事实源为 `backend/app/__init__.py` 的 `__version__`（当前 `0.5.0`），
> 版本历史与发版流程见 [CHANGELOG.md](../CHANGELOG.md)。

---

## 一、项目目标

做一个 **OpenClaw 跨 Agent system-prompt 文件管理器**，名字叫 "Soulforge"（灵魂锻造炉）。

### 一句话描述

> 把 OpenClaw 所有 Agent 的「灵魂文件」当作源码管理：浏览、搜索、编辑、同步、备份、导出，一个 Web 页面搞定。

### 核心痛点

老板目前维护 5+ 个 Agent（main / xiaowei-ops / xiaozhi-contributor / xiaoxi-lawyer / caicai-analyst / susu-tutor），每个 Agent 都有自己的 workspace。每次想做下面这些事都很痛苦：

| 痛点 | 现状 | Soulforge 解法 |
|---|---|---|
| 想看某个 Agent 的 `SOUL.md` 是怎么写的 | 要打开 VSCode 切到对应 workspace | Web 页面左侧 Agent 树，点开就预览 |
| 想在所有 Agent 的 `MEMORY.md` 加同一句规则 | 手动开 5 个文件复制粘贴 | 「跨 Agent 编辑」选多个 Agent，一次写 |
| 想知道两个 Agent 的 `AGENTS.md` 差异 | 手动 `diff` 命令 | 「对比」按钮 → 可视化 diff |
| 误改了某个文件想回滚 | 找 git log（如果 workspace 进了 git） | 「备份历史」一键回滚（自动备份，无需 git） |
| 多个 Agent 的同名核心文档内容漂移 | 手动逐个文件对比、复制粘贴 | 「超级同步」独立守护进程按最新修改优先，秒级保持一致 |
| 想知道哪些文件有 L4 反模式（"最后修订" / "v1.0"） | 手动逐文件检查 | 「健康检查」自动 lint + 高亮违规 |

### 核心体验

- 你**不需要**懂 Git、懂 Markdown 语法细节、懂 workspace 路径
- 它**自动发现**所有 Agent（读 `openclaw.json` 的 `agents.list`）
- 它**自动备份**每次写入的文件（无需你手动 commit）
- 它**图形化**所有危险操作（删文件 / 跨 Agent 覆盖 / 大批量改）
- 它**联动 lint** —— 一边编辑一边提示你"这段有 L4 痕迹，建议删"

---

## 二、核心概念

### 2.1 Agent

OpenClaw 配置文件 `~/.openclaw/openclaw.json` 中的 `agents.list[]` 每一项 = 一个 Agent：

```json
{
  "agents": {
    "list": [
      {
        "id": "main",
        "workspace": "~/.openclaw/workspace"
      },
      {
        "id": "xiaowei-ops",
        "workspace": "~/.openclaw/workspace-agents/xiaowei-ops"
      }
    ]
  }
}
```

**Soulforge 把"Agent"当作一等公民**，每个 Agent 有：

- ID
- workspace 路径
- workspace 下所有 Markdown 文件的清单（含元数据）

### 2.2 Prompt File

workspace 下的所有 Markdown 文件，按"角色"分四类：

| 角色 | 文件 | 加载时机 | 老板关注度 |
|---|---|---|---|
| **CORE** | `SOUL.md` / `AGENTS.md` / `IDENTITY.md` / `USER.md` / `TOOLS.md` / `MEMORY.md` / `HEARTBEAT.md` / `DREAMS.md` | 每次会话启动注入 | ⭐⭐⭐ |
| **MEMORY** | `memory/YYYY-MM-DD.md` / `memory/<topic>.md` | 按需 `memory_search` | ⭐⭐ |
| **SKILL** | `skills/<name>/SKILL.md` | 技能触发时加载 | ⭐⭐ |
| **META** | `openclaw.json` / `.credentials.md` / 其他配置 | Gateway 启动加载 | ⭐（谨慎） |

**Soulforge 默认只管理 CORE + MEMORY 两类**。SKILL / META 列入「高级」开关，默认隐藏。

### 2.3 Prompt Pack

一个 Agent 的全部 CORE + MEMORY 文件 = 一个 **Prompt Pack**。

Soulforge 的导出单位就是 Prompt Pack（`.tar.gz`，含 SHA256 manifest）。

### 2.4 Lint 规则（呼应老板 SOUL/AGENTS 护栏）

Soulforge 内置一套 lint 检查，发现违规主动提示：

| 规则 ID | 名称 | 作用域 | 检查内容（示例） |
|---|---|---|---|
| `L4-TIMESTAMP` | L4 反模式 — 时间戳 | 单个文件 | `*最后修订：…*` / `*最后更新：…*` / `## 更新记录` / `## Changelog` |
| `L4-VERSION` | L4 反模式 — 版本号 | 单个文件 | `## v1.0` / `Skill 版本：v1.0` / `首次验证：YYYY-MM-DD` |
| `L4-NARRATIVE` | L4 反模式 — 修复叙述 | 单个文件 | "用户指出 XXX，触发 YYY" / "起因：…误判事故" |
| `BOUNDARY-VIOLATE` | 5 大文档边界违规 | 单个文件 | 比如"老板偏好"进错了 AGENTS.md |
| `EMPTY-FILE` | 空文件 | 单个文件 | 文件 < 10 字节且不是占位文件 |
| `LARGE-FILE` | 超大文件 | 单个文件 | 单文件 > 50KB 时提示 |
| `CORE-MISSING` | CORE 必填文件缺失 | 整个 Agent | 比如新 Agent 缺 `IDENTITY.md` |
| `CROSS-AGENT-DRIFT` | 跨 Agent 同名文件 drift 过大 | 整个 Agent | 同样叫 `AGENTS.md`，5 个 Agent 内容相似度 < 30% 时警告 |

**规则文案的唯一事实源**：`backend/app/services/lint_service.py` 的各规则类
（`rule_id` / `rule_name` / `scope` / `severity` / `description`），由 `LintService.rule_catalog()` 汇总、
经 `GET /api/lint/rules` 下发，前端（数据中心 → 检查报告顶部的「检查规则」表）直接渲染。
本表只作索引，**改动规则时必须同步本表**。

**lint 不强制拦截，只警告**（除非老板在设置里开启「严格模式」）。

---

## 三、功能模块

### 3.0 模块矩阵

| ID | 模块 | Phase | 状态 |
|---|---|---|---|
| M1 | Agent 管理 | 1 | ✅ |
| M2 | 文件浏览/编辑 | 1 | ✅ |
| M3 | 跨 Agent 搜索 | 1 | ✅ |
| M4 | Diff 对比 | 1 | ✅ |
| M5 | 跨 Agent 同步 | 1 | ✅ |
| M6 | 导出 | 1 | ✅ |
| M7 | 备份/回滚 | 1 | ✅ |
| M8 | Lint | 1 | ✅ |
| M9 | 模板系统（已移除） | 1 | ❌ |
| M10 | 统计/仪表盘 | 1 | ✅ |
| **M11** | **文档预设系统** | **2.5** | **✅** |
| **M12** | **LLM Provider 接入** | **2.5** | **✅** |
| **M13** | **AI 自动整理** | **2.5** | **✅** |
| **M14** | **超级同步（独立守护脚本）** | **2.5** | **✅** |
| **M15** | **工作日志标准化（memory/ 日文件归并）** | **—** | **✅ P0 / P1 / P2 / P3 已交付 + 预设收口 + 空日决策 + 归因修正 + 预设边界**（P2 = 批次编排 + 确认执行 + 碎片清理 + 验收报告 + Tools 页「日志标准化」tab；P3 = 规则投递形态效率对比 + 运维手册；收口 = WORKLOG 预设合并为一个；空日决策 = 全天无内容时不产出日文件；归因修正 = 残留壳口径收窄到真壳 + 输出截断如实归因与重试；预设边界 = 日志预设只在日志标准化界面可见可编辑，见 [MEMORY-DAILY-STANDARDIZER-PLAN.md](MEMORY-DAILY-STANDARDIZER-PLAN.md)） |

---

### 模块 M1：Agent 管理

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/agents` | 左侧栏 | 列出全部 Agent（含 workspace 路径、文件数、最后修改时间） |
| `GET /api/agents/{id}` | Agent 详情页 | 单个 Agent 的元数据 + 文件清单 |
| `POST /api/agents/scan` | 顶部「重新扫描」 | 重新读 `openclaw.json` + 重建索引 |

**自动发现**：优先读 `openclaw.json` 的 `agents.list`；兜底扫描 OpenClaw 根下 `workspace*` 目录，
其中 `workspace-attestations` 等非 Agent 目录会被自动忽略。

### 模块 M2：文件浏览 & 编辑

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/agents/{id}/files` | 左侧 Agent → 中间文件树 | 列出该 Agent 的 Prompt Pack（含角色分类） |
| `GET /api/agents/{id}/files/{path}` | 中间文件树 → 右侧预览 | 读取并预览（read-only） |
| `PUT /api/agents/{id}/files/{path}` | 右侧编辑器 → 「保存」 | 编辑 + 写入（**自动备份**） |
| `GET /api/agents/{id}/files/{path}/history` | 文件详情 → 「历史」 | 备份历史列表 |

**编辑器**：用 Monaco Editor（VSCode 同款内核），老板熟悉，markdown 实时预览。

### 模块 M3：跨 Agent 搜索

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `POST /api/search` | 顶部搜索框 / 命令面板 | 跨 Agent 全文搜（ripgrep 后端）；`agent_ids` 限定 Agent、`file_patterns` 限定文件名（如只搜 `SOUL.md`） |

支持：正则 / 大小写 / 上下文 3 行。

### 模块 M4：Diff 对比

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/diff?a={a}&b={b}&file={f}` | 「对比」按钮 → 选两个 Agent + 选文件 | 行级 diff 高亮 |
| `GET /api/diff/history?agent={id}&file={f}&against={ts}` | 文件历史 → 「对比旧版本」 | 跟历史备份对比 |

Diff 渲染用后端归一化 + 行级 diff（`diff_service`），前端 `DiffView` 高亮渲染。

### 模块 M5：跨 Agent 同步

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/sync/plan?src={a}&dst={b}&files={f1,f2}` | 「同步」按钮 → 选源 Agent + 目标 Agent + 选文件 | **先返回 diff plan，让老板确认** |
| `POST /api/sync/execute` | Diff plan 页面 → 「确认执行」 | 执行选择性合并（绝不整文件覆盖） |

**安全护栏**：跨 Agent 同步必须走「plan + confirm」两步，绝不允许一键 cp。

### 模块 M6：导出

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/export/{id}` | Agent 详情 → 「导出」 | 导出 Prompt Pack 为 `.tar.gz` |
| `GET /api/export/all` | 业务工具 → 「导出全部」 | 全部 Agent |

### 模块 M7：备份与回滚

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/backups/{id}` | Agent 详情 → 「备份历史」 | 列出该 Agent 的所有备份 |
| `POST /api/backups/{agent}/{file}/rollback` | 备份列表 → 「回滚」按钮 | 一键回滚到指定版本（**再备份当前状态一次**，避免回滚丢数据） |

**自动备份**：每次 `PUT /api/agents/{id}/files/{path}` 自动生成 `.bak.YYYYMMDD-HHMMSS`。**保留 30 天**（可在设置里改）。

### 模块 M8：健康检查 / Lint

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/lint/{id}` | Agent 详情 → 「健康检查」按钮 | 对该 Agent 跑全部 lint 规则 |
| `GET /api/lint/all` | 顶部 → 「全局健康检查」 | 全部 Agent |
| `GET /api/lint/file/{agent}/{file}` | 文件编辑页 → 「检查」 | 单文件 lint（编辑器右侧实时提示） |
| `GET /api/lint/rules` | 数据中心 → 检查报告 → 「检查规则」 | 规则清单（id / 名称 / 作用域 / 级别 / 说明），前端不写死文案 |

违规显示为「红点」+ 悬浮提示 + 「一键跳转修复」。

### 模块 M10：统计 & 仪表盘

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/stats` | 首页仪表盘 | 汇总数据：Agent 数、文件数、最大文件、Lint 警告数等 |

---

### 模块 M11：文档预设系统（Phase 2.5 · Step 1）

> 老板诉求：保存「文档应该长什么样」的预设（SOUL/AGENTS/MEMORY/工作日志等），让所有文档结构统一。

**核心数据**：

```json
{
  "name": "SOUL.md 标准结构",
  "target_file_type": "SOUL",
  "sections": [
    {"title": "核心行为准则", "required": true,  "order": 1, "hint": "简洁优先、目标导向"},
    {"title": "工作态度和原则", "required": true,  "order": 2, "hint": "先想后做、不吹嘘"},
    {"title": "学习与连续性",   "required": true,  "order": 3, "hint": "记录、更新、演进"},
    {"title": "核心边界",       "required": true,  "order": 4, "hint": "隐私、操作授权"}
  ],
  "frontmatter": {
    "schema": "soulforge.preset/v1",
    "owner":  "user"
  },
  "style_rules": ["emoji-in-section-title=false", "口语化禁令", "必须带应用范例"]
}
```

**端点**：`GET /api/presets`（`?target_file_type=` 按类型过滤 / `?scope=workbench` 排除大模型专用预设）、`GET/POST/PUT/DELETE /api/presets[/{id}]`、`POST /api/presets/from-document`（由当前文档生成）、`POST /api/presets/{id}/apply`、`POST /api/presets/{id}/apply/execute`。

**UI 入口**：
- 系统配置页 → 「文档预设」 → 列表 + 新建/编辑/删除 + 版本历史/回溯（**不含 WORKLOG 类**）
- 文件编辑页 → 「应用预设」按钮 → 选预设 → 生成 diff plan → 老板确认 → 写入（**不含 WORKLOG 类**）
- 文件编辑页工具栏 → 「设为预设」按钮 → 填写参数（名称/适用类型/说明/章节层级/必填章节/顺序/frontmatter）→ 存为预设
- 业务工具 → 日志标准化 → 预设信息栏「查看 / 编辑」→ 页内编辑工作日志预设（**只在这里**）

**两类预设的边界（不得混淆）**：

| 用途 | 判据 | 可见 / 可编辑的地方 |
|---|---|---|
| 供**大模型归并工作日志**（M15 的规则载体） | `target_file_type = WORKLOG` | 只在「业务工具 → 日志标准化」界面（预设信息栏 + 页内编辑弹窗）；取用方式 `GET /api/presets?target_file_type=WORKLOG` |
| 供**主工作台加载**（应用预设 / AI 整理 / 设为预设） | 其余类型 | 设置页「文档预设」、编辑器「应用预设 / AI 整理」；取用方式 `GET /api/presets?scope=workbench` |

判据只有类型本身，没有额外的开关字段（常量 `preset_service.DAILY_PRESET_TYPE`）；两侧的过滤都在**后端**完成，
前端不自己判断。`Preset.is_builtin`（是否随版本分发的内置预设）用于 UI 展示「预设来源」。

**「设为预设」语义**：以编辑器当前内容作模板正文，按参数生成带 YAML 规则 frontmatter 的模板文档；
章节清单来自文档中指定层级的标题（扫描跳过围栏代码块），用户勾选决定哪些进必填；
`max_heading_level` 由文档实际标题层级推断；模板正文 ≤ 30KB（模板全文会注入 AI 提示词）。

**关键护栏**：
- 内置预设与用户预设**同等可编辑、可删除**（播种时 `is_system=0`）；被用户改过的内置预设不会被升级覆盖（内容锚点比对）
- 应用预设走 plan + execute 两步，**绝不直接覆盖**
- 预设 version 字段自增，老板可迭代升级（`PUT /api/presets/{id}` 也会写版本快照，可回溯）
- 日志标准化用的预设改完**不重算已生成的计划**：新批次才用新规则（批次里记的是创建时的 `preset_version`）

---

### 模块 M12：LLM Provider 接入（Phase 2.5 · Step 2）

> 让 Soulforge 能调任意 OpenAI 兼容协议的 LLM（OpenAI / Anthropic / DeepSeek / Ollama），配置变更可热加载。

**核心数据**：见 `DATA-MODEL.md` 中 `llm_providers` 表。

**协议适配器**：

```python
class LLMProvider(Protocol):
    id: str
    protocol: Literal["openai-completions", "anthropic-messages"]
    base_url: str
    api_key: SecretStr
    model: str

    async def chat(self, messages: list[dict], **kwargs) -> str: ...
```

**OpenAI 协议**：`POST {base_url}/chat/completions`，`Authorization: Bearer {key}`
**Anthropic 协议**：`POST {base_url}/v1/messages`，`x-api-key: {key}` + `anthropic-version: 2023-06-01`

**端点**：`GET/POST/PUT/DELETE /api/llm/providers[/{id}]`、`POST /api/llm/providers/{id}/test`、`POST /api/llm/chat`。

**关键护栏**：
- API key **Fernet 加密存储**（密钥来自 `SOULFORGE_SECRET` 环境变量或首次启动生成 `.soulforge/secrets/key`）
- API key 在 UI 永远显示掩码 `sk-****...****`
- `.gitignore` 加 `.soulforge/secrets/`，备份也排除
- 配置中心 UI 有「泄露检测」按钮：扫描日志/审计里是否泄露过明文 key

---

### 模块 M13：AI 自动整理（Phase 2.5 · Step 3）

> 老板选预设 + 选文件 + 选 provider → AI Agent 按预设重写 → 生成 diff → 老板确认 → 写入。

**完整流程**：

```
1. 老板在文件编辑页点「AI 整理」
2. 弹出向导：选预设（默认按文件类型过滤）→ 选 provider → 附加指令（可选）
3. POST /api/ai/jobs  (status: pending)
4. 后台异步执行：
   a. 读取原文件 → input_snapshot
   b. 构造 prompt：原文件 + preset.sections + preset.style_rules + 附加指令
   c. 调 LLM → output_content
   d. 计算 unified diff → diff_plan_json
   e. status: awaiting_confirm
5. UI 收到通知 → 跳 diff plan 预览页
6. 老板点「应用」→ POST /api/ai/jobs/{id}/apply → status: applied（写入 + 备份 + 审计）
   老板点「拒绝」→ POST /api/ai/jobs/{id}/reject → status: rejected
   老板点「重新生成」→ 回到第 3 步，带新指令
```

**端点**：`POST /api/ai/jobs`、`GET /api/ai/jobs/{id}`、`POST /api/ai/jobs/{id}/apply`、`POST /api/ai/jobs/{id}/reject`、`POST /api/ai/jobs/{id}/regenerate`。

**关键护栏**：
- AI 输出**绝不直接覆盖原文件**，必须经老板 diff 确认
- AI 输出先做**输出净化**：剥离模型写在正文前的思考过程 / 规则复述（如「让我仔细分析这个任务：…」）
  与整篇文档的外层代码围栏，再进入格式校验（见 `FormatValidator.sanitize()`）
- AI 输出过 lint 才能写入（违规拒绝写入 + 提示老板）
- 大文件（> 30KB）拒绝 AI 整理（token 成本 + 质量风险）
- 单文件 AI 调用**默认单次**，老板可点「重新生成」
- 每次调用记录 provider + token 消耗 + 成本（审计日志）

**Prompt 构造模板**（示意；实际实现见 `app/services/ai_job_service.py` 的 `_build_prompt()`，
另额外注入【格式化规则】（`template_rule_summary` 生成）与【模板文档全文】，段名为「风格与内容规则」）：

```text
你是 Soulforge 的 AI 文档整理助手。

【任务】按以下预设结构，重新整理用户的文档，保留原意，不要丢失信息。

【预设：{preset.name}】
适用文件类型：{preset.target_file_type}
必须章节（按顺序）：
{preset.sections_json}

【风格与内容规则】
{preset.style_rules}

【附加指令】（老板可选）
{user_extra_instructions}

【原文档】
```markdown
{file_content}
```

【输出】
只输出整理后的 Markdown 内容，不要解释，不要前缀。
```

### 模块 M14：超级同步（独立守护脚本）

> 与 M5「跨 Agent 同步（plan + confirm 两步）」不同：超级同步是**持续运行的独立进程**，
> 对多个 Agent 的同名核心文档做**秒级双向同步**（冲突策略：最新修改优先）。

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET` / `PUT /api/super-sync/config` | 业务工具 → 超级同步 → 同步范围 | 读取 / 更新同步范围（参与 Agent + 文档矩阵） |
| `GET /api/super-sync/status` | 业务工具 → 超级同步 → 运行状态 | 运行中 / 已停止 / 异常（UI 每 2.5s 轮询） |
| `POST /api/super-sync/start` · `/stop` | 运行状态 → 启动 / 停止 / 重启 | 以**分离进程**启停独立脚本 |
| `GET /api/super-sync/logs`（+ `/export`） | 业务工具 → 超级同步 → 同步日志 | 按级别 / 时间检索、导出 `.jsonl` |

**同步文档白名单**：仅 `SOUL.md` / `AGENTS.md` / `USER.md` / `MEMORY.md` / `IDENTITY.md` 这 5 个核心文档参与同步（配置层强制过滤，其余路径一律丢弃）。

**双启动**：UI 按钮（后端以分离进程拉起，主进程退出后继续运行）与命令行 `python super_sync.py` 等价，共用同一份 `config.json` / `status.json`。

**落盘**：`<data_dir>/super_sync/`（`config.json` / `status.json` / `logs/*.jsonl`，日志留存 ≥ 30 天）。

详见 [ARCHITECTURE.md](./ARCHITECTURE.md) 3.11 与 [API.md](./API.md) 3.13。

---

### 模块 M15：工作日志标准化（P2 / P3 已交付 + 预设收口）

> 目标：把指定 Agent `memory/` 下某段日期范围的工作日志整理成**每天恰好 1 个 `YYYY-MM-DD.md`**。
> 完整方案、范围边界与验收标准见 [MEMORY-DAILY-STANDARDIZER-PLAN.md](MEMORY-DAILY-STANDARDIZER-PLAN.md)；
> 批次状态机与端点见该方案附录 D 与 [API.md](./API.md) 3.15。

| 服务 | 文件 | 职责 |
|---|---|---|
| `DailySourceScanner` | `backend/app/services/daily_source_scanner.py` | 扫 `memory/` **顶层**、按文件名分 A/B/C 三类、按日分组、标出碎片与「单来源但质量差」 |
| （预处理器） | `backend/app/services/daily_preprocessor.py` | 12 条**确定性**规则（零 token）= 真壳 M01~M10 + 归一 M11/M12；`SHELL_RULES` / `detect_residual_shells()`（只查真壳，归一不算残留）供验收「残留 = 0」，`describe_shells()` 渲染可读规则名 |
| `DailyMergeService` | `backend/app/services/daily_merge_service.py` | 单日多来源 → 1 文件：组装 prompt（模板规则 + `style_rules` + 骨架 + 来源）→ LLM → `sanitize()` → `FormatValidator` 强规则校验；超限来源分块摘要，仍超限转人工复核 |
| `DailyRunService` | `backend/app/services/daily_run_service.py` | 批次编排：创建（幂等键 / 天数与 token 上限 / 后台逐日生成）→ 确认执行（批次级写前预检 + 乐观锁 → 写入 + 备份 + 审计 → 碎片 `send2trash`）→ 验收报告（对磁盘真实文件核对 5 项） |
| API | `backend/app/api/daily.py` | `/api/daily-runs` 6 个端点（见 [API.md](./API.md) 3.15） |
| 前端 | `frontend/src/components/DailyStandardizerPanel.tsx` | Tools 页「日志标准化」tab：参数 → 逐日确认（默认全不勾选）→ 验收报告 |
| 对比台 | `backend/daily_form_bench.py` | P3 效率对比（三种规则投递形态 × N 次重复，只读、带 token 预算硬中止）；结论见 [M15-EFFICIENCY-REPORT.md](./M15-EFFICIENCY-REPORT.md) |

**规则投递形态**（`DailyMergeService.plan_day(..., delivery=...)`，P3 定稿）：

| 形态 | 规则放在哪 | 用途 |
|---|---|---|
| `system_embedded`（默认） | 规则全文进 **system prompt**，user prompt 只留任务与来源 | 生产默认；P3 实测定稿（输出 token −9.7%、单日耗时 −13.3%、三次一致性最高） |
| `doc_full` | 规则 + 模板全文进 **user prompt** | P1/P2 的行为；对照基线 |
| `trimmed` | user prompt，且按**当日来源类型**裁剪（无 B 类来源时不注入 session 元数据删除清单与对话腔改写规则）+ 只给章节骨架 | 省 prompt token 的备选；实测输出更长、掉过一次强规则，**不采用**，仅留作复测对照 |

三形态的「任务 / 目标 / 来源 / 输出要求」逐字一致（有单测守着），因此对比结果可归因到形态本身；
业务链路（批次日归并 / M13）不传 `delivery`，形态切换不影响线上行为。

**强/弱规则分层**（M15 的核心机制，改动前务必理解）：

- **强规则**（`TemplateRules` + `FormatValidator`，机械校验并可自动修正）：H1、5 章节与顺序、命名 `YYYY-MM-DD.md`、禁 emoji / 禁裸 HTML → 不过就拦（`DailyRunService._acceptance_error()` 在写入前再跑一遍）
- **弱规则**（技能预设正文 + `style_rules` → LLM）：保留什么 / 删什么 / 改写风格 / 去重合并 / 默认不脱敏

**四条刻意的边界**（易踩坑，详见方案附录 A / 附录 D）：

1. 只扫 `memory/` **顶层**：`archive/`、`dreaming/`、`cases/`、`contacts/`、`logs/`、`iteration/` 等子目录是独立语义目录，混进来会误改误删
2. 只有三种命名模式命中：`YYYY-MM-DD.md`（A）/ `YYYY-MM-DD-HHMM.md`（B，含 `-HHMM-2` 去重后缀）/ `YYYY-MM-DD-<topic>.md`（C）
3. 碎片只删 B/C，A 是被改写的主体；删除走 `send2trash`，且必须先经 diff 确认
4. **批量 apply 是"全或无"**：先对全部目标日做批次级预检，任一日不过（乐观锁冲突 / 写前验收不过）就整批不写；写入后的碎片删失败不回滚日文件（标 `partially_applied`）

**两个实测踩坑（已修，勿回归）**：

1. `forbid_raw_html` 不能把 `<单词>` 一律当 HTML：真实工作日志里的 `` `session:<id>` ``、
   `` `cron:<jobId>` `` 这类枚举/占位符会被误判，而该规则**没有机械修正手段** → 整天无法写入。
   现只认内置**标签白名单**，并跳过行内代码跨度（围栏块早已跳过）。
2. `sanitize()` 必须按标签显式剥离推理模型的思考块（`<think>…</think>`）：中文前言特征词匹配不上
   英文思考内容，漏剥会让 `<think>` 触发 `forbid_raw_html`，把成功的归并误判为强规则失败。
   只剥「以思考块开头且闭合完整」的块，不碰正文里作为示例出现的标签。

**与 M13 的隔离**：`ai_jobs` 保持单文件语义不变，M15 用独立两表 `daily_runs` / `daily_run_items`，
互不污染状态机（见 [DATA-MODEL.md](./DATA-MODEL.md) 2.9）。

**WORKLOG 预设只有一个（v1.7 收口，勿再新增并列项）**：M15 的规则载体是 `preset-wlog-daily-std`
「工作日志日标准化」，章节 = 一、今日概览 / 二、关键事件 / 三、关键决策 / 四、待办事项 / 五、明日计划。
原 `preset-wlog-summary`「工作日志汇总」与它是同一件事的两种口径（单文件整理 vs 逐日归并），
并列会让用户无法判断该选哪个 → 已把它的归档顺序规则与「明日计划」章节并入，旧 id 走
`BUILTIN_PRESETS_RETIRED` 退役（`presets.retired_at` 非空 → `list()` 不返回，`get()` 仍可取）。
存量安装的升级/下线一律以「内容锚点表」判据：库中内容仍等于上一版内置定义才动，用户改过的不动
（`BUILTIN_PRESETS_REFRESHED` / `BUILTIN_PRESETS_RETIRED`，见 `preset_service.py`）。

**「本日无可归档内容」出口（v1.8，勿改成"必须产出"）**：此前 prompt 写死「第一行必须是
`# 工作日志 - <date>`」而强规则又强制必填章节齐全 → 模型没有合法出口，全天噪音的日子只能**凑数**。
现给模型第二个合法出口：`parse_empty_verdict()` 识别「只回一行 `无可归档内容：<理由>`」，命中即
**不产出日文件**（`output_content=""`、不跑强规则、`format_report.ok=True`），该日 `item_status=empty`，
B/C 碎片照常走确认后清理，**A 类主文件 `memory/YYYY-MM-DD.md` 保持不动**。
识别是**从严**的：>3 行、含标题/列表/表格/引用、或首行不是该哨兵 → 一律当普通输出交给强规则，
因此正常文档里的这句话不会被误判。空日的乐观锁改为**逐个碎片比对 SHA-256**
（`DailyRunService._fragment_conflicts`，空日不写目标文件，锁不该锁在它上面）。
**主文件定义**：A 类 = `memory/YYYY-MM-DD.md` **精确命名**（OpenClaw 系统自动生成），
其余命名（`-HHMM` / `-<topic>`）都是碎片——扫描器按纯正则判定，不做模糊匹配。

---

## 四、核心流程（老板视角）

### 流程 A：浏览 + 编辑单个文件

```
1. 打开 Web（http://localhost:8848）
2. 左侧看到 6 个 Agent
3. 点 "main" → 中间出现文件树（SOUL.md / AGENTS.md / ...）
5. 点 "SOUL.md" → 右侧显示内容
6. 直接在编辑器里改
7. 点 "保存" → 自动备份 → 写入 → 顶部 Toast 提示「已保存」
```

### 流程 B：跨 Agent 编辑同一文件

```
1. 顶部菜单 → 「跨 Agent 编辑」
2. 弹出对话框：选 Agent（多选）+ 选文件类型（如 SOUL.md）
3. 右侧出现编辑器，但显示「⚠ 这段将同时写入 5 个 Agent」
4. 改 → 保存 → 弹出确认对话框（显示 5 个 Agent 的 diff plan）
5. 确认 → 每个 Agent 独立备份 → 写入
```

### 流程 C：导出 → 备份到 GitHub

```
1. Agent 详情 → 「导出」→ 下载 main.tar.gz
2. 手动 push 到 GitHub 仓库
3. 需要恢复时：从 GitHub 拉取 tar.gz 后手动解压覆盖对应 Agent 的 workspace
```

### 流程 D：误改后回滚

```
1. 打开被改的文件
2. 右上角「历史」按钮 → 弹出备份列表（按时间倒序）
3. 选一个历史版本 → 「预览」→ 看到 diff
4. 「回滚版本」→ 再备份当前 → 写入历史版本 → 顶部 Toast
```

### 流程 E：发现 lint 警告

```
1. Agent 详情 → 「健康检查」→ 弹出警告列表
2. 点某条警告 → 跳到对应文件 + 高亮违规行
3. 按建议手工修改后保存（lint 只警告、不自动改文件；AI 自动修复能力尚未纳入交付范围）
```

---

## 五、技术架构（待老板拍板）

### 5.1 推荐技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| **后端** | Python + **FastAPI** | 老板 Python 熟；FastAPI 类型安全、自动文档 |
| **前端** | TypeScript + **React** + **Vite** | 生态最熟；Vite 启动快 |
| **UI 组件** | **自研组件 + CSS token**（零第三方 UI 框架，运行时依赖恒为 7 项） | 体量小、可控，避免组件库与自研样式冲突（见 docs/UI-SPECS.md 第四节） |
| **Markdown 编辑器** | **Monaco Editor** | VSCode 内核，老板熟悉 |
| **Diff 渲染** | 自研归一化 + 行级 diff（后端 `diff_service`，前端 `DiffView`） | 需要「忽略格式噪声」口径，通用库无法满足 |
| **全文搜索** | **ripgrep**（Python subprocess） | 快；不可用时 fallback 到 Python `grep` |
| **数据库** | **SQLite**（SQLAlchemy 2.x） | 单文件、零依赖 |
| **打包** | 后端 PyInstaller？前端 Vite build → 静态文件 | 本地自托管 |
| **部署** | 单进程：FastAPI 同时 serve 静态前端 + API | 一个命令起来 |

### 5.2 系统架构图

```
┌─────────────────────────────────────────────────┐
│  Browser (老板本地)                              │
│  http://localhost:8848                          │
└────────────┬────────────────────────────────────┘
             │ HTTP
             ↓
┌─────────────────────────────────────────────────┐
│  Soulforge Server (FastAPI)                     │
│  ├── /api/*           REST API                  │
│  ├── /*               React build (静态)        │
│  └── /app/avatars/    ← 工作区头像等附件           │
│                                                  │
│  Services:                                       │
│  ├── AgentDiscovery   ← 读 openclaw.json         │
│  ├── FileManager      ← 读写 workspace 文件      │
│  ├── BackupService    ← 自动备份 / 回滚          │
│  ├── SearchService    ← ripgrep 调用             │
│  ├── LintService      ← 8 条 lint 规则           │
│  ├── DiffService      ← unified diff → html      │
│  ├── SyncService      ← 跨 Agent 同步            │
│  ├── SuperSyncService ← 超级同步（独立进程启停）  │
│  └── ImportExport     ← Prompt Pack 导出（tar.gz） │
│                                                  │
│  Storage:                                        │
│  └── SQLite (.soulforge/index.db)                 │
│       └── agents / files / backups / audit_log   │
└────────────┬────────────────────────────────────┘
             │ 文件系统
             ↓
┌─────────────────────────────────────────────────┐
│  OpenClaw workspace 文件                          │
│  ~/.openclaw/workspace/                          │
│  ~/.openclaw/workspace-agents/xiaowei-ops/      │
│  ...                                             │
└─────────────────────────────────────────────────┘
```

### 5.3 关键设计

- **单进程部署**：FastAPI 同时 serve React build + API，一个 `uvicorn` 起来完事
- **本地零配置**：默认端口 8848，开箱即用
- **不开公网**：监听 `127.0.0.1`，绝不暴露公网
- **文件系统直接读写**：不引入额外抽象层（Git / DB 镜像）
- **备份外置**：备份文件存项目内 `.soulforge/backups/`，不污染 workspace
- **审计日志**：所有写操作记 `audit_log` 表（含改了哪个文件、哪些 Agent、操作时间）

### 5.4 跨平台与一键启动

两个启动器行为对齐，按平台二选一：

| 平台 | 脚本 | 内容 |
|---|---|---|
| Windows 10/11 | `start.bat` | 探测 OpenClaw 根目录 → 建 `backend\.venv` → 装依赖 → 起服务 → 开浏览器 |
| Linux / macOS | `start.sh` | 同上（探测 → `backend/.venv` → 装依赖 → 端口占用检查 → 起服务 → `xdg-open`/`open`） |

**虚拟环境不可跨平台复用（重要）**：

- Windows 的 venv 是 `backend\.venv\Scripts\python.exe`，Linux/macOS 是 `backend/.venv/bin/python`，
  两者**不能通用**；换平台必须删除后重建（`rm -rf backend/.venv`）。
- 本项目可能同时存在于 Git 与 Syncthing 分发路径下，若把 Windows 的 `.venv`
  同步到 Linux，会导致「应用起不来」；`start.sh` 检测到这种目录会**直接报错并提示重建**，
  不会静默复用。
- Windows 创建的 `.venv` 内含大量 `.exe`（`pip.exe` / `uvicorn.exe` 等），对 Linux 无意义；
  建议在同步/版本控制中排除 `.venv`、`node_modules`、`.soulforge`。
- `start.sh` 必须保持 **LF** 行尾（CRLF 会报 `bad interpreter` / `$'\r': command not found`），
  仓库已用 `.gitattributes`（`*.sh text eol=lf`）固定，不要改成 CRLF。

> 说明：超级同步（M14）自身与平台无关，用 `sys.executable` 拉起独立进程；
> 它的进程存活检测 / 分离启动 / 停止都按 `os.name` 分别走 Windows 与 POSIX 分支。

### 5.5 数据模型

详见 [DATA-MODEL.md](./DATA-MODEL.md)。

---

## 六、API 总览

详见 [API.md](./API.md)。

---

## 七、安全护栏

详见 [docs/SECURITY.md](./docs/SECURITY.md)。

老板的硬约束：

1. **任何交互式写操作必须先自动备份** —— 不允许"直接覆盖"
   （例外：M14 超级同步为后台自动同步，仅记录变更 diff 日志、不落盘备份；范围限于 5 个核心文档）
2. **跨 Agent 整文件覆盖 = 禁止** —— 必须走 diff + confirm
3. **危险操作必须图形化确认** —— 不能只在 API 层确认

---

## 八、落地路径

详见 [ROADMAP.md](./ROADMAP.md)。

---

## 九、给 AI 编程助手的开发指令

**先生成 MVP**：

1. 先建 FastAPI 项目骨架（`backend/`）
2. 实现 M1（Agent 管理）+ M2（文件浏览） + M7（备份）
3. 前端先做"能浏览"的版本：左侧 Agent 树 + 中间文件树 + 右侧预览（只读）
4. 然后加 Monaco 编辑器
5. 然后加 lint（M8）
6. 然后加跨 Agent 编辑（M2 扩展）
7. 然后加 diff / sync（M4 / M5）
8. 然后加导出（M6）
9. 最后加仪表盘（M10）

**开发风格约束**：

- 后端：类型注解完整；Pydantic 模型；OpenAPI 文档自动出
- 前端：TypeScript strict；React 函数组件 + hooks；组件自研，样式集中在 `frontend/src/styles/global.css` 并复用既有 token
- 测试：核心 lint 规则必须有单测；备份/回滚流程必须有集成测试
- 错误处理：前端用 `ErrorBoundary` 兜底；后端用 FastAPI 自带 + 自定义异常
- 日志：loguru 统一日志格式
- 版本号：事实源是 `backend/app/__init__.py` 的 `__version__`；`pyproject.toml` / `package.json` 的静态字段需手工同步，改动后跑 `pytest`（`tests/test_version.py` 会校验一致性）。见 [CHANGELOG.md](../CHANGELOG.md) 发版流程

**别做的事**：

- ❌ 别引入 Redis / PostgreSQL
- ❌ 别引入 Docker
- ❌ 别做账号系统 / 权限系统（单人本地工具）
- ❌ 别做云端同步 / 多人协作
- ❌ 别把元数据写进 workspace（污染源 workspace，外置到项目内 `.soulforge/`）