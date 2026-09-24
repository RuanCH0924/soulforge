<div align="center">

# Soulforge

**OpenClaw 跨 Agent system-prompt 文件管理器（Web GUI）**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.5.0-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](backend/pyproject.toml)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](backend)
[![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB.svg)](frontend)

[English](README.md) · 简体中文

</div>

---

## 项目介绍

OpenClaw 是一个多 Agent 系统，每个 Agent 都拥有自己的 `workspace/`，其中包含核心 "Prompt Pack" 文件，如 `SOUL.md`、`AGENTS.md`、`USER.md`、`MEMORY.md`、`TOOLS.md` 等。

**Soulforge** 是所有这些文件的统一管理工具。它把每个 Agent 的「灵魂文件」当作源码来管理：浏览、搜索、编辑、对比、同步、备份、打包，一个 Web 页面全部搞定。

- **单进程部署** —— 一个 `uvicorn` 进程同时提供 REST API 和构建好的 React 前端。
- **默认仅本地运行** —— 监听 `127.0.0.1:8848`，绝不暴露公网。
- **开箱即用零配置** —— `start.bat` 自动探测 OpenClaw 根目录、创建 Python 虚拟环境、安装依赖并启动应用。

## 核心功能特性

| 功能 | 说明 |
|---|---|
| **统一编辑** | 一次性打开 / 编辑多个 Agent 的同名 prompt 文件；支持所见即所得（WYSIWYG）Markdown 预览并可直接在预览中编辑。 |
| **跨 Agent 搜索** | 全文搜索所有 Agent 的 prompt 文件（基于 ripgrep），支持上下文行与点击跳转。 |
| **导出** | 将 Agent 的 prompt pack 打包为 `.tar.gz`（含 SHA-256 manifest，便于归档 / 迁移）。 |
| **Diff 对比** | 对比两个 Agent 的同名文件或与历史备份对比（相似度评分 + unified/HTML diff）。 |
| **跨 Agent 同步** | 先生成同步计划，再只执行你确认的文件 —— 选择性合并，绝不整文件覆盖。 |
| **超级同步** | 开启后以**独立进程**持续运行（关闭 Soulforge 主进程也照常同步），让多个 Agent 的同名核心文档在**秒级内保持一致**；支持 UI 一键启停、运行状态实时监测、同步范围矩阵配置与日志检索 / 导出。 |
| **备份与回滚** | 每次写入前自动备份，支持保留策略、完整历史与一键回滚。 |
| **Lint 检查** | 内置 8 条规则，包括 L4 反模式检测（时间戳 / 版本号 / 修复叙述）与核心文件缺失检查。 |
| **统计与审计** | 仪表盘指标（Agent / 文件 / 备份 / 警告）与每次写操作的完整审计日志。 |
| **配置中心** | 在界面中直接读写 `config.toml`，无需手工编辑文件。 |
| **安全护栏** | 路径穿越防护、SHA-256 乐观锁、写操作强制先备份。 |
| **文档预设** *(Phase 2.5)*     | 为 `SOUL.md` / `AGENTS.md` / `MEMORY.md` / 工作日志等保存可复用的结构模板，通过 plan + confirm 两步应用。 |
| **LLM 接入** *(Phase 2.5)*     | 接入任意 OpenAI 兼容协议的 LLM（OpenAI / Anthropic / DeepSeek / Ollama），API key 加密存储 + 配置热加载。       |
| **AI 整理** *(Phase 2.5)*       | 选预设 + 选 provider → Agent 按预设重写文档 → diff 预览 → 老板确认后写入，保证所有灵魂文档结构一致。       |
| **工作日志标准化** *(M15)*     | 把 `memory/` 里同一天的多份记录（日文件 / 会话导出 / 主题碎片）归并成**每天恰好 1 个 `YYYY-MM-DD.md`**：确定性剥壳（零 token）→ 大模型归并 → 逐日 diff 确认 → 写入并清理碎片（走回收站）。整天确实无内容时由模型判定「无可归档内容」，不产出日文件、不硬凑。 |

## 路线图

Soulforge 分阶段交付：

| 阶段 | 范围 | 状态 |
|---|---|---|
| **Phase 1 · MVP** | 浏览 + 编辑 + 备份 + lint + 同步 + 导出 + 仪表盘 | ✅ 已交付 |
| **Phase 2 · UI 优化** | 布局微调、主题、快捷键、实时状态条 | ✅ 已交付 |
| **Phase 2.5 · AI Editor** | 文档预设 → LLM 接入 → AI 自动整理（三步走） | ✅ 已交付 |
| **超级同步** | 多 Agent 同名核心文档秒级实时同步（独立守护脚本 + UI 矩阵配置 / 状态 / 日志） | ✅ 已交付 |
| **M15 · 工作日志标准化** | `memory/` 日文件归并（每天 1 个 `YYYY-MM-DD.md` + 元数据剥壳 + 碎片清理），手动批次 + 逐日确认 | ✅ 已交付 |
| **Phase 3 · 远期** | 团队协作 / 云端同步 / 第三方插件 | 📋 规划中 |

统一版本基线自 **v0.5.0** 起 —— 见 [CHANGELOG.md](CHANGELOG.md)。
完整规划见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.10+、FastAPI、SQLAlchemy、Uvicorn、loguru |
| 前端 | React 18 + TypeScript + Vite、Monaco Editor、marked / turndown（所见即所得预览） |
| 存储 | SQLite（`index.db`）+ ripgrep 全文搜索 |
| 部署 | 本地单进程（`start.bat` / uvicorn），托管 `frontend/dist` 构建产物 |

## 环境依赖要求

- **Python 3.10 或更高版本**（含 `pip`）
- **Node.js 18+ 与 npm**（仅构建或开发前端时需要）
- **OpenClaw 安装** —— 应用读取 `openclaw.json` 发现各 Agent 及其 `workspace/` 目录

所有运行时数据都存放在项目目录内的 `.soulforge/`（数据库、备份、日志、`config.toml`，以及超级同步的 `super_sync/`），项目不依赖任何外部全局路径。

## 本地部署与运行步骤

### Windows（一键启动）

1. 将本仓库克隆到 `<OpenClawRoot>\workspace\projects\soulforge`（或设置环境变量 `SOULFORGE_OPENCLAW_DIR` 指向你的 OpenClaw 根目录）。
2. 双击 `start.bat`，脚本会自动：
   - 探测 OpenClaw 根目录（或使用 `SOULFORGE_OPENCLAW_DIR`）；
   - 创建 `backend\.venv` 并安装后端依赖；
   - 启动服务并打开 `http://127.0.0.1:8848`。

### Linux / macOS（一键启动）

1. 将仓库放到 `<OpenClawRoot>/workspace/projects/soulforge`（或设置 `SOULFORGE_OPENCLAW_DIR` 指向你的 OpenClaw 根目录）。
2. 运行：

   ```bash
   bash start.sh          # 或先 chmod +x start.sh && ./start.sh
   ```

   脚本会自动：探测 OpenClaw 根目录 → 创建 `backend/.venv` 并安装依赖 → 检查端口占用
   （若是旧 uvicorn 实例则清理）→ 启动服务并打开 `http://127.0.0.1:8848`
   （设置 `SOULFORGE_NO_BROWSER=1` 可禁用自动开浏览器）。

> **注意：虚拟环境不可跨平台复用。** Windows 的虚拟环境是 `backend\.venv\Scripts\python.exe`，
> Linux / macOS 是 `backend/.venv/bin/python`，两者不能通用。若把 Windows 上的 `.venv`
> （含大量 `.exe`）同步或复制到 Linux，应用会无法启动 —— 请先删除后重建：
> `rm -rf backend/.venv`，再重新运行 `start.sh`（脚本检测到这种目录也会直接报错提示）。
> 建议在 Git / Syncthing 中排除 `.venv`、`node_modules`、`.soulforge`。
> 另：`start.sh` 需保持 **LF** 行尾（CRLF 会导致 `bad interpreter`），仓库已用 `.gitattributes` 固定。

### 手动部署（任意平台）

后端：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows（Linux/macOS: source .venv/bin/activate）
pip install "fastapi>=0.110" "uvicorn[standard]>=0.29" "sqlalchemy>=2.0" \
            "pydantic>=2.6" "python-multipart>=0.0.9" "loguru>=0.7" "send2trash>=1.8" tomli
uvicorn main:app --host 127.0.0.1 --port 8848
```

前端（构建一次即可，由后端托管 `frontend/dist`）：

```bash
cd frontend
npm install
npm run build
```

然后访问 <http://127.0.0.1:8848>。

### 前端开发模式

```bash
cd frontend
npm run dev        # Vite 开发服务器，将 /api 代理到 http://127.0.0.1:8848
```

## 配置说明

| 环境变量 | 默认值 | 作用 |
|---|---|---|
| `SOULFORGE_DATA_DIR` | `<项目根>/.soulforge` | 数据目录（数据库、备份、日志、配置、`super_sync/`） |
| `SOULFORGE_OPENCLAW_DIR` | 自动探测的 OpenClaw 根目录 | 包含 `openclaw.json` 的目录 |
| `SOULFORGE_PORT` | `8848` | 服务端口 |

运行时配置保存在 `.soulforge/config.toml`（server、备份保留、lint 规则、UI 默认项、高级选项），可在界面的**设置**对话框中直接修改。

## API 接口说明

基础地址：`http://127.0.0.1:8848/api` · 交互式 OpenAPI 文档：<http://127.0.0.1:8848/docs>

| 方法 | 端点 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/agents` | 列出所有 Agent |
| `POST` | `/api/agents/scan` | 重新扫描所有 Agent workspace |
| `GET` | `/api/agents/{id}/files` | 列出 Agent 的 prompt-pack 文件 |
| `GET` | `/api/agents/{id}/files/{path}` | 读取文件内容 |
| `PUT` | `/api/agents/{id}/files/{path}` | 写入文件（自动备份、乐观锁） |
| `DELETE` | `/api/agents/{id}/files/{path}` | 删除文件（移入回收站） |
| `POST` | `/api/agents/files/cross-write` | 一次写入多个 Agent 的同名文件 |
| `GET` | `/api/agents/{id}/files/{path}/history` | 文件备份历史 |
| `POST` | `/api/search` | 跨 Agent 全文搜索 |
| `GET` | `/api/diff` | 对比两个 Agent 的同名文件 |
| `POST` | `/api/sync/plan` | 生成同步计划 |
| `POST` | `/api/sync/execute` | 执行同步计划 |
| `GET` / `PUT` | `/api/super-sync/config` | 读取 / 更新超级同步范围（参与 Agent + 文档） |
| `GET` | `/api/super-sync/status` | 超级同步运行状态（运行中 / 已停止 / 异常） |
| `POST` | `/api/super-sync/start` · `/api/super-sync/stop` | 启动 / 停止独立同步进程 |
| `GET` | `/api/super-sync/logs` · `/api/super-sync/logs/export` | 查询 / 导出同步日志 |
| `GET` | `/api/export/{id}` / `/api/export/all` | 导出单个 / 全部 Agent 为 `.tar.gz` |
| `GET` | `/api/backups/{id}` | 列出 Agent 的所有备份 |
| `POST` | `/api/backups/{id}/{path}/rollback` | 回滚文件到指定备份 |
| `GET` | `/api/lint/{id}` / `/api/lint/file/{id}/{path}` / `/api/lint/all` | 对 Agent / 文件 / 全部执行 lint |
| `GET` | `/api/stats` | 仪表盘统计数据 |
| `GET` | `/api/audit` | 审计日志 |
| `GET` / `PUT` | `/api/config` | 读取 / 更新配置 |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/presets[/{id}]` · `/api/presets/{id}/versions[/{vid}/restore]` | 文档预设 CRUD + 版本历史 |
| `POST` | `/api/presets/{id}/apply` · `/api/presets/{id}/apply/execute` | 应用预设（plan + 确认两步） |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/llm/providers[/{id}]` · `/api/llm/providers/{id}/test` · `/api/llm/chat` | LLM Provider 管理与连通性测试 |
| `GET` / `POST` | `/api/ai/jobs[/{id}]` · `/api/ai/jobs/{id}/apply` · `/reject` · `/regenerate` | AI 整理任务（生成 → diff → 写入） |
| `GET` / `POST` | `/api/daily-runs[/{id}]` · `/api/daily-runs/{id}/apply` · `/reject` · `/skip` · `/report` | 工作日志标准化批次（生成计划 → 逐日确认 → 写入 + 碎片清理 → 验收报告） |

所有响应统一封装为 `{"data": ...}`；错误返回 `{"error": {"code", "message", "details"}}`。
`GET /api/health` 返回运行时版本号（`data.version`），与 `backend/app/__init__.py` 中的值一致。
完整规范见 [docs/API.md](docs/API.md)。

## 项目结构

```
soulforge/
├── backend/                  # FastAPI 后端
│   ├── main.py               # 应用入口
│   ├── super_sync.py         # 超级同步独立守护脚本（可脱离主进程运行）
│   ├── app/
│   │   ├── api/              # 路由（agents、files、search、diff、sync、super-sync…）
│   │   ├── services/         # 业务服务（发现、备份、lint、super_sync…）
│   │   ├── models/           # SQLAlchemy 模型 + Pydantic schema
│   │   └── core/             # 错误、日志、安全
│   ├── tests/                # pytest 测试套件
│   └── pyproject.toml
├── frontend/                 # React + Vite 前端
│   ├── src/                  # 组件、hooks、api 客户端、样式
│   ├── dist/                 # 构建产物（由后端托管）
│   └── package.json
├── docs/                     # 详细文档（架构、API、数据模型…）
├── start.bat / start.sh      # 一键启动（Windows / Linux·macOS）
├── .github/                  # Issue 与 PR 模板
├── README.md                 # 本文件
├── CHANGELOG.md              # 版本历史与发版流程
└── LICENSE                   # MIT 许可证
```

## 相关文档

| 文档 | 内容 |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | 版本历史、版本号事实源与发版流程 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 主开发文档（目标 / 架构 / 功能 / 数据模型） |
| [docs/API.md](docs/API.md) | REST API 完整定义 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构详解 |
| [docs/DATA-MODEL.md](docs/DATA-MODEL.md) | 数据模型（SQLite schema、文件元数据） |
| [docs/SECURITY.md](docs/SECURITY.md) | 安全护栏 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 落地路径（分阶段目标与验收清单） |
| [docs/UI-SPECS.md](docs/UI-SPECS.md) | UI 设计规范 |

## 贡献指南

欢迎贡献代码！请遵循以下流程：

1. **Fork** 本仓库并创建特性分支：`git checkout -b feat/my-feature`
2. **编写代码** —— 保持改动聚焦且与现有风格一致：
   - 后端：遵循 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)，运行 `ruff check`，并用 `pytest` 补充 / 扩展测试（在 `backend/` 下执行）。
   - 前端：提交前运行 `npm run build`（包含 `tsc --noEmit`）。
3. **提交** —— 提交信息清晰，说明变更的*原因*。
4. **发起 Pull Request** —— 使用 [PR 模板](.github/PULL_REQUEST_TEMPLATE.md)，确保所有 CI 检查通过。

规范要求：

- 绝不把元数据写进 Agent workspace；Soulforge 数据只放在 `.soulforge/`。
- 跨 Agent 同步绝不整文件覆盖，必须选择性合并。
- 所有写操作必须走备份 + 审计流水线。

## 许可证

本项目基于 [MIT 许可证](LICENSE) 开源。

## 联系方式

- 维护者：**RuanCH0924**
- 遇到 Bug、有功能建议或疑问，请在 [GitHub Issues](https://github.com/RuanCH0924/soulforge/issues) 提交 Issue。
