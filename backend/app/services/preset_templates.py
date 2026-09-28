"""内置预设的标准 Markdown 模板文档（Phase 2.5 · 文档重排校验）。

模板 = YAML frontmatter（机器可读的格式化规则）+ 正文（章节结构骨架）。
TemplateRuleParser 负责解析；FormatValidator 负责校验/修正。
"""
from __future__ import annotations

SOUL_TEMPLATE = """---
schema: soulforge.template/v1
target_file_type: SOUL
structure:
  section_heading_level: 2
  required_sections:
    - title: 核心行为准则
    - title: 工作态度和原则
    - title: 学习与连续性
    - title: 核心边界
  section_order: strict
elements:
  heading_style: atx
  list_style: "-"
  code_fence: "```"
  blockquote_prefix: "> "
  heading_blank_line: true
  paragraph_blank_line: true
typography:
  max_heading_level: 3
  allow_bold: true
  allow_italic: true
  forbid_emoji: true
  forbid_raw_html: true
modules:
  frontmatter: optional
---

# SOUL 文档标准模板

> 本文档即模板本体：重排目标文档时，需严格遵循 YAML 中定义的格式化规则，
> 并按下方「章节模板」的标题结构组织内容；原有信息不得丢失。

## 核心行为准则

<!-- 提示：简洁优先、目标导向 -->
- 列出每条行为准则
- 每条单独一个列表项

## 工作态度和原则

<!-- 提示：先想后做、不吹嘘 -->
- 列出工作原则

## 学习与连续性

<!-- 提示：记录、更新、演进 -->
- 记录关键学习内容

## 核心边界

<!-- 提示：隐私、操作授权 -->
- 明确边界与禁止项
"""

AGENTS_TEMPLATE = """---
schema: soulforge.template/v1
target_file_type: AGENTS
structure:
  section_heading_level: 2
  required_sections:
    - title: 首次运行
    - title: 启动流程
    - title: 记忆
    - title: 工具
    - title: 群聊
    - title: 安全
  section_order: strict
elements:
  heading_style: atx
  list_style: "-"
  code_fence: "```"
  blockquote_prefix: "> "
  heading_blank_line: true
  paragraph_blank_line: true
typography:
  max_heading_level: 3
  allow_bold: true
  allow_italic: true
  forbid_emoji: true
  forbid_raw_html: true
modules:
  frontmatter: optional
---

# AGENTS 文档标准模板

> 严格遵循 YAML 格式化规则，并按下方章节结构组织内容。

## 首次运行

- 初始化步骤

## 启动流程

- 每次会话的启动步骤

## 记忆

- 记忆读写规则

## 工具

- 可用工具与使用边界

## 群聊

- 多 Agent 协作规则

## 安全

- 安全护栏与禁止项
"""

MEMORY_TEMPLATE = """---
schema: soulforge.template/v1
target_file_type: MEMORY
structure:
  section_heading_level: 2
  required_sections:
    - title: 重要决定
    - title: 经验教训
    - title: 待办事项
    - title: 执行摘要
  section_order: strict
elements:
  heading_style: atx
  list_style: "-"
  code_fence: "```"
  blockquote_prefix: "> "
  heading_blank_line: true
  paragraph_blank_line: true
typography:
  max_heading_level: 3
  allow_bold: true
  allow_italic: true
  forbid_emoji: true
  forbid_raw_html: true
modules:
  frontmatter: optional
---

# MEMORY 文档标准模板

> 严格遵循 YAML 格式化规则，按章节结构组织长期记忆。

## 重要决定

- 记录影响后续行为的决定

## 经验教训

- 踩坑与心得

## 待办事项

- 未完成事项

## 执行摘要

- 当前状态速览
"""

# 「工作日志日标准化」（M15 的规则载体）：逐日归并 memory/ 下的日文件，
# 契约来自外部 skill `memory-daily-standardizer`。注意：
# 1) 章节标题含序号（一、二、三、四、五），因为 FormatValidator 对章节标题做精确匹配；
# 2) 章节骨架里 关键决策 使用表格，FormatValidator 已按块级元素处理表格行，不会误判段落空行；
# 3) 不含 HTML 注释提示：模板全文会进入 prompt，模型若照抄注释会触发 forbid_raw_html 而无机械修正手段。
WLOG_DAILY_TEMPLATE = """---
schema: soulforge.template/v1
name: "工作日志日标准化"
target_file_type: WORKLOG
structure:
  section_heading_level: 2
  required_sections:
    - title: 一、今日概览
    - title: 二、关键事件
    - title: 三、关键决策
    - title: 四、待办事项
    - title: 五、明日计划
  section_order: strict
elements:
  heading_style: atx
  list_style: "-"
  code_fence: "```"
  blockquote_prefix: "> "
  heading_blank_line: true
  paragraph_blank_line: true
typography:
  max_heading_level: 3
  allow_bold: true
  allow_italic: true
  forbid_emoji: true
  forbid_raw_html: true
modules:
  frontmatter: optional
---

# 工作日志日标准化模板

> 逐日归并当日全部来源（标准日文件 / 同日 session 导出 / 同日主题文件），
> 剥离元数据壳与对话腔噪音后改写成客观记录。产出文档第一行固定为
> `# 工作日志 - <日期>`（如 `# 工作日志 - 2026-05-20`）；
> 不写来源信息、不保留过程流水，原有事实、决策与待办不得丢失。

## 一、今日概览

- **日期**：YYYY-MM-DD
- **核心活动**：用 1~3 条概括当天最重要的事

## 二、关键事件

### 事件 1

- 事实 / 原因 / 结果

## 三、关键决策

| 决策项 | 内容 |
|--------|------|
| ... | ... |

## 四、待办事项

- [ ] ...

## 五、明日计划

- ...
"""

# 「工作日志总结（记忆归纳）」（M16 的规则载体）：把一段时间的分散记录归纳成**单份**综述，
# 契约来自外部 skill `memory-summarize`（模式 A：月度/主题归纳）。注意：
# 1) 章节标题含序号（一、二、三、四、五），因为 FormatValidator 对章节标题做精确匹配；
# 2) 经验教训 / 重要决定 用表格，FormatValidator 已按块级元素处理表格行；
# 3) 附录「溯源对照表」是**可选**章节 —— 只出现在正文骨架里，不进 required_sections，
#    否则「没有来源可溯源」时会被强规则拦死；
# 4) 不含 HTML 注释提示：模板全文会进入 prompt，模型若照抄注释会触发 forbid_raw_html。
SUMMARY_TEMPLATE = """---
schema: soulforge.template/v1
name: "工作日志总结（记忆归纳）"
target_file_type: SUMMARY
structure:
  section_heading_level: 2
  required_sections:
    - title: 一、完成的工作
    - title: 二、经验教训
    - title: 三、重要决定
    - title: 四、重要信息
    - title: 五、待办事项
  section_order: strict
elements:
  heading_style: atx
  list_style: "-"
  code_fence: "```"
  blockquote_prefix: "> "
  heading_blank_line: true
  paragraph_blank_line: true
typography:
  max_heading_level: 3
  allow_bold: true
  allow_italic: true
  forbid_emoji: true
  forbid_raw_html: true
modules:
  frontmatter: optional
---

# 工作日志总结模板

> 把一段时间（如某个月）的分散记录归纳成一份单一综述：按五大主章节归类，
> 丢弃每天重复的流水账与调试中间态，只保留有长期检索价值的内容。
> 产出文档第一行固定为 `# <时间段> 记忆归纳`（如 `# 2026-08 记忆归纳`）；
> 所有标题使用中文；末尾可附「附录：溯源对照表」。

## 一、完成的工作

- 按主题分类列举完成的任务、产出物与变更项，优先列出有长期价值的内容

## 二、经验教训

| 日期 | 教训 |
|------|------|
| ... | ... |

## 三、重要决定

| 日期 | 决定 |
|------|------|
| ... | ... |

## 四、重要信息

- 身份档案 / 联系人 / 关键配置 / 账号 / 服务器 / 工具脚本

## 五、待办事项

- [ ] ...

## 附录：溯源对照表

| 内容 | 来源日期文件 |
|------|-------------|
| ... | ... |
"""

BUILTIN_TEMPLATES: dict[str, str] = {
    "preset-soul-std": SOUL_TEMPLATE,
    "preset-agents-std": AGENTS_TEMPLATE,
    "preset-mem-std": MEMORY_TEMPLATE,
    "preset-wlog-daily-std": WLOG_DAILY_TEMPLATE,
    "preset-mem-summarize": SUMMARY_TEMPLATE,
}
