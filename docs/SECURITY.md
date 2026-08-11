# Soulforge — 安全护栏

> 配套主文档 [DEVELOPMENT.md](../DEVELOPMENT.md) 的安全章节。
> 设计原则：呼应老板「高危操作分级管控」+「核心文件保护」规则。

---

## 一、威胁模型

### 1.1 攻击面

| 面 | 风险 | 缓解 |
|---|---|---|
| **Web 端暴露** | 任何能访问 `127.0.0.1:8848` 的人都可改文件 | **强制监听 `127.0.0.1`**，绝不暴露公网 |
| **路径穿越** | `../../etc/passwd` | `_safe_join()` 强制校验 |
| **误删 workspace** | 误操作整目录删除 | 删除走 `trash` 命令，不走 `rm` |
| **跨 Agent 整文件覆盖** | cp 把 main 的 SOUL.md 覆盖了 xiaoxi-lawyer 的 | **禁止**，必须走 plan + confirm + 选择性合并 |
| **备份丢失** | 备份和源文件在同一分区，磁盘挂了全没了 | 文档明确提示：用户应额外把重要 Agent 导出到 GitHub |
| **lint 误判** | 自动修复把合法内容改了 | **lint 不自动修改**，只警告 |

### 1.2 非目标（v0.x 不做）

- 多人协作（假设只有老板一个用户）
- 云端同步（不连任何外部服务）
- 账号系统 / 鉴权（单人本地工具）
- 加密存储（老板不加密工作流）

---

## 二、操作分级

| 级别 | 操作 | 验证机制 |
|---|---|---|
| **🟢 低** | 浏览 / 搜索 / diff / lint / stats | 直接执行 |
| **🟡 中** | 编辑单文件保存 | 自动备份 + Toast 提示 |
| **🟠 高** | 跨 Agent 编辑 / 同步 / 导入 | Dialog 确认 + 显示影响范围 + 自动备份 |
| **🔴 极高** | 整 workspace 删除 / 批量删除备份 / 修改 openclaw.json | 老板本人私聊确认 + 输入"确认删除" |

---

## 三、路径安全（铁律）

```python
def _safe_join(workspace_root: Path, user_path: str) -> Path:
    """任何用户输入的路径都必须过这一道"""
    # 1. 拒绝绝对路径
    if Path(user_path).is_absolute():
        raise UnsafePathError(f"绝对路径禁止：{user_path}")

    # 2. 拒绝路径穿越
    parts = Path(user_path).parts
    if ".." in parts:
        raise UnsafePathError(f"相对路径穿越禁止：{user_path}")

    # 3. 解析后必须在 workspace 根下
    resolved = (workspace_root / user_path).resolve()
    if not str(resolved).startswith(str(workspace_root.resolve()) + os.sep):
        raise UnsafePathError(f"路径越界：{user_path}")

    return resolved
```

**FastAPI 依赖注入**：

```python
def safe_path(workspace_root: Path = Depends(get_workspace_root), path: str = Path(...)):
    return _safe_join(workspace_root, path)
```

所有读 / 写 / 备份路由都注入 `safe_path`。

---

## 四、备份安全

### 4.1 备份创建时机

**每一次写入都自动备份**（哪怕是 1 字节修改）：

```python
def write(self, agent_id: str, path: str, content: str):
    # 1. 自动备份（如果文件已存在）
    if self._exists(agent_id, path):
        self.backup_service.backup(agent_id, path, reason="auto-write")

    # 2. 写入
    self._do_write(agent_id, path, content)

    # 3. 审计
    self.audit_log.record("write", agent_id, path, len(content))
```

### 4.2 备份目录隔离

```
~/.soulforge/backups/    ←  Soulforge 自己管
~/.openclaw/workspace/   ←  源文件
```

**绝不混用**。Soulforge 不会写任何文件到 workspace 之外（除了自己管理的 `~/.soulforge/`）。

### 4.3 备份保留策略

```python
RETENTION_DAYS = 30  # 可在 config.toml 改

def cleanup_old_backups(self):
    """启动时 + 每小时跑一次"""
    cutoff = datetime.now() - timedelta(days=self.RETENTION_DAYS)
    # 同时删物理文件和数据库记录
```

### 4.4 回滚的安全语义**

```python
def rollback(self, agent_id: str, file_path: str, backup_id: int):
    """回滚前先把当前状态备份一次（防止回滚丢数据）"""
    # 1. 备份当前状态
    current_backup_id = self.backup(agent_id, file_path, reason="pre-rollback")

    # 2. 读取历史备份
    backup_content = self._read_backup(backup_id)

    # 3. 写入历史内容（不再触发自动备份，因为已经手动备份过）
    self._do_write(agent_id, file_path, backup_content)

    # 4. 审计
    self.audit_log.record(
        "rollback", agent_id, file_path,
        details={"from_backup": current_backup_id, "to_backup": backup_id}
    )
```

---

## 五、跨 Agent 同步安全（最严）

### 5.1 铁律

**绝对禁止**：

- ❌ 整文件 `cp`（`shutil.copy`）
- ❌ 整 workspace `cp -r`
- ❌ 没有 diff plan 直接写
- ❌ 一键同步全部文件（必须用户明确勾选每个文件）

### 5.2 两步强制

```python
# Step 1: Plan（不写入，只算 diff）
POST /api/sync/plan
→ 返回 plan_id + 每个文件的 diff HTML

# Step 2: Execute（必须传 plan_id + 用户确认的文件列表）
POST /api/sync/execute
{ "plan_id": "...", "files": ["SOUL.md"] }
```

**plan 必须 ≤ 30 分钟有效**，过期强制重新 plan。

### 5.3 前端 UI 强制

跨 Agent 同步按钮点击后：

1. 弹出 Diff Plan Modal
2. 每个文件显示**完整 HTML diff**（左源右目标）
3. 用户必须**逐文件勾选**要同步的文件
4. 默认**全部取消勾选**（强迫用户主动选）
5. 点击「执行同步」按钮 + 输入目标 Agent ID 后 4 位确认

---

## 六、导入导出安全

### 6.1 tar 安全

```python
def safe_extract(tar: tarfile.TarFile, path: Path):
    """拒绝路径穿越 tar bomb"""
    for member in tar.getmembers():
        member_path = (path / member.name).resolve()
        if not str(member_path).startswith(str(path.resolve()) + os.sep):
            raise UnsafePathError(f"tar 含路径穿越：{member.name}")
    tar.extractall(path)
```

### 6.2 导入冲突策略

**绝不默认覆盖**：

```python
CONFLICT_STRATEGIES = ["skip", "merge", "overwrite"]

# 前端 UI：每个冲突文件默认 skip，用户主动改
```

### 6.3 Manifest 校验

```python
def verify_manifest(extract_dir: Path) -> dict:
    manifest_path = extract_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())

    # 校验文件 sha256 跟实际一致（防篡改）
    for file_info in manifest["files"]:
        actual_hash = hashlib.sha256(
            (extract_dir / file_info["path"]).read_bytes()
        ).hexdigest()
        if actual_hash != file_info["sha256"]:
            raise ManifestCorruptedError(f"sha256 不匹配：{file_info['path']}")

    return manifest
```

---

## 七、审计日志

**所有写操作记录**，包括：

- 时间（精确到秒）
- 操作类型（write / rollback / import / sync / delete 等）
- Agent ID
- 目标文件
- 详细信息（diff 大小、备份 ID 等）
- 结果（ok / failed）

**保留期**：永久（除非老板手动清理）

**前端可查**：v1.0+ 暴露 `/api/audit` 接口 + UI 页面

---

## 八、销毁 / 重装安全

老板想卸载 Soulforge：

```bash
# 一键清理（保留备份和元数据）
soulforge uninstall --keep-data

# 彻底清理（包括备份和元数据）
soulforge uninstall --purge
```

**绝不自动**清任何东西，所有清理都走显式命令 + Dialog 确认。

---

## 九、核心文件保护

Soulforge 接触的所有文件都在 workspace 内，但有特殊保护层：

### 9.1 SOUL.md / AGENTS.md / USER.md / MEMORY.md

- 写入前 lint 检查
- 严格模式下违规阻止保存
- 默认自动备份

### 9.2 openclaw.json

- **不进入 Soulforge 默认管理范围**（role = META，默认隐藏）
- 如需编辑，需在「高级设置」里开启 `show_meta = true`
- 编辑前显示大字提示「修改 openclaw.json 可能导致 Gateway 不可用」

### 9.3 .credentials.md

- **永不进入 Soulforge 管理范围**
- 文件扫描时跳过 `.credentials.md`、`.env` 等敏感文件
- 永远不进备份列表
- 永远不索引、不 lint

---

## 十、网络安全

### 10.1 监听配置

```python
# main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="127.0.0.1",   # 强制只监听本地
        port=8848,
        log_level="info",
    )
```

**永远不开 `0.0.0.0`**。

### 10.2 CORS

```python
# 只允许本地
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8848", "http://127.0.0.1:8848"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 10.3 不调外部网络

Soulforge Server 启动时不发任何外部请求：

- ❌ 不发遥测
- ❌ 不检查更新（v1.0+ 手动 `soulforge update` 命令）
- ❌ 不连任何 SaaS

---

## 十一、给 AI 编程助手的指令

**生成代码时必须遵守**：

1. **任何文件路径参数都过 `_safe_join()`**
2. **任何写操作都先调用 `backup_service.backup()`**
3. **任何写操作都调用 `audit_log.record()`**
4. **跨 Agent 操作必须两步（plan + execute）**
5. **删除操作走 `send2trash` 库，不用 `os.remove`**
6. **不引入 `subprocess` 调 shell 改文件**（用 Python 标准库）
7. **CORS 仅允许本地**
8. **监听仅 `127.0.0.1`**

**测试要求**：

- `_safe_join` 必须有完整单测（含路径穿越用例）
- 备份流程必须有集成测试
- 跨 Agent 同步必须有 plan-execute 两步测试
- tar 解压必须有 tar bomb 测试