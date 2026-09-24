# Soulforge — UI 设计规范

> 设计目标：**桌面单页 Web 应用**，浏览器全屏使用，**侧边导航 + 三栏布局**（Agent 树 / 文件树 + 编辑器）。
> 类似 VSCode / Obsidian 的工作流气质，但更轻。
> 用户：老板（单人本地自托管）。

> **文档职责划分（M-08）**
> - 本文档 = **视觉与尺寸规范事实源**：布局结构、断点、尺寸、设计 token、组件规范、交互与文案约定。
> - `docs/UI-REDESIGN-PLAN.md` = **架构与演进事实源**：信息架构、页面划分、里程碑与验收记录。
> - `docs/UI-OPTIMIZATION-PLAN.md` = 体验层优化措施（M-01~M-08）与验证指标。
> - `CHANGELOG.md` = 版本历史与发版流程；本文档不记录项目版本号，仅在修订记录中记录规范自身版本。
> - 任何涉及断点 / 尺寸 / token / 顶栏入口数的代码变更，须在同一次提交内更新第十一节的一致性核对表。

### 修订记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | — | 初版（桌面三栏、≥1280px 强制） |
| v1.1 | 2026-09-02 | M-08 同步实现：加入侧边导航、四档断点、最小宽度 320px、自定义组件清单、Alt 折叠快捷键、一致性核对表 |
| v1.2 | 2026-09-02 | 文档编辑体验升级：默认视图模式改为源码编辑、`Ctrl+B` 让位给加粗、新增多窗口/大纲/lint 跳转快捷键、新增草稿保护与会话恢复、回滚增加 diff 预览、文件树支持过滤与键盘导航 |
| v1.3 | 2026-09-02 | 对比工具专项修复：新增文本归一化两档口径（忽略格式噪声 / 严格）、`identical` 与 `noise_kinds` 结果字段、一致时的明确结论展示、同步计划标注「内容一致」、默认 A/B 不再选到同一 Agent |
| v1.4 | 2026-09-22 | 与实现核对修正：顶栏/命令面板索引动作数 17 → 15、内嵌面板数 11 → 9（移除已下线的导入 / 新建 Agent / 模板入口）；状态栏新增后端版本号展示 |
| v1.5 | 2026-09-22 | 编辑器工具栏新增「设为预设」（当前文档存为文档预设，弹窗填写名称 / 适用类型 / 说明 / 章节层级 / 必填章节 / 顺序 / frontmatter）；`parseOutline` 抽为共享工具 `utils/markdown.scanHeadings`（编辑器大纲与「设为预设」共用同一标题扫描口径） |
| v1.6 | 2026-09-23 | 编辑器工具栏取消「整理 ▾」下拉：应用预设 / AI 整理 / 导出文件 平铺为一级按钮；工具栏由「横向滚动」改为「换行」，窄窗口不再裁切按钮，并在窗口宽度 < 780px 时隐藏快捷键提示 |
| v1.7 | 2026-09-23 | 文案规范新增「按钮文案最多 4 个汉字」硬约束，并据此收敛 11 处超长按钮（导出当前文件 / 忽略格式噪声 / 回滚到此版本 / 回溯到此版本 / 生成同步计划 / 执行同步（N 个文件）/ 保存同步范围 / 管理 LLM Provider / 保存为预设 / 统计仪表盘 / 健康检查报告），完整含义移至 `title` |
| v1.8 | 2026-09-23 | lint 规则清单可视化：数据中心 → 检查报告顶部新增可折叠「检查规则（N 条）」表（默认收起、无警告时自动展开），文案由新增的 `GET /api/lint/rules` 下发（后端 `LintService.rule_catalog()` 为唯一事实源）；编辑器「检查」面板与系统配置 Lint 开关处仅放入口指引 |
| v1.9 | 2026-09-23 | **lint 计数口径统一为「实时、单一来源」**：统计面板的 lint 卡片与状态栏警告数不再取 `/api/stats`（索引列恒为 0，是假数据），统一改用 `GET /api/lint/all`，与「检查报告」同源同口径（按报告中列出的条数计，含 error 级）；统计面板**不阻塞**——其余 7 张指标先出，lint 卡片先显示「…」再填数字（全量扫描大库约 1~2 分钟）；状态栏未取到时显示「lint 检查中…」，不谎报「无警告」。文案：命令面板与统计面板标题「统计仪表盘」→「统计面板」（与数据中心 tab 一致） |
| v1.10 | 2026-09-24 | 业务工具页新增「日志标准化」tab（M15 · P2）：三阶段单页流程（参数 → 逐日确认 → 验收报告），**默认全部不勾选**、写入前二次确认列全日期、409 冲突须列出冲突日期、不得谎报失败原因（该日没有生成出内容时不得显示「强规则未通过 0 项」，`applicable = 0` 时不得显示「计划已生成」）；**技能预设选项在名称下方显示一行功能简介（取后端 `presets.description`，前端不硬编码）**；新增 §5.7 交互规范与 4 行一致性核对项 |
| v1.11 | 2026-09-24 | **WORKLOG 预设收口**：预设列表由「两个语义相近的并列项」变为 1 项（`preset-wlog-daily-std`）——两个选项的说明文案都只讲「做什么」、没说「什么时候用哪个」，属并列项本身的设计问题，不是文案问题。已退役的内置预设有 `retired_at`，`GET /api/presets` 不再返回，前端无需过滤 |
| v1.12 | 2026-09-24 | **「无可归档内容」日（M15）**：全天只有噪音时模型可判定不产出日文件（不再硬凑）。§5.7 新增 4 条硬约束（该日不得显示为失败 / 不得展示 diff / 必须给理由 / 主文件保持不动）、按钮文案「写入选中 / 全部写入」→「执行选中 / 全部执行」（空日只清碎片、不写文件，`写入` 会谎报动作）、确认弹窗逐日标注动作；一致性核对表新增 2 行（空日可勾选条件、空日状态色不用红） |
| v1.13 | 2026-09-24 | **失败原因不得谎报（补强）**：§5.7 新增 2 条硬约束——① 输出被 `max_tokens` 截断时该日报 `LLM_OUTPUT_TRUNCATED` + 调大 `max_tokens` 的指引，不得显示成「强规则未通过」，前端不得自行重试；② 残留壳说明用规则名、不暴露 `M01`~`M12` 内部编号。一致性核对表新增 2 行（残留壳检测口径、截断自动重试次数） |
| v1.14 | 2026-09-24 | **两类预设的边界收口**：把「供大模型归并工作日志」与「供主工作台加载」两类预设彻底分开——① 判据 = `target_file_type=WORKLOG`，设置页「文档预设」与主工作台「应用预设 / AI 整理」统一取 `scope=workbench` 排除它们（新建预设的类型下拉也不再提供 WORKLOG，并说明去哪管）；② 日志标准化界面新增预设信息栏（徽章「大模型专用」+ 版本 + 来源 `is_builtin` +「查看 / 编辑」）与页内编辑器（用途说明 / 模板文档 / 风格与内容规则三类），保存即 version+1、重新生成批次生效；③ 逐日确认页信息条补 `预设 v{N}`。§5.1 补主工作台侧约束，§5.7 新增 3 条硬约束，一致性核对表新增 5 行 |

---

## 一、整体布局

### 1.1 布局结构（桌面 ≥1440px）

```
┌──────┬───────────────────────────────────────────────────────────────────────┐
│      │ TopBar   Soulforge · 8 个 Agent      [搜索或执行命令… Ctrl K] [重新扫描]│
│ Side ├────────────┬──────────────────────────┬───────────────────────────────┤
│ Nav  │            │                          │                               │
│ 64px │  Agent 树  │  文件树 / CORE 二级列表   │  编辑器 / 预览（1–3 个窗口）   │
│      │            │                          │                               │
│ ⌂ 主 │  ▾ main    │  ▾ CORE                  │  ┌─────────────────────────┐  │
│ ⇄ 业务│   • SOUL   │    SOUL.md              │  │  # SOUL.md              │  │
│ ◇ 数据│   • USER   │    AGENTS.md            │  │  [Monaco Editor]        │  │
│ ⚙ 配置│  ▸ xiaowei │  ▾ MEMORY                │  └─────────────────────────┘  │
│      │  ▸ caicai  │    2026-08-05.md        │  [保存][历史][应用预设][检查] │
├──────┴────────────┴──────────────────────────┴───────────────────────────────┤
│ StatusBar  ● 已连接到 8 个 Agent · 索引 2461 个文件 · 上次扫描：2 分钟前      │
└───────────────────────────────────────────────────────────────────────────────┘
```

**结构要点**

| 区域 | 说明 |
|---|---|
| SideNav（64px） | 固定 4 项全局导航：主工作台 / 业务工具 / 数据中心 / 系统配置。**跨页导航的唯一入口** |
| TopBar（48px） | **仅全局动作**：品牌 + Agent 计数 + 命令面板入口 + 重新扫描。**不承载导航类按钮** |
| 三栏 | 左栏（Agent 树 / CORE 一级分类）+ 中栏（文件树 / CORE 二级列表）+ 编辑器；左右栏均可拖拽与折叠 |
| StatusBar（28px） | 连接态 + 索引文件数 + 上次扫描 + lint 警告数 + 后端版本号；≤1280px 隐藏中间两项（索引文件数 / 上次扫描） |
| 页面路由 | `#/workbench`、`#/tools`、`#/data`、`#/settings`（hash 路由，刷新保持） |

### 1.2 响应式断点

| 断点 | 布局 |
|---|---|
| ≥1440px | SideNav 64px + 三栏全显；状态栏 4 段信息完整 |
| 1280–1439px | 三栏全显；状态栏隐藏「索引文件数」「上次扫描」，仅留连接态与 lint 警告 |
| 1024–1279px | SideNav 56px（隐藏文字标签）；顶栏按钮压缩；状态栏单行不换行 |
| 768–1023px | SideNav 48px；弹窗转全屏抽屉；命令面板全宽 |
| <768px | 保持可用降级（单栏 + 全屏弹窗 + 编辑优先），非主要适配目标 |

**实现**：断点集中在 `frontend/src/styles/global.css` 的 `@media` 块，不散落硬编码。

---

## 二、窗口尺寸

| 属性 | 值 |
|---|---|
| 默认窗口宽 | 全屏（无固定） |
| 最小支持宽度 | **320px**（`body { min-width: 320px }`，无强制最小窗宽） |
| 默认窗口高 | 全屏（无固定） |
| SideNav 宽 | 64px（>1024px）/ 56px（≤1024px）/ 48px（≤768px） |
| TopBar 高 | 48px（`--topbar-height`） |
| StatusBar 高 | 28px（`--statusbar-height`） |
| 左栏（Agent 树 / CORE 一级） | 默认 240px（可拖拽 180–360px，**可折叠**） |
| 中栏（文件树 / CORE 二级） | 默认 280px（可拖拽 200–400px，**可折叠**） |
| 右栏（编辑器） | 自适应剩余；多窗口模式最多同时打开 3 个窗口 |
| 折叠恢复条 | 32px 宽，栏折叠后在原位保留可点击的展开入口 |

**布局持久化**：左/中栏宽度与折叠态持久化到 `localStorage` 键 `soulforge.layout`，刷新后保持；数据越界时收敛到合法范围，损坏时回落默认值。

---

## 三、配色 & 主题

### 3.1 双主题

| 主题 | 触发 |
|---|---|
| **浅色** | `theme = light`，或 `theme = auto` 且系统为浅色 |
| **深色** | `theme = dark`，或 `theme = auto` 且系统为深色 |

- 切换入口：**系统配置页 → 常规设置**（`auto` / `light` / `dark` 三选一），非顶栏开关。
- 实现：`useSettings` 解析后写入 `<html data-theme="light|dark">`，token 在 `global.css` 的 `:root` 与 `[data-theme='dark']` 双份对齐。

### 3.2 色彩 token

| Token | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--bg-base` | `#FAFAFA` | `#1E1E1E` | 主背景 |
| `--bg-elevated` | `#FFFFFF` | `#252526` | 卡片/侧栏 |
| `--bg-hover` | `#F0F0F0` | `#2A2D2E` | hover 态 |
| `--border` | `#E5E5E5` | `#3C3C3C` | 边框/分割线 |
| `--text-primary` | `#1F1F1F` | `#D4D4D4` | 正文 |
| `--text-secondary` | `#6B6B6B` | `#858585` | 次要文字 |
| `--text-tertiary` | `#9A9A9A` | `#6B6B6B` | 说明文字 / 弱状态位（如「已保存 HH:mm:ss」） |
| `--accent` | `#3B82F6` | `#60A5FA` | 主交互（按钮/链接/激活项） |
| `--accent-hover` | `#2563EB` | `#3B82F6` | 主交互 hover |
| `--accent-soft` | `rgba(59,130,246,0.12)` | `rgba(96,165,250,0.18)` | 激活项底色 |
| `--success` | `#10B981` | `#34D399` | 成功提示 |
| `--warning` | `#F59E0B` | `#FBBF24` | 警告 / 未保存标记 |
| `--danger` | `#EF4444` | `#F87171` | 危险操作 |
| `--code-bg` | `#F4F4F5` | `#1E1E1E` | 代码块背景 |

### 3.3 结构 token

| 类别 | Token | 值 |
|---|---|---|
| 高度 | `--topbar-height` / `--statusbar-height` | 48px / 28px |
| 圆角 | `--radius-sm` / `--radius-md` / `--radius-lg` / `--radius-xl` | 4px / 6px / 8px / 10px |
| 字号 | `--font-size-xs` / `-sm` / `-md` / `-lg` / `-xl` | 11px / 12px / 14px / 15px / 20px |
| 阴影 | `--shadow-pop` / `--shadow-float` | 浮层 / 强浮层（仅用于浮层，层级 ≤3） |
| 字体 | `--font-main` / `--font-mono` | Inter 系 / JetBrains Mono 系 |

### 3.4 语义色

- ✅ 绿色 = 保存成功 / 健康 / 连接正常
- ⚠️ 黄色 = 警告（lint 警告 / 未保存标记）
- ❌ 红色 = 危险（删除 / 覆盖冲突 / 连接断开）
- 🔵 蓝色 = 信息 / 链接 / 激活项

---

## 四、组件库

**零第三方 UI 框架**：全部组件为项目内自研，样式集中在 `frontend/src/styles/global.css`（基于第三节 token 手写 CSS）。
运行时依赖仅 7 项：`react` / `react-dom` / `monaco-editor` / `@monaco-editor/react` / `marked` / `dompurify` / `turndown`，**不引入** UI 组件库、路由库、状态管理库。

### 4.1 通用基础组件

| 组件 | 位置 | 职责 |
|---|---|---|
| `Modal` | `components/Modal.tsx` | 通用弹窗；`embedded` 内嵌为页面区块，`headerless` 隐藏内嵌标题栏 |
| `Dropdown` | `components/Dropdown.tsx` | 通用下拉菜单，点击外部 / `Esc` 关闭 |
| `ConfirmDialog` | `components/ConfirmDialog.tsx` | 二次确认对话框 |
| `CommandPalette` | `components/CommandPalette.tsx` | `Ctrl+K` 命令面板；空查询展示「最近使用」 |
| `ErrorBoundary` | `components/ErrorBoundary.tsx` | 渲染异常兜底 |
| `MarkdownPreview` | `components/MarkdownPreview.tsx` | Markdown 预览（`marked` + `dompurify`） |

### 4.2 布局与导航

| 组件 | 位置 | 职责 |
|---|---|---|
| `SideNav` | `components/SideNav.tsx` | 左侧 4 项全局导航（跨页导航唯一入口） |
| `TopBar` | `components/TopBar.tsx` | 品牌 + Agent 计数 + 命令面板入口 + 重新扫描 |
| `StatusBar` | `components/StatusBar.tsx` | 底部状态栏；次要指标带 `metric-secondary` 语义 class；右端显示后端版本号（`v<版本>`，取自 `GET /api/health`） |
| `ViewToggle` | `components/ViewToggle.tsx` | 浏览模式切换（Agent / CORE 分类） |
| `AgentTree` / `FileTree` | `components/` | Agent 树 / 文件树 |
| `CoreBrowser` | `components/CoreBrowser.tsx` | `CoreCategoryList`（一级）+ `CoreAgentList`（二级，顶部可切换分类） |
| `EditorPane` | `components/EditorPane.tsx` | Monaco 编辑窗口（懒加载分包）；路径栏含角色徽标与保存状态位 |

### 4.3 页面与功能面板

| 页面组件 | 承载内容 | 路由 |
|---|---|---|
| `pages/ToolsPage.tsx` | 同步 / 超级同步 / 跨Agent编辑 / 对比 / 日志标准化 | `#/tools` |
| `pages/DataPage.tsx` | 统计面板 / 检查报告 / 审计日志 | `#/data` |
| `pages/SettingsPage.tsx` | 常规设置 / LLM Provider / 文档预设 | `#/settings` |

> 功能面板（`SyncModal` / `SuperSyncPanel` / `CrossEditModal` / `DiffModal` / `DailyStandardizerPanel` / `StatsModal` / `GlobalLintModal` / `AuditModal` / `SettingsModal` / `LLMProvidersModal` / `PresetModal`）在上述三页内以 `Modal embedded + headerless` 形式渲染，页面内**不出现第二层标题栏与「返回」按钮**（`SuperSyncPanel` / `DailyStandardizerPanel` 为普通面板，无 Modal 外壳）。

---

## 五、交互细节

### 5.1 文件编辑

- **视图模式**（工具栏「编辑 / 预览」，偏好全局记忆）：
  - **源码编辑（默认）**：Monaco 直接编辑 Markdown 源码，所见即所存，**不会改动格式**
  - **预览编辑**：可视化编辑，保存时会把 DOM 转回 Markdown → 列表/强调符号会被规范化、HTML 注释无法保留（表格对齐与任务列表已做保真处理）。工具栏常驻提示「预览保存会规范化 Markdown 格式」
  - 切换文件不再重置视图模式
- **保存快捷键**：`Cmd/Ctrl + S`；`Cmd/Ctrl + Shift + S` 保存全部未保存窗口
- **保存状态位**（编辑器路径栏，二者互斥显示）：
  - 有未保存修改 → `● 未保存`（`--warning` 色）
  - 无修改且已保存过 → `已保存 HH:mm:ss`（`--text-tertiary` 色），时间取最近一次成功保存
  - 自动保存与手动保存共用同一状态位
- **重新加载**：工具栏「重新加载」放弃未保存修改、重新读取磁盘版本（有修改时二次确认）
- **草稿保护**：未保存内容防抖 1.5s 写入 `localStorage`（单条上限 200KB）；重开应用时若发现草稿会询问「恢复 / 丢弃」。草稿在保存成功、关闭窗口、重新加载、删除文档时清除
- **会话恢复**：重开应用自动还原上次打开的编辑窗口（最多 3 个）与左侧选中的 Agent
- **关闭未保存提示**：关闭窗口 / 刷新页面时弹确认（`beforeunload`）
- **自动保存**：默认 **关闭**；开启后编辑暂停 **2s** 自动写入
- **保存前校验**：
  - 单文件 > 50KB → 提示「文件过大，确认保存？」
  - 内容为空 → 提示「将清空文件，确认？」
- **多窗口**：最多同时打开 **3** 个编辑窗口；`Ctrl/Cmd + 1/2/3` 切换、`Alt + W` 关闭当前；单窗口模式打开新文档将替换当前窗口
- **文档状态条**（编辑器底部）：`第 L 行, 第 C 列 · N 字符 · ≈T tokens`（预览模式隐藏行列），选中时显示已选字符数
  - token 为**估算值**：CJK 字符 ≈1 token/字，其余按 4 字符/token；超过 **2000** 转为警告色
- **lint 提示**：点「检查」后警告会**标在正文行内**（波浪线 + 悬浮显示规则与建议），`F8` / `Shift + F8` 在警告间跳转
- **文档大纲**：工具栏「大纲」或 `Cmd/Ctrl + Shift + O`，按 H1–H6 列出标题，点击跳转（预览模式下会先切回源码编辑）
- **设为预设**：工具栏「设为预设」→ 弹窗填写参数（预设名称 / 适用文件类型 / 用途说明 / 章节标题层级 / 必填章节勾选 / 是否严格要求顺序 / 是否要求 frontmatter）→ 保存为文档预设。
  - 来源区展示 `Agent/文件路径` + 字节数 + 当前层级标题数；勾选项由文档标题实时扫描得出（跳过围栏代码块内 `#`）
  - 文档超过 **30KB** 时提示并禁用保存（模板全文会注入 AI 提示词）
  - 保存成功后提示「已保存预设『X』（N 个必填章节）」，可在「系统配置 → 文档预设」查看、编辑与回溯
- **文档整理动作**：工具栏一级按钮「应用预设」（按预设补齐缺失章节）、「AI 整理」（LLM 重写）、「导出文件」——三者平铺于一行，**不再有「整理 ▾」下拉层级**
- **主工作台不出现日志预设**：「应用预设」与「AI 整理」的预设列表都取 `scope=workbench`（`GET /api/presets?scope=workbench`），因此**不含** WORKLOG 类（大模型专用）预设；列表为空时提示「没有可用于主工作台的预设」并指向「业务工具 → 日志标准化」
- **工具栏折行**：按钮既不收缩也不横向滚动；窗口可用宽度不足时**按行折行**，工具栏高度自适应（`min-height: 40px`）。窗口宽度 < **780px** 时隐藏源码编辑模式下的快捷键提示（`Ctrl+B / Ctrl+I / Ctrl+S`），优先保证动作按钮可见——
  折行阈值按**窗口宽度**判定（`@container` 容器查询），因为多窗口平铺时单个窗口的可用宽度远小于视口宽度

### 5.2 危险操作确认

**所有危险操作必须弹对话框二次确认**，不能只靠 Toast：

| 操作 | 确认级别 |
|---|---|
| 编辑单文件保存 | Toast 即可 |
| 跨 Agent 编辑保存 | Dialog 确认（显示影响 Agent 列表） |
| 回滚 | Dialog 确认 + **内嵌「当前内容 vs 该备份」差异预览**（`GET /api/diff/history`，差异加载中禁止确认） |
| 删除文档 | Dialog 确认（提示「移入回收站，可从系统回收站恢复」；未保存的文档先拒绝删除） |
| 删除备份 | Dialog 确认 + 输入「确认删除」 |

### 5.3 Lint 警告显示

- 文件树里有警告的文件 → 文件名右边小红点 ●
- 编辑器右侧 → 警告图标，点击跳到对应行
- 警告悬浮 → 显示规则名 + 建议改法
- **规则清单（在检查什么）**：权威位置只有一个——**数据中心 → 检查报告**顶部的可折叠「检查规则（N 条）」表格（规则 ID / 名称 / 级别 / 作用域 / 检查内容）。**默认收起；无警告时自动展开**（「什么都没查到」时最需要知道查了什么）
  - 规则文案由后端 `GET /api/lint/rules` 下发，前端只渲染，不写死
  - 编辑器「检查」面板头部提供「查看规则」按钮 → 直接跳到检查报告 tab（**不复制清单**，避免多份副本漂移）
  - 系统配置 → 常规设置的 Lint 开关下方给出同一指引文案

### 5.4 跨 Agent 编辑模式

跨 Agent 编辑已**页面化**（不再改变 TopBar 底色）：

- 入口：左侧导航「业务工具」→ 「跨Agent编辑」tab，或 `Ctrl+K` → 「跨 Agent 批量编辑」/ `Ctrl+Shift+E`
- 面板内显示：目标文件路径、候选 Agent 列表、编辑内容与影响范围
- 执行前需**确认对话框**（显示受影响 Agent 列表），执行后自动刷新已打开窗口

> 历史说明：v1.0 规范曾要求「TopBar 变红 + 全局模式标识」，P3 页面化后该做法已废弃，改为页面内上下文表达，避免全局视觉污染。

### 5.5 搜索与命令面板

**命令面板**（`Cmd/Ctrl + K`，顶栏搜索框点击亦可）：

- 单个输入框同时检索：页面导航（4 项） + 功能动作（11 项） + 文件内容
- 空查询时展示分组列表：**「最近使用」置顶**（MRU，上限 8 条，持久化到 `soulforge.palette.recent`），随后为 导航 / 操作 / 数据 / 管理，每组最多显示 6 条，底部提示可检索总量
- 文件检索为防抖 220ms 的异步查询，命中显示：`文件路径 · Agent ID · 行号 · 匹配内容摘要`
- 结果列表显示：`Agent ID · 文件路径 · 匹配行（高亮）`
- 点击结果 → 跳到对应文件 + 滚动到匹配行
- 键盘：`↑↓` 选择、`Enter` 执行、`Esc` 关闭

**高级搜索**（命令面板 → 「高级搜索文件内容」）：

- 支持按 Agent / 文件范围等条件过滤，结果可点击回跳并定位行

### 5.6 对比与同步工具（业务工具页）

**对比口径**（「对比」tab 底部开关，默认「忽略噪声」）：

| 口径 | 忽略范围 | 适用场景 |
|---|---|---|
| **忽略格式噪声**（默认） | BOM、换行符风格、零宽/不可见字符、全角空格与不换行空格、行尾空白、连续空白/缩进、多余空行、文首文末空行 | 判断「业务内容是否一致」——同一份 prompt 被不同工具/系统保存后仍应判为一致 |
| **严格** | 仅 BOM、换行符风格、零宽/不可见字符 | 需要确认空白与空行也确实一致时 |

**结果展示规则**

- `identical = true`（有效内容一致）→ **不再显示空的差异框**，改为显示绿色结论「内容完全一致，无差异」；
  若原始字节不同，追加一行说明「原始文件仅存在格式噪声差异（已忽略）：<噪声类型>」，**判定过程不静默**；
- `identical = false` → 显示行内高亮差异（`diff-add` / `diff-del` / `diff-hunk`）；
- 相似度在归一化文本上计算，**内容一致时恒为 100%**，不会再出现「看起来一样却显示 99%」；
- 默认 Agent A / B 自动选择为**两个不同 Agent**，不会出现「自己和自己比」。

**同步计划**（「同步」tab）：

- 逐文件展示差异 + 相似度；有效内容一致的文件标注「✓ 内容一致」徽标，并在计划顶部汇总「其中 N 个文件的有效内容已经一致，通常无需同步」；
- 执行确认弹窗中，若所选文件包含内容一致者会再次提示「同步只会改写其格式，业务内容不变」；
- 铁律不变：默认全部不勾选，绝不整文件覆盖，写入前自动备份目标 Agent。

### 5.7 日志标准化（业务工具页 · M15）

**三阶段单页流程**（`DailyStandardizerPanel`，内部 `stage` 切换，不跳页、不叠弹窗）：

| 阶段 | 内容 | 出口 |
|---|---|---|
| **参数** | Agent + 日期范围 + WORKLOG 预设 + provider + 附加指令；预设区自上而下 = **信息栏**（徽章「大模型专用」+ 预设名 + 版本 + 来源 +「查看 / 编辑」）→ 预设单选列表（**每个选项在名称下方显示一行功能简介**，文案取自后端 `presets.description`，前端不硬编码）→ 页内编辑弹窗；下方是该 Agent 的批次历史（行可点开复核，含状态 / 天数 / tokens / 创建时间） | 「生成计划」 |
| **逐日确认** | 每日一张卡片：来源 A/B/C 与剥壳前后体积、拟删碎片清单、强规则违规、备注、diff（默认可视化预览 + 可切「查看原始差异」）；生成中按 **1.5s** 轮询并显示进度。判定「无可归档内容」的日期改显示**判定理由 + 不产出文件 / 只清碎片的说明**，**不展示 diff** | 「执行选中 N 天」/「全部执行」/「跳过选中」/「拒绝整批」 |
| **验收报告** | 5 项核对（单文件 / 命名 / 章节 / 无残留壳 / 碎片已清）+ 逐日说明 + 汇总（已交付天数、tokens、成本） | 「返回计划」/「新建批次」/「重新核对」 |

**硬约束（与后端护栏一一对应，不得放宽）**：

- **默认全部不勾选**（与「同步」tab 同一铁律）：只有 `planned` 状态的日期可勾选；「全部执行」是显式动作，不靠「勾选数 = 0」隐式触发
- 写入前必须过二次确认弹窗，弹窗内**列全**将要执行的日期，**逐日标注动作**（「写入 X，并清理 N 个碎片」/「判定无可归档内容 → 不写日文件，只清理 N 个碎片」），并说明「写入前自动备份；碎片移入回收站；任一天被改动则整批不写」
- **「无可归档内容」不是失败**：该日不得显示为 `failed`/红字，不得显示「强规则未通过 0 项」，**不得展示 diff**（没有归并结果，展示会误报「与当前文件一致」）；必须显示模型给的一句话理由
- 主文件的处置必须说清：空日**不产出** `memory/YYYY-MM-DD.md`，且**已有的同名主文件保持不动**（该文件是 OpenClaw 系统自动生成的日文件，其它命名都只是碎片）
- 「拒绝整批」用 `btn-danger` + 二次确认；已是 `applied` / `partially_applied` / `rejected` 时禁用（与后端 `reject()` 一致）
- 生成中（`planned`）不显示勾选框；`failed` / `blocked` / `skipped` 的日期不可勾选
- 409 冲突提示必须列出**冲突日期**并指向解决方案（「请重新生成计划」），不只显示通用错误文案
- **不得谎报失败原因**：只在 `format_report.violations` 非空时才显示「强规则未通过」——
  该日根本没生成出内容（如 LLM 调用失败）时，只显示该日的真实 `error`，
  不能把「没有报告」当成「格式违规 0 项」展示；同理，`applicable = 0` 时顶部提示改为
  「本批没有可应用的日子」，不再显示「计划已生成…」（与第十节「不得用 0 冒充无问题」同一原则）
- **截断不等于内容不合规**：模型输出被 `max_tokens` 截断（`finish_reason` = `length` / `max_tokens`）时，
  该日的 `error` 必须是截断说明（`LLM_OUTPUT_TRUNCATED`）与「调大该 provider 的 `max_tokens`」的指引，
  **不得**显示成「强规则未通过 / 章节缺失」；后端已自动重试 1 次（预算翻倍），
  前端不需要也不得自行重试（会重复烧 token）
- **残留壳文案不暴露内部编号**：验收报告「无残留壳」与写前拦截的说明用规则名（`describe_shells()`），
  不出现 `M01`~`M12` 这类内部编号
- **同一用途不出现两个并列选项**（v1.11 收口）：WORKLOG 只有 `preset-wlog-daily-std` 一项。
  若将来还有语义相近的预设，应合并或明确区分「什么时候用哪个」，不得靠用户自己猜；
  已退役的内置预设由后端 `retired_at` 过滤，前端不参与判断
- **预设来源必须在本界面标明**（v1.14）：预设选择区上方必须有预设信息栏 —— 徽章「大模型专用」+
  预设名 + 版本 + 来源（`is_builtin` ? 「内置预设（随版本分发）」: 「用户自建」）+「查看 / 编辑」按钮，
  并说明「专供大模型处理工作日志」「不出现在文档预设页与主工作台」「修改后重新生成批次即生效」。
  这类预设按边界在主工作台看不到，不在这里标明身份与来源，用户就无处确认「当前生效的是哪个、从哪来、去哪改」
- **页内编辑器必须能改全部三类内容**（v1.14）：用途说明 / 模板文档（YAML 规则 + 章节骨架）/
  风格与内容规则（`style_rules`，每行一条，空行忽略）；保存走 `PUT /api/presets/{id}`（version +1），
  保存后提示「已保存为 vN」并刷新界面上的版本号 —— 但**不得**暗示会重算已生成的计划（只有新批次才用新规则）；
  模板必须含至少一个 `## ` 章节标题（章节列表由模板派生）
- **批量执行信息必须带上预设版本**（v1.14）：逐日确认页的信息条显示 `预设 v{N}`（= 批次创建时记录的
  `preset_version`），让用户知道这批用的是哪一版规则 —— 改预设不会回写已生成的计划

---

## 六、动效

| 场景 | 动效 |
|---|---|
| 页面切换 | 无（保持工作流连贯） |
| Toast 出现 | 顶部滑入，3 秒后自动消失 |
| 危险操作确认 | Dialog 缩放淡入 |
| Lint 警告出现 | 右侧滑入 |
| 文件树展开/收起 | 200ms ease |

**整体原则**：**少动效，专注工作流**。参考 Obsidian 哲学。

---

## 七、空状态 & 加载状态

### 7.1 加载状态

- 第一次打开 → 显示「正在发现 Agent...」+ 进度条
- 搜索时 → 输入框右侧转圈
- 保存时 → 按钮变 spinner

### 7.2 空状态

- 无 Agent → 显示「未找到任何 Agent，请检查 openclaw.json 配置」+ 「重新扫描」按钮
- 无文件 → 显示「这个 Agent 的 workspace 是空的」
- 无搜索结果 → 显示「没有匹配的内容」

---

## 八、可访问性

- **键盘可操作**：所有按钮支持 Tab 聚焦 + Enter 触发
- **快捷键**：

| 快捷键 | 功能 | 作用域 |
|---|---|---|
| `Cmd/Ctrl + S` | 保存当前激活窗口的编辑内容 | 全局 |
| `Cmd/Ctrl + Shift + S` | 保存全部未保存窗口 | 全局 |
| `Cmd/Ctrl + K` | 打开命令面板（导航 / 功能 / 文件 / 最近打开） | 全局 |
| `Cmd/Ctrl + B` | **加粗**（仅编辑器聚焦时；Markdown 源码模式） | 编辑器 |
| `Cmd/Ctrl + I` | 斜体（同上） | 编辑器 |
| `Cmd/Ctrl + 1 / 2 / 3` | 切换到第 N 个编辑窗口 | 工作台 |
| `Alt + W` | 关闭当前文档（有未保存修改会二次确认） | 工作台 |
| `Alt + 1` | 折叠 / 展开左栏（Agent 树） | 工作台 |
| `Alt + 2` | 折叠 / 展开中栏（文件树） | 工作台 |
| `Cmd/Ctrl + Shift + O` | 打开 / 关闭文档大纲 | 编辑器 |
| `F8` / `Shift + F8` | 跳到下一条 / 上一条 lint 警告 | 编辑器 |
| `↑ / ↓`（文件树聚焦时） | 上下移动并打开文件；`Esc` 清空过滤 | 工作台 |
| `Cmd/Ctrl + Shift + E` | 前往业务工具 → 跨 Agent 编辑 | 全局 |
| `Esc` | 关闭弹窗 / 命令面板 / 下拉菜单 | 全局 |

> **快捷键冲突说明**
> - 左栏折叠已由 `Alt + 1` 承担，`Ctrl/Cmd + B` 让位给 Markdown「加粗」（编辑器聚焦时生效，其余场景无绑定）。旧版 `Ctrl+B 折叠左栏` 已取消。
> - 关闭文档使用 `Alt + W` 而非 `Ctrl + W`：后者是浏览器保留键（关闭标签页），页面无法拦截。
> - `Alt + 1` / `Alt + 2`、`Ctrl + 1/2/3`、`Alt + W` 仅在 `#/workbench` 路由生效。

- **字体**：`Inter`（主）+ `JetBrains Mono`（代码/路径）
- **字号**：正文 14px（`--font-size-md`）/ 次要 12px（`--font-size-sm`）/ 区块标题 15px（`--font-size-lg`）/ 页面主标题 20px（`--font-size-xl`）

---

## 九、视觉参考

- **主参考**：VSCode（三栏布局）
- **次参考**：Obsidian（文件树 + Markdown 编辑）
- **不要参考**：Notion（太花哨）、飞书文档（功能太杂）

**老板审美倾向**：简洁、克制、专注。

---

## 十、文案规范

- **按钮文案**：用动词 + 名词（"保存"/"删除备份"/"跨 Agent 同步"）
- **按钮文案长度上限**：**最多 4 个汉字**（英文/数字不计入，如「AI 整理」「管理模型」）；更长的说明一律放 `title` 悬浮提示，不堆在按钮上
- **不用 emoji 按钮文案**（按钮上不用 emoji；导航/文件图标使用字符符号，如 `⌂ ⇄ ◇ ⚙`）
- **错误信息**：说人话 + 给解决方案（"保存失败：权限不足 → 请检查 workspace 路径权限"）
- **不堆技术 jargon**（不写 "500 Internal Server Error"，写 "保存失败：服务器内部错误"）
- **同一指标只能有一个数据源与一个口径**：实时指标（如 lint 计数）不得从索引列推测，也不得在两个界面各算一次——必须取同一接口、按同一口径计数；数据未取到时显示「检查中…」，**不得用 0 冒充「无问题」**（否则等于谎报安全）
- **同一界面元素的命名跨入口一致**（命令面板、页内 tab、弹窗标题用同一名字，如「统计面板」）

---

## 十一、规范与实现一致性核对表（M-08）

> 用途：**防止规范与实现再次漂移**。任何涉及下表数值的代码变更，须在同一次提交内更新本表。
> 核对方式：逐行对照「代码出处」列确认。

| 核对项 | 规范值 | 代码出处 |
|---|---|---|
| 断点集合 | 1440 / 1280 / 1024 / 768 | `styles/global.css` 的 `@media` 块 |
| 最小支持宽度 | 320px | `styles/global.css` `body { min-width: 320px }` |
| SideNav 宽度 | 64 / 56（≤1024）/ 48（≤768）px | `styles/global.css` `.side-nav` 及其媒体查询 |
| SideNav 导航项数 | 4（固定） | `components/SideNav.tsx` `NAV` 常量 |
| 顶栏常驻可点击入口数 | 2（命令面板入口 + 重新扫描） | `components/TopBar.tsx` JSX |
| 顶栏导航类按钮数 | 0 | `components/TopBar.tsx`（不得新增） |
| TopBar / StatusBar 高度 | 48px / 28px | `styles/global.css` `--topbar-height` / `--statusbar-height` |
| 状态栏隐藏项（≤1280px） | 索引文件数、上次扫描 | `components/StatusBar.tsx` `.metric-secondary` + `global.css` |
| 左栏宽度 | 默认 240px，范围 180–360px | `App.tsx` `LEFT_WIDTH_RANGE` / `LAYOUT_DEFAULT` |
| 中栏宽度 | 默认 280px，范围 200–400px | `App.tsx` `MID_WIDTH_RANGE` / `LAYOUT_DEFAULT` |
| 折叠恢复条宽度 | 32px | `styles/global.css` `.pane-collapsed-bar` |
| 编辑窗口上限 | 3 | `App.tsx` `MAX_WINDOWS` |
| 命令面板索引动作数 | 15（4 导航 + 11 功能） | `App.tsx` `paletteItems` |
| 命令面板最近使用上限 | 8 | `App.tsx` `MAX_RECENT_COMMANDS` |
| 命令面板空查询每组上限 | 6 | `components/CommandPalette.tsx` `MAX_PER_GROUP` |
| 命令面板文件检索防抖 | 220ms | `components/CommandPalette.tsx` |
| CORE 下拉滚动容器高度 | `min(320px, 50vh)` | `styles/global.css` `.core-agent-list .dropdown-menu` |
| 对比默认归一化口径 | `ignore_whitespace` | `backend/app/services/diff_service.py` `MODE_IGNORE_WHITESPACE` |
| 对比噪声类型集合 | 8 种（bom / line_ending / invisible_char / space_like_char / trailing_whitespace / multiple_spaces / blank_lines / edge_blank_lines） | `diff_service.py` `_NOISE_STAGES` |
| 相似度行级降级阈值 | 20000 字符 | `diff_service.py` `LINE_SIMILARITY_THRESHOLD` |
| 差异视图渲染口径 | `display_text`（保留空行与缩进） | `diff_service.py` `display_text` |
| 自动保存防抖 | 2s | `App.tsx` 自动保存 effect |
| 编辑器默认视图模式 | `edit`（源码编辑） | `components/EditorPane.tsx` `loadViewMode` |
| 文档 token 提示阈值 | 2000 | `EditorPane.tsx` `TOKEN_WARN_THRESHOLD` |
| 编辑器工具栏折行阈值 | 780px（低于则隐藏 `Ctrl+B / Ctrl+I / Ctrl+S` 提示；按窗口宽度而非视口宽度判定） | `styles/global.css` `.editor-toolbar` 的 `@container` 块 + `.kbd-hint` |
| lint 计数数据源 | `GET /api/lint/all`（唯一来源；按报告中列出的条数计，含 error 级） | `App.tsx`（状态栏 + Agent 角标）、`components/StatsModal.tsx`（统计面板卡片）、`components/GlobalLintModal.tsx`（检查报告） |
| `/api/stats` 是否含 lint 计数 | 否（索引列 `files.lint_warnings` 恒为 0，不得暴露） | `backend/app/models/schemas.py` `StatsResult` + `tests/test_misc_api.py` |
| 统计面板 / 命令面板命名 | 「统计面板」 | `components/StatsModal.tsx` `title` / `App.tsx` `paletteItems` / `pages/DataPage.tsx` tab |
| 大纲面板宽度 | 260px | `styles/global.css` `.outline-panel` |
| 编辑器状态条高度 | 22px | `styles/global.css` `.editor-statusline` |
| 草稿单条体积上限 | 200KB | `App.tsx` `DRAFT_MAX_BYTES` |
| 会话恢复窗口上限 | 3（同 `MAX_WINDOWS`） | `App.tsx` 会话恢复 effect |
| 最近打开文件上限 | 8 | `App.tsx` `MAX_RECENT_FILES` |
| 页面级内嵌面板数（需 `headerless`） | 9（Tools 3 + Data 3 + Settings 3） | `pages/ToolsPage.tsx` / `DataPage.tsx` / `SettingsPage.tsx` |
| 业务工具页 tab 数 | 5（同步 / 超级同步 / 跨Agent编辑 / 对比 / 日志标准化） | `pages/ToolsPage.tsx` `Tab` 联合类型 + tab 数组 |
| 日志标准化默认勾选数 | 0（铁律：默认全部不勾选，与同步一致） | `components/DailyStandardizerPanel.tsx` `checked` 初值 + 「全部执行」是否走显式 `applyAll` |
| 日志标准化生成期轮询间隔 | 1500ms（仅在 `status === 'planned'` 时轮询） | `components/DailyStandardizerPanel.tsx` 轮询 effect |
| 日志标准化预设简介文案来源 | 后端 `presets.description`（前端只渲染，不硬编码；空则显示「（该预设未填写说明）」） | `components/DailyStandardizerPanel.tsx` `.daily-preset-desc` + `api.listPresets('WORKLOG')` |
| 空日（`empty`）是否可勾选 | 仅当该日有 B/C 碎片待清理时可勾选；无碎片则不可勾选（无动作） | `components/DailyStandardizerPanel.tsx` `isApplicable()`（`planned` 或 `empty && fragments_to_delete.length > 0`） |
| 空日状态色 | 中性灰（`--bg-hover` + `--text-secondary`），**不得用 danger 红** | `styles/global.css` `.daily-status.empty` |
| 残留壳检测口径 | 真壳规则 M01~M10（`SHELL_RULES`；M11/M12 归一不计入），文案用规则名 | `backend/app/services/daily_preprocessor.py` `SHELL_RULES` / `detect_residual_shells()` / `describe_shells()` |
| 截断自动重试次数 | 1 次（预算翻倍，封顶 32768），仍截断则 `422` / `LLM_OUTPUT_TRUNCATED` | `backend/app/services/llm_registry.py` `_TRUNCATION_RETRY_CEILING` + `LLMClient.chat()` |
| 「大模型专用」预设的判据 | `target_file_type = WORKLOG`（不加额外开关字段） | `backend/app/services/preset_service.py` `DAILY_PRESET_TYPE` |
| 文档预设页 / 主工作台取预设的范围 | `scope=workbench`（排除 WORKLOG 类） | `PresetModal.tsx` `load()`、`ApplyPresetModal.tsx`、`ApplyAIModal.tsx` 的 `api.listPresets(undefined, 'workbench')`；`preset_service.py` `SCOPE_WORKBENCH` |
| 日志标准化界面的预设来源展示 | 徽章「大模型专用」+ 版本 + 来源（后端 `is_builtin`）+「查看 / 编辑」 | `components/DailyStandardizerPanel.tsx` `.daily-preset-info`；`preset_service.py` `BUILTIN_PRESET_IDS` |
| 页内编辑器可改字段数 | 3（用途说明 / 模板文档 / 风格与内容规则） | `components/DailyPresetEditor.tsx` |
| 状态栏版本号来源 | `GET /api/health` 的 `data.version` | `App.tsx` 初始加载 effect；`components/StatusBar.tsx` `.statusbar-version` |
| 运行时依赖数 | 7（零新增） | `package.json` `dependencies` |
| localStorage 键全集 | `soulforge.settings`、`soulforge.editor.mode`、`soulforge.editor.view`、`soulforge.browse.mode`、`soulforge.intro-v3`、`soulforge.layout`、`soulforge.session`、`soulforge.drafts`、`soulforge.recent.files`、`soulforge.palette.recent`、`soulforge.filetree.collapsed`、`soulforge.filetree.warnOnly` | 各实现处 |