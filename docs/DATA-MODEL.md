# Soulforge — 数据模型

> 配套主文档 [DEVELOPMENT.md](DEVELOPMENT.md) 的数据模型章节。
> 数据库：SQLite（`<项目根>/.soulforge/index.db`，可用 `SOULFORGE_DATA_DIR` 覆盖）。

---

## 一、库位置与生命周期

- **路径**：`<data_dir>/index.db`，`data_dir` 默认为 `<项目根>/.soulforge`（见 `backend/app/config.py`）
- **创建**：首次启动 Soulforge 时自动建表（`Database.init_db()`）
- **备份**：数据库本身**不备份**，丢了无所谓 —— 重扫就能重建
- **迁移**：轻量迁移 `Database._migrate()`（启动时按 `PRAGMA table_info` 比对，为已存在的旧表补列）；
  本项目为单机本地工具，不引入 Alembic 等迁移框架

---

## 二、Schema（核心 4 张表）

### 2.1 `agents` —— Agent 元数据

```sql
CREATE TABLE agents (
    id              TEXT PRIMARY KEY,      -- 'main', 'xiaowei-ops' 等
    workspace       TEXT NOT NULL,          -- 绝对路径，如 '/root/.openclaw/workspace'
    display_name    TEXT,                   -- 人类可读名（可选）
    file_count      INTEGER DEFAULT 0,      -- 缓存：workspace 下 .md 文件数
    last_scanned_at INTEGER,                -- Unix 时间戳
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);

CREATE INDEX idx_agents_workspace ON agents(workspace);
```

### 2.2 `files` —— 文件元数据

```sql
CREATE TABLE files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL,
    path            TEXT NOT NULL,           -- 相对 workspace，如 'SOUL.md' 或 'memory/2026-08-05.md'
    role            TEXT NOT NULL,           -- 'CORE' | 'MEMORY' | 'SKILL' | 'META' | 'OTHER'
    size_bytes      INTEGER NOT NULL,
    mtime           INTEGER NOT NULL,        -- Unix 时间戳
    sha256          TEXT NOT NULL,           -- 16 字节 hex（首次读时算）
    last_lint_at    INTEGER,                 -- 上次 lint 时间
    lint_warnings   INTEGER DEFAULT 0,       -- 缓存：警告数
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,

    UNIQUE(agent_id, path),
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

CREATE INDEX idx_files_agent ON files(agent_id);
CREATE INDEX idx_files_role ON files(role);
CREATE INDEX idx_files_path ON files(path);
```

### 2.3 `backups` —— 备份记录

```sql
CREATE TABLE backups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL,
    file_path       TEXT NOT NULL,           -- 备份的文件
    backup_path     TEXT NOT NULL,           -- 备份文件位置：'<data_dir>/backups/main/SOUL.md/SOUL.md.20260806-105830.bak'
    reason          TEXT,                    -- 'auto-write' | 'manual' | 'pre-rollback' | 'pre-sync'
    sha256          TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    created_at      INTEGER NOT NULL,

    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

CREATE INDEX idx_backups_agent_file ON backups(agent_id, file_path);
CREATE INDEX idx_backups_created ON backups(created_at);
```

**保留策略**：

```sql
-- 启动时清理 > 30 天的备份（同时删除物理文件）
DELETE FROM backups WHERE created_at < strftime('%s', 'now', '-30 days');
```

### 2.4 `audit_log` —— 审计日志

```sql
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       INTEGER NOT NULL,
    action          TEXT NOT NULL,           -- 'write' | 'delete' | 'rollback' | 'sync' | 'lint' | 'export'
    agent_id        TEXT,                    -- 涉及的 Agent（可空，如 export-all）
    target_path     TEXT,                    -- 操作的文件路径
    details_json    TEXT,                    -- 灵活字段，如 diff 大小、备份 ID 列表等
    user            TEXT DEFAULT 'local',    -- 预留：未来多用户
    result          TEXT DEFAULT 'ok'        -- 'ok' | 'failed'

    -- 注意：这条表不级联删除 agent（即使 agent 被移除也要保留审计）
);

CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_agent ON audit_log(agent_id);
CREATE INDEX idx_audit_action ON audit_log(action);
```

**典型记录示例**：

```json
{
  "timestamp": 1754478710,
  "action": "write",
  "agent_id": "main",
  "target_path": "SOUL.md",
  "details_json": {
    "size_before": 4321,
    "size_after": 4500,
    "backup_id": 123,
    "client": "web-ui"
  },
  "result": "ok"
}
```

---

## 二点五、Schema（Phase 2.5 新增 4 张表）

> 与二、节并列，为 Phase 2.5 AI Editor 引入。

### 2.5 `presets` —— 文档预设

保存「文档应该长什么样」的格式预设。系统预设 + 用户自定义。

```sql
CREATE TABLE presets (
    id                  TEXT PRIMARY KEY,          -- UUID
    name                TEXT NOT NULL,             -- 预设名
    target_file_type    TEXT NOT NULL,             -- 适用文件类型：SOUL/AGENTS/MEMORY/USER/IDENTITY/TOOLS/WORKLOG/ANY
    description         TEXT,                      -- 用途说明
    template_md         TEXT,                      -- 标准 Markdown 模板文档（YAML 规则 + 章节骨架），校验唯一标准
    sections_json       TEXT NOT NULL,             -- 章节列表 JSON（由 template_md 派生）：[{title, required, order, hint}]
    frontmatter_json    TEXT,                      -- YAML frontmatter 模板 JSON
    style_rules         TEXT,                      -- 风格规则（自由文本）
    is_system            INTEGER NOT NULL DEFAULT 0,-- 历史字段，恒为 0（内置预设与用户预设同等可编辑 / 可删）
    version             INTEGER NOT NULL DEFAULT 1,-- 预设版本（编辑后自增）
    retired_at          INTEGER,                   -- 非空 = 已退役（内置预设随版本下线）：不再出现在列表，get() 仍可取
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL
);

CREATE INDEX idx_presets_target ON presets(target_file_type);
CREATE INDEX idx_presets_system ON presets(is_system);
```

**sections_json 示例**：

```json
[
  {"title": "核心行为准则", "required": true,  "order": 1, "hint": "简洁优先、目标驱动"},
  {"title": "工作态度和原则", "required": true,  "order": 2, "hint": "先想后做、不吹嘘"},
  {"title": "学习与连续性",   "required": true,  "order": 3, "hint": "记录、更新、演进"},
  {"title": "核心边界",       "required": true,  "order": 4, "hint": "隐私、操作授权"}
]
```

**完整记录示例**：

```json
{
  "id": "preset-soul-std",
  "name": "SOUL.md 标准结构",
  "target_file_type": "SOUL",
  "description": "核心行为准则 + 工作态度 + 学习连续性 + 核心边界",
  "sections_json": "[{...}]",
  "frontmatter_json": "{\"schema\": \"soulforge.preset/v1\", \"owner\": \"user\"}",
  "style_rules": "emoji-in-section-title=false;口语化禁令;必须带应用范例",
  "is_system": 0,
  "version": 2,
  "created_at": 1754478700,
  "updated_at": 1754478800
}
```

**约束**：
- `is_system` 为历史字段，**恒为 0**：内置预设播种时不设保护，与用户预设同等可编辑、可删除；
  被用户改过的内置预设不会被升级覆盖（内容锚点比对，见下表）
- `version` 在 PUT 后自增，并写 `preset_versions` 快照（保留历史，可回溯）
- **`is_builtin` 是派生字段，不在表里**：由「id 是否属于内置预设清单（`BUILTIN_PRESET_IDS`）」算出，
  仅用于 API 响应与 UI 展示「预设来源」（内置预设 = 随版本分发，升级时可能被刷新）
- **两类预设的边界（2026-09-24 收口）**：`target_file_type = WORKLOG` = 专供大模型处理工作日志
  （M15 的规则载体），只在「业务工具 → 日志标准化」界面可见可编辑；其余类型供主工作台加载。
  `list(scope='workbench')` 排除 WORKLOG 类（设置页「文档预设」与主工作台用它）；
  `list(target_file_type='WORKLOG')` 取日志预设
- `retired_at` 非空 = 已退役（当前为 `preset-wlog-summary`「工作日志汇总」，已并入 `preset-wlog-daily-std`）：
  `list()` 不再返回它，但行保留、`get()` 仍可取，避免历史批次 / AI 任务按 id 读取时报 404
- 内置预设 id 前缀 `preset-`（如 `preset-soul-std`、`preset-agents-std`、`preset-mem-std`、`preset-wlog-daily-std`）；
  播种规则：首次启动（表为空）全量播种；存量安装另外做三件事，且都只作用于**内容仍与内置定义一致**
  （用户没改过）的预设：
  ① 补种 `BUILTIN_PRESETS_ADDED`（append-only 白名单）中的新增项，同时写 `preset_versions` v1 快照
  ——该快照充当「已补种」标记，用户删除后重启不再重建；
  ② 刷新 `BUILTIN_PRESETS_REFRESHED` 中内容有更新的（覆盖为新定义 + `version` 自增 + 留快照）；
  ③ 退役 `BUILTIN_PRESETS_RETIRED` 中已下线的（写 `retired_at`）。用户改过的预设一律不动

---

### 2.6 `llm_providers` —— LLM Provider 配置

记录可用的 LLM provider。API key 加密存储。

```sql
CREATE TABLE llm_providers (
    id                  TEXT PRIMARY KEY,          -- provider 名（业务唯一，如 "openai-main"）
    base_url            TEXT NOT NULL,
    api_key_encrypted   TEXT NOT NULL,             -- Fernet 加密后的密文
    model               TEXT NOT NULL,
    protocol            TEXT NOT NULL,             -- openai-completions | anthropic-messages
    enabled             INTEGER NOT NULL DEFAULT 1,
    max_tokens          INTEGER NOT NULL DEFAULT 4096,
    temperature         REAL NOT NULL DEFAULT 0.3,
    timeout_seconds     INTEGER NOT NULL DEFAULT 60,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL
);

CREATE INDEX idx_llm_providers_enabled ON llm_providers(enabled);
```

**API key 加密机制**：
- 加密密钥来自环境变量 `SOULFORGE_SECRET`，**或**首次启动生成 `.soulforge/secrets/key`（权限 600）
- Fernet（cryptography 库）对称加密
- 数据库只存密文，UI 只显示掩码 `sk-****...****`

**完整记录示例**（加密后）：

```json
{
  "id": "openai-main",
  "base_url": "https://api.openai.com/v1",
  "api_key_encrypted": "gAAAAABl...（密文，例 200+ 字符）",
  "model": "gpt-4o",
  "protocol": "openai-completions",
  "enabled": 1,
  "max_tokens": 4096,
  "temperature": 0.3,
  "timeout_seconds": 60
}
```

**约束**：
- 有关联 `ai_jobs` 的 provider 不可删（`409 Conflict`）
- `api_key_encrypted` 字段不出现在任何 GET 响应里；响应只回显掩码（如 `sk-****...****`），
  接口层不提供任何回显明文密钥的端点（更新时 `api_key` 留空 = 保留旧密钥）

---

### 2.8 `ai_jobs` —— AI 整理任务

记录每次 AI 自动整理任务的完整生命周期。

```sql
CREATE TABLE ai_jobs (
    id                  TEXT PRIMARY KEY,          -- UUID
    agent_id            TEXT NOT NULL,
    file_path           TEXT NOT NULL,
    preset_id           TEXT NOT NULL,
    provider_id         TEXT NOT NULL,
    status              TEXT NOT NULL,             -- pending|running|awaiting_confirm|applied|rejected|failed|superseded
    input_snapshot      TEXT,                      -- 原文件快照（生成时锁定）
    output_content      TEXT,                      -- AI 输出（待确认）
    diff_plan_json      TEXT,                      -- unified diff + lint warnings
    extra_instructions  TEXT,                      -- 老板附加指令
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    total_tokens        INTEGER,
    cost_estimate_usd   REAL,
    error               TEXT,                      -- 失败原因
    superseded_by       TEXT,                      -- regenerate 时指向新 job
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL,
    finished_at         INTEGER,

    FOREIGN KEY (preset_id)    REFERENCES presets(id),
    FOREIGN KEY (provider_id)  REFERENCES llm_providers(id)
);

CREATE INDEX idx_ai_jobs_status      ON ai_jobs(status);
CREATE INDEX idx_ai_jobs_agent_file ON ai_jobs(agent_id, file_path);
CREATE INDEX idx_ai_jobs_created    ON ai_jobs(created_at);
```

**状态机**：

```
pending ──► running ──► awaiting_confirm ──┬─► applied   （老板点应用）
                                            ├─► rejected  （老板点拒绝）
                                            └─► superseded（老板点重新生成）
                                           
任意状态可跳转：
- pending|running ──► failed    （LLM 调用失败 / lint 违规）
- awaiting_confirm ──► failed    （老板点应用时 lint 拒绝）
```

**典型记录示例**：

```json
{
  "id": "job-uuid-1234",
  "agent_id": "main",
  "file_path": "SOUL.md",
  "preset_id": "preset-soul-std",
  "provider_id": "openai-main",
  "status": "awaiting_confirm",
  "input_snapshot": "# SOUL.md\n\n当前内容...",
  "output_content": "# SOUL.md\n\n## 核心行为准则\n\n简洁优先...",
  "diff_plan_json": "{\"unified_diff\": \"--- SOUL.md\\n+++ SOUL.md\\n@@ ...\", \"lint_warnings\": []}",
  "extra_instructions": "保留「阅读策略」章节原内容不动",
  "prompt_tokens": 1230,
  "completion_tokens": 856,
  "total_tokens": 2086,
  "cost_estimate_usd": 0.021,
  "created_at": 1754478700,
  "updated_at": 1754478710
}
```

**约束**：
- `status=awaiting_confirm` 的 job 才允许 `apply` / `reject`
- `apply` 时：走 lint（L1-L8 全部跑），不通过则 `409 Conflict` + 提示老板
- `apply` 后写审计日志：`action='ai_apply'`
- `apply` 前必须先备份原文件（复用 M7 备份流程）
- `regenerate` 创建新 job，旧 job `superseded_by` 指向新 job

---

### 2.9 `daily_runs` / `daily_run_items` —— 工作日志标准化批次（M15）

记录「按天归并 `memory/` 日文件」的批次及其逐日条目。**不复用 `ai_jobs`**：后者是单文件语义，
混用会污染既有状态机。

```sql
CREATE TABLE daily_runs (
    id                  TEXT PRIMARY KEY,          -- run-<uuid hex>
    agent_id            TEXT NOT NULL,
    date_from           TEXT NOT NULL,             -- YYYY-MM-DD
    date_to             TEXT NOT NULL,
    preset_id           TEXT NOT NULL,
    preset_version      INTEGER NOT NULL DEFAULT 1, -- 批次绑定预设版本，规则迭代后可追溯
    provider_id         TEXT NOT NULL,
    status              TEXT NOT NULL,             -- planned|awaiting_confirm|applied|partially_applied|
                                                   -- needs_review|rejected|failed|empty
    idempotency_key     TEXT NOT NULL,             -- 与来源内容绑定，命中即复用（不再调 LLM）
    extra_instructions  TEXT,
    days_total          INTEGER NOT NULL DEFAULT 0,
    token_budget        INTEGER NOT NULL DEFAULT 0,-- 0 = 不限
    tokens_used         INTEGER NOT NULL DEFAULT 0,
    cost_estimate_usd   REAL NOT NULL DEFAULT 0,
    error               TEXT,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL,
    finished_at         INTEGER
);

CREATE TABLE daily_run_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT NOT NULL,
    date                TEXT NOT NULL,             -- YYYY-MM-DD
    target_path         TEXT NOT NULL,             -- 恒为 memory/YYYY-MM-DD.md
    source_hashes_json  TEXT NOT NULL,             -- {path: sha256}；乐观锁基准（含目标文件）
    sources_json        TEXT,                      -- 来源概览：path/kind/raw_bytes/clean_bytes/removed_total
    fragments_json      TEXT,                      -- 归并后拟删除的碎片路径
    output_content      TEXT,                      -- 归并结果（待确认）
    unified_diff        TEXT,
    format_report_json  TEXT,                      -- 强规则校验报告（ok + violations）
    lint_warnings_json  TEXT,
    notes_json          TEXT,
    empty_reason        TEXT,                      -- 非空 = 模型判定「本日无可归档内容」：不产出日文件，只清 B/C 碎片
    decision            TEXT NOT NULL DEFAULT 'pending',  -- pending|applied|skipped
    item_status         TEXT NOT NULL DEFAULT 'pending',  -- pending|planned|failed|blocked|applied|
                                                          -- partially_applied|empty|skipped
    applied_at          INTEGER,
    backup_id           INTEGER,                   -- 写入前自动备份（复用 M7）
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    total_tokens        INTEGER NOT NULL DEFAULT 0,
    cost_estimate_usd   REAL NOT NULL DEFAULT 0,
    error               TEXT,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL,

    UNIQUE (run_id, date)
);

CREATE INDEX idx_daily_runs_agent  ON daily_runs(agent_id);
CREATE INDEX idx_daily_runs_status ON daily_runs(status);
CREATE INDEX idx_daily_runs_key    ON daily_runs(idempotency_key);
CREATE INDEX idx_daily_run_items_run ON daily_run_items(run_id);
```

**约束**（护栏，均有测试守着）：

- `apply` 只接受 `status=awaiting_confirm` 的批次；且 `config.daily_standardizer.dry_run_only=true` 时直接 `403`
- `apply` 前对**全部目标日**做批次级预检（写前验收 + `source_hashes_json` 乐观锁）：
  - 任一目标文件当前 SHA-256 与计划时不一致 → `409`，且**整批不写**
  - 任一日强规则不过或仍残留低价值元数据壳 → 该日标 `blocked`，**不写入**
- 写入走 `FileManager`（自动备份 + 审计 `daily_apply`）；碎片删除走 `send2trash`，
  删失败 → 该日 `partially_applied` 且**不回滚日文件**
- 幂等：同 `idempotency_key` 且非终态（`failed` / `rejected`）→ 直接复用既有批次（`reused=true`）

**状态机与端点**见 [MEMORY-DAILY-STANDARDIZER-PLAN.md](MEMORY-DAILY-STANDARDIZER-PLAN.md) 附录 D。

---

## 三、文件分类规则（role 字段判定）

**`FileManager.list()` 时同步给每个文件打 role 标签**：

```python
def classify_role(workspace_root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(workspace_root)
    parts = rel.parts

    # CORE 文件
    CORE_FILES = {
        "SOUL.md", "AGENTS.md", "IDENTITY.md", "USER.md",
        "TOOLS.md", "MEMORY.md", "HEARTBEAT.md", "DREAMS.md",
    }
    if len(parts) == 1 and parts[0] in CORE_FILES:
        return "CORE"

    # MEMORY 文件
    if len(parts) >= 2 and parts[0] == "memory" and parts[1].endswith(".md"):
        return "MEMORY"

    # SKILL 文件
    if len(parts) >= 3 and parts[0] == "skills" and parts[2] == "SKILL.md":
        return "SKILL"

    # META 文件
    if rel.name in {"openclaw.json", ".credentials.md"} or rel.name.startswith("."):
        return "META"

    return "OTHER"
```

**前端 UI 行为**：

| role | UI 显示 |
|---|---|
| CORE | 默认显示，加粗图标 |
| MEMORY | 默认显示，普通图标 |
| SKILL | 默认**隐藏**（高级开关打开后显示） |
| META | 默认**隐藏**（高级开关打开后显示，且加红点警示） |
| OTHER | 默认显示，但标灰（"未知文件"） |

---

## 四、路径安全

**铁律**：任何用户提供的路径都必须 `_safe_join()`，禁止 `../../../`。

```python
def _safe_join(workspace_root: Path, user_path: str) -> Path:
    """把用户的相对路径安全拼接到 workspace 根"""
    # 拒绝绝对路径
    if Path(user_path).is_absolute():
        raise UnsafePathError(f"绝对路径禁止：{user_path}")

    # 拒绝 ..
    if ".." in Path(user_path).parts:
        raise UnsafePathError(f"相对路径穿越禁止：{user_path}")

    # 拼接并校验仍在 workspace 下
    resolved = (workspace_root / user_path).resolve()
    if not str(resolved).startswith(str(workspace_root.resolve())):
        raise UnsafePathError(f"路径越界：{user_path}")

    return resolved
```

**API 层**：所有 `path` 参数都过这个检查。

---

## 五、备份文件命名规范

**物理路径**：

```
<data_dir>/backups/
└── <agent_id>/
    └── <sanitized_file_path>/
        └── <original_filename>.<YYYYMMDD-HHMMSS>.bak
```

**示例**（`<data_dir>` 默认 `<项目根>/.soulforge`）：

```
<data_dir>/backups/main/SOUL.md/SOUL.md.20260806-105830.bak
<data_dir>/backups/main/memory_2026-08-05.md/memory_2026-08-05.md.20260806-110215.bak
<data_dir>/backups/xiaowei-ops/AGENTS.md/AGENTS.md.20260806-114500.bak
```

`sanitized_file_path` 把路径分隔符 `/` 替换成 `_`，避免目录层级爆炸。

---

## 六、SQLite 性能考虑

- **WAL 模式**：开 `PRAGMA journal_mode=WAL`，读写不互锁
- **连接池**：单进程单连接即可（多进程才需要池）
- **定期 VACUUM**：备份清理任务里加 `VACUUM`（每月一次）
- **索引**：所有 `WHERE / ORDER BY` 涉及的字段都有索引

---

## 七、配置存储（不进 DB）

`<data_dir>/config.toml`（默认 `<项目根>/.soulforge/config.toml`，TOML 格式，可读可手改）：

```toml
[server]
host = "127.0.0.1"
port = 8848

[backup]
retention_days = 30
auto_backup_on_write = true

[lint]
enabled = true
strict_mode = false                  # true 时违规阻止保存

[ui]
default_theme = "auto"                # auto | light | dark
default_view = "tree"                # tree | list

[advanced]
show_skills = false
show_meta = false
show_memory = false
show_other = false

[openclaw]
dir = ""                              # 空 = 使用自动探测结果

[daily_standardizer]                  # M15 工作日志标准化（手动批次，无定时字段）
max_days_per_run = 31                 # 单批天数上限，超过则创建批次直接 400
token_budget = 200000                 # 单批 token 预算，越限即中止（0 = 不限）
provider_id = ""                      # 默认 provider（UI 可覆盖）
dry_run_only = false                  # true = 全局「只出计划」：apply 直接 403
```

**为什么用 TOML**：比 JSON 适合人改，比 YAML 不缩进敏感，比 INI 表达力强。

### 7.1 超级同步（文件存储，不进 DB）

超级同步的运行数据以文件形式落在 `<data_dir>/super_sync/`，**不写入 SQLite**：

```
<data_dir>/super_sync/
├── config.json     # 同步范围：参与 Agent + 每个 Agent 的文档清单（仅 5 个核心文档）
├── status.json     # 运行状态 + 心跳（独立脚本每轮覆盖写入）
└── logs/
    └── super_sync-YYYYMMDD.jsonl   # 结构化日志（按天滚动，留存 ≥ 30 天）
```

- `status.json` 含 `pid` / `last_heartbeat`，后端据此判定 运行中 / 已停止 / 异常；
- 日志为 JSON Lines（时间 / 级别 / 事件 / 文件 / 源→目标 / 结果 / 变更 diff / 异常），不落 DB；
- 该目录随数据目录一起迁移，无需重建索引。

---

## 八、给 AI 编程助手的指令

**生成 ORM 模型时**：

- 用 SQLAlchemy 2.x 风格（`Mapped[]` 类型注解）
- 10 张表对应 10 个 Model 类（`agents` / `files` / `backups` / `audit_log` /
  `presets` / `preset_versions` / `llm_providers` / `ai_jobs` / `daily_runs` / `daily_run_items`）
- 提供 `Database.init_db()` 一次性建表函数，以及 `Database._migrate()` 轻量补列迁移
- 不引入 Alembic（单机本地工具，见第一节）

**Pydantic 模型**（API 层）：

- 跟 SQLAlchemy Model 解耦，分开定义
- `AgentInfo` / `FileInfo` / `BackupEntry` / `LintWarning` 等用 Pydantic BaseModel
- 序列化用 `model_dump()` / `model_dump_json()`