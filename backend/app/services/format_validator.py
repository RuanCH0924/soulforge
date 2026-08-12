"""FormatValidator：按模板规则校验文档格式，并支持机械性自动修正。

校验维度（对应模板 YAML 的 structure / elements / typography / modules）：
- 必填章节存在且顺序严格
- ATX 标题（禁用 Setext 下划线）
- 标题层级不超过上限
- 无序列表统一使用指定前缀
- 代码块围栏成对
- 标题后空行 / 段落间空行
- 标题禁 emoji
- 禁原始 HTML
- frontmatter 是否必需

auto_fix 只做机械性修正（不影响语义），修正后再次校验。
FormatReport / FormatViolation 直接复用 schemas 中的 Pydantic 模型。
"""
from __future__ import annotations

import re

from app.models.schemas import FormatReport, FormatViolation
from app.services.template_rules import TemplateRules

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SETEXT_H1_RE = re.compile(r"^=+\s*$")
SETEXT_H2_RE = re.compile(r"^-{3,}\s*$")
FENCE_RE = re.compile(r"^`{3,}")
LIST_BULLET_RE = re.compile(r"^([*+])\s+")
LIST_LINE_RE = re.compile(r"^\s*([-*+]\s|\d+\.\s)")
HR_RE = re.compile(r"^\s*(([*_-]\s*){3,})$")  # 水平分割线：--- / * * * / ___
HTML_TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)(\s|/?>)")
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2B50\u2764\u2705\u2728\u2934]"
)


def _heading_at(content: str, title: str, level: int) -> int | None:
    """返回指定层级标题所在行号（1-based），未找到返回 None。"""
    for i, line in enumerate(content.splitlines(), start=1):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == level and m.group(2).strip() == title:
            return i
    return None


class FormatValidator:
    def validate(self, content: str, rules: TemplateRules) -> FormatReport:
        violations: list[FormatViolation] = []
        lines = content.splitlines()

        # ---------- 结构：必填章节 ----------
        for sec in rules.required_sections:
            if not sec.required:
                continue
            if _heading_at(content, sec.title, rules.section_heading_level) is None:
                violations.append(FormatViolation(
                    rule_id="STR-MISSING-SECTION", rule_name="缺失必填章节",
                    message=f"缺少必填章节「{sec.title}」（应为 {'#' * rules.section_heading_level} 级标题）"))

        # ---------- 结构：章节顺序 ----------
        if rules.section_order == "strict":
            positions = [_heading_at(content, s.title, rules.section_heading_level)
                         for s in rules.required_sections if s.required]
            positions = [p for p in positions if p is not None]
            if len(positions) >= 2 and any(positions[i] > positions[i + 1] for i in range(len(positions) - 1)):
                violations.append(FormatViolation(
                    rule_id="STR-SECTION-ORDER", rule_name="章节顺序错误",
                    message="必填章节未按模板规定的顺序排列"))

        in_fence = False
        fence_count = 0
        for i, line in enumerate(lines, start=1):
            # 代码块状态跟踪
            if FENCE_RE.match(line):
                in_fence = not in_fence
                fence_count += 1
                continue
            if in_fence:
                continue

            # ---------- 元素：标题 ----------
            m = HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                if level > rules.max_heading_level:
                    violations.append(FormatViolation(
                        rule_id="FMT-HEADING-LEVEL", rule_name="标题层级超限", line=i,
                        message=f"标题层级 {level} 超过模板上限 {rules.max_heading_level}"))
                if rules.forbid_emoji and EMOJI_RE.search(line):
                    violations.append(FormatViolation(
                        rule_id="TYP-EMOJI", rule_name="标题含 emoji", line=i,
                        message=f"标题禁止 emoji：{line.strip()}"))
                if rules.heading_blank_line:
                    nxt = lines[i] if i < len(lines) else ""
                    if nxt and nxt.strip() and not HEADING_RE.match(nxt):
                        violations.append(FormatViolation(
                            rule_id="FMT-HEADING-BLANK", rule_name="标题后缺空行", line=i,
                            message="标题后应有一个空行再接正文"))
                continue

            # ---------- 元素：Setext 下划线 ----------
            if (SETEXT_H1_RE.match(line) or SETEXT_H2_RE.match(line)) and i > 1 and lines[i - 2].strip():
                violations.append(FormatViolation(
                    rule_id="FMT-SETEXT-HEADING", rule_name="Setext 下划线标题", line=i,
                    message="应使用 ATX 标题（##），禁用 ===== / ----- 下划线"))

            # ---------- 元素：列表（`-`/`*`/`+`/数字，排除水平分割线） ----------
            lb = LIST_BULLET_RE.match(line)
            if lb and rules.list_style and not HR_RE.match(line):
                violations.append(FormatViolation(
                    rule_id="FMT-LIST-STYLE", rule_name="列表前缀不符", line=i,
                    message=f"无序列表项应以「{rules.list_style} 」开头（当前为「{lb.group(1)} 」）"))

            # ---------- 排版：段落间空行（仅相邻两个段落直接相连时判违规） ----------
            if (rules.paragraph_blank_line and i > 1 and line.strip() and lines[i - 2].strip()
                    and not LIST_LINE_RE.match(line) and not HR_RE.match(line)):
                prev = lines[i - 2]  # enumerate 从 1 开始，i-2 才是紧邻上一行
                if (not HEADING_RE.match(prev) and not LIST_LINE_RE.match(prev)
                        and not prev.lstrip().startswith((">", "```"))
                        and not line.lstrip().startswith((">", "```"))):
                    violations.append(FormatViolation(
                        rule_id="FMT-PARAGRAPH-BLANK", rule_name="段落间缺空行", line=i,
                        message="相邻两个段落之间应有一个空行"))

            # ---------- 排版：原始 HTML ----------
            if rules.forbid_raw_html and HTML_TAG_RE.search(line):
                violations.append(FormatViolation(
                    rule_id="TYP-RAW-HTML", rule_name="含原始 HTML", line=i,
                    message=f"禁止在文档中使用原始 HTML 标签：{line.strip()[:40]}"))

        # ---------- 元素：代码块围栏成对 ----------
        if fence_count % 2 != 0:
            violations.append(FormatViolation(
                rule_id="FMT-CODE-FENCE", rule_name="代码块围栏不闭合",
                message="代码块围栏（```）数量为奇数，未成对闭合"))

        # ---------- 模块：frontmatter ----------
        if rules.frontmatter == "required" and not content.lstrip().startswith("---"):
            violations.append(FormatViolation(
                rule_id="MOD-FRONTMATTER", rule_name="缺少 YAML frontmatter",
                message="模板要求文档以 YAML frontmatter（---）开头"))

        return FormatReport(ok=not violations, violations=violations)

    # ---------- 自动修正（机械性，不影响语义） ----------

    def auto_fix(self, content: str, rules: TemplateRules) -> str:
        lines = content.splitlines()
        out: list[str] = []
        in_fence = False
        prev_is_para = False  # 上一行是否为普通段落（用于补段落间空行）
        for i, line in enumerate(lines):
            if FENCE_RE.match(line):
                in_fence = not in_fence
                out.append(line)
                prev_is_para = False
                continue
            if in_fence:
                out.append(line)
                continue

            # Setext 下划线 → ATX 标题
            if SETEXT_H1_RE.match(line) and out and out[-1].strip():
                out[-1] = f"# {out[-1].strip()}"
                prev_is_para = False
                continue
            if SETEXT_H2_RE.match(line) and out and out[-1].strip():
                out[-1] = f"## {out[-1].strip()}"
                prev_is_para = False
                continue

            # 列表前缀统一（排除水平分割线）
            if rules.list_style and LIST_BULLET_RE.match(line) and not HR_RE.match(line):
                line = rules.list_style + line[1:]

            # 标题 emoji 剔除 + 标题后空行
            m = HEADING_RE.match(line)
            if m:
                if rules.forbid_emoji:
                    line = EMOJI_RE.sub("", line)
                out.append(line)
                prev_is_para = False
                if rules.heading_blank_line:
                    nxt = lines[i + 1] if i + 1 < len(lines) else ""
                    if nxt and nxt.strip() and not HEADING_RE.match(nxt):
                        out.append("")
                continue

            # 空行 / 列表 / 引用 → 非段落，重置段落标记
            stripped = line.lstrip()
            if (not line.strip() or LIST_LINE_RE.match(line)
                    or stripped.startswith((">", "```"))):
                out.append(line)
                prev_is_para = False
                continue

            # 普通段落：与上一段落直接相邻（缺空行）→ 补空行
            if rules.paragraph_blank_line and prev_is_para:
                out.append("")
            out.append(line)
            prev_is_para = True

        # 代码块围栏补全（围栏仍处于未闭合状态 → 追加闭合围栏）
        if in_fence and sum(1 for l in lines if FENCE_RE.match(l)) % 2 != 0:
            out.append(rules.code_fence)

        text = "\n".join(out)
        return text.rstrip() + "\n"

    def validate_and_fix(self, content: str, rules: TemplateRules) -> tuple[str, FormatReport]:
        """校验 →（若有违规）自动修正后重新校验。

        已合规时返回原文（保持字节不变），仅在有违规时做机械修正。
        """
        report = self.validate(content, rules)
        if report.ok:
            return content, report
        fixed = self.auto_fix(content, rules)
        return fixed, self.validate(fixed, rules)
