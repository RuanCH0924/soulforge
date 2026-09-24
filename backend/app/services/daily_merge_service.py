"""单日归并 DailyMergeService（M15 · P1）。

把同一天的多个来源（A 主骨架 / B session 导出 / C 主题文件）归并成 **1 篇** 标准工作日志，
流程对应方案 §6.2 的运行流程第 2~5 步：

1. 扫 + 分类 + 分组（`DailySourceScanner`）
2. 预处理：确定性剥壳 + 归一 + 体积统计（`DailyPreprocessor`）
3. 超限来源 → 分块摘要；仍超限 → 抛 `DailySourceTooLargeError` 转人工复核
4. 组装 prompt（格式化规则 + 风格与内容规则 + 骨架 + 各来源）
5. 调 LLM → `sanitize()` 剥思考过程 → `FormatValidator.validate_and_fix()` 强规则校验/机械修正

**P1 只出计划，绝不写文件、绝不删文件**：写入与碎片删除是 P2 的 plan/execute 两步流。
本服务返回的 `DailyMergePlan` 就是 P2 落库 `daily_run_items` 的载荷形状。

**规则投递形态**（P3 效率对比，`delivery` 参数，默认 `DEFAULT_DELIVERY`）：
`doc_full`（规则 + 模板全文进 user prompt）/ `trimmed`（按当日来源类型裁剪）/
`system_embedded`（规则全文进 system prompt）。业务链路不传该参数，形态切换不影响线上行为；
三者的实测对比与定稿结论见 [docs/M15-EFFICIENCY-REPORT.md](../../../docs/M15-EFFICIENCY-REPORT.md)。

护栏（与项目既有口径一致）：
- 强规则不过 → 计划里 `format_report.ok=False` + `needs_review=True`，交给人工确认（不写入）
- 所有路径都是 Agent 相对路径，读写一律经 `FileManager`（内部过 `_safe_join`）
- token 全量记账（含分块摘要调用），供 P2 做批次预算与 P3 做效率对比
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from loguru import logger

from app.core.errors import BadRequestError, DailySourceTooLargeError
from app.models.schemas import FormatReport, LintWarning, Preset
from app.services.daily_preprocessor import (
    PreprocessedSource,
    preprocess_source,
)
from app.services.daily_source_scanner import (
    KIND_A,
    KIND_B,
    KIND_C,
    DailySourceScanner,
    DayGroup,
)
from app.services.diff_service import unified_diff
from app.services.file_manager import FileManager
from app.services.format_validator import FormatValidator
from app.services.lint_service import LintService
from app.services.llm_registry import LLMRegistry, LLMResponse
from app.services.preset_service import PresetService
from app.services.template_rules import template_rule_summary

# 单来源分块上限：超过即转人工复核（方案 §6.2 第 3 步「仍超限 → 该日转人工复核」）
MAX_CHUNKS_PER_SOURCE = 6
# 单个分块的目标体积（按行切，不切碎行）
CHUNK_TARGET_BYTES = 20 * 1024
# 归并 prompt 体积上限：超了说明当天来源太多太大，转人工复核而不是硬烧 token
MAX_MERGE_PROMPT_BYTES = 160 * 1024

KIND_LABEL = {
    KIND_A: "标准日文件（当天主骨架）",
    KIND_B: "同日 session / 时间戳导出",
    KIND_C: "同日主题文件",
}

# ---------- 规则投递形态（P3 效率对比用，见 docs/M15-EFFICIENCY-REPORT.md） ----------
# 三种形态只在「规则放哪里、放多少」上不同，任务与来源部分的措辞完全一致，
# 这样对比出来的差异才可归因于形态本身。
DELIVERY_DOC_FULL = "doc_full"          # ① 规则 + 模板全文进 user prompt（P1/P2 的行为）
DELIVERY_TRIMMED = "trimmed"            # ② user prompt 内按当日来源类型裁剪规则与模板骨架
DELIVERY_SYSTEM = "system_embedded"     # ③ 规则全文进 system prompt，user prompt 只留任务与来源
DELIVERIES: tuple[str, ...] = (DELIVERY_DOC_FULL, DELIVERY_TRIMMED, DELIVERY_SYSTEM)
# 默认形态由 P3 实测定稿（27 次真实调用，3 样本日 × 3 形态 × 3 重复，结论见效率报告 §4）：
# ③ 在输出 token（−9.7%）、单日耗时（−13.3%）、三次输出一致性（0.442 → 0.518）上同时胜出，
# 强规则通过率与 ① 持平；② 省输入但多输出、且掉过一次强规则，不采用（仅留作复测对照）。
DEFAULT_DELIVERY = DELIVERY_SYSTEM

# B 类（session / 时间戳导出）专属规则的识别特征：命中且当天没有 B 类来源时，该条不注入。
# 口径来自 P3 的实测归类（见报告 §3）：预设的 6 条 style_rules 里只有「元数据壳删除清单」与
# 「对话腔改写」是 session 导出独有的语义，其余 4 条（保留清单 / 只留结论 / 默认不脱敏 /
# 有用优先）是跨来源通用。用文本特征而不是下标识别，是为了对预设被用户重新排序也不失效。
_B_ONLY_MARKERS: tuple[str, ...] = (
    "Session Key", "Session ID", "untrusted metadata", "Queued messages",
    "对话腔", "喵呜", "叠字",
)


def is_b_only_rule(rule: str) -> bool:
    """该条 style_rule 是否只对 B 类（session 导出）来源有意义。"""
    return any(marker in rule for marker in _B_ONLY_MARKERS)


def _skeleton_headings(template_md: str | None) -> str:
    """只取模板的章节骨架（标题行），去掉 frontmatter 规则块与解释性正文。"""
    if not template_md:
        return ""
    lines: list[str] = []
    in_frontmatter = False
    for index, line in enumerate(template_md.splitlines()):
        stripped = line.strip()
        if index == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("#"):
            lines.append(stripped)
    return "\n".join(lines)


# ---------- 「本日无可归档内容」出口 ----------
# 目的：当天全是噪音（心跳 / 状态轮询 / 无结论的调试流水 / 重复重试）时，让模型**有资格不产出**
# 日文件，而不是硬凑一篇。此前 prompt 写死「第一行必须是 # 工作日志 - <date>」，强规则又强制
# 必填章节齐全，模型没有任何合法出口，只能把噪音包装成一篇日志。
EMPTY_VERDICT = "无可归档内容"
_EMPTY_VERDICT_RE = re.compile(r"^(?:\*\*|__|`)?\s*无可归档内容\s*(?:\*\*|__|`)?\s*[:：]?\s*(.*)$")
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_MD_STRUCTURE_RE = re.compile(r"^\s{0,3}(?:[-*+]\s|\d+\.\s|\||>)")


def parse_empty_verdict(text: str) -> str | None:
    """识别「本日无可归档内容」哨兵：命中返回理由（可能为空串），否则 None。

    **从严判定**（宁可把空判定当成普通输出交给强规则，也不误判正常文档）：
    1. 去掉首尾空白后不超过 3 行（理由只允许一句话）；
    2. 不含标题、列表、表格、引用等 Markdown 结构；
    3. 第一个非空行以 `无可归档内容` 开头（允许加粗/反引号包裹，允许 `：理由`）。
    """
    cleaned = text.strip()
    if not cleaned:
        return None
    lines = [ln for ln in cleaned.splitlines() if ln.strip()]
    if len(lines) > 3:
        return None
    for line in lines:
        if _MD_HEADING_RE.match(line) or _MD_STRUCTURE_RE.match(line):
            return None
    match = _EMPTY_VERDICT_RE.match(lines[0].strip())
    return match.group(1).strip() if match else None


SYSTEM_PROMPT = (
    "你是 Soulforge 的工作日志整理助手。把同一天的多个来源记录归并成 1 篇标准工作日志："
    "保留长期有价值的事实、决定、错误与修复、配置变更、可复用数据与待办；"
    "删除只对当时执行过程有意义的噪音（状态轮询、重复重试、调试中间态、过程话与对话腔）。"
    "只保留结论，不保留过程；内容宁可完整，不为精简而丢事实。"
    "禁止在输出中写任何来源说明（不写「整合自」「来源」「原始文件位置」这类行）。"
    "输出必须 100% 符合格式规则；正文只输出 Markdown 文档。"
    "不要输出思考过程、任务分析、规则复述或任何对话性文字，第一行直接进入文档标题。"
    f"唯一的例外：当天全部来源都只有噪音、没有任何值得留存的内容时，不要硬凑成文，"
    f"按输出要求只回一行「{EMPTY_VERDICT}：<一句话理由>」。"
)

CHUNK_PROMPT_TEMPLATE = """【任务】下面是一个过长工作日志来源的第 {index}/{total} 段。
请按「风格与内容规则」把它提炼成事实清单（保留结论与关键信息，删除过程噪音），供后续归并使用。

【风格与内容规则（来自预设，必须逐条遵守）】
{style_block}

【输出要求】
只输出提炼后的 Markdown 片段，不要输出任何说明、总结语或对任务的复述；
不要写来源、不要写「本段」「以下是」这类话；不要用代码围栏包裹。

【本段原文】
{chunk}"""


def sha256_text(text: str) -> str:
    """文本内容的 SHA-256（乐观锁 / 幂等键统一用同一个口径，避免各处各算一份）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class SourceReport:
    """一个来源在归并前后的体积与剥壳事实（供 P2 的批次报告展示）。"""

    path: str
    kind: str
    raw_bytes: int
    clean_bytes: int
    removed_total: int
    rule_counts: dict[str, int] = field(default_factory=dict)
    summarized: bool = False
    chunks: int = 0

    @property
    def saved_bytes(self) -> int:
        return max(self.raw_bytes - self.clean_bytes, 0)


@dataclass
class DailyMergePlan:
    """单日归并计划（P1 的交付形态：只出计划，不写盘）。"""

    agent_id: str
    date: str
    target_path: str           # 恒为 memory/YYYY-MM-DD.md
    target_sha256: str | None  # 计划生成时目标文件的 SHA-256（None = 当时不存在）；P2 的乐观锁用
    has_standard: bool         # 当天原本是否已有 A 类主文件
    sources: list[SourceReport]
    output_content: str
    unified_diff: str
    format_report: FormatReport
    lint_warnings: list[LintWarning]
    fragments_to_delete: list[str]
    # 非 None = 模型判定「本日无可归档内容」（值为一句话理由）：不产出日文件，
    # 只清理 B/C 碎片，A 类主文件保持不动。见 parse_empty_verdict()
    empty_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_estimate_usd: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.empty_reason is not None

    @property
    def format_ok(self) -> bool:
        return self.format_report.ok

    @property
    def needs_review(self) -> bool:
        """需要人工留意：强规则没过，或仍有低价值壳残留。"""
        return not self.format_report.ok or bool(self.notes)


class DailyMergeService:
    """单日「多来源 → 1 文件」归并（只读原文件，只出计划）。"""

    def __init__(self, file_manager: FileManager, presets: PresetService, llm: LLMRegistry,
                 lint: LintService, scanner: DailySourceScanner | None = None):
        self.file_manager = file_manager
        self.presets = presets
        self.llm = llm
        self.lint = lint
        self.scanner = scanner or DailySourceScanner(file_manager)

    # ---------- 预处理 ----------

    @staticmethod
    def _split_chunks(text: str, target_bytes: int | None = None) -> list[str]:
        """按行切块（只在行边界断开，保证不切碎行、每块体积有界）。

        `target_bytes` 默认取模块常量（运行时读取，便于按需调整与测试注入）。
        """
        limit = CHUNK_TARGET_BYTES if target_bytes is None else target_bytes
        lines = text.split("\n")
        chunks: list[str] = []
        current: list[str] = []
        size = 0
        for line in lines:
            line_bytes = len(line.encode("utf-8")) + 1
            if current and size + line_bytes > limit:
                chunks.append("\n".join(current))
                current, size = [], 0
            current.append(line)
            size += line_bytes
        if current:
            chunks.append("\n".join(current))
        return chunks

    @staticmethod
    def _style_block(preset: Preset, kinds: set[str] | None = None) -> str:
        """风格与内容规则块。`kinds=None` → 全量；否则按当日来源类型裁剪。"""
        rules = list(preset.style_rules)
        if kinds is not None and KIND_B not in kinds:
            rules = [r for r in rules if not is_b_only_rule(r)]
        if not rules:
            return "（无）"
        return "\n".join(f"{i}. {line}" for i, line in enumerate(rules, start=1))

    async def _summarize_oversized(self, client, style_block: str, source: PreprocessedSource,
                                   chunks: list[str], usage: list[LLMResponse]) -> PreprocessedSource:
        """超限来源 → 分块摘要；块数超上限则抛错转人工复核。"""
        if len(chunks) > MAX_CHUNKS_PER_SOURCE:
            raise DailySourceTooLargeError(
                f"来源 {source.path} 净化后仍为 {source.clean_bytes // 1024}KB、需切成 {len(chunks)} 块，"
                f"超过单来源上限 {MAX_CHUNKS_PER_SOURCE} 块——该日转人工复核（不做无上限的 token 消耗）",
                details={"path": source.path, "clean_bytes": source.clean_bytes,
                         "chunks": len(chunks), "max_chunks": MAX_CHUNKS_PER_SOURCE})

        parts: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            prompt = CHUNK_PROMPT_TEMPLATE.format(
                index=index, total=len(chunks), style_block=style_block, chunk=chunk)
            resp = await client.chat([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])
            usage.append(resp)
            parts.append(resp.content.strip())
        return PreprocessedSource(
            path=source.path, kind=source.kind, text="\n\n".join(parts),
            raw_bytes=source.raw_bytes, rule_counts=source.rule_counts, summarized=True,
        )

    # ---------- Prompt ----------

    def _rule_block(self, preset: Preset, kinds: set[str], delivery: str) -> tuple[str, str]:
        """规则块的两种措辞：`trimmed` 按来源类型裁剪，其余形态全量。

        返回 `(user 段文案, system 段文案)`——同一份文本只会进其中一个（另一个为空串）。
        """
        trimmed = delivery == DELIVERY_TRIMMED
        rules = self.presets.rules_for(preset)
        style_block = self._style_block(preset, kinds) if trimmed else self._style_block(preset)
        if trimmed:
            skeleton = _skeleton_headings(preset.template_md) or "（该预设未提供模板文档，以上规则即全部要求）"
            skeleton_title = "【模板章节骨架（归并时按此结构组织）】"
        else:
            skeleton = preset.template_md or "（该预设未提供模板文档，以上规则即全部要求）"
            skeleton_title = "【模板文档全文（含章节骨架示例，归并时按此结构组织）】"
        text = f"""【格式化规则（来自模板文档，必须逐条遵守）】
{template_rule_summary(rules)}

【风格与内容规则（来自预设，必须逐条遵守）】
{style_block}

{skeleton_title}
```markdown
{skeleton}
```"""
        return ("", text) if delivery == DELIVERY_SYSTEM else (text, "")

    def _build_prompts(self, preset: Preset, group: DayGroup, prepared: list[tuple],
                       extra_instructions: str | None,
                       delivery: str = DEFAULT_DELIVERY) -> tuple[str, str]:
        """组装 `(system_prompt, user_prompt)`。

        来源在 prompt 内是**带标签**的（模型需要知道优先级与来源类型），
        但输出要求里明确禁止把来源写进结果（决策 4：不写来源、不留痕）。
        """
        kinds = {source.kind for source, _ in prepared}
        user_rules, system_rules = self._rule_block(preset, kinds, delivery)
        if delivery == DELIVERY_SYSTEM:
            rules_hint = "【规则】格式化规则与风格与内容规则已在上方系统提示中给出，必须逐条遵守。\n\n"
        else:
            rules_hint = f"{user_rules}\n\n"
        blocks = []
        for source, pre in prepared:
            note = "（已分块摘要）" if pre.summarized else ""
            blocks.append(
                f"【来源：{source.path}（{KIND_LABEL.get(source.kind, source.kind)}）{note}】\n"
                f"```markdown\n{pre.text}\n```"
            )
        target_hint = (
            f"当天已有标准日文件 {group.target_path}，请以「A 类主骨架」为基础改写，"
            "不要把其它来源的事件覆盖掉已有事实。"
            if group.has_standard
            else f"当天还没有标准日文件，请按骨架新建 {group.target_path} 的内容。"
        )
        user_prompt = f"""【任务】把 {group.date} 这一天的多个来源记录归并成 1 篇标准工作日志，严格遵循：
第一步：读取并解析格式化规则、风格与内容规则；
第二步：读取全部来源（已按来源优先级 A > C > B 排好序）；
第三步：先判断本日是否值得产出日文件（见【输出】的情形二），值得产出的再归并——
        同一天的多来源合并成 1 篇；跨来源重复的事件只保留信息量最大的一条；
        任何来源独有的关键事实都不得丢失；「风格与内容规则」里要求保留的必须保留、要求删除的必须删除；
第四步：自查输出，确保 100% 符合规则后再交付。

【本次归并目标】
- 目标文件：{group.target_path}（命名与结构由强规则校验，必须严格合规）
- {target_hint}
- 输出中不得出现任何来源说明（不写「整合自」「来源」「原始文件位置」等行）

{rules_hint}【附加指令】（老板可选）
{extra_instructions or '无'}

【本日来源（共 {len(prepared)} 个）】
{chr(10).join(blocks)}

【输出】只允许两种情形之一，输出别的内容都算不合格：

情形一（正常，绝大多数情况）：只输出归并后的 Markdown 文档正文本身，严格遵守：
1. 第一行必须是 `# 工作日志 - {group.date}`；
2. 禁止输出思考过程、任务分析、步骤说明、规则复述、前言/结语、来源说明、致谢等任何对话性文字；
3. 禁止用 ``` 代码围栏包裹整篇文档（文档内部的代码块不受此限）；
4. 不要写「让我」「以下是」「以上是」「如需调整」之类的话，直接从正文开始、到正文结束。

情形二（例外，仅当本日确实没有可归档的内容）：如果本日全部来源剥壳后只剩噪音——心跳 / 状态轮询、
无结论的调试流水、重复的失败重试、纯过程叙述——没有任何值得长期检索的事实、决策、待办或可复用数据，
那就**不要硬凑**一篇日志，改为只输出一行：

{EMPTY_VERDICT}：<一句话理由>

判定从严：只要还有一条真实的事实 / 决策 / 待办 / 可复用数据，就必须按情形一产出文档；
只有「整天确实无内容可留」时才允许走情形二。走情形二时不会产出任何日文件，
该日的 B/C 类碎片仍会被清理（A 类主文件 `YYYY-MM-DD.md` 保持不动）。"""
        system_prompt = f"{SYSTEM_PROMPT}\n\n{system_rules}" if system_rules else SYSTEM_PROMPT
        return system_prompt, user_prompt

    # ---------- 单日归并 ----------

    async def plan_day(self, agent_id: str, date: str, preset_id: str, provider_id: str,
                       extra_instructions: str | None = None,
                       delivery: str = DEFAULT_DELIVERY) -> DailyMergePlan:
        """产出某一天的归并计划（只读，不写盘、不删文件）。

        `delivery` 是规则投递形态（P3 效率对比用），默认取 `DEFAULT_DELIVERY`；
        业务链路（批次日归并 / M13）不传该参数，因此形态切换不影响线上行为。
        """
        if delivery not in DELIVERIES:
            raise BadRequestError(
                f"未知的规则投递形态：{delivery!r}（可选 {'/'.join(DELIVERIES)}）",
                details={"delivery": delivery, "allowed": list(DELIVERIES)})
        group = self.scanner.day(agent_id, date)
        if group is None:
            raise BadRequestError(
                f"{date} 在 memory/ 顶层下没有符合 A/B/C 命名的工作日志来源，无需归并",
                details={"agent_id": agent_id, "date": date})
        preset = self.presets.get(preset_id)
        self.llm.get_provider(provider_id)  # 不存在/禁用 → 404
        client = self.llm.get_client(provider_id)

        kinds = {s.kind for s in group.sources}
        style_block = self._style_block(preset, kinds) if delivery == DELIVERY_TRIMMED \
            else self._style_block(preset)
        usage: list[LLMResponse] = []
        prepared, reports, notes = await self._prepare_sources_for(
            client, style_block, group, usage, agent_id)
        system_prompt, prompt = self._build_prompts(
            preset, group, prepared, extra_instructions, delivery)
        if len(prompt.encode("utf-8")) > MAX_MERGE_PROMPT_BYTES:
            raise DailySourceTooLargeError(
                f"归并 prompt 达 {len(prompt.encode('utf-8')) // 1024}KB，超过上限 "
                f"{MAX_MERGE_PROMPT_BYTES // 1024}KB——该日来源过多，转人工复核",
                details={"agent_id": agent_id, "date": date,
                         "prompt_bytes": len(prompt.encode("utf-8"))})

        resp = await client.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ])
        usage.append(resp)

        validator = FormatValidator()
        sanitized, preamble = validator.sanitize(resp.content.strip())
        if preamble:
            logger.warning(f"归并输出含前言，已剥离（{agent_id}/{date}）：{preamble[:120]!r}")

        fragments = [s.path for s in group.fragments]
        current = (self.file_manager.read_text(agent_id, group.target_path)
                   if group.has_standard else "")
        usage_fields = {
            "prompt_tokens": sum(r.usage.prompt_tokens for r in usage),
            "completion_tokens": sum(r.usage.completion_tokens for r in usage),
            "total_tokens": sum(r.usage.total_tokens for r in usage),
            "cost_estimate_usd": round(sum(r.cost_estimate_usd for r in usage), 6),
        }

        # 情形二：模型判定本日无可归档内容 → 不产出日文件（只清碎片），不跑强规则
        empty_reason = parse_empty_verdict(sanitized)
        if empty_reason is not None:
            logger.info(f"{agent_id}/{date} 判定无可归档内容：{empty_reason or '（未给理由）'}")
            return DailyMergePlan(
                agent_id=agent_id, date=date, target_path=group.target_path,
                target_sha256=sha256_text(current) if group.has_standard else None,
                has_standard=group.has_standard, sources=reports,
                output_content="", unified_diff="",
                format_report=FormatReport(ok=True), lint_warnings=[],
                fragments_to_delete=fragments, empty_reason=empty_reason,
                notes=[], **usage_fields,
            )

        output, format_report = validator.validate_and_fix(sanitized, self.presets.rules_for(preset))
        diff = unified_diff(
            current, output,
            fromfile=f"{agent_id}/{group.target_path}（归并前）",
            tofile=f"{agent_id}/{group.target_path}（归并后）")
        return DailyMergePlan(
            agent_id=agent_id, date=date, target_path=group.target_path,
            target_sha256=sha256_text(current) if group.has_standard else None,
            has_standard=group.has_standard, sources=reports,
            output_content=output, unified_diff=diff, format_report=format_report,
            lint_warnings=self.lint.lint_file(agent_id, group.target_path, output),
            fragments_to_delete=fragments, notes=notes, **usage_fields,
        )

    async def _prepare_sources_for(self, client, style_block: str, group: DayGroup,
                                   usage: list[LLMResponse], agent_id: str) -> tuple[list[tuple], list[SourceReport], list[str]]:
        """读 + 剥壳 +（必要时）分块摘要。"""
        prepared: list[tuple] = []
        reports: list[SourceReport] = []
        notes: list[str] = []
        for source in group.sources:
            raw = self.file_manager.read_text(agent_id, source.path)
            pre = preprocess_source(source.path, source.kind, raw)
            chunk_list: list[str] = []
            if pre.oversized:
                chunk_list = self._split_chunks(pre.text)
                logger.info(
                    f"来源超限转分块摘要：{source.path}（{pre.clean_bytes // 1024}KB，{len(chunk_list)} 块）")
                pre = await self._summarize_oversized(client, style_block, pre, chunk_list, usage)
                notes.append(f"{source.path} 净化后仍超限，已分 {len(chunk_list)} 块摘要后归并")
            prepared.append((source, pre))
            reports.append(SourceReport(
                path=source.path, kind=source.kind, raw_bytes=pre.raw_bytes,
                clean_bytes=pre.clean_bytes, removed_total=pre.removed_total,
                rule_counts=pre.rule_counts, summarized=pre.summarized, chunks=len(chunk_list),
            ))
        return prepared, reports, notes
