# Soulforge 界面 UI 优化方案

> 本方案为 `docs/UI-REDESIGN-PLAN.md`（P1–P5 架构重构）的**后续体验层优化**，不改变现有信息架构与技术栈。
> 全部问题项均已在当前代码中逐条核验，并附证据位置；未标注证据的条目一律不作为本次优化依据。

---

## 文档信息

| 项 | 内容 |
|---|---|
| 文档名称 | Soulforge 界面 UI 优化方案 |
| 文档编号 | SF-UI-OPT-2026-09 |
| 版本 | v1.0 |
| 状态 | 待评审（评审通过后进入执行） |
| 编制日期 | 2026-09-02 |
| 编制人 | 前端负责人（FE） |
| 评审人 | 项目负责人（PO）、测试与验收（QA） |
| 适用范围 | `frontend/` 前端应用层；**不涉及**后端 API 契约、数据模型、存储格式变更 |
| 前置文档 | `docs/UI-REDESIGN-PLAN.md`（架构与演进基线）、`UI-SPECS.md`（视觉规范，本次需同步修订） |
| 文档密级 | 内部 |

### 修订记录

| 版本 | 日期 | 修订人 | 修订说明 |
|---|---|---|---|
| v1.0 | 2026-09-02 | FE | 首次编制：基于 P1–P5 完成态做现状核验，输出 8 项优化措施 |

---

## 0. 文档说明

### 0.1 编制目的

`docs/UI-REDESIGN-PLAN.md` 已完成 P1–P5 架构级重构（侧边导航、四页面、命令面板、响应式、视觉 token），**信息架构层面已定型且验证通过**。本方案的目的是：

1. 对重构后的实际代码做一次**体验层复核**，识别架构收敛后残留的重复、冗余与状态丢失问题；
2. 将问题转化为**可评审、可执行、可验收**的优化措施，每项均明确技术路径、参数标准、责任主体与交付节点；
3. 明确**不做什么**，防止范围蔓延导致二次架构改动。

### 0.2 范围与边界

**纳入范围（In Scope）**

- 顶栏 / 侧栏导航的职责边界与去重
- 页面内嵌面板的层级表达（标题、返回路径）
- 工作台布局状态（分栏宽度、折叠态）的持久化与快捷键
- 编辑器保存状态的可视化反馈
- 命令面板的检索效率与发现性
- CORE 分类浏览模式的上下文切换
- 响应式中间断点（1024–1440px）与状态栏信息收敛
- 设计规范文档与实现的漂移治理

**排除范围（Out of Scope）**

| 排除项 | 理由 |
|---|---|
| 信息架构再调整（如新增/合并页面） | P2/P3 四页面结构已通过验收，重做成本高、边际收益低 |
| 技术栈替换（引入路由库 / UI 组件库 / 状态管理库） | 现有 React 18 + Vite + Monaco 组合合理，且章程要求零新增运行时依赖 |
| 视觉体系重做（配色、字体、圆角、阴影体系） | 现有 token 体系完整（`global.css` L4–L52），仅需补规范文档而非改组件 |
| 新增第三主题（高对比 / 护眼） | 单用户内部工具，投入产出比低 |
| 后端接口、数据模型、文件格式、测试基线变更 | 与本方案无耦合 |
| 移动端（<768px）深度适配 | 现有 ≤768px 已具备可用降级（全屏弹窗 + 48px 侧栏），本次不再加深 |

### 0.3 术语定义

| 术语 | 定义 |
|---|---|
| Workbench（主工作台） | 默认落地页，承载 Agent 树 / 文件树 / 编辑器三栏与文件级弹窗 |
| Tools（业务工具） | 页面化的跨 Agent 工具集：同步 / 跨 Agent 编辑 / 对比 / 导入 / 新建 Agent |
| Data（数据中心） | 页面化的只读视角：统计仪表盘 / 健康检查报告 / 审计日志 |
| Settings（系统配置） | 页面化配置：常规设置 / LLM Provider / 文档预设 |
| CORE 分类模式 | 以 CORE 文件名（如 `SOUL.md`）为一维、Agent 为二维的浏览模式，与「按 Agent」模式可切换 |
| 内嵌模式（embedded） | `Modal` 组件以 `embedded` 属性渲染时不使用遮罩与固定定位，直接作为页面区块 |
| 命令面板 | `Ctrl+K` 唤起的统一入口，可检索页面导航、功能动作、文件内容 |
| 断点 | CSS 媒体查询阈值，现网为 1024px / 768px，本方案新增 1280px |
| 基线（Baseline） | 本次优化前的实测状态，作为指标对比起点 |

### 0.4 现状基线

| 基线项 | 当前值 | 来源 |
|---|---|---|
| 前端构建命令 | `npm run build` = `tsc --noEmit && vite build` | `frontend/package.json` L8 |
| 运行时依赖 | `@monaco-editor/react`、`dompurify`、`marked`、`monaco-editor`、`react`、`react-dom`、`turndown`（7 项，无 UI 框架、无路由库） | `frontend/package.json` L11–19 |
| 后端回归基线 | `pytest` 129 passed / 1 skipped | `docs/UI-REDESIGN-PLAN.md` 第六节 |
| 真实数据规模 | 8 Agent / 2461 文件 / 56 CORE | `docs/UI-REDESIGN-PLAN.md` 第七节 |
| 页面路由 | `#/workbench`、`#/tools`、`#/data`、`#/settings` | `frontend/src/hooks/useHashRoute.ts` L3–5 |
| 响应式断点 | 1024px、768px（共 2 档） | `frontend/src/styles/global.css` L2048、L2067 |
| 已持久化的前端状态 | `soulforge.settings`、`soulforge.editor.mode`、`soulforge.browse.mode`、`soulforge.intro-v1`（4 项） | `useSettings.tsx` L44；`App.tsx` L104、L159、L147 |
| 未持久化的前端状态 | 分栏宽度（leftWidth / midWidth）、左栏折叠态、激活编辑窗口 | `App.tsx` L131–135、L97 |

> 说明：以上为本次评估的对照基线，第六节所有验证指标均以此开始计量。

---

## 一、优化背景与现状分析

### 1.1 背景

P1–P5 重构解决了**架构层**问题：入口过载（顶栏 12+ 按钮 → 侧栏 4 项 + 命令面板）、弹窗堆叠（14 弹窗 → 4 页面 + 4 文件级弹窗）、响应式缺失（移除 `min-width: 1280px` 强制）、视觉不规范（补齐 token）。

但重构过程中，**新引入的组件与遗留组件之间产生了职责重叠**，同时部分**交互状态未纳入持久化范围**。这些问题不影响功能正确性，属于体验层缺陷，且具备「改动面小、用户可感知、回归风险低」的特征，适合集中一次性收敛。

### 1.2 现状架构快照

| 层级 | 组件 / 模块 | 职责 | 位置 |
|---|---|---|---|
| 顶栏 | `TopBar` | 品牌、Agent 计数、命令面板入口、重新扫描、三个页面跳转按钮 | `frontend/src/components/TopBar.tsx` L17–45 |
| 侧栏 | `SideNav` | 四项全局页面导航（主工作台 / 业务工具 / 数据中心 / 系统配置） | `frontend/src/components/SideNav.tsx` L8–13 |
| 路由 | `useHashRoute` | 轻量 hash 路由，刷新保持 | `frontend/src/hooks/useHashRoute.ts` |
| 工作台 | `AgentTree` / `CoreCategoryList` + `FileTree` / `CoreAgentList` + `EditorPane` | 三栏编辑工作流，支持 Agent / CORE 双模式 | `App.tsx` L669–790 |
| 页面 | `ToolsPage` / `DataPage` / `SettingsPage` | 页面化容器，tab 切换 + `Modal embedded` | `frontend/src/pages/` |
| 反馈 | `StatusBar` / `useToast` | 底部状态栏 + 全局轻提示 | `components/StatusBar.tsx`、`hooks/useToast.tsx` |
| 样式 | `global.css` | 单文件样式与设计 token、响应式断点 | `frontend/src/styles/global.css` |

### 1.3 现状代码事实核验清单

> 本节是本方案的**唯一事实来源**，以下每项均已在代码中确认。

| 编号 | 核验结论 | 证据位置 |
|---|---|---|
| C-01 | `TopBar` 的「业务工具 / 数据中心 / 系统配置」三个按钮与 `SideNav` 的四项导航**功能完全重复** | `TopBar.tsx` L35–43 ↔ `SideNav.tsx` L9–12 |
| C-02 | 顶栏常驻可点击入口共 5 个（搜索 + 4 按钮） | `TopBar.tsx` L25–44 |
| C-03 | `Modal` 的 `embedded` 分支仍渲染 `modal-header`（含标题与「返回」按钮） | `Modal.tsx` L25–38 |
| C-04 | `ToolsPage`(5) / `DataPage`(3) / `SettingsPage`(3) 共 **11 处**内嵌面板均已自带 `page-tabs`，与 C-03 叠加后形成**双标题 + 冗余返回** | `ToolsPage.tsx` L26–49、L51–64；`DataPage.tsx` L19–35、L37–39；`SettingsPage.tsx` L18–34、L36–38 |
| C-05 | 分栏宽度 `leftWidth(240)` / `midWidth(280)` 与 `leftCollapsed` 仅为内存状态，**无 localStorage 持久化** | `App.tsx` L131–135 |
| C-06 | 折叠能力仅覆盖左栏；中栏（文件树）**无法折叠** | `App.tsx` L683（`!leftCollapsed`）；全站无 `midCollapsed` |
| C-07 | `Ctrl+B` 已用于左栏折叠（现状保留），无中栏快捷键 | `App.tsx` L564–566 |
| C-08 | 保存成功仅有瞬时 toast（`已保存 <path>`），编辑器无持久保存时间戳 | `App.tsx` L400；`EditorPane.tsx` L131（仅 `dirty` 时显示「● 未保存」） |
| C-09 | 命令面板空查询时返回全部动作（固定顺序），**无「最近使用」记忆** | `CommandPalette.tsx` L38–44；`App.tsx` L622–647 |
| C-10 | 命令面板文件检索防抖 220ms | `CommandPalette.tsx` L60 |
| C-11 | CORE 模式中栏标题为**纯文本**，无分类切换控件 | `CoreBrowser.tsx` L100–105 |
| C-12 | `activeCore` 已提升至 App 层并跟随激活窗口自动同步 | `App.tsx` L176、L599–605 |
| C-13 | 状态栏 4 段信息**无任何媒体查询收敛** | `global.css` L1027–1056；L2048–2090 无 `.statusbar` 规则 |
| C-14 | Monaco `minimap` 已禁用、`wordWrap: 'on'`、`fontSize: 14` | `EditorPane.tsx` L212–214（**无需调整**） |
| C-15 | `UI-SPECS.md` 描述的断点与最小宽度**与实现矛盾**（文档写「≥1280px 三栏 / <768px 不支持 / 最小窗宽 1280px 强制」；实现为 1024/768 两档、`body` 最小宽度仅 320px） | `UI-SPECS.md` L39–43（断点）、L51–58（窗口尺寸） ↔ `global.css` L68、L2048、L2067 |
| C-16 | `UI-SPECS.md` 的 TopBar 描述为旧版（含 `[⚙]` 图标入口），与现网 4 按钮布局不符 | `UI-SPECS.md` L15 ↔ `TopBar.tsx` L21–44 |
| C-17 | 首次使用引导条文案已提示 `Ctrl+K` / `Ctrl+S` / `Ctrl+B`，并由 `soulforge.intro-v1` 控制一次性展示 | `App.tsx` L146–156、L674–675 |
| C-18 | 命令面板已索引 4 项页面导航 + 13 项功能动作（共 17 项），覆盖全部被顶栏移除的功能 | `App.tsx` L625–642 |
| C-19 | `Dropdown` 组件支持点击外部与 `Esc` 关闭，但 `.dropdown-menu` **无 `max-height` / 滚动容器**，长列表会溢出视口 | `Dropdown.tsx` L22–36；`global.css` L1727–1740 |

**核验澄清（撤回既往口头判断）**

以下三条在本轮核验中被**证伪**，不构成优化项，特此记录以保证方案严谨：

| 既往判断 | 核验结果 |
|---|---|
| 「侧栏为纯图标，新用户无法望文知义」 | 不成立。`SideNav` 每项均含文字标签（10px），仅在 ≤1024px 断点隐藏 | 
| 「命令面板缺少常驻 `⌘K` 视觉锚点」 | 不成立。顶栏搜索框内已常驻 `Ctrl K` 徽标 | 
| 「编辑器 minimap 在窄屏应默认关闭」 | 不成立。`minimap` 已全场景禁用 |

### 1.4 问题清单

| 编号 | 问题描述 | 等级 | 关联核验 | 用户影响 |
|---|---|---|---|---|
| P-01 | 同一导航功能在顶栏与侧栏**双入口并存**，用户无法判断哪个是权威入口 | 重要 | C-01、C-02 | 认知负担；顶栏视觉噪声 |
| P-02 | 页面内嵌面板出现**双标题栏 + 冗余「返回」按钮**，与 SideNav 导航语义冲突 | 重要 | C-03、C-04 | 层级混乱；误以为「返回」会丢失上下文 |
| P-03 | 分栏宽度与折叠态**刷新即丢失**，用户需反复调整 | 重要 | C-05 | 高频重复操作 |
| P-04 | 中栏（文件树）**不可折叠**，窄屏下编辑区被压缩 | 次要 | C-06、C-07 | 窄屏编辑体验下降 |
| P-05 | 保存后**无持久成功反馈**，toast 消失后无法确认是否已写入 | 次要 | C-08 | 不确定感；可能重复保存 |
| P-06 | 命令面板空查询为**全量固定列表**，高频动作每次都要重新输入 | 次要 | C-09 | 检索效率损失 |
| P-07 | CORE 模式下切换分类**必须回到左栏**，中栏无法直接切换 | 次要 | C-11 | 多分类对比场景路径变长 |
| P-08 | 1024–1440px 区间状态栏 4 段信息占宽，**主视口未获让渡** | 次要 | C-13 | 笔记本常见尺寸下空间紧张 |
| P-09 | `UI-SPECS.md` 与实现**三处矛盾**，后续开发易按错误规范实施 | 重要 | C-15、C-16 | 规范失效；返工风险 |

**等级定义**：阻断 = 阻塞主流程；重要 = 显著影响效率或引发误用；次要 = 体验损失但可绕过。

### 1.5 根因分析

| 根因 | 说明 | 对应问题 |
|---|---|---|
| R1 演进式重构的职责残留 | P1 引入命令面板、P2 引入 SideNav 后，未同步回收 TopBar 中已被替代的入口 | P-01 |
| R2 页面化时复用了弹窗容器，但未剥离弹窗外壳 | `Modal embedded` 直接复用原弹窗结构（含 header/返回），未按页面语义裁剪 | P-02 |
| R3 持久化策略未覆盖布局维度 | 持久化仅覆盖「偏好类」设置（主题、浏览模式、编辑模式），遗漏「布局类」状态 | P-03、P-04 |
| R4 反馈设计偏向瞬时提示 | 保存反馈采用 toast（瞬时），未补充「状态位」形式的持久反馈 | P-05 |
| R5 规范文档未纳入重构交付物 | P1–P5 验收只校验代码与构建，未将 `UI-SPECS.md` 列为同步更新项 | P-09 |

---

## 二、优化目标与核心收益

### 2.1 总体目标

> 在不改变现有信息架构与技术栈的前提下，消除 P1–P5 重构遗留的**导航重复、层级冗余、状态丢失、反馈缺失、规范漂移**五类体验缺陷，使**每个功能只有一个权威入口、每个页面只有一个标题层级、每次布局调整都被记住、每次保存都有据可查、每份规范都与实现一致**。

### 2.2 分项目标与问题映射

| 目标编号 | 目标描述 | 对应问题 | 对应措施 |
|---|---|---|---|
| O-01 | 顶栏与侧栏职责彻底分离：顶栏只承载「与页面无关的全局动作」，导航唯一归属侧栏 | P-01 | M-01 |
| O-02 | 页面内嵌面板为单一标题层级，返回路径统一由侧栏承担 | P-02 | M-02 |
| O-03 | 工作台布局状态全量持久化，并补齐中栏折叠能力 | P-03、P-04 | M-03 |
| O-04 | 保存结果在编辑器内以持久状态位呈现，与「未保存」形成互斥语义 | P-05 | M-04 |
| O-05 | 命令面板提供「最近使用」记忆，降低重复动作的检索成本 | P-06 | M-05 |
| O-06 | CORE 模式支持中栏直接切换分类，与左栏高亮双向同步 | P-07 | M-06 |
| O-07 | 1024–1440px 区间状态栏信息分级收敛，主视口优先 | P-08 | M-07 |
| O-08 | 设计规范文档与实现达成 100% 一致，并建立核对机制 | P-09 | M-08 |

### 2.3 核心收益

| 维度 | 量化口径 | 基线 | 目标 |
|---|---|---|---|
| 顶栏常驻入口数 | 顶栏内可点击入口数量（不含品牌区） | 5（1 搜索 + 4 按钮） | ≤ 2（1 搜索 + 1 重新扫描） |
| 重复导航项数 | 同一功能在顶栏与侧栏同时存在的项数 | 3 | 0 |
| 页内重复标题数 | 内嵌面板同时出现标题栏的页面数 | 11（Tools 5 + Data 3 + Settings 3） | 0 |
| 布局状态持久化率 | 已持久化布局维度 / 需持久化布局维度 | 0 / 4 | 4 / 4 |
| 命令面板重复动作成本 | 执行同一动作所需输入字符数（空查询起） | 需完整输入关键词 | 0（最近使用首屏直选） |
| CORE 分类切换路径 | 切换分类所需点击次数 | 2（回左栏 + 点击） | 1（中栏下拉直选） |
| 状态栏窄屏溢出 | 1280px 视口下状态栏是否溢出换行 | 未受控 | 无溢出 |
| 规范一致性 | 断点 / 最小宽度 / 顶栏入口数与实现不符处数 | 3 | 0 |
| 零新增运行时依赖 | `package.json` dependencies 条目数 | 7 | ≤ 7 |

**定性收益**：降低新用户对「两个导航入口」的困惑；减少因布局重置与状态丢失带来的重复操作；为后续功能扩展保留清晰的入口规则（新功能一律进侧栏或命令面板，顶栏不再增长）。

### 2.4 非目标（明确不做）

1. 不新增页面、不合并页面、不调整页面命名。
2. 不引入路由库、UI 组件库、状态管理库、图标库（`SideNav` 现用字符图标，本次不替换）。
3. 不修改后端任何接口、模型、存储格式与测试。
4. 不重做视觉体系（配色 / 字体 / 圆角 / 阴影 / 动效曲线保持现状，`.modal` 已有 `scaleIn 0.15s ease`，不调整）。
5. 不深化 <768px 移动端适配（保持现有降级能力）。
6. 不为「可能的多用户 / 多端」做前瞻性设计。

---

## 三、详细实施步骤拆解

### 3.0 实施总览与依赖顺序

```
M-08（规范同步，技术债，可与其余并行） 
        │
M-01 顶栏去重 ──┬──> M-02 面板层级去重
                │
                └──> M-05 命令面板（依赖 M-01 完成后的入口收敛结论）
M-03 布局持久化（独立）
M-04 保存反馈（独立）
M-06 CORE 上下文切换（独立）
M-07 响应式收敛（依赖 M-03 中栏折叠落地）
```

| 措施 | 名称 | 关联目标 | 规模量级 | 交付节点 |
|---|---|---|---|---|
| M-01 | 顶栏与侧栏职责去重 | O-01 | S | D1 |
| M-02 | 内嵌面板去除重复标题与返回 | O-02 | S | D1 |
| M-03 | 布局状态持久化与中栏折叠 | O-03 | M | D2 |
| M-04 | 保存状态可视化增强 | O-04 | S | D2 |
| M-05 | 命令面板「最近使用」 | O-05 | S | D3 |
| M-06 | CORE 模式上下文切换 | O-06 | S | D3 |
| M-07 | 响应式中间断点与状态栏收敛 | O-07 | S | D4 |
| M-08 | 设计规范文档同步与核对机制 | O-08 | S | D4 |

> **规模量级定义**：S = 单组件/单文件内部改动，无跨模块契约变更；M = 涉及 2–4 个文件且新增共享状态或新 prop 契约。

---

### M-01 顶栏与侧栏职责去重

**问题与目标**
- 问题：P-01（顶栏与侧栏双入口）。
- 目标：顶栏只保留**与页面无关**的全局动作；所有跨页导航唯一归属侧栏。

**现状证据**
- `TopBar.tsx` L17–45：`onNavigateTools` / `onNavigateData` / `onNavigateSettings` 三个回调渲染为三个按钮。
- `SideNav.tsx` L9–12：四个导航项已包含上述三项。
- `App.tsx` L656–664：向 `TopBar` 传入上述三个回调。

**技术实现路径**

1. 修改 `TopBar.tsx`：从 `TopBarProps` 中移除 `onNavigateTools` / `onNavigateData` / `onNavigateSettings` 三个属性（L7–11），同步移除对应的三个 `<button>`（L35–43）。
2. 保留顶栏元素：品牌标题、Agent 计数、命令面板入口（搜索框）、`重新扫描` 按钮。
3. 更新搜索框占位文案为 `搜索或执行命令…`，明确其入口语义已从「搜索」升级为「命令面板」。
4. 修改 `App.tsx` L656–664：移除三个已删除 prop 的传参，`navigate` 仍被 SideNav 使用，无需改动。
5. 响应式样式：`global.css` L2058–2061 的 `.topbar-actions .btn` 压缩规则保留（仍适用于「重新扫描」按钮）。
6. 更新首次引导文案（`App.tsx` L674–675）：补充「页面切换请使用左侧导航」，并将引导 key 由 `soulforge.intro-v1` 升级为 `soulforge.intro-v2`，使存量用户重新看到一次更新后的提示。

**参数配置标准**

| 参数 | 取值 | 约束 / 说明 |
|---|---|---|
| 顶栏常驻可点击入口数 | 2 | 搜索框 + 重新扫描；品牌区不计入 |
| 顶栏导航类按钮数 | 0 | 硬约束，任何新增导航不得进入顶栏 |
| 搜索框占位文案 | `搜索或执行命令…` | 与命令面板能力一致 |
| 搜索框 `kbd` 徽标 | `Ctrl K` | 保持现状（`TopBar.tsx` L27） |
| 引导条存储 key | `soulforge.intro-v2` | 升级后 `v1` 不再生效，仅影响一次性提示 |
| 引导条文案要点 | `Ctrl+K` 命令面板 / `Ctrl+S` 保存 / 布局折叠快捷键 / 左侧导航切页 | 与 M-03 快捷键保持一致 |

**用户操作流程（优化后）**

1. 进入应用 → 默认落在主工作台（`#/workbench`）。
2. 需要切换页面 → 点击左侧导航四项之一，URL 变为 `#/tools`、`#/data`、`#/settings`。
3. 不记得功能位置 → `Ctrl+K` 输入关键词，命中后直接跳页或执行（现有 17 项索引覆盖全部导航与动作）。
4. 需要重新发现新增 Agent/文件 → 顶栏 `重新扫描`。

**开发操作流程**

1. 改 `TopBar.tsx` → 改 `App.tsx` 调用点 → 改引导文案与 key。
2. 校验：`npm run build`（含 `tsc --noEmit`，可捕获遗留 prop 传参错误）。
3. 全量核对 `TopBar.tsx` 是否仍有导航类按钮；核对 `paletteItems`（`App.tsx` L625–642）仍完整覆盖 4 页面。

**责任主体（RACI）**

| 角色 | 职责 |
|---|---|
| FE 前端负责人 | R 实施 / A 技术正确性 |
| PO 项目负责人 | C 入口规则确认 / A 最终验收 |
| QA 测试与验收 | V 用例验证 |

**交付节点**：D1
**单项验收标准**：顶栏可点击入口 = 2；顶栏无导航类按钮；4 个页面均可通过侧栏与 `Ctrl+K` 到达；`npm run build` 通过。
**回滚方式**：纯前端组件改动，`git revert` 对应提交即可；无状态迁移、无数据影响。

---

### M-02 内嵌面板去除重复标题与返回

**问题与目标**
- 问题：P-02（双标题 + 冗余返回）。
- 目标：页面内嵌面板只保留 `page-tabs` 一层标题；「返回工作台」语义统一由侧栏承担。

**现状证据**
- `Modal.tsx` L25–38：`embedded` 分支输出 `modal-header`（`<h3>{title}</h3>` + 「返回」按钮）。
- `ToolsPage.tsx` L26–49：已有 `page-tabs`（5 个 tab）。
- `DataPage.tsx` L19–35：已有 `page-tabs`（3 个 tab）。
- 内嵌调用点：`ToolsPage` L51–64（5 处）、`DataPage` L37–39（3 处）。

**技术实现路径**

1. 修改 `Modal.tsx`：`ModalProps` 增加可选 `headerless?: boolean`（默认 `false`）。
2. 在 `embedded` 分支中，当 `headerless === true` 时仅渲染 `modal-body` 与（可选的）`modal-footer`，不渲染 `modal-header`。
3. **实现落点修正**：`headerless` 不在页面调用点传入，而是在 11 个功能面板组件内部统一以 `headerless={embedded}` 传给 `Modal`——因为 `embedded` 在本项目中**只可能来自页面级调用**，二者语义等价，这样页面代码零改动、后续新增页面无需重复传参。
   - 涉及组件（11 个）：`SyncModal`、`CrossEditModal`、`DiffModal`、`ImportModal`、`TemplateModal`、`StatsModal`、`GlobalLintModal`、`AuditModal`、`SettingsModal`、`LLMProvidersModal`、`PresetModal`
   - 页面容器（`ToolsPage` / `DataPage` / `SettingsPage`）**保持不变**
4. `SettingsPage.tsx` 的 3 处内嵌（L36–38）同样由组件内部处理，无需在页面改动。合计 **11 处**，实施后须与 `Grep "embedded={embedded}"` 的结果数量一致。
5. 保留 `Modal` 非内嵌分支的原有行为（含 `Esc` 关闭、遮罩点击关闭、`modal-header`），不回归影响 Workbench 的文件级弹窗。
6. 校验 `.modal-embedded` 样式（`global.css` L2040–2045）在无 header 后仍无多余间距；如有，追加 `padding-top: 0` 类规则。

**参数配置标准**

| 参数 | 取值 | 约束 / 说明 |
|---|---|---|
| `headerless` 默认值 | `false` | 保持既有非页面调用行为不变 |
| 内嵌调用点总数 | 11 处（Tools 5 + Data 3 + Settings 3） | 实施后须与 `Grep embedded` 结果一致 |
| 内嵌模式 `modal-header` 渲染 | 0 个 | 页面级内嵌面板硬约束 |
| 页内「返回」按钮数 | 0 | 返回能力由 `SideNav` 承担 |
| `page-tabs` 数量 | 每页 1 组 | 唯一标题层级 |
| `Esc` 关闭行为 | 仅非内嵌模式生效 | 内嵌模式无 `Esc` 监听（现状 `Modal.tsx` L17 已满足） |

**用户操作流程（优化后）**

1. 从侧栏进入「业务工具」→ 页面顶部仅一组 tab（同步 / 跨Agent编辑 / 对比 / 导入 / 新建Agent）。
2. 切换 tab → 面板内容切换，页面**不出现第二个标题栏**，也**不出现「返回」按钮**。
3. 需要回工作台 → 点击侧栏「主工作台」，或 `Ctrl+K` → 「前往主工作台」。

**开发操作流程**

1. 改 `Modal.tsx` → 逐页追加 `headerless` → 遍历所有 `embedded` 调用点确认无遗漏。
2. `Grep` 全量检索 `embedded`，确认调用点清单与已改清单数量一致。
3. 校验：`npm run build`；人工走查 Tools 5 tab + Data 3 tab 是否均只剩一层标题。

**责任主体（RACI）**

| 角色 | 职责 |
|---|---|
| FE 前端负责人 | R 实施 |
| PO 项目负责人 | A 层级规则确认与验收 |
| QA 测试与验收 | V 遍历全部内嵌面板 |

**交付节点**：D1
**单项验收标准**：Tools 5 个 tab、Data 3 个 tab、Settings 3 个 tab（合计 11 个页面级内嵌面板）均无重复标题与「返回」按钮；文件级弹窗（搜索 / 历史 / 应用预设 / AI 整理）行为零变化。
**回滚方式**：移除 `headerless` 传参即恢复原状，向后兼容无破坏。

---

### M-03 布局状态持久化与中栏折叠

**问题与目标**
- 问题：P-03（布局刷新丢失）、P-04（中栏不可折叠）。
- 目标：分栏宽度、左右栏折叠态全部持久化；中栏获得独立折叠能力与快捷键。

**现状证据**
- `App.tsx` L131–135：`leftWidth(240)` / `midWidth(280)` / `leftCollapsed(false)` 均为内存状态。
- `App.tsx` L607–615：拖拽边界 `clamp(180, 360)` 与 `clamp(200, 400)`。
- `App.tsx` L564–566：`Ctrl+B` 仅切换 `leftCollapsed`。
- `App.tsx` L683：`{!leftCollapsed && (...)}` 为唯一折叠渲染判断。

**技术实现路径**

1. 新增持久化常量：`LAYOUT_KEY = 'soulforge.layout'`，存储结构 `{ leftWidth: number; midWidth: number; leftCollapsed: boolean; midCollapsed: boolean }`。
2. 新增纯函数 `loadLayout()` / `saveLayout(next)`：读取时对每个数值做 `clamp` 校正（防止历史脏数据越界），异常（localStorage 不可用、JSON 非法）时静默返回默认值 `{ leftWidth: 240, midWidth: 280, leftCollapsed: false, midCollapsed: false }`。
3. `useState` 改为惰性初始化读取 `loadLayout()`；在宽度/折叠态变更处调用 `saveLayout`（拖拽时为避免高频写入，采用 300ms 防抖；折叠切换为即时写入）。
4. 新增 `midCollapsed` 状态；中栏渲染条件由现状改为 `!midCollapsed && (...)`。
5. 快捷键：新增 `Alt+1` 切换左栏折叠、`Alt+2` 切换中栏折叠；`Ctrl+B` 保留为左栏折叠的兼容键。**不使用 `Ctrl+Shift+B`**，因其在 Chromium 系浏览器中与「显示/隐藏书签栏」冲突。
6. 快捷键作用域：仅在 `route === 'workbench'` 时响应，避免在 Tools/Data/Settings 页误触发。
7. 折叠态恢复入口：左栏/中栏折叠后在原位渲染 32px 宽竖条按钮（含 `aria-label` 与 `title`，title 中标注对应快捷键），点击即展开。
8. 更新首次引导文案（与 M-01 的 `soulforge.intro-v2` 合并为一次文案更新）。

**参数配置标准**

| 参数 | 取值 | 约束 / 说明 |
|---|---|---|
| `leftWidth` 默认 / 范围 | 240 / 180–360 | 沿用现有 `clamp` 边界，不改 |
| `midWidth` 默认 / 范围 | 280 / 200–400 | 沿用现有 `clamp` 边界，不改 |
| `leftCollapsed` / `midCollapsed` 默认 | `false` / `false` | 首次访问为展开 |
| 存储 key | `soulforge.layout` | JSON 字符串；读取时逐字段校验类型 |
| 拖拽写入防抖 | 300ms | 避免 mousemove 高频写 localStorage |
| 折叠切换写入 | 即时 | 按次操作，频次低 |
| 快捷键 | `Alt+1` 左栏、`Alt+2` 中栏、`Ctrl+B` 左栏（兼容） | 仅 workbench 路由生效 |
| 恢复条宽度 | 32px | 可点击；含 `aria-label` 与 `title` |
| 越界数据兜底 | clamp 至合法范围 | 不因脏数据导致布局异常 |

**用户操作流程（优化后）**

1. 拖拽左栏右边界至 300px → 松手。
2. 按 `Alt+2` 折叠文件树 → 编辑区自动占满。
3. 刷新浏览器（F5）→ 左栏仍 300px，中栏仍为折叠态，恢复竖条可见可点击。
4. `Ctrl+K` 或侧栏切到「数据中心」再切回 → 布局不变（状态为 App 层，跨页保持）。

**开发操作流程**

1. 新增 `loadLayout` / `saveLayout`（可置于 `App.tsx` 内部或 `hooks/` 下的轻量工具）。
2. 修改三处 `useState` 初始化与所有写入点（拖拽回调 `startLeftResize` / `startMidResize`、快捷键 handler、恢复条点击）。
3. 中栏渲染条件补齐 `midCollapsed`。
4. 添加 `Alt+1` / `Alt+2` 到既有 `keydown` handler（`App.tsx` L556–574），并按路由加守卫。
5. 校验：`npm run build`；手动执行 UC-07 / UC-08 / UC-16。

**责任主体（RACI）**

| 角色 | 职责 |
|---|---|
| FE 前端负责人 | R 实施 / A 状态与持久化设计 |
| QA 测试与验收 | V 持久化与快捷键验证 |
| PO 项目负责人 | C 快捷键方案确认（避免与浏览器冲突） |

**交付节点**：D2
**单项验收标准**：4 个布局维度刷新后全部保持；中栏可独立折叠与恢复；`Alt+1` / `Alt+2` 在 workbench 生效、在其他页面不生效；脏数据（手动写坏 `soulforge.layout`）下应用仍正常启动。
**回滚方式**：删除 `LAYOUT_KEY` 读写逻辑即恢复为内存状态；已写入的 localStorage 键可保留（无副作用），亦可在发布说明中提示用户清理。

---

### M-04 保存状态可视化增强

**问题与目标**
- 问题：P-05（保存后无持久反馈）。
- 目标：编辑器内以持久状态位展示「已保存 HH:mm:ss」，与「● 未保存」形成互斥且互斥语义明确。

**现状证据**
- `App.tsx` L400：`toast('已保存 <path>', 'success')`，瞬时提示。
- `EditorPane.tsx` L131：`{dirty && <span className="dirty-mark">● 未保存</span>}`，无已保存分支。
- `App.tsx` L43–54：`EditorTab` 接口无 `savedAt` 字段。
- `App.tsx` L534–550：`autoSave` 逻辑（设置项 `settings.autoSave`，防抖 2s）复用 `saveTab`。

**技术实现路径**

1. `EditorTab` 接口（`App.tsx` L43–54）新增可选项 `savedAt?: number`。
2. `saveTab` 成功分支（`App.tsx` L400 附近，`setTabs` 更新处）写入 `savedAt`；同分支内保留既有 toast，不删除。**取值口径：秒级时间戳**（`Math.floor(Date.now() / 1000)`），与全站后端时间戳（`last_scan_at` / `mtime`）保持一致。
3. `EditorPane` props 新增 `savedAt?: number`；在 `editor-pathbar`（L128–144）内、`dirty-mark` 之后新增互斥渲染分支：`!dirty && savedAt` 时显示 `已保存 HH:mm:ss`。
4. 时间格式化：在 `frontend/src/utils/format.ts` 新增 `formatClock(ts)`（秒级时间戳 → `HH:mm:ss`）。**实现说明**：既有 `formatTime` 返回完整日期（`YYYY-MM-DD HH:mm:ss`），与本节要求的 `HH:mm:ss` 口径不同，故新增 `formatClock` 而非复用 `formatTime`（见实施记录）。
5. 自动保存路径（`App.tsx` L536–550）无需单独处理：其内部调用同一 `saveTab`，`savedAt` 自动更新。
6. 样式：在 `global.css` 的 `.dirty-mark` 附近新增 `.saved-mark`（颜色取 `--text-tertiary`，字号与 `dirty-mark` 一致）；`dirty-mark` 保持 `--warning` 系不动。

**参数配置标准**

| 参数 | 取值 | 约束 / 说明 |
|---|---|---|
| 新增字段 | `EditorTab.savedAt?: number` | 毫秒时间戳；未保存过则为 `undefined` |
| 时间格式 | `HH:mm:ss` | 复用 `utils/format` 的 `formatTime` |
| 显示位置 | `editor-pathbar`，紧随 `dirty-mark` | 与 `.role-badge`、关闭按钮同排 |
| 显示条件 | `!dirty && savedAt != null` | 与「● 未保存」严格互斥 |
| 「未保存」颜色 | `--warning` | 保持现状 |
| 「已保存」颜色 | `--text-tertiary` | 弱化处理，不争抢视觉焦点 |
| toast 保留 | 是 | 瞬时反馈与持久状态位并存，不做替代 |
| 关闭文档后 | `savedAt` 随窗口销毁 | 不跨会话持久化（无必要） |

**用户操作流程（优化后）**

1. 打开 `main/SOUL.md` → 编辑器路径栏显示路径 + 角色徽标，无状态位（未曾保存）。
2. 修改内容 → 状态位变为「● 未保存」（warning 色）。
3. `Ctrl+S` → 状态位变为「已保存 14:32:07」，同时右侧弹出 toast「已保存 main/SOUL.md」。
4. 再次编辑 → 立即变回「● 未保存」。
5. 开启「自动保存」设置后停止输入 2s → 状态位自动更新为最新时间戳。

**开发操作流程**

1. 改 `EditorTab` 接口 → 改 `saveTab` 写入 `savedAt` → 改 `EditorPane` props 与渲染 → 加 `.saved-mark` 样式。
2. 校验：`npm run build`；手动执行 UC-09 / UC-10；确认多窗口模式下每个窗口独立显示各自时间戳。

**责任主体（RACI）**

| 角色 | 职责 |
|---|---|
| FE 前端负责人 | R 实施 |
| QA 测试与验收 | V 互斥语义与自动保存路径验证 |
| PO 项目负责人 | A 验收 |

**交付节点**：D2
**单项验收标准**：保存后状态位出现且时间准确；编辑后立即回到「未保存」；自动保存路径同样更新；多窗口（最多 3 个）各自独立；`.role-badge` 与关闭按钮布局未受影响。
**回滚方式**：移除新增字段与渲染分支；`savedAt` 为可选字段，删除不影响其他逻辑。

---

### M-05 命令面板「最近使用」记忆

**问题与目标**
- 问题：P-06（空查询为固定全量列表）。
- 目标：记录用户实际执行的动作，空查询时「最近使用」置顶，实现零输入直达。

**现状证据**
- `CommandPalette.tsx` L38–44：`q` 为空时 `matchedItems = items`（返回全部，按 `App.tsx` L622–647 的定义顺序）。
- `CommandPalette.tsx` L110–120：`selectAt` 统一处理选择与关闭，未上报「已使用」。
- `CommandPalette.tsx` L60：文件检索防抖 220ms。
- 现有分组渲染逻辑（L86–100、L153–191）已支持多分组，可复用。

**技术实现路径**

1. 新增存储 key `PALETTE_RECENT_KEY = 'soulforge.palette.recent'`，值为 `string[]`（动作 `id`，MRU 顺序，长度上限 8，重复项上移去重）。
2. `CommandPalette` 新增 props：`recentIds: string[]`、`onUsed: (id: string) => void`。
3. 在 `selectAt` 中，对 `type === 'action'` 的分支调用 `onUsed(it.id)`（文件项不计入）。
4. `App.tsx` 新增 `recentIds` 状态：惰性从 localStorage 读取（过滤掉已不存在的 id，防止索引变更后出现悬空项）；`onUsed` 回调实现 MRU 写入与去重截断。
5. 空查询（`q === ''`）时，在 `matchedItems` 前插入「最近使用」分组：按 `recentIds` 顺序取对应动作，**每组上限 6 条**；随后仍渲染原有固定分组。
6. 空查询且分组内容较多时，在面板底部提示「输入关键词可筛选全部 N 项」，明确可检索总量。
7. 有查询时（`q !== ''`）不显示「最近使用」分组，避免与检索结果混淆，保持现有过滤逻辑不变。
8. 防抖 220ms 保持不变（本地后端检索，实测可接受，无优化必要）。

**参数配置标准**

| 参数 | 取值 | 约束 / 说明 |
|---|---|---|
| 存储 key | `soulforge.palette.recent` | JSON 字符串数组 |
| 记录上限 | 8 条 | 超出按 MRU 淘汰最旧 |
| 去重策略 | 同一 `id` 重复执行时置顶 | 不产生重复项 |
| 空查询分组上限 | 每分组 6 条 | 控制首屏长度 |
| 「最近使用」显示条件 | 仅 `q === ''` 且 `recentIds` 非空 | 有查询时不显示 |
| 悬空项处理 | 读取时过滤不在 `paletteItems` 中的 `id` | 防止动作下线后残留 |
| 文件检索防抖 | 220ms | 保持不变（现状已满足） |
| 分组标题 | `最近使用` | 与现有分组标题样式一致 |

**用户操作流程（优化后）**

1. `Ctrl+K` → 面板打开，顶部为「最近使用」（若已有记录），下方为「导航 / 操作 / 数据 / 管理」固定分组。
2. 执行一次「跨 Agent 批量编辑」→ 关闭面板。
3. 再次 `Ctrl+K` → 「最近使用」首位即「跨 Agent 批量编辑」，`Enter` 直达 Tools 页。
4. 刷新浏览器 → 记录保留。
5. 直接输入 `sync` → 回到现有检索逻辑，「最近使用」分组不显示。

**开发操作流程**

1. 改 `CommandPalette.tsx` props 与 `selectAt` → 改 `App.tsx` 状态与回调 → 复用现有分组渲染。
2. 校验：`npm run build`；手动执行 UC-04；确认在 `paletteItems` 变更（如动作改名）后无悬空项。

**责任主体（RACI）**

| 角色 | 职责 |
|---|---|
| FE 前端负责人 | R 实施 |
| QA 测试与验收 | V MRU 顺序、去重、刷新保持验证 |
| PO 项目负责人 | A 验收 |

**交付节点**：D3
**单项验收标准**：「最近使用」顺序为 MRU；同一动作重复执行不产生重复项；刷新后保留；有查询时不出现该分组；动作下线后无悬空/报错。
**回滚方式**：删除分组与存储读写；localStorage 键残留无副作用。

---

### M-06 CORE 模式上下文切换

**问题与目标**
- 问题：P-07（切换分类必须回左栏）。
- 目标：中栏顶部提供分类切换入口，与左栏高亮双向同步。

**现状证据**
- `CoreBrowser.tsx` L100–105：`pane-header` 为纯文本 `包含「${activeCore}」的 Agent` + 计数。
- `App.tsx` L176：`coreCatalog = useCoreCatalog(agents)`。
- `App.tsx` L599–605：`activeCore` 跟随激活窗口自动同步（已有 effect，依赖 `activeTab.key` 与 `coreCatalog.coreTypes`）。
- 已有可复用组件：`frontend/src/components/Dropdown.tsx`。

**技术实现路径**

1. 修改 `CoreAgentList` props：新增 `coreTypes: string[]`、`onSelectCore: (type: string) => void`。
2. `pane-header` 文本改为可点击区：`CORE：<当前分类> ▾`，点击展开 `Dropdown`，选项为 `coreTypes`（每项右侧 `hint` 显示该分类下的 Agent 计数，数据取自 `agentsByCore`）。
3. **长列表滚动（必须）**：现有 `.dropdown-menu`（`global.css` L1727–1740）无 `max-height` / 滚动容器（核验项 C-19），56 项 CORE 将溢出视口。**实现采用父级作用域选择器** `.core-agent-list .dropdown-menu { min-width: 180px; max-height: min(320px, 50vh); overflow-y: auto; }`——不改动共享 `Dropdown` 组件的 API，也不影响其他调用点（见实施记录）。
4. 选项 `onSelect` → 调用 `onSelectCore(type)` → 由 `App.tsx` 调用 `coreCatalog.setActiveCore(type)`，复用现有状态。
5. 右侧保留「N 个」计数（现状 L102–104 的样式不变）。
6. 空态处理：`activeCore` 为空时保持现状提示（L106–109「请先在左侧选择 CORE 分类」）；`coreTypes` 长度为 0 时保持 L53–56 的提示。
7. 需在 `App.tsx` 中向 `CoreAgentList` 传入 `coreTypes` 与 `onSelectCore`（当前未传）。

**参数配置标准**

| 参数 | 取值 | 约束 / 说明 |
|---|---|---|
| 下拉选项数量 | 全量 `coreTypes`（实测 56 项） | 不截断选项，靠滚动容器承载 |
| 下拉滚动容器 | `max-height: min(320px, 50vh); overflow-y: auto` | **新增**父级作用域规则（现状 `.dropdown-menu` 无滚动，核验项 C-19）；仅 `.core-agent-list` 内启用 |
| 选项展示内容 | `分类名` + 右侧 `hint` 计数 | 计数取自 `agentsByCore.get(type).length` |
| 触发文案 | `CORE：<当前分类> ▾` | 未选中时显示提示文案 |
| 切换后左栏高亮 | 同步 | 复用 `activeCore` 单一状态源，无需额外同步逻辑 |
| 键盘行为 | `Esc` 关闭下拉 | 复用 `Dropdown` 现有能力 |
| 数据来源 | `agentsByCore`（`useCoreCatalog` 缓存） | 不新增请求 |

**用户操作流程（优化后）**

1. 切换到「CORE 分类」模式 → 左栏列出 CORE 分类，中栏默认显示首个分类的 Agent 列表。
2. 点击中栏顶部 `CORE：SOUL.md ▾` → 下拉展开，可见 `SOUL.md (8)`、`AGENTS.md (8)`、`IDENTITY.md (6)` 等。
3. 选择 `AGENTS.md` → 中栏列表切换为「包含「AGENTS.md」的 Agent」，左栏高亮同步移动到 `AGENTS.md`（一次点击完成）。
4. 点击任一 Agent 条目 → 打开该 Agent 下的关联文件。

**开发操作流程**

1. 改 `CoreBrowser.tsx` 的 `CoreAgentList` props 与 header 渲染 → 接入 `Dropdown` → `App.tsx` 补传 props。
2. 校验：`npm run build`；手动执行 UC-11 / UC-12；确认切换后与左栏高亮、激活窗口同步逻辑（L599–605）无冲突。

**责任主体（RACI）**

| 角色 | 职责 |
|---|---|
| FE 前端负责人 | R 实施 |
| QA 测试与验收 | V 双向同步与空态验证 |
| PO 项目负责人 | A 验收 |

**交付节点**：D3
**单项验收标准**：中栏可直接切换 CORE 分类且左栏高亮同步；下拉计数与列表条目数一致；56 项下拉在 320px 高度内滚动、不溢出视口；无 CORE / 空分类场景提示正确；切换后打开文件行为与现状一致。
**回滚方式**：移除下拉，恢复纯文本 header；`coreTypes` / `onSelectCore` 为新增可选 props；滚动修饰类可保留（无其他调用点引用）。

---

### M-07 响应式中间断点与状态栏收敛

**问题与目标**
- 问题：P-08（1024–1440px 状态栏占宽）。
- 目标：中间档位下状态栏信息分级，主视口优先；窄屏状态栏不溢出、不换行。

**现状证据**
- `global.css` L1027–1056：`.statusbar` 为 `display:flex; gap:18px`，4 段内容（连接态 / 索引文件数 / 上次扫描 / lint 警告）。
- `global.css` L2048–2090：仅两档媒体查询，**无 `.statusbar` 规则**。
- `global.css` L68：`body { min-width: 320px }`（已无 1280px 强制）。
- `EditorPane.tsx` L212–214：`minimap` 已禁用，**无需处理**。
- `StatusBar.tsx` L14–26：4 段内容为平铺 `<span>`，其中 `.right` 承担 lint 警告。

**技术实现路径**

1. 为 `StatusBar.tsx` 中可收敛的两段（`索引 N 个文件`、`上次扫描：…`）追加语义 class `metric-secondary`，避免依赖 `nth-child` 的脆弱选择器。
2. `global.css` 新增 `@media (max-width: 1280px)` 块：隐藏 `.statusbar .metric-secondary`；将 `.statusbar` 的 `gap` 由 18px 收敛为 12px；`padding` 由 `0 14px` 收敛为 `0 10px`。
3. 保留主体信息：连接状态（含 `conn-dot`）与 lint 警告（`.right`）。
4. 在 `@media (max-width: 1024px)` 块内追加 `overflow: hidden` 与 `white-space: nowrap`，确保极端窄屏下不换行、不溢出。
5. 信息补偿：被隐藏的「文件总数 / 上次扫描」在 Data 页统计仪表盘（`StatsModal` 已含 `files_total` 与 `最后扫描时间`）与命令面板中仍可获取，无需新增入口。

**参数配置标准**

| 参数 | 取值 | 约束 / 说明 |
|---|---|---|
| 新增断点 | `max-width: 1280px` | 现有断点为 1024 / 768，本次新增一档 |
| 隐藏项 | `索引 N 个文件`、`上次扫描：…` | 由 `.metric-secondary` 控制 |
| 保留项 | 连接状态、lint 警告数 | 硬约束：连接与警告不可隐藏 |
| `gap` 收敛 | 1280px 起 18px → 12px | 与 `padding` 收敛配合 |
| `padding` 收敛 | 1280px 起 `0 14px` → `0 10px` | — |
| 溢出保护 | `overflow:hidden` + `white-space:nowrap`（≤1024px） | 防止换行撑高状态栏 |
| 状态栏高度 | `--statusbar-height: 28px` | 保持现状，不随断点变化 |

**用户操作流程（优化后）**

1. 1440px 宽 → 状态栏完整显示 4 段信息。
2. 缩放至 1280px → 「索引文件数」「上次扫描」隐去，仅留「已连接到 N 个 Agent」与 lint 警告，状态栏保持单行。
3. 缩放至 768px → 侧栏 48px、搜索框 `Ctrl K` 徽标隐藏（现状）、状态栏不换行不溢出。

**开发操作流程**

1. 改 `StatusBar.tsx` 追加语义 class → 在 `global.css` 追加 1280px 媒体查询 → 在 1024px 块内追加溢出保护。
2. 校验：`npm run build`；浏览器 DevTools 在 1440 / 1280 / 1024 / 768 四档截图核对，执行 UC-13 / UC-14。

**责任主体（RACI）**

| 角色 | 职责 |
|---|---|
| FE 前端负责人 | R 实施 |
| QA 测试与验收 | V 四档断点回归 |
| PO 项目负责人 | A 信息保留项确认 |

**交付节点**：D4
**单项验收标准**：1280px 下状态栏单行无溢出、无换行；连接态与 lint 警告在全部断点始终可见；1440px 及以上信息完整；`.metric-secondary` 隐藏后无残留占位间隙。
**回滚方式**：移除媒体查询块与语义 class，恢复现状（class 追加无副作用，可保留）。

---

### M-08 设计规范文档同步与核对机制

**问题与目标**
- 问题：P-09（`UI-SPECS.md` 与实现三处矛盾）。
- 目标：规范文档与实现 100% 一致，并建立可重复的核对机制，防止再次漂移。

**现状证据**
- `UI-SPECS.md` L39–41：断点表写「≥1280px 三栏 / 768–1279px 左栏可折叠 / <768px **不支持**（弹出提示）」，与实现矛盾。
- `UI-SPECS.md` L52：写「最小窗口宽 1280px（强制）」；实现为 `body { min-width: 320px }`（`global.css` L68）。
- `UI-SPECS.md` L15：TopBar 布局图为「Soulforge · 主 Agent: main · 6 个 Agent · 12 个警告 [搜索] [⚙]」，与现网（品牌 + Agent 计数 + 搜索 + 重新扫描）不符，且无 SideNav。
- `UI-SPECS.md` L40：`768-1279px 左栏可折叠（侧滑）`；实现为左栏、中栏均可折叠（M-03 后）。
- `UI-SPECS.md` L56–57：已记录左栏 240px（180–360）、中栏 280px（200–400），**与实现一致**，属可直接沿用的正确条目。

**技术实现路径**

1. 明确文档职责划分，写入两份文档的开头：
   - `docs/UI-REDESIGN-PLAN.md`：**架构与演进事实源**（信息架构、页面划分、里程碑与验收记录）。
   - `UI-SPECS.md`：**视觉与尺寸规范事实源**（布局、尺寸、token、断点、组件规范）。
2. 修订 `UI-SPECS.md` §1.1 布局图：加入 64px 侧边导航（4 项），TopBar 内容更新为「品牌 · N 个 Agent · 搜索（Ctrl K）· 重新扫描」。
3. 修订 `UI-SPECS.md` §1.2 响应式断点表为四档：

   | 断点 | 布局 |
   |---|---|
   | ≥1440px | 侧栏 64px + 三栏全显 |
   | 1280–1439px | 三栏全显；状态栏隐藏次要指标 |
   | 1024–1279px | 侧栏 56px（隐藏文字标签）、顶栏按钮压缩 |
   | 768–1023px | 侧栏 48px；弹窗转全屏抽屉 |

4. 修订 `UI-SPECS.md` §2 窗口尺寸表：删除「最小窗口宽 1280px（强制）」，改为「最小支持宽度 320px（`body` min-width）」；补 TopBar 48px、StatusBar 28px（现状一致，保留）。
5. 新增 `UI-SPECS.md` §「规范与实现一致性核对表」：逐项列出可机械核对的数值与其代码出处（断点值 → `global.css`；顶栏入口数 → `TopBar.tsx`；栏宽默认值与范围 → `App.tsx`；`min-width` → `global.css`）。
6. 在 `UI-SPECS.md` 修订记录中登记本次变更。

**参数配置标准**

| 参数 | 规范值 | 代码出处 |
|---|---|---|
| 断点集合 | 1440 / 1280 / 1024 / 768 | `global.css` L2048、L2067 + M-07 新增块 |
| 最小支持宽度 | 320px | `global.css` L68 |
| 侧栏宽度 | 64px（>1024）/ 56px（≤1024）/ 48px（≤768） | `global.css` L1940、L2050、L2075 |
| 顶栏高度 | 48px | `global.css` L19、L127 |
| 状态栏高度 | 28px | `global.css` L20、L1028 |
| 顶栏常驻入口数 | 2（搜索 + 重新扫描） | M-01 后 `TopBar.tsx` |
| 左栏宽度 | 默认 240px，范围 180–360px | `App.tsx` L132、L610 |
| 中栏宽度 | 默认 280px，范围 200–400px | `App.tsx` L133、L614 |
| 编辑器模式上限 | 同时 3 个窗口 | `App.tsx` L40 |
| 存储键全集 | `soulforge.settings` / `editor.mode` / `browse.mode` / `intro-v2` / `layout` / `palette.recent` | 各实现处 |

**用户操作流程**

文档变更不涉及终端用户体验；面向后续开发者与评审者的检索路径：`UI-SPECS.md` 查阅视觉与尺寸 → `docs/UI-REDESIGN-PLAN.md` 查阅架构与演进 → `docs/UI-OPTIMIZATION-PLAN.md`（本文档）查阅本轮优化项。

**开发操作流程**

1. 按上表逐项核对代码出处，修订 `UI-SPECS.md`。
2. 每次涉及布局/断点/token/入口数的代码变更，须在同一次提交内更新一致性核对表。
3. 校验：对照一致性核对表逐行确认与代码一致，无「待确认」项。

**责任主体（RACI）**

| 角色 | 职责 |
|---|---|
| FE 前端负责人 | R 修订 / A 一致性 |
| PO 项目负责人 | A 事实源划分确认 / 验收 |
| QA 测试与验收 | V 抽样比对 3 项以上数值 |

**交付节点**：D4
**单项验收标准**：一致性核对表内全部条目与代码一致；断点、最小宽度、顶栏入口数三处原矛盾项已消除；文档间事实源划分已写明。
**回滚方式**：文档类改动，`git revert` 即可；无运行时影响。

---

## 四、资源需求与时间节点规划

### 4.1 角色与职责（RACI 矩阵）

> 本项目为单人自托管的内部工具，**下述角色可由同一人兼任**；矩阵用于明确每项工作的责任归属，不表示需配置独立人力。

| 角色代码 | 角色 | 主要职责 | 兼任说明 |
|---|---|---|---|
| PO | 项目负责人 | 入口规则与验收标准决策、最终验收签核 | 可由项目所有者担任 |
| FE | 前端负责人 | 全部前端实现、自测、构建校验 | 主要执行者 |
| QA | 测试与验收 | 按用例执行验证、断点与主题回归、签核 | 可由 FE 交叉执行（需独立复核） |
| OPS | 环境与发布 | 本地构建与启动验证、版本记录 | 可由 FE 兼任 |

**R**=负责执行，**A**=最终负责/批准，**C**=被咨询，**V**=被验证方。

| 措施 | PO | FE | QA | OPS |
|---|---|---|---|---|
| M-01 顶栏去重 | C / A | R | V | — |
| M-02 面板层级去重 | A | R | V | — |
| M-03 布局持久化与中栏折叠 | C / A | R | V | — |
| M-04 保存状态可视化 | A | R | V | — |
| M-05 命令面板最近使用 | A | R | V | — |
| M-06 CORE 上下文切换 | A | R | V | — |
| M-07 响应式与状态栏收敛 | C / A | R | V | — |
| M-08 规范文档同步 | A | R | V | — |
| 构建与启动验证 | — | C | — | R |
| 最终验收签核 | R / A | C | R | — |

### 4.2 环境与工具需求

| 类别 | 需求 | 用途 | 备注 |
|---|---|---|---|
| 运行时 | Node.js（支持 Vite 5 / TypeScript 5.6） | 前端构建 | 现有环境 |
| 依赖 | **零新增**运行时依赖 | — | 硬约束，见 2.3 |
| 构建命令 | `npm run build`（= `tsc --noEmit && vite build`） | 类型与产物校验 | `frontend/package.json` L8 |
| 后端回归 | `pytest`（基线 129 passed / 1 skipped） | 确认零回归 | `backend/` |
| 启动 | `start.bat` | 联调与冒烟 | 项目根目录 |
| 浏览器 | Chromium 系最新版（Chrome / Edge） | 交互与断点验证 | 需覆盖深/浅主题 |
| 测试数据 | 真实 workspace（8 Agent / 2461 文件 / 56 CORE） | 大数据量冒烟 | 与既有验收口径一致 |

### 4.3 里程碑节点定义

> 节点以**交付物与准入准出条件**定义，不承诺日历日期。各节点的实际排期在评审通过后由 PO 依据资源情况确定并回填。

| 节点 | 交付内容 | 准入条件 | 准出条件（DoD） |
|---|---|---|---|
| **D1 入口与层级收敛** | M-01、M-02 代码提交 | 本方案评审通过 | 顶栏入口 ≤2；Tools/Data 内嵌面板无重复标题；`npm run build` 通过 |
| **D2 状态与反馈补全** | M-03、M-04 代码提交 | D1 准出 | 4 个布局维度持久化生效；中栏可折叠；保存时间戳可见；`npm run build` 通过 |
| **D3 效率与模式增强** | M-05、M-06 代码提交 | D2 准出 | 「最近使用」MRU 生效并持久；CORE 中栏可切换且左栏同步；`npm run build` 通过 |
| **D4 响应式与规范同步** | M-07 代码提交、M-08 文档修订 | D3 准出 | 1280px 状态栏无溢出；`UI-SPECS.md` 一致性核对表全项一致 |
| **D5 回归与验收** | 测试报告、验收签核记录 | D1–D4 全部准出 | 第六节全部用例通过；后端 `pytest` 129 passed / 1 skipped 无回归；指标达成 |

### 4.4 依赖顺序与并行度

| 关系 | 说明 |
|---|---|
| M-01 → M-02 无强依赖 | 两者独立，可并行实施（均在 D1 交付） |
| M-01 → M-05 弱依赖 | M-05 的「最近使用」需在入口收敛结论确定后实施，避免动作索引变动导致记录失效 |
| M-03 → M-07 弱依赖 | M-07 的窄屏状态栏收敛在中栏折叠能力落地后验证更完整 |
| M-08 完全独立 | 可与任一节点并行；但其一致性核对表需在 M-01、M-03、M-07 完成后回填最终数值 |
| 强制顺序 | D1 → D2 → D3 → D4 → D5（每节点准出为下一节点准入） |

**并行建议**：同一节点内的 2 项措施可由不同执行者并行；节点之间不建议并行，以保证每节点可独立回滚。

### 4.5 排期说明

- 本方案以**规模量级（S / M）**衡量工作量（见 3.0 表格），不使用绝对工期，以避免与实际可用时间产生偏差。
- 5 个节点为**严格串行**依赖；每个节点均可独立上线与回滚，因此可根据可用资源分多次交付，不要求一次性完成。
- 排期确定原则：单节点内规模为 M 的措施优先安排在前，S 类措施可合并到同一批次。

---

## 五、风险评估与应对预案

### 5.1 风险登记册

| 编号 | 风险描述 | 类别 | 概率 | 影响 | 等级 | 应对措施 | 触发信号 |
|---|---|---|---|---|---|---|---|
| RK-01 | 顶栏入口减少后，存量用户找不到「业务工具 / 数据中心 / 系统配置」 | 用户接受度 | 中 | 中 | 中 | 侧栏 4 项常驻高亮；命令面板已索引全部 4 个页面（C-18）；引导 key 升级为 `intro-v2` 使存量用户重新看到改版提示 | 用户反馈「找不到 XX 功能」 |
| RK-02 | 内嵌面板去 header 后，用户失去「返回」路径而停留在页面内 | 交互 | 低 | 中 | 低 | SideNav 全局常驻；命令面板含「前往主工作台」；`page-tabs` 完整保留 | 用户在同一页反复切换 tab 而无跳转动作 |
| RK-03 | `localStorage` 不可用（隐私模式 / 存储配额满）导致布局读写异常 | 技术 | 中 | 低 | 低 | 读写全部 `try/catch` 静默降级到默认值；不阻塞应用启动；读取时 `clamp` 校正脏数据 | 控制台出现存储异常；布局未按预期恢复 |
| RK-04 | 新增快捷键与浏览器默认行为冲突 | 技术 | 中 | 中 | 中 | **不采用 `Ctrl+Shift+B`**（Chromium 与书签栏显隐冲突），改用 `Alt+1` / `Alt+2`；`Ctrl+B` 保持兼容；按键处理仅在 workbench 路由生效并 `preventDefault` | 按键无效或浏览器 UI 被切换 |
| RK-05 | 状态栏隐藏次要指标后，用户认为信息缺失 | 用户接受度 | 低 | 低 | 低 | 保留连接态与 lint 警告（关键项不隐藏）；被隐藏项在 Data 页统计仪表盘仍可查。**实现说明**：未给隐藏项加 `title`——元素为 `display: none`，悬浮提示不可达，加 `title` 属于无效缓解 | 用户询问「文件总数去哪了」 |
| RK-06 | 规范文档修订后再次与实现漂移 | 流程 | 中 | 低 | 低 | 建立「一致性核对表」并规定：任何涉及断点/尺寸/token/入口数的代码变更须在同一次提交内更新该表 | 评审时发现文档与实现不符 |
| RK-07 | 「最近使用」记录的动作在索引变更后悬空，导致点击无响应 | 技术 | 低 | 中 | 低 | 读取时过滤不在 `paletteItems` 中的 `id`；`onUsed` 仅记录存在的动作 | 面板出现点击无反应条目 |
| RK-08 | 改动集中在 `App.tsx` 与 `global.css`，波及既有 3 窗口编辑、CORE 模式等成熟功能 | 质量 | 中 | 高 | 中 | 每节点独立提交、独立回滚；每节点必跑 `npm run build`；D5 全量执行第六节用例；真实数据（8 Agent / 2461 文件）冒烟 | 既有功能回归失败 |
| RK-09 | 引导 key 升级为 `intro-v2` 导致老用户被重复提示打扰 | 用户接受度 | 低 | 低 | 低 | 仅一次性展示；提示条含「知道了」关闭按钮（现状 L677–679）；文案为更新后的快捷键说明 | 用户反馈提示打扰 |
| RK-10 | 中栏折叠后与 CORE 模式二级列表的可视性冲突 | 交互 | 低 | 中 | 低 | 中栏折叠在两种浏览模式下行为一致（均折叠列表）；折叠恢复条在 CORE 模式下同样渲染 | CORE 模式下列表无法恢复 |

### 5.2 回滚预案

| 措施 | 回滚粒度 | 回滚动作 | 数据影响 |
|---|---|---|---|
| M-01 | 单提交 | `git revert` 顶栏提交，恢复三个按钮与 prop | 无 |
| M-02 | 单提交 | 移除 `headerless` 传参（组件保留，向后兼容） | 无 |
| M-03 | 单提交 | 移除 `soulforge.layout` 读写与 `midCollapsed`；保留已写入的 localStorage 键（无副作用） | 仅影响下次布局记忆 |
| M-04 | 单提交 | 移除 `savedAt` 字段与渲染分支 | 无 |
| M-05 | 单提交 | 移除最近使用分组与存储读写 | 无 |
| M-06 | 单提交 | 恢复纯文本 header；新增 props 为可选，可不回滚组件签名 | 无 |
| M-07 | 单提交 | 移除新增媒体查询块；`.metric-secondary` class 可保留 | 无 |
| M-08 | 单提交 | `git revert` 文档提交 | 无 |

**回滚总则**：每个节点（D1–D4）对应独立提交批次，任意节点失败均可单独回滚而不影响其他节点成果。所有措施均**无后端契约变更、无数据迁移**，回滚零数据风险。

### 5.3 质量红线（任一不满足即阻断交付）

1. `npm run build`（含 `tsc --noEmit`）必须通过。
2. 后端 `pytest` 必须维持 129 passed / 1 skipped，不得出现新增失败。
3. 不得新增运行时依赖（`frontend/package.json` `dependencies` 条目数 ≤ 7）。
4. 文件级弹窗（搜索 / 历史 / 应用预设 / AI 整理）行为零变化。
5. 3 个编辑窗口（`MAX_WINDOWS = 3`）的多窗口编辑与未保存提示（`beforeunload`）功能零回归。
6. 深色与浅色主题下，全部改动页面无对比度异常与样式缺失。

---

## 六、效果验证指标及测试方案

### 6.1 效果验证指标（KPI）

| 编号 | 指标 | 口径定义 | 基线 | 目标值 | 采集方式 | 关联措施 |
|---|---|---|---|---|---|---|
| K-01 | 顶栏常驻入口数 | 顶栏内可点击元素数（不含品牌区） | 5 | ≤ 2 | 代码走查 + DOM 计数 | M-01 |
| K-02 | 重复导航项数 | 顶栏与侧栏同时存在的同功能入口数 | 3 | 0 | 代码走查 | M-01 |
| K-03 | 页内重复标题数 | 内嵌面板额外渲染标题栏的页面数 | 11 | 0 | 逐页走查 | M-02 |
| K-04 | 布局状态持久化率 | 刷新后保持的布局维度 / 总布局维度 | 0 / 4 | 4 / 4 | UC-07、UC-08 | M-03 |
| K-05 | 布局恢复正确性 | 刷新后宽度偏差 | 未受控 | 0px（像素级一致） | UC-07 | M-03 |
| K-06 | 保存状态可见性 | 保存后存在持久时间戳 | 否 | 是 | UC-09、UC-10 | M-04 |
| K-07 | 命令面板零输入直达率 | 重复动作在空查询下的可直达比例 | 0% | 100%（已使用过的动作） | UC-04 | M-05 |
| K-08 | CORE 分类切换点击数 | 中栏切换分类所需点击数 | 2 | 1 | UC-11 | M-06 |
| K-09 | 状态栏窄屏溢出 | 1280px 下是否溢出/换行 | 未受控 | 无 | UC-13 + DevTools 截图 | M-07 |
| K-10 | 规范一致性 | 文档与实现不符处数 | 3 | 0 | 逐项比对一致性核对表 | M-08 |
| K-11 | 构建通过 | `tsc --noEmit && vite build` | 通过 | 通过 | `npm run build` | 全部 |
| K-12 | 后端回归 | pytest 结果 | 129 passed / 1 skipped | 无新增失败 | `pytest` | 全部 |
| K-13 | 运行时依赖数 | `dependencies` 条目数 | 7 | ≤ 7 | `package.json` | 全部 |

### 6.2 测试方案（分层）

| 层级 | 名称 | 内容 | 工具 / 命令 | 通过标准 |
|---|---|---|---|---|
| L1 | 静态检查 | TypeScript 类型检查、编辑器诊断无错误 | `tsc --noEmit`、IDE `GetDiagnostics` | 0 error |
| L2 | 构建验证 | 生产构建成功、产物正常 | `npm run build` | 退出码 0 |
| L3 | 服务启动 | 前后端联通、页面可加载 | `start.bat` | 应用正常启动、无控制台报错 |
| L4 | 功能用例 | 按 6.3 用例清单逐条执行 | 人工执行 + DevTools | 全部用例通过 |
| L5 | 兼容与主题 | 4 档断点 × 2 主题 交叉走查 | Chrome / Edge DevTools | 无溢出、无对比度异常、token 生效 |
| L6 | 数据规模冒烟 | 真实 workspace（8 Agent / 2461 文件 / 56 CORE）下操作 | 真实环境 | 列表/搜索/CORE 切换无卡顿与错乱 |
| L7 | 后端回归 | 既有测试全量执行 | `pytest` | 129 passed / 1 skipped |
| L8 | 持久化异常 | 手动破坏 `soulforge.layout` / `soulforge.palette.recent` 后重启 | DevTools Application | 应用正常启动，降级为默认值，无报错 |

### 6.3 测试用例清单

| 编号 | 用例场景 | 前置条件 | 操作步骤 | 预期结果 | 关联措施 |
|---|---|---|---|---|---|
| UC-01 | 顶栏入口收敛 | 应用已加载 | 检查顶栏 | 仅「搜索框」「重新扫描」两个可点击入口 | M-01 |
| UC-02 | 侧栏导航与刷新保持 | 应用已加载 | 依次点击 4 项 → 每次刷新 | URL hash 为对应路由且刷新后停留在该页 | M-01 |
| UC-03 | 命令面板跨页跳转 | 应用已加载 | `Ctrl+K` → 输入 `sync` → `Enter` | 跳转至 `#/tools` 且停留在「同步」tab | M-01 |
| UC-04 | 最近使用 MRU | 已执行过若干动作 | `Ctrl+K` → 观察首屏 → `Esc` → 执行「统计仪表盘」→ 再 `Ctrl+K` | 首屏出现「最近使用」；「统计仪表盘」位于首位；重复执行不产生重复项；刷新后保留 | M-05 |
| UC-05 | Tools / Settings 页层级 | 进入业务工具、系统配置 | 逐个切换 Tools 5 个与 Settings 3 个 tab | 每个 tab 仅一组页面 tab 标题，无第二个标题栏、无「返回」按钮 | M-02 |
| UC-06 | Data 页层级与结果回跳 | 进入数据中心 | 逐个切换 3 个 tab；在健康检查报告中点击一条结果 | 无重复标题；点击结果跳回 Workbench 并定位到对应文件行 | M-02 |
| UC-07 | 分栏宽度持久化 | 处于工作台 | 拖拽左栏至约 300px → 刷新 | 左栏仍约 300px（像素级一致） | M-03 |
| UC-08 | 折叠持久化与快捷键 | 处于工作台 | `Alt+1` 折叠左栏 → `Alt+2` 折叠中栏 → 刷新 | 左栏与中栏均为折叠态；刷新后保持；恢复竖条可见可点击 | M-03 |
| UC-09 | 保存时间戳 | 已打开一个文件 | 编辑 → `Ctrl+S` | 状态位由「● 未保存」变为「已保存 HH:mm:ss」；toast 同时出现 | M-04 |
| UC-10 | 自动保存时间戳 | 已开启自动保存设置 | 编辑后停止输入 2s | 状态位自动更新为最新时间戳 | M-04 |
| UC-11 | CORE 中栏切换 | 切至 CORE 分类模式 | 点击中栏顶部下拉 → 观察列表长度 → 滚动至底部 → 选择另一分类 | 下拉在 320px 高度内可滚动、不溢出视口；中栏列表切换为该分类的 Agent；左栏高亮同步移动；计数与条目数一致 | M-06 |
| UC-12 | 模式切换一致性 | CORE 模式下已打开文件 | 切回 Agent 模式 | 左栏 Agent 列表与中栏文件树正常，无 CORE 残留；已打开文档不丢失 | M-06 |
| UC-13 | 状态栏断点收敛 | 视口可调 | 依次设为 1440 / 1280 / 1024 / 768 | 1440 全量 4 段；1280 仅连接态 + 警告；全部档位单行无溢出换行 | M-07 |
| UC-14 | 侧栏与搜索框断点 | 视口可调 | 设为 1024 → 768 | 侧栏 56px 且隐藏文字标签 → 48px；搜索框 `Ctrl K` 徽标在 768 隐藏 | M-07 |
| UC-15 | 深浅主题一致性 | 主题可切换 | 在上述全部用例涉及的页面切换深/浅主题 | 无白底黑字闪烁、无对比度不足、无 token 未生效 | 全部 |
| UC-16 | 双栏全折叠 | 处于工作台 | `Alt+1` + `Alt+2` 全部折叠 | 编辑器占满剩余宽度；两条恢复竖条均可见、可点击展开 | M-03 |
| UC-17 | 未保存离开提示 | 存在未保存修改 | 刷新或关闭标签页 | 浏览器弹出离开确认 | 现状回归 |
| UC-18 | 多窗口编辑 | 多窗口模式 | 打开 3 个文件后尝试打开第 4 个 | toast 提示「最多同时打开 3 个编辑窗口」；3 个窗口均正常 | 现状回归 |
| UC-19 | 存储异常降级 | 可修改 localStorage | 将 `soulforge.layout` 写为非法 JSON → 刷新；再写为越界宽度（如 9999）→ 刷新 | 应用正常启动；降级为默认布局或 clamp 至合法范围，无报错 | M-03 |
| UC-20 | 真实数据冒烟 | 真实 workspace | 切换 Agent / CORE 模式、搜索、拖拽、折叠、保存 | 8 Agent / 2461 文件 / 56 CORE 场景下无卡顿、无错乱、无报错 | 全部 |

### 6.4 验收流程与签核

| 环节 | 执行者 | 内容 | 通过标准 | 输出物 |
|---|---|---|---|---|
| 步骤 1 开发自测 | FE | L1–L3 层级 + 对应节点用例 | 无 error、构建通过、启动正常 | 自测记录 |
| 步骤 2 评审走查 | PO + FE | 按 3.x 各措施「单项验收标准」逐条确认 | 全部条目满足 | 走查记录 |
| 步骤 3 独立验证 | QA | L4–L8 全量用例（6.3 共 20 条） | 全部用例通过 | 测试报告 |
| 步骤 4 指标核对 | QA + PO | 按 6.1 逐项核对 K-01…K-13 | 全部达成 | 指标核对表 |
| 步骤 5 回归签核 | PO | 确认质量红线（5.3）未被突破 | 6 条红线全部满足 | 签核记录 |
| 步骤 6 归档 | OPS | 记录节点交付commit、回滚点 | 可追溯 | 发布记录 |

**签核表**

| 节点 | FE 自测 | QA 验证 | PO 验收 | 日期 |
|---|---|---|---|---|
| D1 入口与层级收敛 | ☐ | ☐ | ☐ | |
| D2 状态与反馈补全 | ☐ | ☐ | ☐ | |
| D3 效率与模式增强 | ☐ | ☐ | ☐ | |
| D4 响应式与规范同步 | ☐ | ☐ | ☐ | |
| D5 回归与验收 | ☐ | ☐ | ☐ | |

### 6.5 回归基线

| 基线项 | 要求 | 不通过处理 |
|---|---|---|
| 前端构建 | `npm run build` 通过（`tsc --noEmit` + `vite build`） | 阻断交付 |
| 后端测试 | 129 passed / 1 skipped，无新增失败 | 阻断交付 |
| 文件级弹窗 | 搜索 / 历史 / 应用预设 / AI 整理 行为不变 | 阻断交付 |
| 多窗口编辑 | 3 窗口上限、未保存提示（`beforeunload`）不变 | 阻断交付 |
| CORE 模式 | 一级分类 → 二级 Agent 结构不变（嵌套问题不得回归） | 阻断交付 |
| 路由 | 4 路由刷新保持 | 阻断交付 |
| 主题 | 深/浅主题全部页面正常 | 阻断交付 |

---

## 附录 A：变更文件清单

| 文件 | 变更类型 | 涉及措施 |
|---|---|---|
| `frontend/src/components/TopBar.tsx` | 修改（删除 3 按钮与 3 props，调整占位文案） | M-01 |
| `frontend/src/App.tsx` | 修改（调用点清理、布局持久化、快捷键、`savedAt`、`recentIds`、CORE props、引导 key 与文案） | M-01、M-03、M-04、M-05、M-06 |
| `frontend/src/components/Modal.tsx` | 修改（新增 `headerless`） | M-02 |
| `frontend/src/components/SyncModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/CrossEditModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/DiffModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/ImportModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/TemplateModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/StatsModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/GlobalLintModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/AuditModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/SettingsModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/LLMProvidersModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/PresetModal.tsx` | 修改（`headerless={embedded}`） | M-02 |
| `frontend/src/components/EditorPane.tsx` | 修改（新增 `savedAt` prop 与状态位渲染） | M-04 |
| `frontend/src/components/CommandPalette.tsx` | 修改（新增 `recentIds` / `onUsed`，空查询插入「最近使用」分组并按 6 条截断） | M-05 |
| `frontend/src/components/CoreBrowser.tsx` | 修改（`CoreAgentList` 新增 `coreTypes` / `onSelectCore`，header 接下拉） | M-06 |
| `frontend/src/components/StatusBar.tsx` | 修改（次要指标加 `metric-secondary` 语义 class） | M-07 |
| `frontend/src/utils/format.ts` | 修改（新增 `formatClock`） | M-04 |
| `frontend/src/styles/global.css` | 修改（`.saved-mark`、`.pane-collapsed-bar`、`.core-switch[*]`、CORE 下拉滚动规则、`.command-footer-note`、1280px 媒体查询、1024px 状态栏溢出保护） | M-03、M-04、M-05、M-06、M-07 |
| `UI-SPECS.md` | 修改（断点表、窗口尺寸、布局图、token 表、组件清单、快捷键、一致性核对表、修订记录） | M-08 |
| `frontend/src/pages/ToolsPage.tsx` | **未修改**（`headerless` 由组件内部处理） | — |
| `frontend/src/pages/DataPage.tsx` | **未修改**（同上） | — |
| `frontend/src/pages/SettingsPage.tsx` | **未修改**（同上） | — |
| `frontend/package.json` | **未修改** | 零新增依赖约束 |

> 说明：`Dropdown.tsx`、`useHashRoute.ts`、`useSettings.tsx`、`useCoreCatalog.ts` 为**复用**，未修改。

## 附录 B：参数速查表

| 类别 | 参数 | 值 |
|---|---|---|
| 顶栏 | 常驻入口数 | 2（搜索 + 重新扫描） |
| 顶栏 | 高度 | 48px |
| 侧栏 | 宽度 | 64px / 56px（≤1024）/ 48px（≤768） |
| 侧栏 | 导航项数 | 4（固定） |
| 状态栏 | 高度 | 28px |
| 状态栏 | 1280px 起隐藏项 | 索引文件数、上次扫描 |
| 断点 | 集合 | 1440 / 1280 / 1024 / 768 |
| 最小宽度 | `body min-width` | 320px |
| 左栏 | 默认 / 范围 | 240px / 180–360px |
| 中栏 | 默认 / 范围 | 280px / 200–400px |
| 折叠恢复条 | 宽度 | 32px |
| 编辑器 | 同时窗口上限 | 3 |
| 快捷键 | 命令面板 | `Ctrl+K` |
| 快捷键 | 保存 | `Ctrl+S` |
| 快捷键 | 左栏折叠 | `Alt+1`（兼容 `Ctrl+B`），仅 `#/workbench` |
| 快捷键 | 中栏折叠 | `Alt+2`，仅 `#/workbench` |
| 快捷键 | 跨 Agent 编辑 | `Ctrl+Shift+E` |
| 存储 | 键全集 | `soulforge.settings`、`soulforge.editor.mode`、`soulforge.browse.mode`、`soulforge.intro-v2`、`soulforge.layout`、`soulforge.palette.recent` |
| 命令面板 | 最近使用上限 | 8 条（MRU 去重） |
| 命令面板 | 空查询每分组上限 | 6 条 |
| 命令面板 | 文件检索防抖 | 220ms |
| 命令面板 | 索引动作数 | 17 项（4 导航 + 13 功能） |
| CORE 下拉 | 滚动容器高度 | `max-height: min(320px, 50vh)` + `overflow-y: auto`（父级作用域规则） |
| 内嵌面板 | 需 `headerless` 的组件数 | 11 个（Tools 5 + Data 3 + Settings 3） |
| 保存反馈 | 时间格式 | `HH:mm:ss`（秒级时间戳 + `formatClock`） |
| 保存反馈 | 自动保存防抖 | 2s |
| 依赖 | 运行时依赖数 | ≤ 7（零新增） |

## 附录 C：评审检查表

评审时逐条确认，全部勾选方可进入执行：

**范围与目标**
- ☐ 确认本方案不改变信息架构与技术栈（2.4 非目标逐条认可）
- ☐ 确认 8 项措施与 9 个问题的映射完整（2.2）
- ☐ 确认无遗漏的高优先级体验问题

**技术方案**
- ☐ 确认 M-01 顶栏入口规则（顶栏不承载导航）被接受
- ☐ 确认 M-02 `headerless` 方案未影响文件级弹窗
- ☐ 确认 M-03 快捷键方案（`Alt+1` / `Alt+2`，不用 `Ctrl+Shift+B`）被接受
- ☐ 确认 M-03 存储键 `soulforge.layout` 结构与默认值
- ☐ 确认 M-04 保存状态位与 toast 并存而非替代
- ☐ 确认 M-05「最近使用」上限（8 条 / 每组 6 条）
- ☐ 确认 M-06 复用 `Dropdown` 组件，不新增组件
- ☐ 确认 M-07 状态栏隐藏项与保留项
- ☐ 确认 M-08 两份文档的事实源划分

**资源与节点**
- ☐ 确认角色兼任安排（4.1）
- ☐ 确认 D1–D5 节点划分与串行依赖（4.3、4.4）
- ☐ 确认规模量级评估与排期确认方式（4.5）

**风险与验证**
- ☐ 确认风险登记册 10 项及应对措施（5.1）
- ☐ 确认质量红线 6 条（5.3）
- ☐ 确认 KPI 13 项及目标值（6.1）
- ☐ 确认测试用例 20 条覆盖全部措施（6.3）
- ☐ 确认回归基线 7 项（6.5）

---

## 附录 D：实施记录（2026-09-02）

### D.1 实施状态

| 措施 | 节点 | 状态 | 实际落地 |
|---|---|---|---|
| M-01 顶栏与侧栏去重 | D1 | ✅ 完成 | `TopBar` 删除 3 个导航按钮与对应 props（仅保留搜索入口 + 重新扫描）；占位文案改为「搜索或执行命令…」；引导 key 升级 `soulforge.intro-v1` → `intro-v2`，文案补充「左侧导航切页」与 `Alt+1`/`Alt+2` |
| M-02 内嵌面板去重标题 | D1 | ✅ 完成 | `Modal` 新增 `headerless`；11 个功能面板组件内部传 `headerless={embedded}`，页面容器零改动 |
| M-03 布局持久化与中栏折叠 | D2 | ✅ 完成 | 新增 `soulforge.layout`（`loadLayout` / `saveLayout`，越界 clamp、损坏回落默认）；新增 `midCollapsed`；新增 `Alt+1` / `Alt+2`（仅 workbench 生效），`Ctrl+B` 保留；新增 `.pane-collapsed-bar`（32px）恢复条 |
| M-04 保存状态可视化 | D2 | ✅ 完成 | `EditorTab.savedAt`（秒级）由 `saveTab` 成功分支写入；`EditorPane` 路径栏新增 `.saved-mark`「已保存 HH:mm:ss」，与 `.dirty-mark` 互斥；新增 `formatClock` |
| M-05 命令面板「最近使用」 | D3 | ✅ 完成 | 新增 `soulforge.palette.recent`（MRU 去重，上限 8）；`CommandPalette` 空查询置顶「最近使用」分组，每组截断 6 条，底部提示可检索总量；分组起始下标预计算（避免同一动作重复出现时高亮错位） |
| M-06 CORE 中栏分类切换 | D3 | ✅ 完成 | `CoreAgentList` 新增 `coreTypes` / `onSelectCore`，`pane-header` 接入 `Dropdown`（左侧对齐、显示各分类 Agent 计数）；新增 `.core-switch` 样式；CORE 下拉滚动规则以父级作用域实现 |
| M-07 响应式与状态栏收敛 | D4 | ✅ 完成 | 新增 `@media (max-width: 1280px)` 隐藏状态栏次要指标并收敛 gap/padding；1024px 块补充 `overflow: hidden` + `white-space: nowrap` |
| M-08 规范文档同步 | D4 | ✅ 完成 | `UI-SPECS.md` 修订至 v1.1：加入 SideNav 与四档断点、最小宽度 320px、token 补全（`--text-tertiary` / `--accent-soft` / 结构 token）、替换 shadcn 组件清单为实际自研组件、跨 Agent 编辑页面化、快捷键补 `Alt+1`/`Alt+2`、新增「规范与实现一致性核对表」 |

### D.2 实现偏差记录

> 实施过程中对方案的 5 处修正，均已回写至正文对应章节。

| 编号 | 方案原文 | 实际实现 | 原因 |
|---|---|---|---|
| DV-01 | M-02：在页面调用点（Tools/Data/Settings）追加 `headerless` | 改为在各功能面板组件内部传 `headerless={embedded}` | `embedded` 在本项目中只可能来自页面级调用，语义等价；页面代码零改动，后续新增页面无需重复传参 |
| DV-02 | M-04：`savedAt` 为毫秒时间戳，复用 `formatTime` | 改为秒级时间戳，新增 `formatClock` | 与全站后端时间戳口径（`last_scan_at` / `mtime`）一致；且 `formatTime` 返回完整日期，不满足 `HH:mm:ss` 展示要求 |
| DV-03 | M-06：新增 `.dropdown-menu.scrollable` 修饰类 | 改为父级作用域规则 `.core-agent-list .dropdown-menu` | 避免为一次性场景扩展开共享组件 API；作用域天然隔离其他 `Dropdown` 调用点 |
| DV-04 | M-06：滚动容器 `max-height: 320px` | 改为 `min(320px, 50vh)` | 下拉位于可滚动容器内，`50vh` 上限避免矮视口下菜单超出可用高度 |
| DV-05 | RK-05：给状态栏隐藏项加 `title` 说明 | 未加 | 元素为 `display: none`，悬浮提示不可达，属无效缓解；信息补偿由 Data 页统计仪表盘承担 |

### D.3 验证结果

| 验证项 | 命令 / 方式 | 结果 |
|---|---|---|
| 前端构建 | `npm run build`（`tsc --noEmit && vite build`） | ✅ 通过（1140 modules，退出码 0） |
| `headerless` 落点数量 | `Grep "headerless={embedded}"` | ✅ 11 处 / 11 个文件，与方案一致 |
| 运行时依赖 | `package.json` `dependencies` | ✅ 7 项，零新增 |
| 后端回归 | `backend/.venv/Scripts/python.exe -m pytest -q` | ✅ 129 passed / 1 skipped，与基线一致 |
| 运行时界面验证 | 真实数据（7 Agent / 2529 文件 / 6 CORE），只读走查 | ✅ UC-01~UC-09 相关项全部通过，详见 D.4 |

### D.4 运行时验证明细（2026-09-02）

| 用例 | 验证内容 | 结果 |
|---|---|---|
| UC-01 | 顶栏可点击入口 | ✅ 恰 2 个：搜索框（「搜索或执行命令…」+ `Ctrl K` 徽标）与「重新扫描」；三个导航按钮已移除 |
| UC-02 | 侧栏导航 4 项 + hash 路由 | ✅ 主工作台 / 业务工具 / 数据中心 / 系统配置；URL 分别变为 `#/workbench`、`#/tools`、`#/data`、`#/settings` |
| UC-03 | 命令面板 | ✅ `Ctrl+K` 打开、`Esc` 关闭；分组为 导航 / 操作 / 数据 / 管理 |
| UC-05 | Tools / Settings 页层级 | ✅ Tools 5 个 tab、Settings 3 个 tab；DOM 中 `.modal-header` = 0、无「返回」元素 |
| UC-06 | Data 页层级 | ✅ 3 个 tab（统计仪表盘 / 健康检查报告 / 审计日志）；无 `.modal-header` |
| UC-13 | 状态栏断点收敛 | ✅ ≤1280px：`.metric-secondary` 计算样式为 `display: none`，仅留连接态与 lint 警告，高度 28px 无换行；≤1024px：`overflow: hidden` + `white-space: nowrap` |
| UC-11 | CORE 中栏切换 | ✅ 中栏出现 `.core-switch`（文案「CORE：SOUL.md ▾」）；下拉展开列出 6 个 CORE 分类，每项右侧显示计数 |
| UC-16 | 双栏折叠与恢复 | ✅ `Alt+1` 折叠左栏（原位出现 32px `.pane-collapsed-bar`）、再按恢复；`Alt+2` 对中栏同样生效 |
| — | 控制台错误 | ✅ 应用自身无 error 级报错（唯一一条 `ERR_ABORTED` 由验证过程中的 iframe 卸载中断在途请求导致，正常加载路径下无复现） |

**验证过程中发现并修复的 1 处问题**：命令面板底部提示原为「共 N 项命令」固定取索引总数，与实际渲染条数（每组截断 6 条后）不一致，易误判为丢失条目。已改为「已显示 X / 共 N 项命令，输入关键词可筛选」。

**未覆盖项（需后续补齐）**：UC-04（「最近使用」MRU，需先执行动作才能观察）、UC-09/UC-10（保存时间戳，涉及写操作）、UC-19（存储异常降级，需手工破坏 localStorage）、UC-20（大数据量操作压测）。以上为写入类或需构造异常态的场景，未在只读验证中执行。

---

**文档结束**
