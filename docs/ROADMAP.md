# Soulforge — 落地路径

> 配套主文档 [DEVELOPMENT.md](../DEVELOPMENT.md) 的落地路径章节。

---

## 一、版本规划

| 版本 | 范围 | 周期 | 状态 |
|---|---|---|---|
| **v0.1 MVP** | 浏览 + 编辑 + 备份 + lint | 2 周 | 待开发 |
| **v0.2** | 搜索 + diff | 1 周 | 待开发 |
| **v0.3** | 跨 Agent 同步 + 导入导出 | 1 周 | 待开发 |
| **v1.0** | 模板 + 统计 + 审计日志 UI | 1 周 | 待开发 |
| **v1.x** | 性能优化 / WebSocket / 第三方插件 | 按需 | 远期 |

---

## 二、MVP (v0.1) 详细拆解

### 2.1 目标

> **能浏览 + 编辑 + 自动备份 + lint 的最小可用版本**
> 老板可以立即开始管理 6 个 Agent 的灵魂文件，不再手动 cp。

### 2.2 功能范围

| 模块 | MVP 是否做 | 备注 |
|---|---|---|
| M1 Agent 管理 | ✅ | 必须 |
| M2 文件浏览 / 编辑 | ✅ | 必须，Monaco 编辑器 |
| M7 备份 / 回滚 | ✅ | 必须 |
| M8 Lint | ✅ | 必须，8 条规则 |
| M3 搜索 | ❌ | v0.2 |
| M4 Diff | ❌ | v0.2 |
| M5 同步 | ❌ | v0.3 |
| M6 导入导出 | ❌ | v0.3 |
| M9 模板 | ❌ | v1.0 |
| M10 统计 | ❌ | v1.0 |

### 2.3 MVP 技术清单

**后端**：
- FastAPI 单进程
- SQLite（4 张表）
- ripgrep Python wrapper（v0.2）
- 文件 IO（pathlib）
- 8 条 lint 规则

**前端**：
- React + TypeScript + Vite
- shadcn/ui（Button / Dialog / Toast / Input）
- Monaco Editor（markdown 模式）
- 三栏布局
- 主题切换（浅色 / 深色）

**工具**：
- uvicorn（启动）
- loguru（日志）
- pytest（测试）
- ruff / black（格式）

### 2.4 MVP 工作分解

#### Week 1：后端骨架 + 数据层

- [ ] 建 FastAPI 项目（`backend/pyproject.toml` + `main.py`）
- [ ] SQLite schema + 4 张表 + init_db()
- [ ] AgentDiscovery 实现
- [ ] FileManager 实现（read / write + 自动备份）
- [ ] BackupService 实现（backup / list_history / rollback）
- [ ] LintService 实现（8 条规则）
- [ ] 路由：agents / files / backups / lint
- [ ] 单元测试：核心路径

#### Week 2：前端骨架 + 三栏布局

- [ ] Vite + React + TS 项目初始化
- [ ] shadcn/ui 接入
- [ ] 三栏布局（Agent 树 + 文件树 + 编辑器）
- [ ] API 客户端（fetch 封装）
- [ ] Monaco Editor 接入（markdown 模式）
- [ ] 保存 / 加载 / Toast 提示
- [ ] lint 警告显示
- [ ] 历史 / 回滚 UI

#### Week 2 末尾：联调 + 验收

- [ ] 端到端测试：编辑一个 Agent 的 SOUL.md → 自动备份 → lint 警告显示 → 回滚
- [ ] 性能测试：6 个 Agent × 20 文件 启动 < 3s
- [ ] 安全测试：路径穿越 / 备份恢复

### 2.5 MVP 验收标准

老板逐项确认：

1. ✅ 启动后能看到 6 个 Agent 列表
2. ✅ 点开 main → 看到全部 Prompt Pack 文件
3. ✅ 点开 SOUL.md → 编辑器显示内容
4. ✅ 改一个字符 → 保存 → 自动备份
5. ✅ 顶部提示「已保存」+ 显示备份 ID
6. ✅ 改完后回滚 → 验证回到改之前
7. ✅ 在某文件加一行 `*最后更新：2026-08-06*` → lint 警告红点 + 提示
8. ✅ 关闭后重启 → 数据完好

---

## 三、v0.2：搜索 + Diff（1 周）

- [ ] ripgrep 集成 + fallback
- [ ] 全文搜索 API + UI（Cmd+K 命令面板）
- [ ] Diff API + diff2html 渲染
- [ ] 对比两个 Agent 同名文件
- [ ] 对比当前 vs 历史备份

**验收**：能搜「汇报风格」→ 看到所有 Agent 里包含该词的行 + 上下文。

---

## 四、v0.3：同步 + 导入导出（1 周）

- [ ] 跨 Agent 同步：plan + execute 两步
- [ ] 强制 plan-30 分钟有效期
- [ ] 强制每文件 diff 确认 UI
- [ ] 导入导出 tar.gz
- [ ] Manifest 校验 + sha256 校验
- [ ] 冲突策略：skip / merge / overwrite
- [ ] 安全：tar bomb 防护

**验收**：能导出 main → 改两字 → 导入到新 Agent xiaowei-v2。

---

## 五、v1.0：模板 + 统计 + 审计 UI（1 周）

- [ ] 4 个内置模板
- [ ] 模板应用：生成新 Agent
- [ ] 仪表盘统计 API + UI
- [ ] 审计日志 UI（按 Agent / 时间 / 操作类型过滤）
- [ ] 配置中心 UI（`config.toml` 改完自动重启）
- [ ] 一键升级命令 `soulforge update`

**验收**：能基于 `lawyer-agent` 模板一键生成 `xiaoxi-lawyer-v2`。

---

## 六、v1.x：远期优化

| 优化 | 优先级 | 说明 |
|---|---|---|
| 性能：> 20 Agent × > 500 文件 | 低 | 单老板规模用不到 |
| WebSocket 实时同步 | 低 | 单人本地不需要 |
| 第三方 lint 规则插件 | 中 | 未来可扩展 |
| 第三方模板贡献 | 中 | 跟规则插件一起做 |
| Web UI 多窗口拖拽 | 低 | 单人用不到 |
| 备份压缩（gzip） | 低 | 30 天备份总量一般 < 100MB |
| 多用户 / 鉴权 | 极低 | 单人工具 |
| 云端同步 | 极低 | 隐私敏感 |

---

## 七、风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| OpenClaw workspace 路径变更 | 数据全丢 | AgentDiscovery 自动发现 + 软链 |
| 误操作删了整个 workspace | 全部 Agent 失效 | Soulforge 永不删 workspace 根目录 |
| ripgrep 不可用（v0.2） | 搜索功能降级 | Python `grep` 库 fallback |
| 大文件（> 50KB）编辑卡 | UX 差 | Monaco 分块加载 + 大文件警告 |
| 老板不懂 git 但习惯 cp | 误覆盖 | UI 强制两步确认 + lint 拦截 |

---

## 八、给 AI 编程助手的开发节奏建议

### 8.1 每个版本的工作流

1. **先写测试**（红）：核心 lint 规则 + 备份流程
2. **写后端 API**（绿）：最小可用的端点
3. **写前端 UI**（绿）：能调通后端的页面
4. **跑通验收清单**（refactor）：老板逐项点 ✓
5. **提 git commit**

### 8.2 不要做的事

- ❌ MVP 阶段加 WebSocket（过早优化）
- ❌ MVP 阶段做账号系统
- ❌ MVP 阶段做云端同步
- ❌ MVP 阶段加插件机制
- ❌ MVP 阶段做 mobile responsive

### 8.3 老板验收节点

| 节点 | 验收人 | 验收内容 |
|---|---|---|
| Week 1 结束 | 老板 | 后端 6 个核心端点 + curl 测试 |
| Week 2 结束 | 老板 | MVP 完整流程（8 项验收清单） |
| v0.2 结束 | 老板 | 搜索 + diff 用例 |
| v0.3 结束 | 老板 | 同步 + 导入导出用例 |
| v1.0 结束 | 老板 | 模板 + 仪表盘验收 |

---

## 九、上线计划

### 9.1 v1.0 正式发布后

- [ ] 写 README + 中文用户文档
- [ ] 录 1 个 5 分钟演示视频
- [ ] 发到 GitHub（RuanCH0924/soulforge）
- [ ] 接入 OpenClaw 生态（如有）

### 9.2 GitHub 仓库结构

```
soulforge/
├── README.md
├── LICENSE (MIT)
├── docs/
├── backend/
├── frontend/
├── templates/
├── tests/
└── docker-compose.yml (v1.0+ 可选)
```

---

## 十、长期愿景

**v3.0 远期**：

> Soulforge 不再只是 OpenClaw 内部工具，而是「任何 LLM Agent system-prompt 文件」的通用管理器。
> 支持多种 Agent 框架（OpenClaw / LangGraph / AutoGen / CrewAI / 自研），
> 形成一个跨框架的 prompt 工程生态。

但**先专注 OpenClaw 单一场景**，MVP 是 v0.1，能跑起来再说。