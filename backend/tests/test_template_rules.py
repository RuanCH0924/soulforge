"""单元测试：模板规则解析（TemplateRuleParser）与格式校验（FormatValidator）。

覆盖：
- 模板文档 → 结构化规则（frontmatter + 正文骨架兜底）
- 规则摘要生成（供 AI prompt）
- 格式校验各维度：章节缺失/顺序、标题风格/层级、列表前缀、段落空行、
  emoji、原始 HTML、代码围栏、frontmatter
- 机械性自动修正 + 修正后重校验（100% 合规）
"""
from __future__ import annotations

from app.services.format_validator import FormatValidator
from app.services.preset_templates import SOUL_TEMPLATE
from app.services.template_rules import derive_sections, parse_template, template_rule_summary

EMPTY_TEMPLATE = "# 无 frontmatter 模板\n\n## 章节甲\n\n正文。\n\n## 章节乙\n\n正文。\n"

# 精简模板：仅两个必填章节，便于聚焦各维度校验
COMPACT_TEMPLATE = """---
schema: soulforge.template/v1
target_file_type: SOUL
structure:
  section_heading_level: 2
  required_sections:
    - title: 章节A
    - title: 章节B
  section_order: strict
elements:
  heading_style: atx
  list_style: "-"
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
"""


# ---------- 模板规则解析 ----------

def test_parse_template_full_rules():
    rules = parse_template(SOUL_TEMPLATE)
    assert rules.name == "SOUL 文档标准模板"  # frontmatter 未写 name，正文 H1 兜底
    assert rules.target_file_type == "SOUL"
    assert rules.section_heading_level == 2
    assert rules.section_order == "strict"
    assert [s.title for s in rules.required_sections] == [
        "核心行为准则", "工作态度和原则", "学习与连续性", "核心边界"]
    assert all(s.required for s in rules.required_sections)
    assert rules.heading_style == "atx"
    assert rules.list_style == "-"
    assert rules.code_fence == "```"
    assert rules.heading_blank_line is True
    assert rules.paragraph_blank_line is True
    assert rules.max_heading_level == 3
    assert rules.allow_bold is True
    assert rules.forbid_emoji is True
    assert rules.forbid_raw_html is True
    assert rules.frontmatter == "optional"


def test_parse_template_fallback_without_frontmatter():
    rules = parse_template(EMPTY_TEMPLATE)
    assert rules.target_file_type == "ANY"
    assert rules.section_heading_level == 2
    # 正文二级标题兜底为必填章节
    assert [s.title for s in rules.required_sections] == ["章节甲", "章节乙"]
    assert rules.name == "无 frontmatter 模板"  # 正文 H1 兜底


def test_derive_sections_orders_by_template():
    sections = derive_sections(SOUL_TEMPLATE)
    assert sections[0] == {"title": "核心行为准则", "required": True, "order": 1, "hint": None}
    assert [s["title"] for s in sections] == [
        "核心行为准则", "工作态度和原则", "学习与连续性", "核心边界"]


def test_template_rule_summary_contains_key_rules():
    summary = template_rule_summary(parse_template(SOUL_TEMPLATE))
    assert "适用文件类型：SOUL" in summary
    assert "##（二级标题）" in summary
    assert "核心行为准则（必填）" in summary
    assert "严格按下列顺序" in summary
    assert "无序列表统一用「- 」" in summary
    assert "禁止 emoji：是" in summary
    assert "禁止原始 HTML：是" in summary


# ---------- 格式校验 ----------

def _rules(template_md=COMPACT_TEMPLATE):
    return parse_template(template_md)


def test_validate_ok_for_compliant_doc():
    content = (
        "# 标题\n\n"
        "## 章节A\n\n- 内容甲\n\n"
        "## 章节B\n\n- 内容乙\n"
    )
    report = FormatValidator().validate(content, _rules())
    assert report.ok is True
    assert report.violations == []


def test_validate_missing_required_section():
    content = "# 标题\n\n## 章节B\n\n- 内容乙\n"
    report = FormatValidator().validate(content, _rules())
    assert report.ok is False
    assert "STR-MISSING-SECTION" in {v.rule_id for v in report.violations}
    assert any("章节A" in v.message for v in report.violations)


def test_validate_section_order_wrong():
    content = (
        "# 标题\n\n"
        "## 章节B\n\n- 内容乙\n\n"
        "## 章节A\n\n- 内容甲\n"
    )
    report = FormatValidator().validate(content, _rules())
    assert "STR-SECTION-ORDER" in {v.rule_id for v in report.violations}


def test_validate_setext_heading_flagged():
    content = "# 标题\n\n章节A\n------------\n\n- 内容甲\n\n## 章节B\n\n- 内容乙\n"
    report = FormatValidator().validate(content, _rules())
    assert "FMT-SETEXT-HEADING" in {v.rule_id for v in report.violations}


def test_validate_heading_level_above_max():
    content = "# 标题\n\n## 章节A\n\n#### 子级标题\n\n- 内容甲\n\n## 章节B\n\n- 内容乙\n"
    report = FormatValidator().validate(content, _rules())
    assert "FMT-HEADING-LEVEL" in {v.rule_id for v in report.violations}


def test_validate_list_prefix_mismatch():
    content = "# 标题\n\n## 章节A\n\n* 内容甲\n\n## 章节B\n\n- 内容乙\n"
    report = FormatValidator().validate(content, _rules())
    assert "FMT-LIST-STYLE" in {v.rule_id for v in report.violations}


def test_validate_emoji_in_heading():
    content = "# 标题\n\n## 章节A 🚀\n\n- 内容甲\n\n## 章节B\n\n- 内容乙\n"
    report = FormatValidator().validate(content, _rules())
    assert "TYP-EMOJI" in {v.rule_id for v in report.violations}


def test_validate_raw_html_flagged():
    content = "# 标题\n\n## 章节A\n\n<div>不应存在</div>\n\n## 章节B\n\n- 内容乙\n"
    report = FormatValidator().validate(content, _rules())
    assert "TYP-RAW-HTML" in {v.rule_id for v in report.violations}


def test_validate_html_placeholders_not_flagged():
    """实测回归：工作日志里的占位符（`session:<id>` / `<jobId>`）不是原始 HTML。

    此前把任何 `<单词>` 都判为原始 HTML，而该规则**没有机械修正手段** →
    真实日志里只要出现这类枚举/占位符写法，整天就被拦死、无法写入（P3 实测发现）。
    """
    content = (
        "# 标题\n\n## 章节A\n\n"
        '- 类型定义：`"enum": ["main","isolated","current","session:<id>"]`\n'
        "- 每个 cron job 只能指定一个 `cron:<jobId>`\n"
        "- 裸占位符 <jobId> 与 <ID> 也不是标签\n\n"
        "## 章节B\n\n- 内容乙\n"
    )
    report = FormatValidator().validate(content, _rules())
    assert "TYP-RAW-HTML" not in {v.rule_id for v in report.violations}


def test_validate_inline_code_html_example_not_flagged():
    """行内代码 / 围栏代码块里的 HTML 示例是「说明」，不算文档使用原始 HTML。"""
    content = (
        "# 标题\n\n## 章节A\n\n"
        "- 用 `<br>` 表示换行：\n\n"
        "```html\n<div>x</div>\n```\n\n"
        "## 章节B\n\n- 内容乙\n"
    )
    report = FormatValidator().validate(content, _rules())
    assert "TYP-RAW-HTML" not in {v.rule_id for v in report.violations}


def test_validate_real_html_variants_still_flagged():
    """真实标签（带属性 / 自闭合 / 闭合标签 / 大写）仍必须被拦。"""
    for bad in ('<span style="color:red">x</span>', "<br/>", "</div>", "<IMG src=a>"):
        content = f"# 标题\n\n## 章节A\n\n{bad}\n\n## 章节B\n\n- 内容乙\n"
        report = FormatValidator().validate(content, _rules())
        assert "TYP-RAW-HTML" in {v.rule_id for v in report.violations}, bad


def test_validate_unclosed_code_fence():
    content = "# 标题\n\n## 章节A\n\n```python\nx = 1\n\n## 章节B\n\n- 内容乙\n"
    report = FormatValidator().validate(content, _rules())
    assert "FMT-CODE-FENCE" in {v.rule_id for v in report.violations}


def test_validate_adjacent_paragraphs_no_blank():
    content = "# 标题\n\n## 章节A\n\n第一段\n第二段\n\n## 章节B\n\n- 内容乙\n"
    report = FormatValidator().validate(content, _rules())
    assert "FMT-PARAGRAPH-BLANK" in {v.rule_id for v in report.violations}


def test_validate_dash_list_items_not_flagged_as_paragraphs():
    # 相邻的「- 」列表项是正常写法，不得误判为「段落间缺空行」
    content = "# 标题\n\n## 章节A\n\n- 项一\n- 项二\n\n## 章节B\n\n- 内容乙\n"
    report = FormatValidator().validate(content, _rules())
    assert report.ok is True


def test_validate_table_rows_not_flagged_as_paragraphs():
    # 回归：Markdown 表格的相邻行不是「段落间缺空行」（曾误报，且 auto_fix 会在表行间插空行、破坏表格）
    content = (
        "# 标题\n\n## 章节A\n\n"
        "| 决策项 | 内容 |\n"
        "|--------|------|\n"
        "| 日志格式 | 每天 1 个文件 |\n\n"
        "## 章节B\n\n- 内容乙\n"
    )
    report = FormatValidator().validate(content, _rules())
    assert report.ok is True
    assert "FMT-PARAGRAPH-BLANK" not in {v.rule_id for v in report.violations}


def test_auto_fix_keeps_table_intact_while_fixing_other_issues():
    # 触发 auto_fix 的同时，表格结构必须原样保留
    content = (
        "# 标题\n\n## 章节A\n\n"
        "| 决策项 | 内容 |\n"
        "|--------|------|\n"
        "| 日志格式 | 每天 1 个文件 |\n\n"
        "## 章节B\n\n* 内容乙\n"  # 违规：列表前缀应为「- 」
    )
    fixed, report = FormatValidator().validate_and_fix(content, _rules())
    assert report.ok is True
    assert "| 决策项 | 内容 |\n|--------|------|\n| 日志格式 | 每天 1 个文件 |" in fixed
    assert "- 内容乙" in fixed


def test_validate_horizontal_rule_not_flagged_as_list():
    content = "# 标题\n\n## 章节A\n\n- 项一\n\n* * *\n\n- 项二\n\n## 章节B\n\n- 内容乙\n"
    report = FormatValidator().validate(content, _rules())
    assert report.ok is True
    assert "FMT-LIST-STYLE" not in {v.rule_id for v in report.violations}


def test_validate_required_frontmatter():
    rules = parse_template(COMPACT_TEMPLATE)
    rules.frontmatter = "required"
    report = FormatValidator().validate("# 标题\n\n## 章节A\n\n- 内容甲\n\n## 章节B\n\n- 内容乙\n", rules)
    assert "MOD-FRONTMATTER" in {v.rule_id for v in report.violations}


# ---------- 自动修正 ----------

def test_auto_fix_setext_to_atx_and_blank_line():
    content = "# 标题\n章节A\n------------\n\n- 内容甲\n\n## 章节B\n\n- 内容乙\n"
    rules = _rules()
    fixed, report = FormatValidator().validate_and_fix(content, rules)
    assert report.ok is True
    assert "## 章节A" in fixed
    assert "------------" not in fixed


def test_auto_fix_list_prefix_and_emoji():
    content = "# 标题\n\n## 章节A 🚀\n\n* 内容甲\n\n## 章节B\n\n- 内容乙\n"
    rules = _rules()
    fixed, report = FormatValidator().validate_and_fix(content, rules)
    assert report.ok is True
    assert "## 章节A" in fixed
    assert "🚀" not in fixed
    assert "* 内容甲" not in fixed
    assert "- 内容甲" in fixed


def test_auto_fix_closes_unclosed_fence():
    content = "# 标题\n\n## 章节A\n\n- 内容甲\n\n## 章节B\n\n- 内容乙\n\n```\nx = 1\n"
    fixed, report = FormatValidator().validate_and_fix(content, _rules())
    assert report.ok is True
    assert fixed.rstrip().endswith("```")


def test_auto_fix_adjacent_paragraphs_adds_blank():
    content = "# 标题\n\n## 章节A\n\n第一段\n第二段\n\n## 章节B\n\n- 内容乙\n"
    rules = _rules()
    fixed, report = FormatValidator().validate_and_fix(content, rules)
    assert report.ok is True
    assert "第一段\n\n第二段" in fixed


def test_validate_and_fix_idempotent_for_compliant_doc():
    content = "# 标题\n\n## 章节A\n\n- 内容甲\n\n## 章节B\n\n- 内容乙\n"
    fixed, report = FormatValidator().validate_and_fix(content, _rules())
    assert report.ok is True
    assert fixed == content  # 已合规时保持原文不变


def test_validate_and_fix_unfixable_missing_section():
    content = "# 标题\n\n## 章节B\n\n- 内容乙\n"
    _, report = FormatValidator().validate_and_fix(content, _rules())
    assert report.ok is False  # 缺失章节无法机械补齐
    assert "STR-MISSING-SECTION" in {v.rule_id for v in report.violations}


# ---------- 输出净化：剥离思考过程 / 前言（sanitize） ----------

# 典型病灶：模型在正文前复述任务与格式化规则
PREAMBLE_OUTPUT = (
    "让我仔细分析这个任务：\n"
    "格式化规则要求：\n"
    "文件类型：SOUL\n"
    "章节标题层级：##（二级标题）\n"
    "章节顺序：核心行为准则 → 工作态度和原则\n\n"
    "# 整理后\n\n"
    "## 章节A\n\n- 内容甲\n\n"
    "## 章节B\n\n- 内容乙\n"
)


def test_sanitize_strips_conversational_preamble():
    body, removed = FormatValidator().sanitize(PREAMBLE_OUTPUT)
    assert removed is not None and "让我仔细分析" in removed
    assert body.startswith("# 整理后")          # 正文从标题开始
    assert "让我仔细分析" not in body
    assert "文件类型：SOUL" not in body


def test_sanitize_keeps_legit_intro_paragraph():
    """文档自身的开头段落（无对话特征）不得被误删。"""
    content = "本文件是 main Agent 的灵魂文档，用于约束日常行为。\n\n# 整理后\n\n## 章节A\n\n- 内容甲\n"
    body, removed = FormatValidator().sanitize(content)
    assert removed is None
    assert body.startswith("本文件是 main Agent")


def test_sanitize_unwraps_whole_document_fence():
    content = "以下是整理后的文档：\n\n```markdown\n# 整理后\n\n## 章节A\n\n- 内容甲\n```\n"
    body, removed = FormatValidator().sanitize(content)
    assert removed is not None
    assert body.startswith("# 整理后")
    assert "```" not in body


def test_sanitize_keeps_inner_code_fence():
    """文档内部的代码块不受外层围栏剥离影响。"""
    content = "# 整理后\n\n## 章节A\n\n- 内容甲\n\n```bash\necho hi\n```\n"
    body, removed = FormatValidator().sanitize(content)
    assert removed is None
    assert body == content.strip("\n")


def test_sanitize_leaves_compliant_output_untouched():
    content = "# 整理后\n\n## 章节A\n\n- 内容甲\n\n## 章节B\n\n- 内容乙\n"
    body, removed = FormatValidator().sanitize(content)
    assert removed is None
    assert body == content.strip("\n")


def test_sanitize_strips_reasoning_block_with_english_content():
    """P3 实测：推理模型的思考块内容可能是英文，前言特征词匹配不上，必须按标签显式剥离。

    漏剥时 `<think>` 会触发 forbid_raw_html，把一次成功的归并误判为强规则失败。
    """
    content = (
        "<think>\nThe user wants me to merge the day's sources into one log.\n"
        "Step 1: read rules. Step 2: merge.\n</think>\n"
        "# 工作日志 - 2026-07-03\n\n## 一、今日概览\n\n- 完成端口巡检\n"
    )
    body, removed = FormatValidator().sanitize(content)
    assert removed is not None and "Step 1: read rules" in removed
    assert body.startswith("# 工作日志 - 2026-07-03")
    assert "<think>" not in body and "</think>" not in body


def test_sanitize_strips_reasoning_block_mid_document_lead():
    """思考块之后还有一段中文前言时，两者都被剥离（顺序：先剥标签块，再判前言）。"""
    content = (
        "<thinking>let me plan</thinking>\n"
        "让我先读取全部来源，然后归并。\n\n"
        "# 工作日志 - 2026-07-03\n\n## 一、今日概览\n\n- 完成巡检\n"
    )
    body, removed = FormatValidator().sanitize(content)
    assert removed is not None
    assert "let me plan" in removed and "让我先读取" in removed
    assert body.startswith("# 工作日志 - 2026-07-03")


def test_sanitize_keeps_tag_example_inside_document():
    """正文（非开头）里作为示例出现的标签不得被误删——只有「以思考块开头」才剥。"""
    content = (
        "# 工作日志 - 2026-07-03\n\n## 二、关键事件\n\n"
        "prompt 里用 `<think>hidden</think>` 包裹思考过程。\n"
    )
    body, removed = FormatValidator().sanitize(content)
    assert removed is None
    assert "<think>hidden</think>" in body


def test_sanitize_keeps_unclosed_reasoning_block():
    """未闭合的思考块说明被 max_tokens 截断：不剥（此时没有正文，交给强规则报错）。"""
    content = "<think>\nThe user wants me to merge sources but the output was truncated"
    body, removed = FormatValidator().sanitize(content)
    assert removed is None
    assert body.startswith("<think>")


def test_sanitize_handles_crlf_and_bom():
    content = "\ufeff让我先分析：\r\n\r\n# 整理后\r\n\r\n## 章节A\r\n\r\n- 内容甲\r\n"
    body, removed = FormatValidator().sanitize(content)
    assert removed is not None
    assert "\r" not in body
    assert body.startswith("# 整理后")


def test_sanitized_preamble_output_passes_validation():
    """净化后的输出可正常通过格式校验（不再因前言而携带噪音内容）。"""
    body, _ = FormatValidator().sanitize(PREAMBLE_OUTPUT)
    fixed, report = FormatValidator().validate_and_fix(body, _rules())
    assert report.ok is True
    assert "让我仔细分析" not in fixed
