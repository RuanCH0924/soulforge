# Soulforge — REST API 定义

> 配套主文档 [DEVELOPMENT.md](../DEVELOPMENT.md) 的 API 章节。
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
  "meta": { "timestamp": 1754478710, "version": "0.1.0" }
}
```

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

**响应**：

```json
{
  "data": {
    "agent_a": "main",
    "agent_b": "xiaowei-ops",
    "file": "SOUL.md",
    "similarity": 0.42,           // 0-1，越高越相似
    "unified_diff": "--- main/SOUL.md\n+++ xiaowei-ops/SOUL.md\n@@ ...",
    "html_diff": "<div class='diff'>...</div>"  // diff2html 输出
  }
}
```

#### `GET /api/diff/history`

对比当前文件 vs 历史备份。

**查询参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `agent` | string | Agent id |
| `file` | string | 文件路径 |
| `against` | string | 备份 ID（数字） |

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

### 3.6 导入导出

#### `GET /api/export/{agent_id}`

导出 Prompt Pack。

**响应**：`Content-Type: application/gzip`，返回 `.tar.gz` 文件。

**响应头**：

```
Content-Disposition: attachment; filename="soulforge-main-20260806-110000.tar.gz"
```

#### `GET /api/export/all`

导出全部 Agent（打包成一个 tarball，每个 Agent 一个子目录）。

#### `POST /api/import/preview`

上传 tar.gz，先解析 manifest 列出冲突。

**请求**：`multipart/form-data`，file 字段为 tar.gz。

**响应**：

```json
{
  "data": {
    "manifest": {
      "soulforge_version": "0.1.0",
      "agent_id": "main",
      "files": [
        { "path": "SOUL.md", "size": 4500, "sha256": "..." }
      ]
    },
    "conflicts": [
      { "path": "SOUL.md", "exists_in_target": true, "target_size": 4300 }
    ],
    "target_agent_id": "main"
  }
}
```

#### `POST /api/import/execute`

执行导入。

**请求**：

```json
{
  "upload_id": "upload-uuid-xxx",    // 上传时返回的临时 id
  "target_agent_id": "main",
  "conflicts": {
    "SOUL.md": "skip"                 // skip | merge | overwrite
  }
}
```

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

### 3.9 模板

#### `GET /api/templates`

列出内置模板。

**响应**：

```json
{
  "data": [
    {
      "id": "standard",
      "name": "Standard",
      "description": "标准配置（含全部 CORE 文件）",
      "file_count": 8
    },
    {
      "id": "minimal",
      "name": "Minimal",
      "description": "极简（仅 AGENTS.md + IDENTITY.md）",
      "file_count": 2
    },
    {
      "id": "lawyer-agent",
      "name": "Lawyer Agent",
      "description": "律师专用模板",
      "file_count": 9
    },
    {
      "id": "writer-agent",
      "name": "Writer Agent",
      "description": "作家专用模板",
      "file_count": 9
    }
  ]
}
```

#### `POST /api/templates/apply`

应用模板创建新 Agent。

**请求**：

```json
{
  "template_id": "lawyer-agent",
  "new_agent_id": "xiaoxi-lawyer-v2",
  "target_workspace": "/root/.openclaw/workspace-agents/xiaoxi-lawyer-v2"
}
```

---

### 3.10 统计

#### `GET /api/stats`

首页仪表盘数据。

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
    "lint_warnings_total": 5,
    "last_scan_at": 1754478700,
    "disk_usage_bytes": 12345678
  }
}
```

---

### 3.11 文档预设（Phase 2.5 · Step 1）

> 数据模型见 `DATA-MODEL.md` 的 `presets` 表。

#### `GET /api/presets`

列出全部预设（系统预设 + 用户自定义）。

**Query**：`?target_file_type=SOUL`（可选，过滤）

```json
{
  "data": [
    {
      "id": "preset-soul-std",
      "name": "SOUL.md 标准结构",
      "target_file_type": "SOUL",
      "is_system": true,
      "version": 1,
      "description": "核心行为准则 + 工作态度 + 学习连续性 + 核心边界",
      "created_at": 1754478700,
      "updated_at": 1754478700
    },
    {
      "id": "preset-mem-wlog",
      "name": "工作日志汇总",
      "target_file_type": "WORKLOG",
      "is_system": true,
      "version": 2,
      "description": "按时间倒序归档 memory/YYYY-MM-DD.md，提取关键决策"
    }
  ]
}
```

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

### 3.12 LLM Provider（Phase 2.5 · Step 2）

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

### 3.13 AI 自动整理（Phase 2.5 · Step 3）

> 数据模型见 `DATA-MODEL.md` 的 `ai_jobs` 表。

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

---

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