# Soulforge — 系统架构详解

> 配套主文档 [DEVELOPMENT.md](DEVELOPMENT.md) 的架构章节。

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (Chrome / Edge / Safari)                           │
│  http://127.0.0.1:8848                                       │
└────────────┬────────────────────────────────────────────────┘
             │ HTTP / JSON
             ↓
┌─────────────────────────────────────────────────────────────┐
│  Soulforge Server (FastAPI + uvicorn, 单进程)                │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Router 层  (/api/*)                                │    │
│  │  ├── /agents       Agent 管理 + 文件读写/删除        │    │
│  │  ├── /search       搜索路由                          │    │
│  │  ├── /diff         diff 路由                         │    │
│  │  ├── /sync         跨 Agent 同步路由                 │    │
│  │  ├── /super-sync   超级同步路由（启停 / 状态 / 日志）│    │
│  │  ├── /export       导出路由                          │    │
│  │  ├── /backups      备份路由                          │    │
│  │  ├── /lint         lint 路由                         │    │
│  │  ├── /stats        统计路由                          │    │
│  │  ├── /audit        审计日志路由                      │    │
│  │  ├── /config       配置中心路由                      │    │
│  │  ├── /presets      文档预设路由（M11）              │    │
│  │  ├── /llm          LLM Provider 路由（M12）         │    │
│  │  ├── /ai           AI 整理任务路由（M13）           │    │
│  │  └── /daily-runs   日志标准化批次路由（M15）        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Service 层                                          │    │
│  │  ├── AgentDiscovery     读 openclaw.json → Agent 列表│   │
│  │  ├── FileManager        读 / 写 / 删除文件            │    │
│  │  ├── BackupService      自动备份 / 历史 / 回滚        │    │
│  │  ├── SearchService      ripgrep 包装                  │    │
│  │  ├── LintService        8 条规则执行                  │    │
│  │  ├── DiffService        归一化 + unified diff        │    │
│  │  ├── SyncService        跨 Agent 选择性合并           │    │
│  │  ├── SuperSyncService   超级同步：启停 / 状态 / 日志 │    │
│  │  ├── ImportExport       Prompt Pack 导出             │    │
│  │  ├── PresetService      文档预设 CRUD + 应用（两类预设 │    │
│  │  │                     的 scope 边界见 3.8）         │    │
│  │  ├── TemplateRuleParser 模板规则解析 / 格式校验       │    │
│  │  ├── LLMRegistry        多协议 LLM 注册表（热加载 +   │    │
│  │  │                     截断识别/重试）                │    │
│  │  ├── AIJobService       AI 整理任务生命周期          │    │
│  │  ├── DailySourceScanner memory/ 日文件 A/B/C 分类     │    │
│  │  ├── DailyMergeService  单日多来源 → 1 文件（M15）    │    │
│  │  ├── DailyRunService    日志标准化批次编排（M15）     │    │
│  │  ├── AuditService       审计日志                      │    │
│  │  └── StatsService       统计聚合                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Storage 层                                          │    │
│  │  ├── SQLite (<data_dir>/index.db)                    │    │
│  │  │     └── agents / files / backups / audit_log       │    │
│  │  │         presets / preset_versions                 │    │
│  │  │         llm_providers / ai_jobs                   │    │
│  │  └── 文件系统（workspace / <data_dir>、super_sync/） │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└────────────┬────────────────────────────────────────────────┘
             │ 文件系统直接读写（不抽象层）
             ↓
┌─────────────────────────────────────────────────────────────┐
│  OpenClaw Workspace 文件                                     │
│  ~/.openclaw/workspace/                                      │
│  ~/.openclaw/workspace-agents/xiaowei-ops/                  │
│  ~/.openclaw/workspace-agents/xiaoxi-lawyer/                │
│  ...                                                         │
│  ~/.openclaw/openclaw.json                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、单进程部署

**FastAPI 同时 serve React build 静态文件 + REST API**：

```python
# backend/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app import __version__   # 版本号唯一事实源（backend/app/__init__.py）

app = FastAPI(title="Soulforge", version=__version__)

# API 路由
app.include_router(agents_router, prefix="/api/agents")
app.include_router(files_router, prefix="/api/files")
# ...

# 静态文件（前端 build）
app.mount("/assets", StaticFiles(directory="../frontend/dist/assets"))

@app.get("/{path:path}")
async def spa(path: str):
    return FileResponse("../frontend/dist/index.html")
```

启动命令：

```bash
cd backend
uvicorn main:app --host 127.0.0.1 --port 8848 --reload
```

**一个进程，一个端口，老板双击启动**。

---

## 三、关键模块设计

### 3.1 AgentDiscovery

```python
class AgentDiscovery:
    """读 ~/.openclaw/openclaw.json 的 agents.list + agents.defaults.workspace"""

    def discover(self) -> list[AgentInfo]:
        config = self._read_openclaw_config()
        workspace_root = Path("~/.openclaw").expanduser()

        agents = []
        # 来自 agents.list 显式声明
        for entry in config.get("agents", {}).get("list", []):
            agents.append(self._build_agent_info(entry, workspace_root))

        # 自动发现 workspace-agents/* 下的子目录（兜底）
        workspace_agents_dir = workspace_root / "workspace-agents"
        if workspace_agents_dir.exists():
            for sub in workspace_agents_dir.iterdir():
                if sub.is_dir() and not any(a.id == sub.name for a in agents):
                    agents.append(self._auto_agent(sub))

        return agents

    def _build_agent_info(self, entry, workspace_root) -> AgentInfo:
        workspace = Path(entry["workspace"]).expanduser()
        return AgentInfo(
            id=entry["id"],
            workspace=workspace,
            # ... 元数据
        )
```

### 3.2 FileManager

**职责**：封装所有 workspace 文件读写，自动触发 BackupService。

```python
class FileManager:
    def read(self, agent_id: str, path: str) -> FileContent:
        """只读读取"""
        agent = self._get_agent(agent_id)
        full_path = self._safe_join(agent.workspace, path)
        return FileContent(
            path=path,
            content=full_path.read_text(encoding="utf-8"),
            mtime=full_path.stat().st_mtime,
            size=full_path.stat().st_size,
        )

    def write(self, agent_id: str, path: str, content: str, *, auto_backup: bool = True):
        """写入前自动备份"""
        if auto_backup:
            self.backup_service.backup(agent_id, path)

        full_path = self._safe_join(self._get_agent(agent_id).workspace, path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

        # 重新索引
        self.index_service.upsert_file(agent_id, path)

        # 审计日志
        self.audit_log.record("write", agent_id, path, len(content))

    def list(self, agent_id: str) -> list[FileInfo]:
        """列出 workspace 下所有 .md 文件"""
        agent = self._get_agent(agent_id)
        files = []
        for path in agent.workspace.rglob("*.md"):
            if self._should_include(path):
                files.append(self._build_file_info(agent_id, path))
        return files
```

**安全约束**：`_safe_join` 防路径穿越（拒绝 `../../../etc/passwd`）。

### 3.3 BackupService

```python
class BackupService:
    BACKUP_ROOT = config.backups_dir   # <data_dir>/backups（默认 <项目根>/.soulforge/backups）
    RETENTION_DAYS = 30

    def backup(self, agent_id: str, file_path: str):
        """写入前自动调用"""
        source = self._resolve(agent_id, file_path)
        if not source.exists():
            return  # 新文件无需备份

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = (
            self.BACKUP_ROOT
            / agent_id
            / file_path.replace("/", "_")
            / f"{source.name}.{ts}.bak"
        )
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup_path)
        self.index.record_backup(agent_id, file_path, backup_path)

    def list_history(self, agent_id: str, file_path: str) -> list[BackupEntry]:
        """列出某文件的所有备份"""
        return self.index.query_backups(agent_id, file_path)

    def rollback(self, agent_id: str, file_path: str, backup_id: str):
        """回滚：先备份当前，再写入历史"""
        # 1. 备份当前
        self.backup(agent_id, file_path)
        # 2. 拿到历史内容
        content = self._read_backup(backup_id)
        # 3. 写入（这次不触发自动备份，因为已经手动备份过）
        self.file_manager.write(agent_id, file_path, content, auto_backup=False)
```

### 3.4 SearchService

**优先用 ripgrep（毫秒级），fallback 到 Python `grep` 库**。

```python
class SearchService:
    def search(
        self,
        query: str,
        *,
        agent_ids: list[str] | None = None,
        file_patterns: list[str] | None = None,
        regex: bool = False,
        case_sensitive: bool = True,
        context_lines: int = 3,
    ) -> list[SearchHit]:
        if shutil.which("rg"):
            return self._search_ripgrep(query, agent_ids, file_patterns, regex, case_sensitive, context_lines)
        return self._search_python(query, agent_ids, file_patterns, regex, case_sensitive, context_lines)

    def _search_ripgrep(self, ...) -> list[SearchHit]:
        cmd = [
            "rg",
            "--json",
            "--type", "md",
            "--context", str(context_lines),
        ]
        if not case_sensitive:
            cmd.append("--ignore-case")
        if agent_ids:
            for aid in agent_ids:
                agent = self.agent_discovery.get(aid)
                cmd.extend(["--glob", f"!{agent.workspace}/**"])
                # 只在指定 workspace 搜
        # ... 拼接 + 执行 + 解析 JSON 输出
```

### 3.5 LintService

**8 条规则，每条规则一个独立类**：

```python
class LintService:
    RULES = [
        L4TimestampRule(),
        L4VersionRule(),
        L4NarrativeRule(),
        BoundaryViolateRule(),
        CoreMissingRule(),
        CrossAgentDriftRule(),
        EmptyFileRule(),
        LargeFileRule(),
    ]

    def lint_file(self, agent_id: str, file_path: str, content: str) -> list[LintWarning]:
        warnings = []
        for rule in self.RULES:
            warnings.extend(rule.check(agent_id, file_path, content))
        return warnings

    def lint_agent(self, agent_id: str) -> list[LintWarning]:
        files = self.file_manager.list(agent_id)
        warnings = []
        for f in files:
            content = self.file_manager.read(agent_id, f.path).content
            warnings.extend(self.lint_file(agent_id, f.path, content))
        return warnings
```

**LintWarning 结构**：

```python
@dataclass
class LintWarning:
    rule_id: str              # "L4-TIMESTAMP"
    rule_name: str            # "L4 反模式 — 时间戳"
    severity: str             # "warning" | "error"
    agent_id: str
    file_path: str
    line_number: int | None
    line_content: str | None
    suggestion: str           # "删除这一行..."
```

### 3.6 SyncService（最关键，最危险）

**铁律：跨 Agent 同步必须 plan + confirm 两步**。

```python
class SyncService:
    def plan(
        self,
        src_agent: str,
        dst_agent: str,
        files: list[str],
    ) -> SyncPlan:
        """对比 src 和 dst 的指定文件，返回 diff plan"""
        plan = SyncPlan(src=src_agent, dst=dst_agent, files=[])
        for f in files:
            src_content = self.file_manager.read(src_agent, f).content
            dst_content = self.file_manager.read(dst_agent, f).content
            plan.files.append(SyncFilePlan(
                path=f,
                src_content=src_content,
                dst_content=dst_content,
                diff=generate_html_diff(src_content, dst_content),
                similarity=compute_similarity(src_content, dst_content),
            ))
        return plan

    def execute(self, plan: SyncPlan, *, auto_backup: bool = True):
        """执行 plan（前端已确认）"""
        results = []
        for f in plan.files:
            # 先备份 dst
            if auto_backup:
                self.backup_service.backup(plan.dst, f.path)
            # 写入 src 内容到 dst
            self.file_manager.write(plan.dst, f.path, f.src_content, auto_backup=False)
            results.append({"file": f.path, "status": "ok"})
        return results
```

**绝不允许的功能**：
- ❌ 整 workspace cp（`shutil.copytree`）
- ❌ 没有 plan 直接写

### 3.7 ImportExport（导出）

```python
class ImportExportService:
    def export_agent(self, agent_id: str) -> Path:
        """导出单个 Agent 的 Prompt Pack 为 .tar.gz"""
        agent = self.discovery.require(agent_id)
        tmp_dir = Path(tempfile.mkdtemp())

        # 拷贝全部 .md 文件到临时目录
        for f in self.file_manager.list(agent_id):
            src = Path(agent.workspace) / f.path
            dst = tmp_dir / f.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        # 生成 manifest（SHA-256 校验信息）
        manifest = Manifest(
            soulforge_version=__version__,   # 唯一事实源：backend/app/__init__.py
            export_time=datetime.now().isoformat(),
            agent_id=agent_id,
            files=[
                ManifestFile(path=f.path, size=f.size_bytes,
                             sha256=sha256_of(Path(agent.workspace) / f.path))
                for f in self.file_manager.list(agent_id)
            ],
        )
        (tmp_dir / "MANIFEST.json").write_text(
            json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8",
        )

        # 打包
        output = Path(tempfile.mkdtemp()) / f"soulforge-{agent_id}-{datetime.now():%Y%m%d-%H%M%S}.tar.gz"
        shutil.make_archive(str(output).removesuffix(".tar.gz"), "gztar", tmp_dir)
        return output

    def export_all(self) -> Path:
        """导出全部 Agent：每个 Agent 一个子目录 + 根 manifest"""
```

> 导入功能已移除；类名 `ImportExportService` 为历史命名保留。

---

## 三点八、Phase 2.5 新增模块设计

> 与三、节并列，为 Phase 2.5 AI Editor 引入。

### 3.8 PresetService（M11 · 文档预设系统）

```python
class PresetService:
    """管理文档预设的 CRUD + 应用"""

    def list(self, target_file_type: str | None = None,
             scope: str = "all") -> list[Preset]:
        """列出预设（已退役的内置预设不返回）
        scope=workbench → 排除「专供大模型处理工作日志」的 WORKLOG 类预设
        （设置页「文档预设」与主工作台「应用预设 / AI 整理」用它）"""

    def get(self, preset_id: str) -> Preset: ...

    def create(self, payload: PresetCreate) -> Preset:
        """创建用户预设，is_system=False"""

    def update(self, preset_id: str, payload: PresetUpdate) -> Preset:
        """更新预设（所有预设均可改全部字段——内置预设播种即 is_system=0）
        版本号 version 自增 +1，并写版本快照"""

    def delete(self, preset_id: str) -> None:
        """删除预设（内置预设也可删；删后重启不会重建）"""

    def apply_plan(
        self,
        preset_id: str,
        agent_id: str,
        file_path: str,
        extra_instructions: str | None = None,
    ) -> PresetApplyPlan:
        """生成应用 plan（不写入文件）"""
        # 1) 读取原文件 → current_content
        # 2) 加载预设 sections_json + style_rules
        # 3) 按预设结构补齐缺失章节（不动原内容）
        # 4) 生成 unified diff → diff_plan.unified_diff
        # 5) 跑 lint → diff_plan.lint_warnings
        # 返回 PresetApplyPlan（不入库）

    def apply_execute(self, plan_id: str, agent_id: str, file_path: str) -> ApplyResult:
        """执行应用：备份 → 写入 → 审计"""
```

**关键设计**：
- 预设与应用计划**解耦**：`apply_plan` 只读不写，生成纯计算结果
- `apply_execute` 是唯一会写文件的入口，复用 `BackupService` 链路
- 预设版本化：每次 `update` 自增 `version`，并写版本快照（可查看历史与回溯）
- **两类预设的边界**（2026-09-24 收口）：`target_file_type = WORKLOG` 即「专供大模型处理工作日志」
  （常量 `DAILY_PRESET_TYPE`），只在「业务工具 → 日志标准化」界面可见可编辑；
  其余类型供主工作台加载。两侧过滤都在后端：`SCOPE_WORKBENCH` 排除 WORKLOG 类
- `is_builtin`（是否随版本分发的内置预设）用于 UI 展示「预设来源」；
  历史字段 `is_system` 恒为 `false`（内置预设与用户预设同等可编辑、可删除）

---

### 3.9 LLMRegistry + LLMClient（M12 · LLM Provider 接入）

```python
class LLMRegistry:
    """管理 llm_providers 注册表，支持热加载"""

    _providers: dict[str, LLMProvider]
    _lock: asyncio.Lock

    async def load_from_db(self) -> None:
        """启动时从 llm_providers 表加载"""

    async def reload_one(self, provider_id: str) -> None:
        """热加载单个 provider（PUT/POST/DELETE 后调用）"""

    def get(self, provider_id: str) -> LLMProvider: ...

    async def reload_all(self) -> None:
        """热加载全部（配置中心手动触发）"""


class LLMClient:
    """LLM 调用客户端，支持多协议"""

    def __init__(self, provider: LLMProvider): ...

    async def chat(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """根据 provider.protocol 调用对应适配器"""
        if self.provider.protocol == "openai-completions":
            return await self._openai_completions(messages, ...)
        elif self.provider.protocol == "anthropic-messages":
            return await self._anthropic_messages(messages, ...)
        else:
            raise UnsupportedProtocolError(...)


class LLMResponse:
    content: str
    usage: TokenUsage       # prompt / completion / total
    cost_estimate_usd: float
```

**密钥解密**：

```python
class KeyVault:
    """API key 加解密"""

    def __init__(self):
        # 读取 SOULFORGE_SECRET 环境变量
        # 缺失则读 .soulforge/secrets/key
        # 都没有则首次启动生成（权限 600）
        self._fernet = Fernet(self._load_or_create_key())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
```

**热加载机制**：

```
[Soulforge 启动]
  ↓
LLMRegistry.load_from_db()  → 初始化内存表
  ↓
[PUT /api/llm/providers/{id}]
  ↓
PresetService.update()  → 写 DB
  ↓
LLMRegistry.reload_one()  → 内存更新（不重启）
```

---

### 3.10 AIJobService（M13 · AI 自动整理）

```python
class AIJobService:
    """管理 AI 整理任务的生命周期"""

    async def create(
        self,
        agent_id: str,
        file_path: str,
        preset_id: str,
        provider_id: str,
        extra_instructions: str | None,
    ) -> AIJob:
        """创建任务，status=pending，提交到后台队列"""

    async def execute(self, job_id: str) -> None:
        """后台异步执行：
        1. job.status = running
        2. 读取原文件 → input_snapshot
        3. 加载预设 → 构造 prompt
        4. 调 LLMClient.chat() → output_content
        5. 计算 unified diff + lint
        6. job.status = awaiting_confirm
        异常 → job.status = failed + error
        """

    async def apply(self, job_id: str) -> ApplyResult:
        """老板点应用：
        1. 校验 status == awaiting_confirm
        2. 跑 lint，不通过 → status=failed + 报错
        3. 备份原文件（复用 BackupService）
        4. 写入新内容
        5. job.status = applied
        6. 写审计日志（action='ai_apply'）
        """

    async def reject(self, job_id: str) -> None:
        """老板点拒绝：status=rejected"""

    async def regenerate(
        self,
        job_id: str,
        extra_instructions: str,
    ) -> AIJob:
        """老板点重新生成：
        旧 job.superseded_by = 新 job.id
        新 job.status = pending
        提交到后台队列
        """
```

**异步队列选型**：

```
当前：asyncio.create_task()   ──── 单进程够用
将来：ARQ / Celery / RQ      ──── 多 worker 时换（Phase 3 再评估）
```

当前 MVP 阶段用 `asyncio.create_task()`，单进程足够。

**Prompt 构造**（见 DEVELOPMENT.md M13 节）。

---

### 3.11 超级同步（Super Sync · 独立守护脚本）

**目标**：多个 Agent 之间对「同名文件」做**秒级双向同步**，且**脱离主进程**持续运行。

```
┌──────────────────────────────┐        ┌────────────────────────────────────┐
│  Soulforge Server (FastAPI)  │        │  super_sync.py（独立进程，可脱离）  │
│  /api/super-sync/*           │        │  轮询 → 比较同名文件 → 最新覆盖其余  │
│  ├─ SuperSyncService         │ 分离    │  写入 status.json（心跳）           │
│  │   start(): Popen(detach)  │ 进程    │  追加 logs/*.jsonl（按天滚动）      │
│  │   stop(): taskkill/SIGTERM│ ─────▶  └────────────────────────────────────┘
│  │   status(): pid+心跳判定  │                     ▲
│  └─ 读 config.json 供 UI     │                     │ 同一份 config.json / status.json
└──────────────────────────────┘                     │（UI 与命令行两种启动方式等价）
```

**模块划分**：

| 文件 | 职责 |
|---|---|
| `app/services/super_sync_common.py` | 路径 / 配置 / 状态 / 日志的落盘协议；跨平台进程存活检测 |
| `app/services/super_sync_engine.py` | 同步引擎：扫描 + 冲突裁决 + 原子写入 + diff 记录 |
| `backend/super_sync.py` | 独立守护脚本（CLI 入口；心跳、日志、信号、单实例互斥） |
| `app/services/super_sync_service.py` | 后端管理面：启停 / 状态 / 日志查询导出 |
| `app/api/super_sync.py` | 路由 `/api/super-sync/*` |

**冲突策略**：最新修改优先（双向）——同一相对路径在各参与 Agent 间内容不一致时，
取 `mtime` 最新者为源覆盖其余；并列时按 Agent id 升序择源，保证确定性。
内容一致则跳过（天然避免回声循环）。

**同步范围**：仅 `SOUL.md` / `AGENTS.md` / `USER.md` / `MEMORY.md` / `IDENTITY.md`
这 5 个核心文档可纳入同步（`SYNC_FILENAMES` 白名单，配置层强制过滤，其余路径一律丢弃）。
`config.json` 显式声明参与 Agent 及每个 Agent 的文件清单；未选中的 Agent / 文件绝不触碰。
文件缺失于某 Agent 时不凭空创建（仅同步「同名且已存在」的文件）。
UI 以「矩阵」呈现：行 = Agent、列 = 文档、交叉打勾；全选/清空按**文档列**操作
（对同一文档一次勾选所有拥有它的 Agent）。

**安全性 / 稳定性**：

- 写目标走「临时文件 + `os.replace`」原子替换，杜绝读到半截内容；
- 以 `(mtime, size)` 缓存 `sha256`，未变更文件不重复读取，降低轮询开销；
- 跳过隐藏目录 / `node_modules` / 敏感文件（`.credentials.md`、`.env`）；
- 相对路径经规范化并拒绝越界；引擎吞掉单轮异常，守护循环不因单点失败退出。

**状态可视化**：脚本每轮写 `status.json`（含 `pid` + `last_heartbeat`）；
后端据此判定 `running`（进程在 + 心跳新鲜）/ `error`（进程在 + 心跳超时）/ `stopped`；
UI 每 2.5s 轮询一次（满足 ≤ 3s 延迟）并支持手动刷新。

**日志**：JSON Lines 结构化记录（时间 / 级别 / 事件 / 文件 / 源→目标 / 结果 / 变更 diff / 异常），
按天滚动且留存 ≥ 30 天，UI 可按级别与时间范围检索、下载导出。

---

### 3.12 DailySourceScanner + DailyPreprocessor + DailyMergeService + DailyRunService（M15 · 工作日志标准化）

> 目标：把某 Agent `memory/` 下一天的**多份**记录归并成**恰好 1 个** `YYYY-MM-DD.md`，
> 剥掉元数据壳与对话腔、清理碎片。完整方案见
> [MEMORY-DAILY-STANDARDIZER-PLAN.md](MEMORY-DAILY-STANDARDIZER-PLAN.md)。

**四个服务（单日归并 → 批次编排）**：

| 服务 | 文件 | 职责 |
|---|---|---|
| `DailySourceScanner` | `app/services/daily_source_scanner.py` | 只扫 `memory/` **顶层**，按文件名分 A（`YYYY-MM-DD.md`，系统自动生成的日文件）/ B（`YYYY-MM-DD-HHMM.md`，含 `-HHMM-2`）/ C（`YYYY-MM-DD-<topic>.md`）三类，按日分组、排出碎片、标出「单来源但质量差」 |
| （预处理器） | `app/services/daily_preprocessor.py` | 12 条**确定性**规则（零 token）：真壳 M01~M10（会话键 / untrusted metadata / 引用壳 / 排队消息 / dreaming 统计壳 / 纯 `HEARTBEAT_OK` / 过程过渡语）+ 归一 M11/M12（BOM·换行·空白）。`SHELL_RULES` / `detect_residual_shells()` 只查真壳（归一不算残留） |
| `DailyMergeService` | `app/services/daily_merge_service.py` | 单日多来源 → 1 文件：组装 prompt（模板规则 + `style_rules` + 骨架 + 带优先级来源）→ LLM → `sanitize()` → `FormatValidator` 强规则校验/机械修正；只出 `DailyMergePlan`，**不写盘、不删碎片** |
| `DailyRunService` | `app/services/daily_run_service.py` | 批次编排：创建（幂等键 / 天数与 token 上限 / 后台逐日生成）→ 确认执行（批次级写前预检 + 乐观锁 → 写入 + 备份 + 审计 → 碎片 `send2trash`）→ 验收报告（对磁盘真实文件核对 5 项） |

**规则分层（强 / 弱）**：

- **强规则**（机械可判定，不过就拦）：`preset.template_md` 的 YAML frontmatter → `TemplateRules`
  （必填章节 / 顺序 / 禁止 emoji / 禁止原始 HTML …）→ `FormatValidator.validate_and_fix()`；
  写前验收还要求真壳残留 = 0（`detect_residual_shells()`）
- **弱规则**（语义，交给模型）：`preset.style_rules` + 模板正文，注入 prompt；
  形态默认 `system_embedded`（规则全文进 system prompt，P3 实测最优）

**关键设计**：

- **零污染写入**：`apply()` 是唯一写盘入口且只接受 `awaiting_confirm`；先对全部目标日做批次级预检
  （SHA-256 乐观锁 + 写前验收），**任一日不过就整批不写**；碎片删除走 `send2trash` 可恢复
- **「本日无可归档内容」出口**：模型可只回一行哨兵（`无可归档内容：<理由>`），命中则该日不产出日文件
  （逐日状态 `empty` + `empty_reason`），只清 B/C 碎片、A 类主文件保持不动；识别从严
  （`parse_empty_verdict()`：>3 行 / 含结构 / 首行非哨兵 → 当普通输出）
- **失败归因如实**：`LLMClient.chat()` 读 `finish_reason`（Anthropic 为 `stop_reason`），
  输出被 `max_tokens` 截断 → 自动以翻倍预算重试一次，仍截断则抛 `LLMOutputTruncatedError`
  （`422` / `LLM_OUTPUT_TRUNCATED`），不报成「强规则未通过」
- **状态机**：批次 `planned → awaiting_confirm → applied / partially_applied / needs_review /
  rejected / failed / empty`；逐日 `pending / planned / blocked / applied / partially_applied /
  skipped / empty / failed`（见 [DATA-MODEL.md](DATA-MODEL.md) 2.9）
- **与 M13 隔离**：不复用 `ai_jobs`（保持单文件语义），批次独立两表 `daily_runs` / `daily_run_items`

**规则载体（预设）**：`preset-wlog-daily-std`「工作日志日标准化」（`target_file_type=WORKLOG`），
属于「大模型专用」预设——只在日志标准化界面可见可编辑（预设信息栏 + 页内编辑器，
可改用途说明 / 模板文档 / `style_rules`），文档预设页与主工作台按 `scope=workbench` 排除（见 3.8）。

**API**：`/api/daily-runs` 6 个端点（创建 / 列表 / 详情 / 应用 / 拒绝 / 跳过 / 报告，见 [API.md](API.md) 3.15）；
错误码 `DAILY_RUN_NOT_FOUND`（404）/ `DAILY_RUN_STATUS`（409）/ `DAILY_RUN_DISABLED`（403）/
`DAILY_SOURCE_TOO_LARGE`（422）/ `LLM_OUTPUT_TRUNCATED`（422）。

---

## 四、错误处理

### 4.1 后端

```python
class SoulforgeError(Exception):
    """基类"""
    http_status: int = 500
    code: str = "INTERNAL_ERROR"

class AgentNotFoundError(SoulforgeError):
    http_status = 404
    code = "AGENT_NOT_FOUND"

class FileNotFoundError(SoulforgeError):
    http_status = 404
    code = "FILE_NOT_FOUND"

class UnsafePathError(SoulforgeError):
    """路径穿越检测"""
    http_status = 403
    code = "UNSAFE_PATH"

class BackupFailedError(SoulforgeError):
    http_status = 500
    code = "BACKUP_FAILED"

# 全局异常处理
@app.exception_handler(SoulforgeError)
async def handle_soulforge_error(request, exc):
    return JSONResponse(
        status_code=exc.http_status,
        content={"error": {"code": exc.code, "message": str(exc)}},
    )
```

### 4.2 前端

- 用自研 `components/ErrorBoundary.tsx` 包裹关键区域
- API 错误统一由 `api/client.ts` 抛出 `ApiError {code, message, details}`，调用处用 Toast 提示
- 关键操作失败 → Toast 显示错误信息（不引入状态管理 / 请求缓存库）

---

## 五、性能与扩展

| 场景 | 性能要求 | 实现 |
|---|---|---|
| 启动时间 | < 3s | 启动时只加载 Agent 列表，文件懒加载 |
| 文件读取 | < 100ms | 直接文件 IO |
| 搜索 100 文件 | < 500ms | ripgrep |
| Diff 1000 行 | < 200ms | python-diff |
| 备份 1 文件 | < 50ms | shutil.copy2 |

**目标规模**：≤ 20 个 Agent × ≤ 500 文件 / Agent × ≤ 50KB / 文件。

超出规模走性能优化路线（暂不在 MVP 范围）。

---

## 六、技术债与未来扩展

- **配置中心化**：lint 规则、备份保留策略走 `<data_dir>/config.toml`（默认 `<项目根>/.soulforge/config.toml`），不硬编码
- **插件机制**：让 lint 规则、文档预设可由第三方贡献（Phase 3 考虑）
- **WebSocket**：实时同步多端（暂不需要，超级同步已用独立进程 + 轮询覆盖）
- **AI 自动修复 lint 违规**：当前 AI 整理仅按预设重排全文，尚未做行级定向修复