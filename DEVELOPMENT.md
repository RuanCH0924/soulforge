# Soulforge — 开发文档

> 本文件是写给 **AI 编程助手**（Trae / Cursor / Windsurf）阅读的完整开发说明书。
> 项目拥有者不需要懂代码，把本文档丢给 AI，它就能理解项目全貌并逐步生成代码。
> 开发方式：Vibe Coding（自然语言描述 → AI 生成代码 → 老板验收）

---

## 一、项目目标

做一个 **OpenClaw 跨 Agent system-prompt 文件管理器**，名字叫 "Soulforge"（灵魂锻造炉）。

### 一句话描述

> 把 OpenClaw 所有 Agent 的「灵魂文件」当作源码管理：浏览、搜索、编辑、同步、备份、导入导出，一个 Web 页面搞定。

### 核心痛点

老板目前维护 5+ 个 Agent（main / xiaowei-ops / xiaozhi-contributor / xiaoxi-lawyer / caicai-analyst / susu-tutor），每个 Agent 都有自己的 workspace。每次想做下面这些事都很痛苦：

| 痛点 | 现状 | Soulforge 解法 |
|---|---|---|
| 想看某个 Agent 的 `SOUL.md` 是怎么写的 | 要打开 VSCode 切到对应 workspace | Web 页面左侧 Agent 树，点开就预览 |
| 想在所有 Agent 的 `MEMORY.md` 加同一句规则 | 手动开 5 个文件复制粘贴 | 「跨 Agent 编辑」选多个 Agent，一次写 |
| 想知道两个 Agent 的 `AGENTS.md` 差异 | 手动 `diff` 命令 | 「对比」按钮 → 可视化 diff |
| 误改了某个文件想回滚 | 找 git log（如果 workspace 进了 git） | 「备份历史」一键回滚（自动备份，无需 git） |
| 复制一个 Agent 起新号 | 整目录 cp，改一堆 ID | 「模板」一键生成新 Agent |
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

Soulforge 的导入导出单位就是 Prompt Pack（`.tar.gz`，含 SHA256 manifest）。

### 2.4 Lint 规则（呼应老板 SOUL/AGENTS 护栏）

Soulforge 内置一套 lint 检查，发现违规主动提示：

| 规则 ID | 名称 | 检查内容 |
|---|---|---|
| `L4-TIMESTAMP` | L4 反模式 — 时间戳 | `*最后修订：…*` / `*最后更新：…*` / `## 更新记录` / `## Changelog` |
| `L4-VERSION` | L4 反模式 — 版本号 | `## v1.0` / `Skill 版本：v1.0` / `首次验证：YYYY-MM-DD` |
| `L4-NARRATIVE` | L4 反模式 — 修复叙述 | "用户指出 XXX，触发 YYY" / "起因：…误判事故" |
| `BOUNDARY-VIOLATE` | 5 大文档边界违规 | 比如"老板偏好"进错了 AGENTS.md |
| `CORE-MISSING` | CORE 必填文件缺失 | 比如新 Agent 缺 `IDENTITY.md` |
| `CROSS-AGENT-DRIFT` | 跨 Agent 同名文件 drift 过大 | 同样叫 `AGENTS.md`，5 个 Agent 内容相似度 < 30% 时警告 |
| `EMPTY-FILE` | 空文件 | 文件 < 10 字节且不是占位文件 |
| `LARGE-FILE` | 超大文件 | 单文件 > 50KB 时提示 |

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
| M6 | 导入导出 | 1 | ✅ |
| M7 | 备份/回滚 | 1 | ✅ |
| M8 | Lint | 1 | ✅ |
| M9 | 模板系统 | 1 | ✅ |
| M10 | 统计/仪表盘 | 1 | ✅ |
| **M11** | **文档预设系统** | **2.5** | **🚧** |
| **M12** | **LLM Provider 接入** | **2.5** | **🚧** |
| **M13** | **AI 自动整理** | **2.5** | **🚧** |

---

### 模块 M1：Agent 管理

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/agents` | 左侧栏 | 列出全部 Agent（含 workspace 路径、文件数、最后修改时间） |
| `GET /api/agents/{id}` | Agent 详情页 | 单个 Agent 的元数据 + 文件清单 |
| `POST /api/agents/scan` | 顶部「重新扫描」 | 重新读 `openclaw.json` + 重建索引 |

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
| `POST /api/search` | 顶部搜索框 | 跨 Agent 全文搜（ripgrep 后端） |
| `POST /api/search/agents` | 搜索框 → 「限定 Agent」 | 限定某些 Agent 内搜 |
| `POST /api/search/files` | 搜索框 → 「限定文件类型」 | 限定某些文件名（如只搜 SOUL.md） |

支持：正则 / 大小写 / 上下文 3 行。

### 模块 M4：Diff 对比

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/diff?a={a}&b={b}&file={f}` | 「对比」按钮 → 选两个 Agent + 选文件 | 行级 diff 高亮 |
| `GET /api/diff/history?agent={id}&file={f}&against={ts}` | 文件历史 → 「对比旧版本」 | 跟历史备份对比 |

Diff 渲染用 `diff2html`（业界标准）。

### 模块 M5：跨 Agent 同步

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/sync/plan?src={a}&dst={b}&files={f1,f2}` | 「同步」按钮 → 选源 Agent + 目标 Agent + 选文件 | **先返回 diff plan，让老板确认** |
| `POST /api/sync/execute` | Diff plan 页面 → 「确认执行」 | 执行选择性合并（绝不整文件覆盖） |

**安全护栏**：跨 Agent 同步必须走「plan + confirm」两步，绝不允许一键 cp。

### 模块 M6：导入导出

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/export/{id}` | Agent 详情 → 「导出」 | 导出 Prompt Pack 为 `.tar.gz` |
| `GET /api/export/all` | 顶部 → 「导出全部」 | 全部 Agent |
| `POST /api/import` | 顶部 → 「导入」按钮 | 上传 `.tar.gz` → 解压 → 备份 → 写入 |
| `POST /api/import/preview` | 导入流程 → 「先预览」 | 先解析 manifest，列出冲突文件，让老板选择 skip/merge/overwrite |

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

违规显示为「红点」+ 悬浮提示 + 「一键跳转修复」。

### 模块 M9：模板系统

| 命令 | UI 入口 | 功能 |
|---|---|---|
| `GET /api/templates` | 顶部 → 「新建 Agent」→ 「从模板」 | 列出内置模板 |
| `POST /api/templates/apply` | 模板页 → 「应用到新 Agent」 | 生成新 Agent 的 Prompt Pack |

内置模板：

- `standard` — 标准配置（含全部 CORE 文件 + 一个 SOUL.md 示例）
- `minimal` — 极简（仅 AGENTS.md + IDENTITY.md）
- `lawyer-agent` — 律师专用（含法答 / IMA 知识库偏好）
- `writer-agent` — 作家专用（含小说 / 公众号）

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

**端点**：`GET/POST/PUT/DELETE /api/presets[/{id}]`、`POST /api/presets/{id}/apply`、`POST /api/presets/{id}/apply/execute`。

**UI 入口**：
- 顶部菜单 → 「预设」 → 列表 + 新建/编辑/删除
- 文件编辑页 → 「应用预设」按钮 → 选预设 → 生成 diff plan → 老板确认 → 写入

**关键护栏**：
- 系统预设不可删（前端隐藏按钮，后端 403）
- 应用预设走 plan + execute 两步，**绝不直接覆盖**
- 预设 version 字段自增，老板可迭代升级

---

### 模块 M12：LLM Provider 接入（Phase 2.5 · Step 2）

> 让 Soulforge 能调任意 OpenAI 兼容协议的 LLM（OpenAI / Anthropic / DeepSeek / Ollama），配置变更可热加载。

**核心数据**：见 `docs/DATA-MODEL.md` 中 `llm_providers` 表。

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
- AI 输出过 lint 才能写入（违规拒绝写入 + 提示老板）
- 大文件（> 30KB）拒绝 AI 整理（token 成本 + 质量风险）
- 单文件 AI 调用**默认单次**，老板可点「重新生成」
- 每次调用记录 provider + token 消耗 + 成本（审计日志）

**Prompt 构造模板**：

```text
你是 Soulforge 的 AI 文档整理助手。

【任务】按以下预设结构，重新整理用户的文档，保留原意，不要丢失信息。

【预设：{preset.name}】
适用文件类型：{preset.target_file_type}
必须章节（按顺序）：
{preset.sections_json}

【风格规则】
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
3. 以后想恢复 → 「导入」→ 上传 tar.gz → 解压到指定 Agent
```

### 流程 D：误改后回滚

```
1. 打开被改的文件
2. 右上角「历史」按钮 → 弹出备份列表（按时间倒序）
3. 选一个历史版本 → 「预览」→ 看到 diff
4. 「回滚到此版本」→ 再备份当前 → 写入历史版本 → 顶部 Toast
```

### 流程 E：发现 lint 警告

```
1. Agent 详情 → 「健康检查」→ 弹出警告列表
2. 点某条警告 → 跳到对应文件 + 高亮违规行
3. 右上角提示「建议改法」一键应用 / 手动改
```

---

## 五、技术架构（待老板拍板）

### 5.1 推荐技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| **后端** | Python + **FastAPI** | 老板 Python 熟；FastAPI 类型安全、自动文档 |
| **前端** | TypeScript + **React** + **Vite** | 生态最熟；Vite 启动快 |
| **UI 组件** | **shadcn/ui**（基于 Radix + Tailwind） | 轻量、可定制、复制粘贴式 |
| **Markdown 编辑器** | **Monaco Editor** | VSCode 内核，老板熟悉 |
| **Diff 渲染** | **diff2html** | 业界标准 |
| **全文搜索** | **ripgrep**（Python subprocess） | 快；不可用时 fallback 到 Python `grep` |
| **数据库** | **SQLite**（`better-sqlite3`） | 单文件、零依赖 |
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
│  ├── ImportExport     ← tar.gz 打包 / 解压       │
│  └── TemplateService  ← 内置模板                  │
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

### 5.4 数据模型

详见 [docs/DATA-MODEL.md](./docs/DATA-MODEL.md)。

---

## 六、API 总览

详见 [docs/API.md](./docs/API.md)。

---

## 七、安全护栏

详见 [docs/SECURITY.md](./docs/SECURITY.md)。

老板的硬约束：

1. **任何写操作必须先自动备份** —— 不允许"直接覆盖"
2. **跨 Agent 整文件覆盖 = 禁止** —— 必须走 diff + confirm
3. **危险操作必须图形化确认** —— 不能只在 API 层确认

---

## 八、落地路径

详见 [docs/ROADMAP.md](./docs/ROADMAP.md)。

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
8. 然后加导入导出（M6）
9. 最后加模板（M9）+ 仪表盘（M10）

**开发风格约束**：

- 后端：类型注解完整；Pydantic 模型；OpenAPI 文档自动出
- 前端：TypeScript strict；React 函数组件 + hooks；shadcn/ui 复制粘贴
- 测试：核心 lint 规则必须有单测；备份/回滚流程必须有集成测试
- 错误处理：前端用 react-error-boundary；后端用 FastAPI 自带 + 自定义异常
- 日志：loguru 统一日志格式

**别做的事**：

- ❌ 别引入 Redis / PostgreSQL
- ❌ 别引入 Docker
- ❌ 别做账号系统 / 权限系统（单人本地工具）
- ❌ 别做云端同步 / 多人协作
- ❌ 别把元数据写进 workspace（污染源 workspace，外置到项目内 `.soulforge/`）