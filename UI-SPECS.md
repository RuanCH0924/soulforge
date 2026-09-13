# Soulforge — UI 设计规范

> 设计目标：**桌面单页 Web 应用**，浏览器全屏使用，**侧边导航 + 三栏布局**（Agent 树 / 文件树 + 编辑器）。
> 类似 VSCode / Obsidian 的工作流气质，但更轻。
> 用户：老板（单人本地自托管）。

> **文档职责划分（M-08）**
> - 本文档 = **视觉与尺寸规范事实源**：布局结构、断点、尺寸、设计 token、组件规范、交互与文案约定。
> - `docs/UI-REDESIGN-PLAN.md` = **架构与演进事实源**：信息架构、页面划分、里程碑与验收记录。
> - `docs/UI-OPTIMIZATION-PLAN.md` = 体验层优化措施（M-01~M-08）与验证指标。
> - 任何涉及断点 / 尺寸 / token / 顶栏入口数的代码变更，须在同一次提交内更新第十一节的一致性核对表。

### 修订记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | — | 初版（桌面三栏、≥1280px 强制） |
| v1.1 | 2026-09-02 | M-08 同步实现：加入侧边导航、四档断点、最小宽度 320px、自定义组件清单、Alt 折叠快捷键、一致性核对表 |
| v1.2 | 2026-09-02 | 文档编辑体验升级：默认视图模式改为源码编辑、`Ctrl+B` 让位给加粗、新增多窗口/大纲/lint 跳转快捷键、新增草稿保护与会话恢复、回滚增加 diff 预览、文件树支持过滤与键盘导航 |
| v1.3 | 2026-09-02 | 对比工具专项修复：新增文本归一化两档口径（忽略格式噪声 / 严格）、`identical` 与 `noise_kinds` 结果字段、一致时的明确结论展示、同步计划标注「内容一致」、默认 A/B 不再选到同一 Agent |

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
| StatusBar（28px） | 连接态 + 索引文件数 + 上次扫描 + lint 警告数；≤1280px 隐藏中间两项（索引文件数 / 上次扫描） |
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
| `StatusBar` | `components/StatusBar.tsx` | 底部状态栏；次要指标带 `metric-secondary` 语义 class |
| `ViewToggle` | `components/ViewToggle.tsx` | 浏览模式切换（Agent / CORE 分类） |
| `AgentTree` / `FileTree` | `components/` | Agent 树 / 文件树 |
| `CoreBrowser` | `components/CoreBrowser.tsx` | `CoreCategoryList`（一级）+ `CoreAgentList`（二级，顶部可切换分类） |
| `EditorPane` | `components/EditorPane.tsx` | Monaco 编辑窗口（懒加载分包）；路径栏含角色徽标与保存状态位 |

### 4.3 页面与功能面板

| 页面组件 | 承载内容 | 路由 |
|---|---|---|
| `pages/ToolsPage.tsx` | 同步 / 超级同步 / 跨Agent编辑 / 对比 | `#/tools` |
| `pages/DataPage.tsx` | 统计仪表盘 / 健康检查报告 / 审计日志 | `#/data` |
| `pages/SettingsPage.tsx` | 常规设置 / LLM Provider / 文档预设 | `#/settings` |

> 功能面板（`SyncModal` / `SuperSyncPanel` / `CrossEditModal` / `DiffModal` / `StatsModal` / `GlobalLintModal` / `AuditModal` / `SettingsModal` / `LLMProvidersModal` / `PresetModal`）在上述三页内以 `Modal embedded + headerless` 形式渲染，页面内**不出现第二层标题栏与「返回」按钮**。

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

### 5.4 跨 Agent 编辑模式

跨 Agent 编辑已**页面化**（不再改变 TopBar 底色）：

- 入口：左侧导航「业务工具」→ 「跨Agent编辑」tab，或 `Ctrl+K` → 「跨 Agent 批量编辑」/ `Ctrl+Shift+E`
- 面板内显示：目标文件路径、候选 Agent 列表、编辑内容与影响范围
- 执行前需**确认对话框**（显示受影响 Agent 列表），执行后自动刷新已打开窗口

> 历史说明：v1.0 规范曾要求「TopBar 变红 + 全局模式标识」，P3 页面化后该做法已废弃，改为页面内上下文表达，避免全局视觉污染。

### 5.5 搜索与命令面板

**命令面板**（`Cmd/Ctrl + K`，顶栏搜索框点击亦可）：

- 单个输入框同时检索：页面导航（4 项） + 功能动作（13 项） + 文件内容
- 空查询时展示分组列表：**「最近使用」置顶**（MRU，上限 8 条，持久化到 `soulforge.palette.recent`），随后为 导航 / 操作 / 数据 / 管理，每组最多显示 6 条，底部提示可检索总量
- 文件检索为防抖 220ms 的异步查询，命中显示：`文件路径 · Agent ID · 行号 · 匹配内容摘要`
- 结果列表显示：`Agent ID · 文件路径 · 匹配行（高亮）`
- 点击结果 → 跳到对应文件 + 滚动到匹配行
- 键盘：`↑↓` 选择、`Enter` 执行、`Esc` 关闭

**高级搜索**（命令面板 → 「高级搜索文件内容」）：

- 支持按 Agent / 文件范围等条件过滤，结果可点击回跳并定位行

### 5.6 对比与同步工具（业务工具页）

**对比口径**（「对比」tab 底部开关，默认「忽略格式噪声」）：

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
- **不用 emoji 按钮文案**（按钮上不用 emoji；导航/文件图标使用字符符号，如 `⌂ ⇄ ◇ ⚙`）
- **错误信息**：说人话 + 给解决方案（"保存失败：权限不足 → 请检查 workspace 路径权限"）
- **不堆技术 jargon**（不写 "500 Internal Server Error"，写 "保存失败：服务器内部错误"）

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
| 命令面板索引动作数 | 17（4 导航 + 13 功能） | `App.tsx` `paletteItems` |
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
| 大纲面板宽度 | 260px | `styles/global.css` `.outline-panel` |
| 编辑器状态条高度 | 22px | `styles/global.css` `.editor-statusline` |
| 草稿单条体积上限 | 200KB | `App.tsx` `DRAFT_MAX_BYTES` |
| 会话恢复窗口上限 | 3（同 `MAX_WINDOWS`） | `App.tsx` 会话恢复 effect |
| 最近打开文件上限 | 8 | `App.tsx` `MAX_RECENT_FILES` |
| 页面级内嵌面板数（需 `headerless`） | 11（Tools 5 + Data 3 + Settings 3） | `pages/ToolsPage.tsx` / `DataPage.tsx` / `SettingsPage.tsx` |
| 运行时依赖数 | 7（零新增） | `package.json` `dependencies` |
| localStorage 键全集 | `soulforge.settings`、`soulforge.editor.mode`、`soulforge.editor.view`、`soulforge.browse.mode`、`soulforge.intro-v3`、`soulforge.layout`、`soulforge.session`、`soulforge.drafts`、`soulforge.recent.files`、`soulforge.palette.recent`、`soulforge.filetree.collapsed`、`soulforge.filetree.warnOnly` | 各实现处 |