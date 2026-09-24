# Soulforge — REST API 定义

> 配套主文档 [DEVELOPMENT.md](DEVELOPMENT.md) 的 API 章节。
> 框架：FastAPI（自动 OpenAPI 文档，访问 `http://127.0.0.1:8848/docs`）。

---

## 一、设计原则

1. **路径前缀**：所有 API 在 `/api/*` 下，前端静态文件直接走根路径
2. **JSON only**：请求 / 响应全部 JSON
3. **REST 风格**：GET（读）/ POST（创建或副作用）/ PUT（更新）/ DELETE（删除）
4. **错误统一**：所有错误返回 `{"error": {"code": "...", "message": "..."}}`
5. **分页**：列表接口用 `?limit=&offset=` 或 `?page=&page_size=`
6. **审计**：所有写操作必须记录 `audit_log`

---

## 二、通用响应格式

### 2.1 成功响应

```json
{
  "data": { ... },
  "meta": { "timestamp": 1754478710, "version": "0.5.0" }
}
```

> `meta.version` 取自 `backend/app/__init__.py` 的 `__version__`（版本号唯一事实源）。
> 错误响应（2.2）不带 `meta`。

### 2.2 错误响应

```json
{
  "error": {
    "code": "FILE_NOT_FOUND",
    "message": "main workspace 下找不到 SOUL.md",
    "details": { "agent_id": "main", "path": "SOUL.md" }
  }
}
```

**错误码清单**：

| HTTP | code | 含义 |
|---|---|---|
| 400 | `BAD_REQUEST` | 参数错误 |
| 401 | `UNAUTHORIZED` | 未授权（预留） |
| 403 | `UNSAFE_PATH` | 路径穿越 |
| 404 | `AGENT_NOT_FOUND` | Agent 不存在 |
| 404 | `FILE_NOT_FOUND` | 文件不存在 |
| 409 | `CONFLICT` | 冲突（如 lint 严格模式违规） |
| 422 | `LLM_OUTPUT_TRUNCATED` | 模型输出被 `max_tokens` 截断（`finish_reason` = `length` / `max_tokens`），自动重试 1 次（预算翻倍）后仍未写完 → 请调大该 provider 的 `max_tokens` |
| 500 | `BACKUP_FAILED` | 备份失败 |
| 500 | `INTERNAL_ERROR` | 服务器内部错误 |

---

## 三、API 端点

### 3.1 Agent 管理

#### `GET /api/agents`

列出所有 Agent。

**响应**：

```json
{
  "data": [
    {
      "id": "main",
      "workspace": "/root/.openclaw/workspace",
      "display_name": "主 Agent",
      "file_count": 18,
      "last_scanned_at": 1754478700,
      "created_at": 1700000000,
      "updated_at": 1754478700
    },
    {
      "id": "xiaowei-ops",
      "workspace": "/root/.openclaw/workspace-agents/xiaowei-ops",
      "file_count": 12,
      "last_scanned_at": 1754478700,
      "created_at": 1700000000,
      "updated_at": 1754478700
    }
  ]
}
```

#### `GET /api/agents/{id}`

获取单个 Agent 详情（含最近活动）。

**响应**：

```json
{
  "data": {
    "id": "main",
    "workspace": "/root/.openclaw/workspace",
    "display_name": "主 Agent",
    "file_count": 18,
    "last_scanned_at": 1754478700,
    "recent_files": [
      { "path": "SOUL.md", "mtime": 1754478000, "size_bytes": 4500 },
      { "path": "AGENTS.md", "mtime": 1754470000, "size_bytes": 8000 }
    ]
  }
}
```

#### `POST /api/agents/scan`

重新扫描所有 Agent workspace，更新索引。

**响应**：

```json
{
  "data": {
    "agents_scanned": 6,
    "files_indexed": 87,
    "duration_ms": 234
  }
}
```

---

### 3.2 文件管理

#### `GET /api/agents/{id}/files`

列出 Agent 的所有 Prompt Pack 文件。

**查询参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `role` | string | 按角色过滤：`CORE` / `MEMORY` / `SKILL` / `META` / `OTHER` |

**响应**：

```json
{
  "data": [
    {
      "path": "SOUL.md",
      "role": "CORE",
      "size_bytes": 4500,
      "mtime": 1754478000,
      "sha256": "abc123...",
      "lint_warnings": 0
    },
    {
      "path": "memory/2026-08-05.md",
      "role": "MEMORY",
      "size_bytes": 1200,
      "mtime": 1754470000,
      "sha256": "def456...",
      "lint_warnings": 2
    }
  ]
}
```

#### `GET /api/agents/{id}/files/{path:path}`

读取文件内容。

**响应**：

```json
{
  "data": {
    "agent_id": "main",
    "path": "SOUL.md",
    "role": "CORE",
    "content": "# SOUL.md ...",
    "size_bytes": 4500,
    "mtime": 1754478000,
    "sha256": "abc123..."
  }
}
```

#### `PUT /api/agents/{id}/files/{path:path}`

写入文件（自动备份）。

**请求**：

```json
{
  "content": "# SOUL.md\n新内容...",
  "expected_sha256": "abc123..."    // 可选：乐观锁，期望的旧 hash
}
```

**响应**：

```json
{
  "data": {
    "agent_id": "main",
    "path": "SOUL.md",
    "size_bytes": 4600,
    "mtime": 1754478800,
    "sha256": "new123...",
    "backup_id": 145,
    "lint_warnings": 1
  }
}
```

**如果 `expected_sha256` 不匹配** → 返回 409 Conflict，提示文件已被外部修改。

#### `DELETE /api/agents/{id}/files/{path:path}`

删除文件。走系统回收站（`send2trash`），可从回收站恢复；不产生备份记录。

**响应**：

```json
{
  "data": { "agent_id": "main", "path": "SOUL.md", "deleted": true }
}
```

#### `POST /api/agents/files/cross-write`

跨 Agent 编辑：把同一份内容写入多个 Agent 的同名（或指定）文件，**每个 Agent 独立备份**。

**请求**：

```json
{
  "files": [
    { "agent_id": "main", "path": "SOUL.md" },
    { "agent_id": "xiaowei-ops", "path": "SOUL.md" }
  ],
  "content": "# SOUL.md\n统一后的内容..."
}
```

**响应**：

```json
{
  "data": {
    "results": [
      { "agent_id": "main", "path": "SOUL.md", "backup_id": 145 },
      { "agent_id": "xiaowei-ops", "path": "SOUL.md", "backup_id": 146 }
    ],
    "agents": 2
  }
}
```

> 护栏：前端必须先弹确认对话框展示受影响 Agent 列表，确认后才调用本接口。

#### `GET /api/agents/{id}/files/{path:path}/history`

获取文件备份历史。

**响应**：

```json
{
  "data": [
    {
      "backup_id": 145,
      "reason": "auto-write",
      "size_bytes": 4500,
      "sha256": "abc123...",
      "created_at": 1754478000
    },
    {
      "backup_id": 142,
      "reason": "auto-write",
      "size_bytes": 4300,
      "sha256": "old789...",
      "created_at": 1754470000
    }
  ]
}
```

---

### 3.3 搜索

#### `POST /api/search`

跨 Agent 全文搜索。

**请求**：

```json
{
  "query": "汇报风格",
  "agent_ids": ["main", "xiaowei-ops"],     // 可选，不传 = 全部
  "file_patterns": ["SOUL.md", "AGENTS.md"], // 可选，glob 模式
  "regex": false,
  "case_sensitive": true,
  "context_lines": 3,
  "limit": 100
}
```

**响应**：

```json
{
  "data": {
    "hits": [
      {
        "agent_id": "main",
        "file_path": "MEMORY.md",
        "line_number": 42,
        "line_content": "- 汇报风格（2026-08-03，老板明确要求）",
        "context_before": [...],
        "context_after": [...]
      }
    ],
    "total": 1,
    "duration_ms": 23
  }
}
```

---

### 3.4 Diff

#### `GET /api/diff`

对比两个 Agent 的同名文件。

**查询参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `a` | string | Agent A id |
| `b` | string | Agent B id |
| `file` | string | 文件路径 |
| `mode` | string | 归一化口径（可选，默认 `ignore_whitespace`）。`ignore_whitespace` 忽略空白 / 空行 / 缩进 / BOM / 零宽字符等格式噪声；`strict` 仅忽略 BOM / 换行符风格 / 零宽字符。非法值回落到默认 |

**响应**：

```json
{
  "data": {
    "agent_a": "main",
    "agent_b": "xiaowei-ops",
    "file": "SOUL.md",
    "similarity": 0.42,           // 0-1，在归一化文本上计算；内容一致时恒为 1.0
    "unified_diff": "--- main/SOUL.md\n+++ xiaowei-ops/SOUL.md\n@@ ...",
    "html_diff": "<pre class='diff-view'>...</pre>",  // 一致时为空字符串
    "identical": false,           // 有效内容（归一化后）是否一致
    "noise_kinds": [],            // 解释本次差异的格式噪声类型；空表示差异是真实业务差异
    "mode": "ignore_whitespace"
  }
}
```

**`noise_kinds` 取值**：

| 值 | 含义 |
|---|---|
| `bom` | UTF-8 BOM 差异 |
| `line_ending` | 换行符风格差异（CRLF / CR / LF） |
| `invisible_char` | 零宽 / 不可见字符（U+200B–200F、U+2060、U+FEFF、U+FE0F 等） |
| `space_like_char` | 全角空格 / 不换行空格等「看似空格」的字符 |
| `trailing_whitespace` | 行尾空白差异 |
| `multiple_spaces` | 连续空白 / Tab 缩进差异 |
| `blank_lines` | 多余空行差异 |
| `edge_blank_lines` | 文首 / 文末空行差异 |

> `identical=true` 时 `unified_diff` 与 `html_diff` 均为空字符串；若文件字节不同，
> `noise_kinds` 会列出导致差异的噪声类型，便于前端明确告知用户「差异仅来自格式噪声」。
> 性能：内容一致时走快路径，不做 diff 计算（大文件从秒级降到亚毫秒级）。

#### `GET /api/diff/history`

对比当前文件 vs 历史备份。

**查询参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `agent` | string | Agent id |
| `file` | string | 文件路径 |
| `against` | string | 备份 ID（数字） |
| `mode` | string | 归一化口径（可选，同 `GET /api/diff`） |

**响应**：同 `GET /api/diff`。

---

### 3.5 跨 Agent 同步

#### `POST /api/sync/plan`

生成同步计划（不执行）。

**请求**：

```json
{
  "src_agent": "main",
  "dst_agent": "xiaowei-ops",
  "files": ["SOUL.md", "AGENTS.md"]
}
```

**响应**：

```json
{
  "data": {
    "plan_id": "plan-uuid-xxx",
    "src_agent": "main",
    "dst_agent": "xiaowei-ops",
    "files": [
      {
        "path": "SOUL.md",
        "similarity": 0.42,
        "html_diff": "<div>...</div>",
        "size_src": 4500,
        "size_dst": 4300
      }
    ]
  }
}
```

#### `POST /api/sync/execute`

执行同步计划（必须先 plan）。

**请求**：

```json
{
  "plan_id": "plan-uuid-xxx",
  "files": ["SOUL.md", "AGENTS.md"]    // 用户确认要同步的文件子集
}
```

**响应**：

```json
{
  "data": {
    "results": [
      { "file": "SOUL.md", "status": "ok", "backup_id": 156 },
      { "file": "AGENTS.md", "status": "ok", "backup_id": 157 }
    ]
  }
}
```

**plan 必须 ≤ 30 分钟有效**（过期拒绝，防误操作）。

---

### 3.6 导出

#### `GET /api/export/{agent_id}`

导出 Prompt Pack。

**响应**：`Content-Type: application/gzip`，返回 `.tar.gz` 文件。

**响应头**：

```
Content-Disposition: attachment; filename="soulforge-main-20260806-110000.tar.gz"
```

#### `GET /api/export/all`

导出全部 Agent（打包成一个 tarball，每个 Agent 一个子目录）。

---

### 3.7 备份与回滚

#### `GET /api/backups/{agent_id}`

列出 Agent 的所有备份（按文件分组）。

**响应**：

```json
{
  "data": {
    "agent_id": "main",
    "files": [
      {
        "file_path": "SOUL.md",
        "backups": [
          { "backup_id": 145, "reason": "auto-write", "size_bytes": 4500, "created_at": 1754478000 },
          { "backup_id": 142, "reason": "auto-write", "size_bytes": 4300, "created_at": 1754470000 }
        ]
      }
    ]
  }
}
```

#### `POST /api/backups/{agent_id}/{file_path}/rollback`

回滚到指定备份。

**请求**：

```json
{
  "backup_id": 142
}
```

**响应**：

```json
{
  "data": {
    "file_path": "SOUL.md",
    "rolled_back_to": 142,
    "new_backup_id": 158,    // 回滚前的当前状态备份
    "sha256": "..."
  }
}
```

---

### 3.8 Lint

#### `GET /api/lint/rules`

列出全部 lint 规则（供 UI 展示「在检查什么」）。

规则文案的唯一事实源是 `backend/app/services/lint_service.py` 的规则类
（`rule_id` / `rule_name` / `scope` / `severity` / `description`），本接口由 `LintService.rule_catalog()` 下发。

**响应**：

```json
{
  "data": {
    "rules": [
      {
        "rule_id": "L4-TIMESTAMP",
        "rule_name": "L4 反模式 — 时间戳",
        "scope": "file",
        "severity": "warning",
        "description": "正文出现时效性标记（最后修订 / 最后更新 / ## 更新记录 / ## Changelog）——CORE 文档只保留最终规则，不记录时间"
      }
    ],
    "count": 8
  }
}
```

> `scope`：`file` = 逐文件即可判定；`agent` = 需要 Agent 全貌（跨文件 / 跨 Agent，如 `CORE-MISSING`、`CROSS-AGENT-DRIFT`）。

#### `GET /api/lint/{agent_id}`

对整个 Agent 跑 lint。

**响应**：

```json
{
  "data": {
    "agent_id": "main",
    "warnings": [
      {
        "rule_id": "L4-TIMESTAMP",
        "rule_name": "L4 反模式 — 时间戳",
        "severity": "warning",
        "file_path": "SOUL.md",
        "line_number": 5,
        "line_content": "*最后更新：2026-07-09*",
        "suggestion": "删除该行，时间戳不应进入 L4 文件"
      }
    ],
    "stats": {
      "files_checked": 18,
      "warnings": 3,
      "errors": 0
    }
  }
}
```

#### `GET /api/lint/file/{agent_id}/{file_path}`

对单文件 lint。

#### `GET /api/lint/all`

对所有 Agent 跑 lint。

---

### 3.9 统计

#### `GET /api/stats`

数据中心「统计面板」的索引类指标（agents / files / backups / disk）。

> **不含 lint 警告数**：该指标必须实时跑 lint 才能得到。此前用索引列 `files.lint_warnings` 求和，
> 但该列从不被扫描填充（`FileInfo.lint_warnings` 恒为默认 0），返回的一直是**假数据**。
> UI 的 lint 计数统一取自 `GET /api/lint/all`（与「检查报告」同源同口径），
> 见「统计面板」的 lint 卡片与底部状态栏。

**响应**：

```json
{
  "data": {
    "agents_total": 6,
    "files_total": 87,
    "core_files": 32,
    "memory_files": 45,
    "backup_total": 234,
    "backup_size_bytes": 5242880,
    "last_scan_at": 1754478700,
    "disk_usage_bytes": 12345678
  }
}
```

---

### 3.10 文档预设（Phase 2.5 · Step 1）

> 数据模型见 `DATA-MODEL.md` 的 `presets` 表。

#### `GET /api/presets`

列出预设（系统预设 + 用户自定义）。已退役的内置预设（`retired_at` 非空）不返回。

**Query**：

| 参数 | 说明 |
|---|---|
| `target_file_type` | 可选，按适用文件类型过滤（`SOUL` / `AGENTS` / `MEMORY` / `USER` / `IDENTITY` / `TOOLS` / `WORKLOG` / `ANY`） |
| `scope` | 可选，`all`（缺省）或 `workbench`。`workbench` = **主工作台 / 设置页用**：排除「专供大模型处理工作日志」的预设（即 `target_file_type=WORKLOG`），只留下供主工作台加载的预设。非法值 → `400 BAD_REQUEST` |

> 两类预设的边界（UI-SPECS §5.7）：`target_file_type=WORKLOG` 的预设是 M15 日志标准化的规则载体，
> 只在「业务工具 → 日志标准化」界面（及其 API）可见、可编辑；设置页「文档预设」与主工作台
> 「应用预设 / AI 整理」都传 `scope=workbench`，因此不会出现它们。日志标准化界面按
> `?target_file_type=WORKLOG` 取（不传 `scope`）。

```json
{
  "data": [
    {
      "id": "preset-soul-std",
      "name": "SOUL.md 标准结构",
      "target_file_type": "SOUL",
      "is_system": false,
      "is_builtin": true,
      "version": 1,
      "description": "核心行为准则 + 工作态度 + 学习连续性 + 核心边界",
      "created_at": 1754478700,
      "updated_at": 1754478700
    },
    {
      "id": "preset-wlog-daily-std",
      "name": "工作日志日标准化",
      "target_file_type": "WORKLOG",
      "is_system": false,
      "is_builtin": true,
      "version": 2,
      "description": "把同一天的多份来源归并成 1 份标准工作日志并清理碎片；也可整理单份日文件"
    }
  ]
}
```

> `is_builtin`：是否内置预设（随版本分发，升级时可能被刷新）；`false` = 用户自建。
> UI 用它展示「预设来源」（M15 预设信息栏）。注意与历史字段 `is_system`（恒为 `false`）的区别。

#### `POST /api/presets`

创建用户预设。

```json
{
  "name": "AGENTS.md 老板风格",
  "target_file_type": "AGENTS",
  "description": "符合老板偏好的 AGENTS.md 结构",
  "sections_json": [
    {"title": "首次运行", "required": true, "order": 1},
    {"title": "会话启动", "required": true, "order": 2},
    {"title": "执行原则：三档授权", "required": true, "order": 3}
  ],
  "frontmatter_json": {"schema": "soulforge.preset/v1", "owner": "user"},
  "style_rules": ["emoji-in-section-title=false", "口语化禁令"]
}
```

**响应**：`201 Created` + 新预设详情（含 id、version=1、is_system=false）。

#### `POST /api/presets/from-document`

由当前文档生成预设（编辑栏「设为预设」按钮）。以编辑器当前内容作为**模板正文**，
配合用户填写的规则参数生成带 YAML 规则 frontmatter 的模板文档，等价于一次
「从现有文档反推结构」的预设创建。

```json
{
  "name": "我的 SOUL 结构",
  "target_file_type": "SOUL",
  "content": "# SOUL.md\n\n## 核心行为准则\n\n- 简洁优先\n…",
  "description": "由 main/SOUL.md 提取",
  "section_heading_level": 2,
  "required_sections": ["核心行为准则", "核心边界"],
  "section_order": "strict",
  "require_frontmatter": false
}
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 预设名称（写入模板 frontmatter） |
| `target_file_type` | 是 | 适用文件类型 |
| `content` | 是 | 作为模板正文的文档内容；UTF-8 体积 ≤ 30KB |
| `description` | 否 | 用途说明 |
| `section_heading_level` | 否 | 章节标题层级（1–6，默认 2）：该层级的标题构成章节清单 |
| `required_sections` | 否 | 必填章节（须为文档中该层级的标题）；留空 = 该层级全部标题；顺序始终按文档出现顺序 |
| `section_order` | 否 | `strict`（默认）/ `loose` |
| `require_frontmatter` | 否 | 是否要求目标文档带 YAML frontmatter（默认 `false`） |

**响应**：`201 Created` + 新预设详情（`sections_json` 由模板 frontmatter 派生）。

**错误**：

| HTTP | code | 场景 |
|---|---|---|
| 400 | `BAD_REQUEST` | 文档超过 30KB；文档中未发现该层级的标题；`required_sections` 在文档中均不存在 |

> 说明：`max_heading_level` 由文档实际标题层级推断，无需用户填写；
> 标题扫描会跳过围栏代码块内的 `#`（与编辑器大纲口径一致）。

#### `GET /api/presets/{id}`

查看预设完整内容（含 sections_json / frontmatter_json / style_rules）。

#### `PUT /api/presets/{id}`

编辑预设。**version 自增 +1**。

**约束**：
- 系统预设（`is_system=true`）只能编辑 `description` 和 `style_rules`，不能改 sections
- 用户预设可改全部字段

```json
{
  "name": "AGENTS.md 老板风格（v2）",
  "sections_json": [...],
  "style_rules": [...]
}
```

**响应**：`200 OK` + 更新后预设（含新 version）。

#### `DELETE /api/presets/{id}`

删除用户预设。

**约束**：系统预设 → `403 Forbidden`。

#### `POST /api/presets/{id}/apply`

生成应用 plan（不写入文件）。

**请求**：

```json
{
  "agent_id": "main",
  "file_path": "SOUL.md",
  "extra_instructions": "保留『阅读策略』章节原内容不动"
}
```

**响应**：

```json
{
  "data": {
    "plan_id": "plan-uuid",
    "agent_id": "main",
    "file_path": "SOUL.md",
    "preset_id": "preset-soul-std",
    "current_snapshot": "# 当前内容前 200 字符...",
    "proposed_content": "# 新内容...",
    "unified_diff": "--- SOUL.md\n+++ SOUL.md\n@@ -1,3 +1,5 @@\n...",
    "lint_warnings": []
  }
}
```

#### `POST /api/presets/{id}/apply/execute`

执行应用（写入文件 + 自动备份 + 审计）。

**请求**：

```json
{
  "plan_id": "plan-uuid",
  "agent_id": "main",
  "file_path": "SOUL.md"
}
```

**响应**：

```json
{
  "data": {
    "backup_id": "bak-uuid",
    "applied_at": 1754478700,
    "file_size": 1234
  }
}
```

---

### 3.11 LLM Provider（Phase 2.5 · Step 2）

> 数据模型见 `DATA-MODEL.md` 的 `llm_providers` 表。

#### `GET /api/llm/providers`

列出所有 provider（**api_key 字段返回掩码 `sk-****...****`**）。

```json
{
  "data": [
    {
      "id": "openai-main",
      "base_url": "https://api.openai.com/v1",
      "api_key_masked": "sk-****1234",
      "model": "gpt-4o",
      "protocol": "openai-completions",
      "enabled": true,
      "max_tokens": 4096,
      "temperature": 0.3,
      "timeout_seconds": 60
    }
  ]
}
```

#### `POST /api/llm/providers`

新增 provider。

```json
{
  "id": "openai-main",
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-...",
  "model": "gpt-4o",
  "protocol": "openai-completions",
  "max_tokens": 4096,
  "temperature": 0.3
}
```

**约束**：
- `protocol` ∈ `{openai-completions, anthropic-messages}`
- `api_key` 加密存储，**永不回显明文**

#### `PUT /api/llm/providers/{id}`

编辑 provider。

**特殊规则**：`api_key` 字段**留空 = 保留旧 key**（前端 UX：密码框可空）。

#### `DELETE /api/llm/providers/{id}`

**约束**：有关联 `ai_jobs` 的 provider 不可删（避免历史断链）→ `409 Conflict`。

#### `POST /api/llm/providers/{id}/test`

测试连通性。发一条 `{"role":"user","content":"ping"}`，期望收到非空回复。

```json
{
  "data": {
    "ok": true,
    "latency_ms": 1234,
    "response_preview": "pong"
  }
}
```

#### `POST /api/llm/chat`

通用 chat 端点（内部用，AI Editor 调用）。

```json
{
  "provider_id": "openai-main",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "max_tokens": 4096,
  "temperature": 0.3
}
```

**响应**：

```json
{
  "data": {
    "content": "...",
    "usage": {"prompt_tokens": 123, "completion_tokens": 456, "total_tokens": 579},
    "cost_estimate_usd": 0.0123
  }
}
```

---

### 3.12 AI 自动整理（Phase 2.5 · Step 3）

> 数据模型见 `DATA-MODEL.md` 的 `ai_jobs` 表。
> `output_content` 是**已净化**的文档正文：模型写在正文前的思考过程 / 规则复述
> （如「让我仔细分析这个任务：…」）与整篇文档的外层代码围栏会在入库前剥离，
> 并在其后执行模板格式校验（`diff_plan.format_report`）。

#### `POST /api/ai/jobs`

创建 AI 整理任务（异步执行）。

```json
{
  "agent_id": "main",
  "file_path": "SOUL.md",
  "preset_id": "preset-soul-std",
  "provider_id": "openai-main",
  "extra_instructions": "保留「阅读策略」章节原内容不动"
}
```

**响应**：`202 Accepted`：

```json
{
  "data": {
    "job_id": "job-uuid",
    "status": "pending",
    "created_at": 1754478700
  }
}
```

#### `GET /api/ai/jobs/{id}`

查询任务状态。

```json
{
  "data": {
    "job_id": "job-uuid",
    "status": "awaiting_confirm",
    "agent_id": "main",
    "file_path": "SOUL.md",
    "preset_id": "preset-soul-std",
    "provider_id": "openai-main",
    "input_snapshot": "# 原内容...",
    "output_content": "# AI 整理后...",
    "diff_plan_json": {...},
    "lint_warnings": [],
    "usage": {"prompt_tokens": 123, "completion_tokens": 456, "total_tokens": 579},
    "created_at": 1754478700,
    "updated_at": 1754478710
  }
}
```

#### `POST /api/ai/jobs/{id}/apply`

应用 AI 输出（写入文件 + 自动备份 + 审计）。

**约束**：
- `status` 必须是 `awaiting_confirm`，否则 `409 Conflict`
- 输出必须通过 lint 规则，否则 `422 Unprocessable Entity`

#### `POST /api/ai/jobs/{id}/reject`

拒绝 AI 输出（不写入）。

#### `POST /api/ai/jobs/{id}/regenerate`

重新生成（带新指令）。

```json
{
  "extra_instructions": "上次漏了「核心边界」章节，请补上"
}
```

**响应**：新建 job（status=pending），原 job 标记为 `superseded`。

#### `GET /api/ai/jobs`

列出 AI 任务历史（按时间倒序）。

**Query**：`?agent_id=main&status=applied&limit=50`

### 3.13 超级同步（独立守护脚本）

> 与 3.5「跨 Agent 同步（plan + confirm 两步）」不同：超级同步是**持续运行的独立进程**，
> 在多个 Agent 之间对「同名文件」做秒级双向同步（冲突策略：最新修改优先）。
> 该进程由后端以「分离进程」方式拉起，Soulforge 主进程退出后仍继续运行。
> 落盘目录：`<data_dir>/super_sync/`（`config.json` / `status.json` / `logs/*.jsonl`）。

#### `GET /api/super-sync/config`

读取同步范围配置。

```json
{
  "data": {
    "interval_seconds": 1,
    "retention_days": 30,
    "agents": ["alpha", "beta"],
    "files": {"alpha": ["SOUL.md", "AGENTS.md"], "beta": ["SOUL.md"]}
  }
}
```

#### `PUT /api/super-sync/config`

更新同步范围（局部合并）。`retention_days` 后端强制 ≥ 30；`interval_seconds` 钳制在 0.5–60；
`files` 仅接受 5 个核心文档（`SOUL.md` / `AGENTS.md` / `USER.md` / `MEMORY.md` / `IDENTITY.md`），
其余路径（含子目录 / 历史遗留配置）一律被丢弃。

```json
{
  "agents": ["alpha", "beta"],
  "files": {"alpha": ["SOUL.md"], "beta": ["SOUL.md"]},
  "interval_seconds": 1
}
```

#### `GET /api/super-sync/status`

运行状态：`running | stopped | error`（`error` = 进程存活但心跳超时）。

```json
{
  "data": {
    "state": "running",
    "pid": 12345,
    "pid_alive": true,
    "source": "ui",
    "started_at": "2026-09-13T20:00:00.000",
    "last_heartbeat": "2026-09-13T20:05:00.000",
    "heartbeat_age_seconds": 0.42,
    "interval_seconds": 1,
    "agents": ["alpha", "beta"],
    "synced_total": 12,
    "ticks": 300,
    "last_sync_at": "2026-09-13T20:04:59.000",
    "last_error": null
  }
}
```

#### `POST /api/super-sync/start`

以独立进程启动超级同步（已在运行则直接返回当前状态）。响应体同 `GET /status`。

#### `POST /api/super-sync/stop`

停止独立进程（Windows 走 `taskkill /F`，POSIX 走 `SIGTERM`）。响应体同 `GET /status`。

#### `GET /api/super-sync/logs`

按级别 / 时间范围查询日志（倒序）。

**Query**：`?levels=INFO,ERROR&since=1754478700&until=1754479000&limit=200&offset=0`

```json
{
  "data": {
    "items": [
      {
        "ts": "2026-09-13T20:00:01.000",
        "ts_unix": 1757772001.0,
        "level": "INFO",
        "event": "sync",
        "path": "SOUL.md",
        "source_agent": "alpha",
        "target_agent": "beta",
        "result": "ok",
        "size_bytes": 128,
        "sha256": "…",
        "diff": "--- a/SOUL.md\n+++ b/SOUL.md\n@@ -1 +1 @@\n-…\n+…"
      }
    ],
    "total": 1,
    "limit": 200,
    "offset": 0,
    "retention_days": 30
  }
}
```

非法级别返回 `400 BAD_REQUEST`。

#### `GET /api/super-sync/logs/export`

导出筛选后的日志（`application/x-ndjson`，`Content-Disposition` 附件下载）。Query 同 `GET /logs`（不含分页）。

#### 命令行启动（等价入口）

```bash
cd backend
python super_sync.py --data-dir <data_dir> --openclaw-dir <openclaw_dir> --source cli
python super_sync.py --once        # 只执行一轮（自检）
```

两种启动方式共用同一份 `config.json` 与 `status.json`，因此 UI 能正确识别命令行启动的进程。

---

### 3.14 系统接口（健康检查 / 审计 / 配置）

#### `GET /api/health`

健康检查。不发任何外部请求；前端启动时调用以获取后端版本号（状态栏展示）。

**响应**：

```json
{
  "data": { "status": "ok", "version": "0.5.0" }
}
```

> `version` 与 `meta.version` 同源，均取自 `backend/app/__init__.py` 的 `__version__`。

#### `GET /api/audit`

查询审计日志（按时间倒序）。

**查询参数**：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | int | `100` | 返回条数（1–500） |
| `offset` | int | `0` | 偏移量 |
| `agent_id` | string | — | 按 Agent 过滤 |
| `action` | string | — | 按操作类型过滤（`write` / `delete` / `rollback` / `sync` / `export` / `preset_apply` / `ai_apply` 等） |

**响应**：

```json
{
  "data": [
    {
      "id": 512,
      "timestamp": 1754478710,
      "action": "write",
      "agent_id": "main",
      "target_path": "SOUL.md",
      "details_json": "{\"size_before\": 4321, \"backup_id\": 145}",
      "user": "local",
      "result": "ok"
    }
  ]
}
```

#### `GET /api/config` / `PUT /api/config`

读取 / 局部更新 `config.toml`（未传字段保持不变）。

**PUT 请求**（各段均可选）：

```json
{
  "server":    { "host": "127.0.0.1", "port": 8848 },
  "backup":    { "retention_days": 30, "auto_backup_on_write": true },
  "lint":      { "enabled": true, "strict_mode": false },
  "ui":        { "default_theme": "auto", "default_view": "tree" },
  "advanced":  { "show_skills": false, "show_meta": false, "show_memory": false, "show_other": false },
  "openclaw":  { "dir": "" },
  "daily_standardizer": {
    "max_days_per_run": 31,
    "token_budget": 200000,
    "provider_id": "",
    "dry_run_only": false
  }
}
```

**生效时机**：`backup` / `lint` / `ui` / `advanced` / `openclaw` / `daily_standardizer` 立即生效；
`server.host` / `server.port` 需重启服务。

---

### 3.15 工作日志标准化（M15 · P2）

把某个 Agent `memory/` 下指定日期范围内的工作日志归并为**每天恰好 1 个 `YYYY-MM-DD.md`**。
核心约束与 AI 整理一致：**计划与写入分离**——先出计划（只读、不落盘），人逐个 diff 确认后才写入，
碎片删除走系统回收站。批次状态机与逐日状态见
[MEMORY-DAILY-STANDARDIZER-PLAN.md](MEMORY-DAILY-STANDARDIZER-PLAN.md) 附录 D。

#### `POST /api/daily-runs`

创建批次。**异步**：立即返回 `202`，后台逐日生成计划（`planned` → `awaiting_confirm`）。
命中幂等键（同 Agent / 范围 / 预设 / provider / 来源内容）时直接复用既有批次，不产生第二次 LLM 调用。

**请求**：

```json
{
  "agent_id": "main",
  "date_from": "2026-08-01",
  "date_to": "2026-08-31",
  "preset_id": "preset-wlog-daily-std",
  "provider_id": "openai-main",
  "extra_instructions": "把「端口巡检」相关条目合并到一节"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `agent_id` | ✅ | Agent id |
| `date_from` / `date_to` | ✅ | `YYYY-MM-DD`；只处理「需要整理」的日子（同日多来源，或唯一来源质量差） |
| `preset_id` | — | 默认 `preset-wlog-daily-std`（内置「工作日志日标准化」） |
| `provider_id` | ✅ | 必须存在且启用 |
| `extra_instructions` | — | 附加指令 |

**响应**（`202`）：

```json
{
  "data": {
    "run_id": "run-3f6b1c0d9a2e4b7f8c1d5e6a7b8c9d0e",
    "status": "planned",
    "days_total": 11,
    "reused": false,
    "created_at": 1758700000
  }
}
```

**错误**：

| 场景 | HTTP | code |
|---|---|---|
| `date_from` / `date_to` 含 `/`、`\`、`..` | `403` | `UNSAFE_PATH` |
| 日期不是合法 `YYYY-MM-DD` 或 `date_from > date_to` | `400` | `BAD_REQUEST` |
| 需要整理的天数 > `max_days_per_run` | `400` | `BAD_REQUEST` |
| `preset_id` / `provider_id` 不存在或未启用 | `404` | `NOT_FOUND` |

> 该范围没有任何需要整理的日子时，批次直接落 `empty`（`days_total=0`），不发起 LLM 调用。

#### `GET /api/daily-runs`

批次列表（按创建时间倒序）。

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `agent_id` | string | — | 按 Agent 过滤 |
| `status` | string | — | 按状态过滤 |
| `limit` | int | `50` | 1–200 |

#### `GET /api/daily-runs/{run_id}`

批次详情：批次摘要 + `items[]`（逐日条目）。每个条目含来源清单（`sources[]`：路径 / A·B·C 类别 /
剥壳前后体积）、`fragments_to_delete[]`、`output_content`、`unified_diff` / `html_diff`、
`format_report`、`lint_warnings`、`notes`、`empty_reason`、`status`、逐日 token 与成本。

`status` 取值：`pending` / `planned` / `failed` / `blocked` / `applied` / `partially_applied` /
`empty`（判定本日无可归档内容：不产出日文件，`empty_reason` 为一句话理由，只清 B/C 碎片）/ `skipped`。

#### `POST /api/daily-runs/{run_id}/apply`

应用选中日期。**两步预检 + 三步执行**：

1. 批次级预检：对**全部目标日**跑写前验收（强规则 + 12 类残留壳检测）与乐观锁比对
   - 任一目标文件当前 SHA-256 ≠ 计划时 → 抛 `409`，**整批不写**
   - 任一日验收不过 → 该日标 `blocked`，不写入（其余继续）
   - 「无可归档内容」的日期不写文件，改按**逐个碎片**的 SHA-256 比对（碎片被改动同样抛 `409`）
2. 逐个写入日文件（`FileManager.write`：自动备份 + 审计），随后删除该日碎片（`send2trash`）；
   「无可归档内容」的日期**跳过写入**，只清碎片（A 类主文件 `YYYY-MM-DD.md` 不动），审计动作 `daily_empty_content`
3. 写批次状态并跑验收报告；报告不通过 → 批次标 `needs_review`（已写入的日文件**不回滚**）

**请求**（`dates` 与 `apply_all` 二者其一）：

```json
{ "dates": ["2026-08-03", "2026-08-05"], "apply_all": false }
```

**响应**：

```json
{
  "data": {
    "run_id": "run-3f6b...",
    "status": "applied",
    "applied": ["2026-08-03"],
    "partial": ["2026-08-05"],
    "blocked": [],
    "failed": [],
    "no_content": ["2026-08-04"],
    "skipped": []
  }
}
```

| 字段 | 含义 |
|---|---|
| `applied` | 已写入日文件且碎片已清理 |
| `partial` | 日文件已写，碎片删失败 |
| `blocked` | 写前验收不过，未写入 |
| `no_content` | 判定「无可归档内容」：未产出日文件，仅清理碎片 |
| `failed` | 写入失败 |

**错误**：

| 场景 | HTTP | code |
|---|---|---|
| `config.daily_standardizer.dry_run_only = true` | `403` | `DAILY_RUN_DISABLED` |
| 批次不是 `awaiting_confirm` | `409` | `DAILY_RUN_STATUS` |
| 目标文件或碎片被外部改动（乐观锁冲突） | `409` | `CONFLICT`（`details.conflicts[]` 列出日期与原因） |
| 没有可应用的日子 | `400` | `BAD_REQUEST` |

#### `POST /api/daily-runs/{run_id}/reject`

拒绝整批（不写入任何文件）。已是 `applied` / `partially_applied` / `rejected` 时 `409 DAILY_RUN_STATUS`。

#### `POST /api/daily-runs/{run_id}/skip`

跳过若干日（人工决策，不改写这些天）。请求 `{"dates": ["2026-08-04"]}`；
所选日期没有可跳过的条目 → `400 BAD_REQUEST`。

#### `GET /api/daily-runs/{run_id}/report`

验收报告。**只读**（不改批次状态），随时可重复跑；对磁盘上的**真实文件**核对 5 项。
判定「无可归档内容」的日期 `empty=true`、`delivered=false`，只核对 `fragments_gone`（其余四项标注为不适用）。

```json
{
  "data": {
    "run_id": "run-3f6b...",
    "agent_id": "main",
    "status": "applied",
    "passed": true,
    "items": [
      {
        "date": "2026-08-03",
        "target_path": "memory/2026-08-03.md",
        "status": "applied",
        "empty": false,
        "delivered": true,
        "single_file": true,
        "naming_ok": true,
        "sections_ok": true,
        "no_residue": true,
        "fragments_gone": true,
        "details": []
      },
      {
        "date": "2026-08-04",
        "target_path": "memory/2026-08-04.md",
        "status": "empty",
        "empty": true,
        "delivered": false,
        "single_file": true,
        "naming_ok": true,
        "sections_ok": true,
        "no_residue": true,
        "fragments_gone": true,
        "details": ["判定无可归档内容：全天只有心跳与状态轮询"]
      }
    ],
    "days_delivered": 1,
    "days_total": 2,
    "tokens_used": 4120,
    "cost_estimate_usd": 0.0103,
    "generated_at": 1758700300
  }
}
```

---

## 四、给 AI 编程助手的指令

**生成路由时**：

- 每个模块一个 `router.py`：`/api/agents.py`、`/api/files.py` 等
- 用 FastAPI `APIRouter` + 依赖注入（`Depends`）注入 Service
- 所有路径参数过 `Depends(safe_path)` 自动校验
- 所有写操作调用 `audit_service.record(...)`

**生成 Pydantic 模型时**：

- 请求 / 响应模型分开定义
- 用 `Field(..., description="...")` 加描述（自动进 OpenAPI 文档）
- 用 `Literal` 限定枚举值（如 `Literal["CORE", "MEMORY", ...]`）

**测试**：

- 用 `httpx.AsyncClient` 跑集成测试
- 关键路径：`test_files_write_with_backup` / `test_sync_plan_execute` / `test_rollback` / `test_lint_*`