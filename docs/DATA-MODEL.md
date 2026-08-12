# Soulforge — 数据模型

> 配套主文档 [DEVELOPMENT.md](../DEVELOPMENT.md) 的数据模型章节。
> 数据库：SQLite（`~/.soulforge/index.db`）。

---

## 一、库位置与生命周期

- **路径**：`~/.soulforge/index.db`
- **创建**：首次启动 Soulforge 时自动建表（`init_db()`）
- **备份**：数据库本身**不备份**，丢了无所谓 —— 重扫就能重建
- **迁移**：用 Alembic 管理 schema 版本（v0.2+ 启用）

---

## 二、Schema（4 张核心表）

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
    backup_path     TEXT NOT NULL,           -- 备份文件位置：'~/.soulforge/backups/main/SOUL.md/SOUL.md.20260806-105830.bak'
    reason          TEXT,                    -- 'auto-write' | 'manual' | 'pre-rollback' | 'pre-import'
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
    action          TEXT NOT NULL,           -- 'write' | 'delete' | 'rollback' | 'import' | 'sync' | 'lint' | 'export'
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

## 二点五、Schema（Phase 2.5 新增 3 张表）

> 与二、节并列，为 Phase 2.5 AI Editor 引入。

### 2.5 `presets` —— 文档预设

保存「文档应该长什么样」的格式预设。系统预设 + 用户自定义。

```sql
CREATE TABLE presets (
    id                  TEXT PRIMARY KEY,          -- UUID
    name                TEXT NOT NULL,             -- 预设名
    target_file_type    TEXT NOT NULL,             -- 适用文件类型：SOUL/AGENTS/MEMORY/USER/IDENTITY/TOOLS/WORKLOG/ANY
    description         TEXT,                      -- 用途说明
    sections_json       TEXT NOT NULL,             -- 章节列表 JSON，例：[{title, required, order, hint}]
    frontmatter_json    TEXT,                      -- YAML frontmatter 模板 JSON
    style_rules         TEXT,                      -- 风格规则（自由文本）
    is_system            INTEGER NOT NULL DEFAULT 0,-- 1=系统预设（不可删），0=用户预设
    version             INTEGER NOT NULL DEFAULT 1,-- 预设版本（编辑后自增）
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
  "is_system": 1,
  "version": 2,
  "created_at": 1754478700,
  "updated_at": 1754478800
}
```

**约束**：
- `is_system=1` 的预设不能 DELETE，只能 PUT（且只能改 `description` 和 `style_rules`）
- `version` 在 PUT 后自增，保留历史
- 内置预设 id 前缀 `preset-`（如 `preset-soul-std`、`preset-agents-std`、`preset-mem-std`、`preset-wlog-summary`）

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
- `api_key_encrypted` 字段不出现在任何 GET 响应里，UI 走专用 `/api/llm/providers/{id}/reveal` 端点（需二次确认）

---

### 2.7 `ai_jobs` —— AI 整理任务

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
~/.soulforge/backups/
└── <agent_id>/
    └── <sanitized_file_path>/
        └── <original_filename>.<YYYYMMDD-HHMMSS>.bak
```

**示例**：

```
~/.soulforge/backups/main/SOUL.md/SOUL.md.20260806-105830.bak
~/.soulforge/backups/main/memory_2026-08-05.md/memory_2026-08-05.md.20260806-110215.bak
~/.soulforge/backups/xiaowei-ops/AGENTS.md/AGENTS.md.20260806-114500.bak
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

`~/.soulforge/config.toml`（TOML 格式，可读可手改）：

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
```

**为什么用 TOML**：比 JSON 适合人改，比 YAML 不缩进敏感，比 INI 表达力强。

---

## 八、给 AI 编程助手的指令

**生成 ORM 模型时**：

- 用 SQLAlchemy 2.x 风格（`Mapped[]` 类型注解）
- 4 张表对应 4 个 Model 类
- 提供 `init_db()` 一次性建表函数
- 提供 Alembic 迁移起点（v0.2+ 启用，MVP 不需要）

**Pydantic 模型**（API 层）：

- 跟 SQLAlchemy Model 解耦，分开定义
- `AgentInfo` / `FileInfo` / `BackupEntry` / `LintWarning` 等用 Pydantic BaseModel
- 序列化用 `model_dump()` / `model_dump_json()`