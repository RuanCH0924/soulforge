"""TemplateRuleParser：解析标准 Markdown 模板文档 → 结构化格式化规则。

模板文档结构（见 services/preset_templates.py）：
- YAML frontmatter：schema / target_file_type / structure / elements / typography / modules
- 正文：章节结构骨架（标题 + 示例内容）

若模板缺少 frontmatter，则回退到内置默认规则，并从正文标题推断必填章节。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---[ \t]*(?:\n|$)", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class RequiredSection:
    title: str
    required: bool = True


@dataclass
class TemplateRules:
    """模板定义的完整格式化规则（供重排与校验使用）。"""

    name: str = ""
    target_file_type: str = "ANY"
    section_heading_level: int = 2
    required_sections: list[RequiredSection] = field(default_factory=list)
    section_order: str = "strict"  # strict | loose
    heading_style: str = "atx"  # atx | setext
    list_style: str = "-"
    code_fence: str = "```"
    blockquote_prefix: str = "> "
    heading_blank_line: bool = True
    paragraph_blank_line: bool = True
    max_heading_level: int = 3
    allow_bold: bool = True
    allow_italic: bool = True
    forbid_emoji: bool = True
    forbid_raw_html: bool = True
    frontmatter: str = "optional"  # required | optional


def _extract_frontmatter(template_md: str) -> tuple[dict | None, str]:
    m = FRONTMATTER_RE.match(template_md.strip())
    if not m:
        return None, template_md
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    return data, template_md[m.end():]


def _body_headings(body: str, level: int) -> list[str]:
    return [title.strip() for m in re.finditer(HEADING_RE, body)
            for lvl, title in [m.groups()] if len(lvl) == level]


def parse_template(template_md: str) -> TemplateRules:
    """解析模板文档 → TemplateRules（缺省规则用内置默认值）。"""
    rules = TemplateRules()
    fm, body = _extract_frontmatter(template_md)

    if fm:
        rules.name = str(fm.get("name", rules.name))
        rules.target_file_type = str(fm.get("target_file_type", rules.target_file_type) or "ANY")
        structure = fm.get("structure") or {}
        if "section_heading_level" in structure:
            rules.section_heading_level = int(structure["section_heading_level"])
        raw_sections = structure.get("required_sections") or []
        if raw_sections:
            for item in raw_sections:
                if isinstance(item, str):
                    rules.required_sections.append(RequiredSection(title=item))
                elif isinstance(item, dict) and item.get("title"):
                    rules.required_sections.append(RequiredSection(
                        title=str(item["title"]), required=bool(item.get("required", True))))
        if structure.get("section_order"):
            rules.section_order = str(structure["section_order"])
        elements = fm.get("elements") or {}
        rules.heading_style = str(elements.get("heading_style", rules.heading_style))
        rules.list_style = str(elements.get("list_style", rules.list_style))
        rules.code_fence = str(elements.get("code_fence", rules.code_fence))
        rules.blockquote_prefix = str(elements.get("blockquote_prefix", rules.blockquote_prefix))
        if "heading_blank_line" in elements:
            rules.heading_blank_line = bool(elements["heading_blank_line"])
        if "paragraph_blank_line" in elements:
            rules.paragraph_blank_line = bool(elements["paragraph_blank_line"])
        typography = fm.get("typography") or {}
        if "max_heading_level" in typography:
            rules.max_heading_level = int(typography["max_heading_level"])
        if "allow_bold" in typography:
            rules.allow_bold = bool(typography["allow_bold"])
        if "allow_italic" in typography:
            rules.allow_italic = bool(typography["allow_italic"])
        if "forbid_emoji" in typography:
            rules.forbid_emoji = bool(typography["forbid_emoji"])
        if "forbid_raw_html" in typography:
            rules.forbid_raw_html = bool(typography["forbid_raw_html"])
        modules = fm.get("modules") or {}
        if modules.get("frontmatter"):
            rules.frontmatter = str(modules["frontmatter"])

    # 兜底：正文一级/二级标题推断名称与必填章节
    if not rules.name:
        h1 = _body_headings(body, 1)
        if h1:
            rules.name = h1[0]
    if not rules.required_sections:
        for title in _body_headings(body, rules.section_heading_level):
            rules.required_sections.append(RequiredSection(title=title))
    return rules


def derive_sections(template_md: str) -> list[dict]:
    """由模板文档派生 sections_json（供 presets.sections_json 同步）。"""
    rules = parse_template(template_md)
    return [
        {"title": s.title, "required": s.required, "order": i + 1, "hint": None}
        for i, s in enumerate(rules.required_sections)
    ]


def template_rule_summary(rules: TemplateRules) -> str:
    """生成供 AI prompt 使用的人类可读规则摘要。"""
    sections = "\n".join(
        f"  {i + 1}. {s.title}（{'必填' if s.required else '可选'}）"
        for i, s in enumerate(rules.required_sections)
    )
    return (
        f"适用文件类型：{rules.target_file_type}\n"
        f"章节标题层级：{'#' * rules.section_heading_level}（二级标题）\n"
        f"章节顺序：{'严格按下列顺序' if rules.section_order == 'strict' else '不强制顺序'}\n"
        f"必填章节（按顺序）：\n{sections or '  （无）'}\n"
        f"标题风格：ATX（## 形式，禁用 Setext 下划线）\n"
        f"列表风格：无序列表统一用「{rules.list_style} 」\n"
        f"代码块围栏：{rules.code_fence}\n"
        f"引用前缀：{rules.blockquote_prefix}\n"
        f"标题后需空行：{'是' if rules.heading_blank_line else '否'}\n"
        f"段落间需空行：{'是' if rules.paragraph_blank_line else '否'}\n"
        f"最大标题层级：{rules.max_heading_level}\n"
        f"加粗/斜体：{'允许' if rules.allow_bold else '禁止'}/{'允许' if rules.allow_italic else '禁止'}\n"
        f"禁止 emoji：{'是' if rules.forbid_emoji else '否'}\n"
        f"禁止原始 HTML：{'是' if rules.forbid_raw_html else '否'}"
    )
