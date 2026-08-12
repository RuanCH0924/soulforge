# Soulforge — 落地路径

> 配套主文档 [DEVELOPMENT.md](../DEVELOPMENT.md) 的落地路径章节。
> 本文档按 **Phase** 组织，每个 Phase 有明确目标、验收清单、回退方案。

---

## 一、版本规划总览

| Phase | 范围 | 状态 |
|---|---|---|
| **Phase 1 · MVP** | 浏览 + 编辑 + 备份 + lint + 同步 + 导入导出 | ✅ 已完成（v0.1 → v1.0 累计交付） |
| **Phase 2 · UI 优化** | 页面交互美观、编辑器体验、视觉一致性 | 🚧 进行中 |
| **Phase 2.5 · AI Editor** | 模板预设 + Agent 大模型接入 + AI 文档整理 | 🚧 进行中（**当前主方向**） |
| **Phase 3 · 远期** | 团队协作 / 云端同步 / 第三方插件 | 📋 规划 |

> Phase 1 的完整历程见 [附录 A](#附录-a-phase-1-mvp-1 回顾)。

---

## 二、当前主线：Phase 2.5 AI Editor

### 2.1 阶段目标

> 让老板的 **OpenClaw 灵魂文档** 和 **memory/ 工作日志** 都能按统一格式规范化，
> 通过 AI Agent 自动整理，**保证所有文档结构一致、章节齐全、风格统一**。

### 2.2 三步走规划

```
Step 1 ──► Step 2 ──► Step 3
模板预设     Agent 接入     AI 自动整理
（静态）     （能力）       （应用）
```

| Step | 范围 | 验收标准 | 估时 |
|---|---|---|---|
| **Step 1：模板预设** | 保存文档格式预设（SOUL/AGENTS/MEMORY/user/工作日志等），可在 UI 选择 + 应用 | 4 个内置预设（SOUL/AGENTS/MEMORY/工作日志）+ 用户可新建/编辑预设 | 1 周 |
| **Step 2：Agent 接入** | 接入 LLM 大模型（OpenAI 兼容协议），支持多 provider（OpenAI / Anthropic / 本地 Ollama） | 至少一个 provider 跑通 + 后端配置可热加载 | 1 周 |
| **Step 3：AI 自动整理** | 选定预设 + 选定文件 → AI Agent 按预设重写文档 → 生成 diff → 老板确认后写入 | E2E 流程跑通：对一个 Agent 的 MEMORY.md 应用"工作日志汇总"预设 | 2 周 |

### 2.3 Step 1 详细拆解：模板预设系统

#### 目标

> 把"SOUL.md 应该有哪几章、MEMORY.md 应该按什么格式"这件事**结构化、可复用、可版本化**。

#### 数据模型

新增 `presets` 表：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | text PK | UUID |
| `name` | text | 预设名（如 "SOUL.md 标准结构"） |
| `target_file_type` | text | 适用文件类型（SOUL/AGENTS/MEMORY/USER/IDENTITY/TOOLS/WORKLOG/ANY） |
| `description` | text | 用途说明 |
| `sections_json` | text | 章节列表（JSON），每个章节 = `{title, required, order, hint}` |
| `frontmatter_json` | text | YAML frontmatter 模板（JSON），每个字段 = `{key, required, default}` |
| `style_rules` | text | 风格规则（Markdown 规范、emoji 禁令、口语化禁令等） |
| `created_at` / `updated_at` | text | 时间戳 |
| `version` | integer | 预设版本（老板可迭代升级） |

#### 内置预设（v1）

| 预设名 | target_file_type | 适用场景 |
|---|---|---|
| `SOUL 标准结构` | SOUL | 新建/重整 SOUL.md（核心行为准则、学习连续性、核心边界） |
| `AGENTS 标准结构` | AGENTS | 新建/重整 AGENTS.md（启动流程、记忆、工具、群聊、安全） |
| `MEMORY 标准结构` | MEMORY | 重整长期记忆（重要决定、经验教训、待办） |
| `工作日志汇总` | WORKLOG | 整理 `memory/YYYY-MM-DD.md`（按时间倒序归档、提取关键决策） |

#### UI 入口

- 顶部菜单 → 「预设」 → 列表 + 新建/编辑/删除
- 文件编辑页 → 「应用预设」按钮 → 选预设 → 生成 diff 预览 → 老板确认 → 写入

#### API 端点

| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/api/presets` | 列出全部预设（系统 + 用户自定义） |
| `POST` | `/api/presets` | 创建新预设 |
| `GET` | `/api/presets/{id}` | 查看预设详情 |
| `PUT` | `/api/presets/{id}` | 编辑预设（version 自增） |
| `DELETE` | `/api/presets/{id}` | 删除用户预设（系统预设不可删） |
| `POST` | `/api/presets/{id}/apply` | 应用预设到指定 Agent + 文件（返回 diff plan） |
| `POST` | `/api/presets/{id}/apply/execute` | 执行应用（写入文件，自动备份） |

#### 验收清单

1. ✅ 顶部菜单有「预设」入口
2. ✅ 系统提供 4 个内置预设
3. ✅ 用户可新建/编辑/删除自己的预设
4. ✅ 预设编辑器支持 JSON 或可视化拖拽两种模式
5. ✅ 文件编辑页有「应用预设」按钮
6. ✅ 应用预设走 plan + execute 两步，绝不直接覆盖
7. ✅ 系统预设不可删（前端 UI 隐藏删除按钮，后端 403）

---

### 2.4 Step 2 详细拆解：Agent 大模型接入

#### 目标

> 让 Soulforge 后端能调用任意 **OpenAI 兼容协议**的 LLM，
> 支持多 provider 配置（OpenAI / Anthropic / DeepSeek / Ollama / 其他），
> 配置变更可热加载（不需要重启服务）。

#### 数据模型

新增 `llm_providers` 表：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | text PK | provider 名（如 "openai-main" / "ollama-local"） |
| `base_url` | text | API 端点 |
| `api_key` | text | 密钥（**加密存储**） |
| `model` | text | 模型名（gpt-4 / claude-sonnet / qwen2.5 / llama3） |
| `protocol` | text | `openai-completions` / `anthropic-messages` |
| `enabled` | integer | 是否启用 |
| `max_tokens` | integer | 单次最大 token |
| `temperature` | real | 默认温度 |
| `timeout_seconds` | integer | 超时 |
| `created_at` / `updated_at` | text | 时间戳 |

#### 配置加载机制

```
[Soulforge 启动]
  ↓
读 .soulforge/config.toml → llm_providers 段
  ↓
注册到内存 LLMRegistry
  ↓
[文件变更 / PUT /api/config]
  ↓
热加载：diff 新旧 → 增量注册/失效 → 不重启
```

#### UI 入口

- 设置 → 「LLM Provider」 → 列表 + 新增/编辑/删除
- 「测试连通性」按钮（发一条 "ping" 看是否返回）

#### API 端点

| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/api/llm/providers` | 列出所有 provider |
| `POST` | `/api/llm/providers` | 新增 provider |
| `PUT` | `/api/llm/providers/{id}` | 编辑 provider（**key 留空 = 保留旧 key**） |
| `DELETE` | `/api/llm/providers/{id}` | 删除 provider |
| `POST` | `/api/llm/providers/{id}/test` | 测试连通性 |
| `POST` | `/api/llm/chat` | 通用 chat 端点（内部用） |

#### 安全护栏

- API key **加密存储**（Fernet，对称加密，密钥来自 `SOULFORGE_SECRET` 或首次启动生成）
- API key 在 UI 上**永远显示掩码**（`sk-****...****`）
- API key 不进 git（`.gitignore` 加 `.soulforge/secrets/`，备份也排除）
- 配置中心 UI 有「泄露检测」按钮：扫描日志/审计里是否泄露过明文 key

#### 验收清单

1. ✅ 设置里有「LLM Provider」管理页
2. ✅ 至少能跑通 OpenAI / Anthropic / Ollama 三个协议
3. ✅ 修改配置后**不重启**就生效
4. ✅ API key 在 UI 永远显示掩码
5. ✅ 「测试连通性」按钮能用
6. ✅ 删除 provider 会拒绝有关联 ai_job 的删除（避免历史断链）

---

### 2.5 Step 3 详细拆解：AI 自动整理

#### 目标

> 老板选一个预设 + 选一个文件 + 选一个 LLM provider →
> AI Agent 按预设重写文档 → 生成 diff plan → 老板确认 → 写入。

#### 数据模型

新增 `ai_jobs` 表：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | text PK | UUID |
| `agent_id` | text | 目标 Agent |
| `file_path` | text | 目标文件路径 |
| `preset_id` | text | 使用的预设 |
| `provider_id` | text | 使用的 LLM provider |
| `status` | text | `pending` / `running` / `awaiting_confirm` / `applied` / `rejected` / `failed` |
| `input_snapshot` | text | 原始内容快照 |
| `output_content` | text | AI 输出（待确认内容） |
| `diff_plan_json` | text | 生成的 diff plan |
| `error` | text | 失败原因 |
| `created_at` / `updated_at` / `finished_at` | text | 时间戳 |

#### 完整流程

```
[老板选文件 + 选预设 + 选 provider]
  ↓
POST /api/ai/jobs  (status: pending)
  ↓
后台异步执行
  ↓
1) 读取原文件 → 快照
2) 构造 prompt：原文件 + 预设 + 老板可选的额外指令
3) 调 LLM → 拿到新内容
4) 计算 unified diff → diff_plan
5) status: awaiting_confirm
  ↓
[UI 弹出 diff plan，老板预览]
  ↓
POST /api/ai/jobs/{id}/apply   → status: applied（写入文件 + 自动备份 + 审计）
POST /api/ai/jobs/{id}/reject  → status: rejected（不写入）
  ↓
[失败处理]
status: failed + error 字段
```

#### UI 设计

- 文件编辑页 → 「AI 整理」按钮 → 弹出向导：
  1. 选预设（默认按文件类型过滤）
  2. 选 provider（默认按上次使用）
  3. 可选：附加指令（"把 SOUL.md 里关于群聊的章节合并"）
  4. 「生成」按钮 → 后台任务
- 异步任务跑完后，右下角弹通知 → 点击进入 diff plan 预览页
- Diff plan 页：左右 diff（diff2html）+ 「应用」/「拒绝」按钮 + 「重新生成」按钮（带新指令）

#### 安全护栏

- AI 输出**绝不直接覆盖原文件**，必须经过老板 diff 确认
- AI 输出必须通过 lint 检查，违规拒绝写入
- 大文件（> 30KB）拒绝 AI 整理（token 成本 + 质量风险）
- API key 审计：每次调用记录 provider + token 消耗（成本追踪）
- 单文件 AI 调用**默认单次**（老板可点「再来一次」），不自动循环

#### 验收清单

1. ✅ 文件编辑页有「AI 整理」按钮
2. ✅ 向导流程 4 步走（选预设/选 provider/附加指令/生成）
3. ✅ 异步任务跑完后有通知
4. ✅ diff plan 预览页可视化 diff
5. ✅ 应用/拒绝按钮可点
6. ✅ 「重新生成」按钮可带新指令
7. ✅ AI 输出过 lint 才能写入
8. ✅ 大文件 > 30KB 自动拒绝
9. ✅ 调用记录写审计日志

---

## 三、Phase 2 · UI 优化（并行进行中）

### 3.1 目标

> 提升页面交互和美观度，让老板用得更顺手。

### 3.2 任务清单

| 优先级 | 任务 | 说明 |
|---|---|---|
| 高 | 顶部状态条加实时指示 | 连接状态 / 索引文件数 / 上次扫描时间 |
| 高 | 文件树加折叠 + 搜索 | 支持 `/` 快捷键聚焦搜索框 |
| 高 | 编辑器加字体大小调节 | Ctrl +/- 缩放 |
| 中 | 主题切换 | 浅色 / 深色 / 跟随系统 |
| 中 | diff 页加并排/上下两种模式 | 默认并排，可切上下 |
| 中 | toast 通知加分类 | success / warning / error 三色 |
| 低 | 加载动画统一 | spinner / skeleton |
| 低 | 键盘快捷键文档 | `/` 搜索 / `Ctrl+S` 保存 / `Ctrl+K` 命令面板 |

### 3.3 验收清单

1. ✅ 所有交互在 ≥1280px 屏幕上视觉一致
2. ✅ 顶部状态条实时更新（≤ 5s 延迟）
3. ✅ 主题切换记忆（localStorage）
4. ✅ 快捷键 Ctrl+S 保存不刷新页面

---

## 四、Phase 3 · 远期规划

| 优化 | 优先级 | 说明 |
|---|---|---|
| 多用户 / 鉴权 | 低 | 单人本地用不到 |
| 云端同步 | 低 | 隐私敏感 |
| WebSocket 实时同步 | 低 | 单老板规模不需要 |
| 第三方 lint 规则插件 | 中 | 跟模板贡献一起做 |
| 第三方预设贡献 | 中 | GitHub PR 形式 |
| 跨框架适配 | 中 | OpenClaw → LangGraph / AutoGen |
| AI 整理的「规则库」 | 中 | 把老板常用的整理规则沉淀成可复用 preset |
| AI 整理的「批量模式」 | 低 | 一次对多个文件应用同一预设 |

---

## 五、风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| LLM 输出质量不稳定 | AI 整理结果难用 | 强制走 diff 确认，不自动写入 |
| LLM API 成本失控 | 月账单爆炸 | 审计日志记录 token 消耗 + 单文件单次默认 |
| 预设被滥用 | 老板的预设被批量改坏 | 预设按 Agent 隔离，跨 Agent 应用走 plan + confirm |
| API key 泄露 | 严重安全事件 | 加密存储 + UI 掩码 + 泄露检测 |
| 大文件 token 超限 | AI 调用失败 | > 30KB 自动拒绝，强制文件拆分 |
| OpenClaw workspace 路径变更 | 数据全丢 | AgentDiscovery 自动发现 + 软链 |
| 误操作删了整个 workspace | 全部 Agent 失效 | Soulforge 永不删 workspace 根目录 |

---

## 六、给 AI 编程助手（Trae）的开发节奏建议

### 6.1 Phase 2.5 的工作流

1. **Step 1 优先**：先把 presets 数据模型 + 4 个内置预设 + 基础 CRUD 跑通
2. **Step 2 接 provider**：先跑通 OpenAI 一个协议，再补 Anthropic / Ollama
3. **Step 3 做端到端**：选 SOUL.md + 内置 preset + OpenAI → diff 确认 → 写入，跑通最小闭环
4. **每步完成就跑验收清单**：老板逐项点 ✓

### 6.2 别做的事

- ❌ Step 1 不要做 AI 调用（先把数据层跑通）
- ❌ Step 2 不要做 Anthropic 协议（先跑通 OpenAI，再扩展）
- ❌ Step 3 不要做自动写入（必须老板确认）
- ❌ 不要在 Phase 2.5 做 WebSocket / 云端同步 / 多用户
- ❌ 不要把 API key 落 git

### 6.3 老板验收节点

| 节点 | 验收人 | 验收内容 |
|---|---|---|
| Step 1 结束 | 老板 | 4 个内置预设 + CRUD + 应用流程 |
| Step 2 结束 | 老板 | LLM Provider 管理 + 热加载 |
| Step 3 结束 | 老板 | AI 整理 E2E 流程（生成→diff→确认→写入） |
| Phase 2 UI 结束 | 老板 | UI 优化 9 项验收清单 |

---

## 七、上线计划

### 7.1 Phase 2.5 完成后

- [ ] 更新 README 加 "AI Editor" 章节
- [ ] 录 1 个 5 分钟 AI Editor 演示视频
- [ ] 发 GitHub Release（v2.0.0-beta）
- [ ] 写迁移指南（从 v1.0 升级）

### 7.2 GitHub 仓库结构（不变）

```
soulforge/
├── README.md
├── LICENSE (MIT)
├── docs/
├── backend/
├── frontend/
├── templates/
├── tests/
└── .github/
```

---

## 八、长期愿景

> Soulforge 不再只是 OpenClaw 内部工具，而是「任何 LLM Agent system-prompt 文件」的通用管理器 + AI 文档整理助手。
> 形成一个跨框架的 prompt 工程 + AI 文档工程生态。

但**先专注 Phase 2.5 三步走**，跑通再说。

---

## 附录 A · Phase 1 MVP 回顾

> 保留旧版 v0.1 → v1.0 落地路径作为历史存档。

### A.1 Phase 1 版本节奏

| 版本 | 范围 | 周期 | 状态 |
|---|---|---|---|
| v0.1 MVP | 浏览 + 编辑 + 备份 + lint | 2 周 | ✅ 已交付 |
| v0.2 | 搜索 + diff | 1 周 | ✅ 已交付 |
| v0.3 | 跨 Agent 同步 + 导入导出 | 1 周 | ✅ 已交付 |
| v1.0 | 模板 + 统计 + 审计日志 UI | 1 周 | ✅ 已交付 |

### A.2 Phase 1 模块矩阵

| 模块 | 交付物 | 状态 |
|---|---|---|
| M1 Agent 管理 | `GET/POST /api/agents` + Agent 树 UI | ✅ |
| M2 文件浏览/编辑 | Monaco 编辑器 + 自动备份 | ✅ |
| M3 跨 Agent 搜索 | ripgrep 后端 + Cmd+K UI | ✅ |
| M4 Diff 对比 | diff2html + 双 Agent 对比 + 历史对比 | ✅ |
| M5 跨 Agent 同步 | plan + execute 两步流程 | ✅ |
| M6 导入导出 | `.tar.gz` + manifest 校验 + 冲突策略 | ✅ |
| M7 备份/回滚 | 自动备份 + 30 天保留 + 一键回滚 | ✅ |
| M8 Lint | 8 条规则 + 健康检查 UI | ✅ |
| M9 模板系统 | 4 个内置模板 + 应用到新 Agent | ✅ |
| M10 统计/仪表盘 | 仪表盘 API + UI + 审计日志 | ✅ |

### A.3 Phase 1 关键决策（保留供 Phase 2.5 参考）

- **单进程部署**：FastAPI 同时 serve React build + API
- **本地零配置**：默认端口 8848，127.0.0.1，不暴露公网
- **备份外置**：`.soulforge/backups/`，不污染 workspace
- **审计日志**：所有写操作进 `audit_log` 表
- **lint 不强制拦截**：只警告，除非老板开启「严格模式」

---

*最后更新：2026-08-12 · Phase 2.5 AI Editor 三步走规划建立*