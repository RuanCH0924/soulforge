"""FormatValidator：按模板规则校验文档格式，并支持机械性自动修正。

校验维度（对应模板 YAML 的 structure / elements / typography / modules）：
- 必填章节存在且顺序严格
- ATX 标题（禁用 Setext 下划线）
- 标题层级不超过上限
- 无序列表统一使用指定前缀
- 代码块围栏成对
- 标题后空行 / 段落间空行（表格行按块级元素处理，不参与段落空行判定）
- 标题禁 emoji
- 禁原始 HTML
- frontmatter 是否必需

auto_fix 只做机械性修正（不影响语义），修正后再次校验。
FormatReport / FormatViolation 直接复用 schemas 中的 Pydantic 模型。

另提供 `sanitize()`：剥离模型输出中的「思考过程 / 前言」与「整篇围栏包裹」。
LLM 常在正文前写一段对话性文字（如「让我仔细分析这个任务：…」），这类文本不构成
格式违规，必须在此前置净化，否则会随正文一起进入预览与写入。
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
TABLE_ROW_RE = re.compile(r"^\s*\|")  # 表格行：相邻表行不需要空行（否则会破坏表格结构）
HTML_TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)(?=[\s/>])")
# 只有**真实会渲染的 HTML 标签**才算违规。此前把所有 `<单词>` 都当标签，实测把工作日志里
# 合法的占位符（`session:<id>`、`<jobId>` 这类，且通常写在行内代码里）误判为原始 HTML，
# 而该规则没有机械修正手段 → 直接拦死整天的写入（P3 实测发现，见 docs/M15-EFFICIENCY-REPORT.md）。
HTML_TAGS = frozenset({
    "a", "abbr", "audio", "b", "blockquote", "br", "button", "caption", "center", "code",
    "col", "colgroup", "dd", "del", "details", "div", "dl", "dt", "em", "embed", "figcaption",
    "figure", "font", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header",
    "hr", "html", "i", "iframe", "img", "input", "ins", "kbd", "label", "li", "link", "main",
    "mark", "meta", "nav", "ol", "option", "p", "path", "picture", "pre", "q", "s", "script",
    "section", "select", "small", "source", "span", "strong", "style", "sub", "summary", "sup",
    "svg", "table", "tbody", "td", "template", "textarea", "tfoot", "th", "thead", "tr", "u",
    "ul", "video",
})
# 行内代码跨度：写成 `` `<br>` `` 的示例是「说明」而不是「文档里的原始 HTML」，不参与判定
INLINE_CODE_RE = re.compile(r"`[^`]*`")
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2B50\u2764\u2705\u2728\u2934]"
)

# ---------- 用于 sanitize：结构行识别与前言特征 ----------
ATX_LINE_RE = re.compile(r"^#{1,6}\s+\S")
FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})[^\s`~]*\s*$")
FENCE_CLOSE_RE = re.compile(r"^(`{3,}|~{3,})\s*$")
FRONTMATTER_MARKER = "---"

# 前言特征词：仅当出现在「首个结构行（标题 / frontmatter / 围栏）之前」时才判定为思考过程，
# 避免误伤文档自身的开头段落。
PREAMBLE_MARKERS = (
    "让我", "我来", "我先", "首先", "以下是", "以下为", "下面是", "下面我",
    "分析", "思考", "自查", "整理后", "整理如下", "好的", "收到", "已按", "如需",
)

# 推理模型（MiniMax / DeepSeek / Qwen 等）会把思考过程包在 XML 风格标签里。
# 这类块**必须显式剥离**：它不是「前言」——前言特征词是中文启发式，英文思考内容匹配不上，
# 漏剥后 `<think>` 会触发 forbid_raw_html，把一次成功的归并误判为强规则失败（P3 实测发现）。
# 只在「整段输出以思考块开头」时才剥（`REASONING_LEAD_RE`），避免误删正文里作为示例出现的标签；
# 且只剥**闭合完整**的块——未闭合说明被 max_tokens 截断，此时根本没有正文，留给强规则去报错。
REASONING_BLOCK_RE = re.compile(
    r"<(thinking|reasoning|scratchpad|analysis|think)>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
REASONING_LEAD_RE = re.compile(
    r"^\s*<(thinking|reasoning|scratchpad|analysis|think)>",
    re.IGNORECASE,
)


def raw_html_tag(line: str) -> str | None:
    """该行是否含**真实的**原始 HTML 标签（行内代码里的示例不算）。返回命中的标签名。"""
    for match in HTML_TAG_RE.finditer(INLINE_CODE_RE.sub("", line)):
        if match.group(1).lower() in HTML_TAGS:
            return match.group(1)
    return None


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
            # 表格行按「块级元素」处理，自身不参与判定：表头行 / 分隔行 / 数据行之间插空行会破坏表格
            if (rules.paragraph_blank_line and i > 1 and line.strip() and lines[i - 2].strip()
                    and not LIST_LINE_RE.match(line) and not HR_RE.match(line)
                    and not TABLE_ROW_RE.match(line)):
                prev = lines[i - 2]  # enumerate 从 1 开始，i-2 才是紧邻上一行
                if (not HEADING_RE.match(prev) and not LIST_LINE_RE.match(prev)
                        and not prev.lstrip().startswith((">", "```"))
                        and not line.lstrip().startswith((">", "```"))):
                    violations.append(FormatViolation(
                        rule_id="FMT-PARAGRAPH-BLANK", rule_name="段落间缺空行", line=i,
                        message="相邻两个段落之间应有一个空行"))

            # ---------- 排版：原始 HTML ----------
            # 只认真实标签 + 跳过行内代码里的示例（`session:<id>` 这类占位符不是 HTML）
            if rules.forbid_raw_html:
                tag = raw_html_tag(line)
                if tag:
                    violations.append(FormatViolation(
                        rule_id="TYP-RAW-HTML", rule_name="含原始 HTML", line=i,
                        message=f"禁止在文档中使用原始 HTML 标签 <{tag}>：{line.strip()[:40]}"))

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

    # ---------- 输出净化（剥离思考过程 / 前言 / 整篇围栏包裹） ----------

    @staticmethod
    def _first_structural_line(lines: list[str]) -> int | None:
        """返回首个「结构行」行下标：ATX 标题 / YAML frontmatter 起始 / 代码围栏起始。"""
        for i, line in enumerate(lines):
            s = line.strip()
            if not s:
                continue
            if ATX_LINE_RE.match(s) or FENCE_OPEN_RE.match(s):
                return i
            if s == FRONTMATTER_MARKER and any(l.strip() == FRONTMATTER_MARKER for l in lines[i + 1:]):
                return i
        return None

    @staticmethod
    def _looks_like_preamble(block: str) -> bool:
        """判断「首个结构行之前」的文本是否为对话性前言（思考过程 / 复述要求）。"""
        if not block.strip():
            return False
        return any(
            marker in line.strip()
            for line in block.splitlines()
            for marker in PREAMBLE_MARKERS
        )

    @staticmethod
    def _unwrap_outer_fence(content: str) -> str:
        """整篇文档被模型包进 ``` 围栏时，剥掉最外层围栏（内部还有围栏则不处理）。"""
        lines = content.splitlines()
        first = next((i for i, l in enumerate(lines) if l.strip()), None)
        last = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
        if first is None or last is None or last <= first:
            return content
        if not FENCE_OPEN_RE.match(lines[first].strip()) or not FENCE_CLOSE_RE.match(lines[last].strip()):
            return content
        inner = lines[first + 1:last]
        if any(FENCE_CLOSE_RE.match(l.strip()) for l in inner):
            return content
        return "\n".join(inner).strip("\n")

    def sanitize(self, content: str) -> tuple[str, str | None]:
        """净化模型原始输出，返回 (正文, 被剥离的前言文本或 None)。

        顺序：① 剥离推理模型的思考块（`<think>…</think>` 之类，见 `REASONING_BLOCK_RE`）；
        ② 仅当「首个结构行之前」的文本具有明显对话特征时才剥离前置前言，
        以免误删文档自身的开头段落；③ 若整篇仍被代码围栏包裹，则一并剥掉外层围栏。
        """
        text = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip("\n")
        reasoning = ([m.group(0) for m in REASONING_BLOCK_RE.finditer(text)]
                     if REASONING_LEAD_RE.match(text) else [])
        if reasoning:
            text = REASONING_BLOCK_RE.sub("", text).strip("\n")
        lines = text.splitlines()
        start = self._first_structural_line(lines)
        removed: str | None = None
        if start is not None and start > 0:
            block = "\n".join(lines[:start])
            if self._looks_like_preamble(block):
                removed = block.strip()
                text = "\n".join(lines[start:])
        if reasoning:
            removed = "\n".join([*reasoning, removed or ""]).strip()
        text = self._unwrap_outer_fence(text)
        return text.strip("\n"), removed

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

            # 空行 / 列表 / 引用 / 表格行 → 非段落，重置段落标记
            stripped = line.lstrip()
            if (not line.strip() or LIST_LINE_RE.match(line)
                    or TABLE_ROW_RE.match(line)
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
