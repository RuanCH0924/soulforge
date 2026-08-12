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
