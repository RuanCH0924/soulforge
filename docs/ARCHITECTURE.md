# Soulforge — 系统架构详解

> 配套主文档 [DEVELOPMENT.md](../DEVELOPMENT.md) 的架构章节。

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
│  │  ├── /agents       Agent 管理路由                    │    │
│  │  ├── /files        文件路由                         │    │
│  │  ├── /search       搜索路由                          │    │
│  │  ├── /diff         diff 路由                         │    │
│  │  ├── /sync         跨 Agent 同步路由                 │    │
│  │  ├── /export       导出路由                          │    │
│  │  ├── /import       导入路由                          │    │
│  │  ├── /backups      备份路由                          │    │
│  │  ├── /lint         lint 路由                         │    │
│  │  ├── /templates    模板路由                          │    │
│  │  └── /stats        统计路由                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Service 层                                          │    │
│  │  ├── AgentDiscovery     读 openclaw.json → Agent 列表│   │
│  │  ├── FileManager        读 / 写 / 删除文件            │    │
│  │  ├── BackupService      自动备份 / 历史 / 回滚        │    │
│  │  ├── SearchService      ripgrep 包装                  │    │
│  │  ├── LintService        8 条规则执行                  │    │
│  │  ├── DiffService        unified diff → HTML          │    │
│  │  ├── SyncService        跨 Agent 选择性合并           │    │
│  │  ├── ImportExport       tar.gz 打包 / 解压 / manifest │    │
│  │  └── TemplateService    内置模板                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Storage 层                                          │    │
│  │  ├── SQLite (~/.soulforge/index.db)                  │    │
│  │  │     └── agents / files / backups / audit_log       │    │
│  │  └── 文件系统 (OpenClaw workspace / ~/.soulforge/)   │    │
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

app = FastAPI(title="Soulforge", version="0.1.0")

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
    BACKUP_ROOT = Path("~/.soulforge/backups").expanduser()
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

### 3.7 ImportExport

```python
class ImportExport:
    def export(self, agent_id: str) -> Path:
        """导出 Prompt Pack 为 .tar.gz"""
        agent = self.agent_discovery.get(agent_id)
        tmp_dir = Path(tempfile.mkdtemp())

        # 拷贝全部 .md 文件到临时目录
        for f in self.file_manager.list(agent_id):
            src = agent.workspace / f.path
            dst = tmp_dir / f.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        # 生成 manifest
        manifest = {
            "soulforge_version": "0.1.0",
            "export_time": datetime.now().isoformat(),
            "agent_id": agent_id,
            "files": [
                {"path": f.path, "size": f.size, "sha256": hashlib.sha256(...).hexdigest()}
                for f in self.file_manager.list(agent_id)
            ],
        }
        (tmp_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))

        # 打包
        output = Path(tempfile.mkdtemp()) / f"soulforge-{agent_id}-{datetime.now():%Y%m%d-%H%M%S}.tar.gz"
        shutil.make_archive(str(output).replace(".tar.gz", ""), "gztar", tmp_dir)
        return output

    def import_pack(self, tarball: Path, target_agent_id: str, *, conflicts: dict[str, str]) -> ImportResult:
        """导入 tar.gz 到指定 Agent

        conflicts: {"file_path": "skip" | "merge" | "overwrite"}
        """
        # 1. 解压到临时目录
        extract_dir = Path(tempfile.mkdtemp())
        with tarfile.open(tarball, "r:gz") as tf:
            tf.extractall(extract_dir)

        # 2. 读 manifest
        manifest = json.loads((extract_dir / "MANIFEST.json").read_text())

        # 3. 逐文件处理（按 conflicts 策略）
        results = []
        for file_info in manifest["files"]:
            path = file_info["path"]
            src = extract_dir / path
            target_agent = self.agent_discovery.get(target_agent_id)

            target_file = target_agent.workspace / path
            exists = target_file.exists()

            if exists and path not in conflicts:
                strategy = "skip"  # 默认跳过冲突
            else:
                strategy = conflicts.get(path, "skip")

            if strategy == "skip":
                continue
            elif strategy == "overwrite":
                self.file_manager.write(target_agent_id, path, src.read_text())
                results.append({"file": path, "action": "overwritten"})
            elif strategy == "merge":
                # 简单行级合并（不全可靠，留 TODO）
                merged = self._merge_files(target_file, src)
                self.file_manager.write(target_agent_id, path, merged)
                results.append({"file": path, "action": "merged"})

        return ImportResult(manifest=manifest, results=results)
```

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

- 用 `react-error-boundary` 包裹关键区域
- API 错误用 TanStack Query 自动重试 + 错误提示
- 关键操作失败 → Toast 显示错误信息 + 「重试」按钮

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

- **配置中心化**：lint 规则、备份保留策略走 `~/.soulforge/config.toml`，不硬编码
- **插件机制**：让 lint 规则、模板可由第三方贡献（v2.0+ 考虑）
- **WebSocket**：实时同步多端（暂不需要）
- **审计日志界面**：前端展示 audit_log 表（v1.0）