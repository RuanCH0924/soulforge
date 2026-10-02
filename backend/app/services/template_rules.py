"""TemplateRuleParser：解析预设的格式化规则 → 结构化 `TemplateRules`。

**两类来源，一个入口**：

1. `format_rules`（结构化；`presets.format_rules_json`）—— 预设级只保留必要开关：
   `section_heading_level`（用于从参考文档派生章节清单，供「应用预设」机械补齐）与
   `require_frontmatter`。其余排版键收敛为 `TemplateRules` 的**全局默认值**。
2. `template_md` 里的旧 YAML frontmatter（存量兼容）—— 老安装的模板仍是「YAML 规则 + 参考文档」。

解析优先级：`format_rules`（显式）> 旧 YAML frontmatter > 全局默认。

> 说明（本次调整）：**「章节」不再是一项独立配置**——不再有「可选章节 / 必须章节 / 章节顺序」的设置，
> 「章节清单」只由**预设参考文档**的标题派生，作为机械补齐（应用预设）的依据，不再作为大模型
> 任务执行的约束。详见 docs/PRESET-TEMPLATE-REFACTOR-PLAN.md。

`parse_preset(template_md, format_rules=None)` 是唯一入口；`parse_template(template_md)`
是它的存量兼容别名。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---[ \t]*(?:\n|$)", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

FORMAT_RULES_SCHEMA = "soulforge.format-rules/v1"

# 预设级格式化规则的默认值（UI 只暴露这两项；其余排版键由 TemplateRules 默认值承担）
FORMAT_RULES_DEFAULTS: dict = {
    "schema": FORMAT_RULES_SCHEMA,
    "section_heading_level": 2,
    "require_frontmatter": False,
}

# 作为「覆盖项」接受的其它排版键（迁移时可保留用户定制；新 UI 不暴露）
_OVERRIDE_CASTERS = {
    "heading_style": str,
    "list_style": str,
    "code_fence": str,
    "blockquote_prefix": str,
    "heading_blank_line": bool,
    "paragraph_blank_line": bool,
    "max_heading_level": int,
    "allow_bold": bool,
    "allow_italic": bool,
    "forbid_emoji": bool,
    "forbid_raw_html": bool,
}


@dataclass
class RequiredSection:
    title: str
    required: bool = True


@dataclass
class TemplateRules:
    """模板定义的完整格式化规则（供重排与排版校验使用）。

    字段的默认值即**全局默认**。注意：**不含章节顺序 / 必填约束**（已随「章节」配置一并移除）。
    """

    name: str = ""
    target_file_type: str = "ANY"
    section_heading_level: int = 2
    # 由「预设参考文档」的标题派生，仅供「应用预设」的机械补齐使用（非模型约束）
    required_sections: list[RequiredSection] = field(default_factory=list)
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


def template_body(template_md: str | None) -> str:
    """模板的正文（剥掉 YAML frontmatter）——「预设参考文档」的形态。"""
    if not template_md:
        return ""
    _, body = _extract_frontmatter(template_md)
    return body.lstrip("\n")


_FENCE_LINE_RE = re.compile(r"^\s*(```|~~~)")


def _body_headings(body: str, level: int) -> list[str]:
    """正文里指定层级的标题（**跳过围栏代码块**，代码块里的 `## 假章节` 不算）。"""
    out: list[str] = []
    in_fence = False
    for line in body.split("\n"):
        if _FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == level:
            out.append(m.group(2).strip())
    return out


def _apply_yaml(rules: TemplateRules, fm: dict) -> None:
    """把旧 YAML frontmatter 的规则合并进 rules（存量兼容路径）。"""
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


def apply_format_rules(rules: TemplateRules, data: dict) -> TemplateRules:
    """把结构化 `format_rules` 合并进 rules（显式优先）；返回同一个 rules（链式用）。"""
    if not isinstance(data, dict):
        return rules
    if data.get("section_heading_level") is not None:
        rules.section_heading_level = int(data["section_heading_level"])
    if "require_frontmatter" in data:
        rules.frontmatter = "required" if bool(data["require_frontmatter"]) else "optional"
    for key, caster in _OVERRIDE_CASTERS.items():  # 覆盖项（迁移保留用户定制用）
        if key in data and data[key] is not None:
            setattr(rules, key, caster(data[key]))
    return rules


def parse_preset(template_md: str | None, format_rules: dict | None = None) -> TemplateRules:
    """解析预设 → `TemplateRules`（唯一入口，含存量兼容）。

    - `format_rules` 显式给出的键优先于 `template_md` 内的旧 YAML。
    - `required_sections` 恒由**预设参考文档**（`template_md` 的标题）派生；仅当正文没有任何该层级
      标题时，才回退到旧 YAML 里手写的 `required_sections`。
    """
    rules = TemplateRules()
    fm, body = _extract_frontmatter(template_md or "")

    if fm:
        _apply_yaml(rules, fm)
    if isinstance(format_rules, dict):
        apply_format_rules(rules, format_rules)

    body_headings = _body_headings(body, rules.section_heading_level)
    if body_headings:
        rules.required_sections = [RequiredSection(title=h) for h in body_headings]

    if not rules.name:
        h1 = _body_headings(body, 1)
        if h1:
            rules.name = h1[0]
    return rules


def parse_template(template_md: str) -> TemplateRules:
    """存量兼容别名：等价于不带结构化规则的 `parse_preset`。"""
    return parse_preset(template_md, None)


def normalize_format_rules(data: dict | None) -> dict:
    """补齐结构化规则的键（+ schema）；非法值回落默认。"""
    out = {
        "schema": FORMAT_RULES_SCHEMA,
        "section_heading_level": FORMAT_RULES_DEFAULTS["section_heading_level"],
        "require_frontmatter": FORMAT_RULES_DEFAULTS["require_frontmatter"],
    }
    if not isinstance(data, dict):
        return out
    if data.get("section_heading_level") is not None:
        try:
            out["section_heading_level"] = int(data["section_heading_level"])
        except (TypeError, ValueError):
            pass
    if "require_frontmatter" in data:
        out["require_frontmatter"] = bool(data["require_frontmatter"])
    # 排版覆盖项：仅当存量迁移确实需要保留「与全局默认不同」的定制时才出现
    for key, caster in _OVERRIDE_CASTERS.items():
        if key in data and data[key] is not None:
            try:
                out[key] = caster(data[key])
            except (TypeError, ValueError):
                pass
    return out


def extract_format_rules(template_md: str | None) -> dict:
    """由（可能是旧的）模板文档反推结构化规则——API 读路径补齐用。"""
    rules = parse_preset(template_md, None)
    data: dict = {
        "section_heading_level": rules.section_heading_level,
        "require_frontmatter": rules.frontmatter == "required",
    }
    # 保留「与全局默认不同」的排版定制（迁移时不丢用户改动）
    defaults = TemplateRules()
    for key in _OVERRIDE_CASTERS:
        if getattr(rules, key) != getattr(defaults, key):
            data[key] = getattr(rules, key)
    return normalize_format_rules(data)


def derive_sections(template_md: str, format_rules: dict | None = None) -> list[dict]:
    """由参考文档派生章节清单（供 presets.sections_json 同步 / 应用预设机械补齐）。"""
    rules = parse_preset(template_md, format_rules)
    return [
        {"title": s.title, "required": s.required, "order": i + 1, "hint": None}
        for i, s in enumerate(rules.required_sections)
    ]
