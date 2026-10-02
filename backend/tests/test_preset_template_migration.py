"""黄金等值测试：模板「存量形态」与「新形态」的解析结果逐字段一致。

这是本次改造（docs/PRESET-TEMPLATE-REFACTOR-PLAN.md）的**核心防回归闸门**：
无论走哪条路径，`FormatValidator` 拿到的 `TemplateRules` 必须完全相同——

- 存量路径：`parse_preset(旧模板 YAML+参考文档, None)`（惰性兼容，不写库）
- 新形态路径：`parse_preset(纯参考文档, format_rules)`（参考文档 + 结构化规则）

只比较**校验相关字段**（`name` / `target_file_type` 是展示字段，以预设表字段为准，不参与校验）。
`section_order` 已随「章节」配置移除，不再是规则键。
"""
from __future__ import annotations

from dataclasses import asdict

import pytest

from app.services.preset_service import BUILTIN_PRESETS
from app.services.preset_templates import BUILTIN_FORMAT_RULES, BUILTIN_TEMPLATES
from app.services.template_rules import extract_format_rules, parse_preset, template_body

# 校验相关字段（排除 name / target_file_type）
_VALIDATOR_FIELDS = (
    "required_sections", "section_heading_level",
    "heading_style", "list_style", "code_fence", "blockquote_prefix",
    "heading_blank_line", "paragraph_blank_line", "max_heading_level",
    "allow_bold", "allow_italic", "forbid_emoji", "forbid_raw_html", "frontmatter",
)


def _validator_view(rules) -> dict:
    data = asdict(rules)
    return {k: data[k] for k in _VALIDATOR_FIELDS}


def _assert_migrated_equals_legacy(legacy_doc: str) -> None:
    """存量解析 == 迁移后的新形态解析。"""
    legacy = parse_preset(legacy_doc, None)
    migrated_rules = extract_format_rules(legacy_doc)
    migrated = parse_preset(template_body(legacy_doc), migrated_rules)
    assert _validator_view(migrated) == _validator_view(legacy)


def _legacy_wrap(skeleton: str, rules: dict, sections: list[str], target: str,
                 typography: dict | None = None) -> str:
    """按「改造前」的形态把纯参考文档包成 YAML + 正文（测试自有，不依赖生产代码）。"""
    required = "\n".join(f"    - title: {t}" for t in sections)
    typo = {"max_heading_level": 3, "allow_bold": True, "allow_italic": True,
            "forbid_emoji": True, "forbid_raw_html": True}
    typo.update(typography or {})
    typo_block = "\n".join(f"  {k}: {str(v).lower() if isinstance(v, bool) else v}"
                           for k, v in typo.items())
    return (
        "---\n"
        "schema: soulforge.template/v1\n"
        f"target_file_type: {target}\n"
        "structure:\n"
        f"  section_heading_level: {rules['section_heading_level']}\n"
        "  required_sections:\n"
        f"{required}\n"
        "elements:\n"
        "  heading_style: atx\n"
        '  list_style: "-"\n'
        "  heading_blank_line: true\n"
        "  paragraph_blank_line: true\n"
        "typography:\n"
        f"{typo_block}\n"
        "modules:\n"
        f"  frontmatter: {'required' if rules['require_frontmatter'] else 'optional'}\n"
        "---\n\n"
        f"{skeleton}"
    )


# ---------- 5 个内置预设：把纯参考文档还原成旧形态，断言新旧解析一致 ----------

@pytest.mark.parametrize("data", BUILTIN_PRESETS, ids=lambda d: d["id"])
def test_builtin_reference_migrates_without_behavior_change(data):
    skeleton = BUILTIN_TEMPLATES[data["id"]]
    rules = BUILTIN_FORMAT_RULES[data["id"]]
    legacy = _legacy_wrap(skeleton, rules,
                          [s["title"] for s in data["sections"]], data["target_file_type"])

    legacy_rules = parse_preset(legacy, None)
    new_rules = parse_preset(skeleton, rules)

    assert _validator_view(new_rules) == _validator_view(legacy_rules)
    # 顺带钉住契约：章节与 sections 一致
    assert [s.title for s in new_rules.required_sections] == [s["title"] for s in data["sections"]]


def test_summary_reference_headings_survive_migration():
    """SUMMARY 的附录仍是参考文档里的普通章节：两条路径解析出的章节完全一致。"""
    data = next(d for d in BUILTIN_PRESETS if d["id"] == "preset-mem-summarize")
    skeleton = BUILTIN_TEMPLATES[data["id"]]
    rules = BUILTIN_FORMAT_RULES[data["id"]]
    legacy = _legacy_wrap(skeleton, rules,
                          [s["title"] for s in data["sections"]], data["target_file_type"])

    titles = [s.title for s in parse_preset(skeleton, rules).required_sections]
    assert "附录：溯源对照表" in titles
    assert titles == [s.title for s in parse_preset(legacy, None).required_sections]


# ---------- 边界样本：非默认排版定制 / 必填 frontmatter / 乱序 / 无 YAML ----------

NON_DEFAULT_TYPO_LEGACY = """---
schema: soulforge.template/v1
target_file_type: ANY
structure:
  section_heading_level: 2
  required_sections:
    - title: 甲
    - title: 乙
  section_order: loose
elements:
  heading_style: atx
  list_style: "*"
  heading_blank_line: true
  paragraph_blank_line: true
typography:
  max_heading_level: 4
  allow_bold: true
  allow_italic: true
  forbid_emoji: false
  forbid_raw_html: true
modules:
  frontmatter: required
---

# 标题

## 甲

- a

## 乙

- b

## 丙（可选）

- c
"""


def test_non_default_typography_is_preserved_by_migration():
    """存量用户改过的排版键（与全局默认不同）迁移后必须保留，不得被收敛掉。"""
    migrated = extract_format_rules(NON_DEFAULT_TYPO_LEGACY)
    assert migrated["forbid_emoji"] is False
    assert migrated["max_heading_level"] == 4
    assert migrated["list_style"] == "*"
    assert migrated["require_frontmatter"] is True
    assert "section_order" not in migrated
    assert "optional_sections" not in migrated
    _assert_migrated_equals_legacy(NON_DEFAULT_TYPO_LEGACY)


def test_no_yaml_skeleton_is_unchanged():
    doc = "# 标题\n\n## 甲\n\n- a\n\n## 乙\n\n- b\n"
    _assert_migrated_equals_legacy(doc)
