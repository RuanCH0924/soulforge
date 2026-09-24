"""来源预处理器 Preprocessor（M15 · P1 单日归并）。

确定性剥壳 + 归一，**零 token**：把工作日志里的低价值元数据壳在进 prompt 之前就删掉，
不依赖模型「自觉不抄回来」。规则契约来自外部 skill `memory-daily-standardizer`（低价值内容识别）。

**12 条规则**（`PREPROCESS_RULES` 是文案唯一事实源，UI 与文档均以此为准）：

| ID | 名称 | 命中对象 |
|---|---|---|
| M01 | 会话元数据行 | `Session Key` / `Session ID` / `Source` 键值行 |
| M02 | session 标题壳 | `# Session: 2026-09-23 09:16:04 Asia/Shanghai` |
| M03 | Conversation info 块 | 标题行 + 紧随的 JSON 块 |
| M04 | Sender 块 | 标题行 + 紧随的 JSON 块 |
| M05 | Reply target 上下文壳 | 标题行 + 紧随的引用块 |
| M06 | Queued messages 块 | 标题行 + 紧随的列表块 |
| M07 | Possible Lasting Truths 空判 | `Possible Lasting Truths: No strong candidate truths surfaced` |
| M08 | dreaming 统计壳 | `Reflections` / `Themes` / `Candidate Truths` 统计行 |
| M09 | 过程过渡语行 | 整行仅为「让我检查一下」「我来看看」「任务还在运行中」这类过渡语 |
| M10 | 纯 HEARTBEAT_OK 行 | 整行仅为 `HEARTBEAT_OK`（重复心跳记录） |
| M11 | 编码与换行归一 | BOM 剥离 + `CRLF`/`CR` → `LF` |
| M12 | 空白归一 | 行尾空白清理 + 连续空行折叠 + 首尾空行剥离 |

> M01~M10 是**真壳**（剥掉的是低价值元数据，残留检测只看这 10 条）；M11/M12 是收尾**归一**，
> 对任何文本都可能命中，不算残留（`PreprocessRule.is_shell` 即此分界）。

**保守性原则**（宁可不删，不可误删）：
- M03~M06 只删「标题行 + 紧随其后的那种块」；标题行后面是普通正文时，只删标题行本身。
- 正文里合法的 ```json 代码块**没有**上述标题行引导 → 一律保留（见单元测试反例）。
- M09/M10 只匹配「整行就是那句话」的情况（容忍角色前缀 / 引号 / 加粗），不做子串替换。

以上规则只删「对后续检索无价值的壳」；「什么该保留」由弱规则（技能文档 + `style_rules`）交给 LLM。
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

# 单来源进 prompt 的体积阈值：超过则建议分块摘要（见方案 §6.2 第 3 步）
CHUNK_THRESHOLD_BYTES = 24 * 1024

_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})")
_FENCE_CLOSE_RE = re.compile(r"^(`{3,}|~{3,})\s*$")
_LIST_LINE_RE = re.compile(r"^\s*[-*+]\s+|\s*\d+\.\s+")

# M01：会话元数据键值行（兼容 `- **Session Key**: x` / `Session Key: x` / `> Session ID: x`）
SESSION_KEY_LINE_RE = re.compile(
    r"^[\s>*+\-]*\**\s*(Session Key|Session ID|SessionId|Source)\s*\**\s*[:：]")
# M02：session 导出标题壳
SESSION_TITLE_RE = re.compile(r"^#{1,6}\s*Session\b")
# M07：dreaming 的空判结论
LASTING_TRUTHS_RE = re.compile(
    r"^\s*[-*]?\s*Possible Lasting Truths\s*[:：]\s*No strong candidate truths surfaced\s*$",
    re.IGNORECASE)
# M08：dreaming 统计壳（只出现在 dreaming 产物里）
DREAMING_STAT_RE = re.compile(
    r"^\s*[-*]?\s*\**\s*(Reflections|Themes|Candidate Truths|Possible Lasting Truths|Theme Summary)"
    r"\s*\**\s*[:：]",
    re.IGNORECASE)


def _header_pattern(phrase: str) -> re.Pattern:
    """构造「元数据块标题行」的正则：短语必须位于行首（容忍列表符号 / 加粗），
    且整行不能是带句读的正文（排除 `。！？；，、`）。"""
    return re.compile(
        rf"^[\s>*+\-]*\**\s*{phrase}\b[^。！？；，、]{{0,80}}$", re.IGNORECASE)


# M03：Conversation info (untrusted metadata) 块
CONVERSATION_INFO_RE = _header_pattern("Conversation info")
# M04：Sender (untrusted metadata) 块
SENDER_BLOCK_RE = _header_pattern("Sender")
# M05：当前用户消息的回复目标上下文壳
REPLY_TARGET_RE = _header_pattern("Reply target of current user message")
# M06：忙碌期间排队的消息
QUEUED_MESSAGES_RE = _header_pattern("Queued messages while agent was busy")

# M09：整行仅仅是过程过渡语（不做子串替换，避免误伤正文）
TRANSITION_PHRASES = frozenset({
    "让我检查一下", "让我来看一下", "让我看看", "我来看看", "我来查一下", "我来帮你查一下",
    "让我确认一下", "让我看看情况", "正在处理中", "任务还在运行中", "稍等", "稍等一下",
    "让我重新检查一下", "检查一下", "看看情况",
})

_ROLE_PREFIX_RE = re.compile(r"^(user|assistant|system|tool)\s*[:：]\s*", re.IGNORECASE)
_LEADING_DECOR_RE = re.compile(r"^[-*+>\s]+")
_TRAILING_DECOR_RE = re.compile(r"[\s*_~]+$")
_QUOTE_WRAP_RE = re.compile(r'^["“”\'‘’]+|["“”\'‘’]+$')
_TRAILING_PUNCT_RE = re.compile(r"[。.!！?？~]+$")


@dataclass(frozen=True)
class PreprocessRule:
    """一条确定性预处理规则：rule_id 是稳定标识，apply 返回 (新文本, 命中数)。

    `is_shell` 区分两类规则（决定它算不算「残留壳」）：
    - `True`（M01~M10）：**真壳**，删掉的是低价值元数据；文本里还命中 = 没剥干净。
    - `False`（M11/M12）：**归一**，BOM/换行/空白这类收尾动作，对任何合法文档都会有命中，
      不能当成残留（否则一份完全合规、只是结尾带换行的文档会被误判为「仍有残留壳」）。
    """

    rule_id: str
    name: str
    description: str
    apply: Callable[[str], tuple[str, int]]
    is_shell: bool = True


@dataclass
class PreprocessResult:
    """预处理结果：净化后的文本 + 逐规则命中计数。"""

    text: str
    rule_counts: dict[str, int] = field(default_factory=dict)

    @property
    def removed_total(self) -> int:
        return sum(self.rule_counts.values())

    def hits(self, rule_id: str) -> int:
        return self.rule_counts.get(rule_id, 0)


# ---------- 行 / 块级删除 ----------


def _skip_following_block(lines: list[str], start: int) -> int:
    """从 start 起跳过紧随的「元数据块」，返回新位置。

    识别的块形态：围栏代码块 / 引用块 / JSON 行 / 列表块。
    若紧随的是普通正文，则返回 start（只删标题行本身，不牵连内容）。
    """
    j = start
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j >= len(lines):
        return start
    current = lines[j].strip()

    if _FENCE_OPEN_RE.match(current):
        j += 1
        while j < len(lines) and not _FENCE_CLOSE_RE.match(lines[j].strip()):
            j += 1
        return len(lines) if j >= len(lines) else j + 1  # 未闭合 → 视为整段元数据，删到文末
    if current.startswith(">"):
        while j < len(lines) and (lines[j].strip().startswith(">") or not lines[j].strip()):
            j += 1
        return j
    if current.startswith(("{", "[")):
        while j < len(lines) and lines[j].strip():
            j += 1
        return j
    if _LIST_LINE_RE.match(lines[j]):
        while j < len(lines) and lines[j].strip() and _LIST_LINE_RE.match(lines[j]):
            j += 1
        return j
    return start


def _drop_lines(pattern: re.Pattern) -> Callable[[str], tuple[str, int]]:
    """删掉整行匹配 pattern 的行。"""

    def _apply(text: str) -> tuple[str, int]:
        out, hits = [], 0
        for line in text.split("\n"):
            if pattern.search(line):
                hits += 1
                continue
            out.append(line)
        return "\n".join(out), hits

    return _apply


def _drop_headed_block(pattern: re.Pattern) -> Callable[[str], tuple[str, int]]:
    """删掉「匹配 pattern 的标题行 + 紧随其后的元数据块」。"""

    def _apply(text: str) -> tuple[str, int]:
        lines = text.split("\n")
        out: list[str] = []
        hits, i = 0, 0
        while i < len(lines):
            if pattern.search(lines[i]):
                hits += 1
                i = _skip_following_block(lines, i + 1)
                continue
            out.append(lines[i])
            i += 1
        return "\n".join(out), hits

    return _apply


def _phrase_of(line: str) -> str:
    """把一行归一成「可能的过渡语」：去角色前缀 / 列表符号 / 加粗 / 引号 / 句末标点。

    只用于整行等值比较（`_phrase_of(line) in TRANSITION_PHRASES`），不做子串替换。
    """
    text = _ROLE_PREFIX_RE.sub("", line.strip())
    for _ in range(3):
        before = text
        text = _LEADING_DECOR_RE.sub("", text).strip()
        text = _TRAILING_DECOR_RE.sub("", text).strip()
        text = _QUOTE_WRAP_RE.sub("", text).strip()
        text = _TRAILING_PUNCT_RE.sub("", text).strip()
        if text == before:
            break
    return text


def _normalize_transitions(text: str) -> tuple[str, int]:
    """M09：整行仅仅是过程过渡语 → 删（容忍 `assistant: "…"` 这类角色前缀与引号）。"""
    out, hits = [], 0
    for line in text.split("\n"):
        if _phrase_of(line) in TRANSITION_PHRASES:
            hits += 1
            continue
        out.append(line)
    return "\n".join(out), hits


def _drop_heartbeat_only(text: str) -> tuple[str, int]:
    """M10：整行仅仅是 HEARTBEAT_OK（重复心跳记录）→ 删。"""
    out, hits = [], 0
    for line in text.split("\n"):
        if _phrase_of(line).upper() == "HEARTBEAT_OK":
            hits += 1
            continue
        out.append(line)
    return "\n".join(out), hits


def _normalize_encoding(text: str) -> tuple[str, int]:
    """M11：BOM 剥离 + 换行统一为 LF。"""
    hits = 0
    if text.startswith("\ufeff"):
        text = text[1:]
        hits += 1
    if "\r" in text:
        hits += 1
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, hits


def _normalize_blank_lines(text: str) -> tuple[str, int]:
    """M12：行尾空白清理 + 连续空行折叠为 1 + 首尾空行剥离。"""
    hits = 0
    cleaned: list[str] = []
    for line in text.split("\n"):
        stripped = line.rstrip()
        if stripped != line:
            hits += 1
        cleaned.append(stripped)

    folded: list[str] = []
    blank = False
    for line in cleaned:
        if line:
            blank = False
            folded.append(line)
            continue
        if blank:
            hits += 1
            continue
        blank = True
        folded.append(line)

    while folded and not folded[0]:
        folded.pop(0)
        hits += 1
    while folded and not folded[-1]:
        folded.pop()
        hits += 1
    return "\n".join(folded), hits


PREPROCESS_RULES: tuple[PreprocessRule, ...] = (
    PreprocessRule("M01", "会话元数据行", "Session Key / Session ID / Source 键值行",
                   _drop_lines(SESSION_KEY_LINE_RE)),
    PreprocessRule("M02", "session 标题壳", "# Session: <时间> 导出标题",
                   _drop_lines(SESSION_TITLE_RE)),
    PreprocessRule("M03", "Conversation info 块", "Conversation info (untrusted metadata) 标题行 + 紧随 JSON 块",
                   _drop_headed_block(CONVERSATION_INFO_RE)),
    PreprocessRule("M04", "Sender 块", "Sender (untrusted metadata) 标题行 + 紧随 JSON 块",
                   _drop_headed_block(SENDER_BLOCK_RE)),
    PreprocessRule("M05", "Reply target 上下文壳", "Reply target of current user message 标题行 + 紧随引用块",
                   _drop_headed_block(REPLY_TARGET_RE)),
    PreprocessRule("M06", "Queued messages 块", "Queued messages while agent was busy 标题行 + 紧随列表块",
                   _drop_headed_block(QUEUED_MESSAGES_RE)),
    PreprocessRule("M07", "Possible Lasting Truths 空判", "dreaming 的空结论行",
                   _drop_lines(LASTING_TRUTHS_RE)),
    PreprocessRule("M08", "dreaming 统计壳", "Reflections / Themes / Candidate Truths 统计行",
                   _drop_lines(DREAMING_STAT_RE)),
    PreprocessRule("M09", "过程过渡语行", "整行仅为「让我检查一下」「我来看看」这类过程话",
                   _normalize_transitions),
    PreprocessRule("M10", "纯 HEARTBEAT_OK 行", "整行仅为 HEARTBEAT_OK 的重复心跳记录",
                   _drop_heartbeat_only),
    PreprocessRule("M11", "编码与换行归一", "BOM 剥离 + CRLF/CR → LF",
                   _normalize_encoding, is_shell=False),
    PreprocessRule("M12", "空白归一", "行尾空白清理 + 连续空行折叠 + 首尾空行剥离",
                   _normalize_blank_lines, is_shell=False),
)

# 只含「真壳」规则（M01~M10）——残留检测与验收口径以此为准。
SHELL_RULES: tuple[PreprocessRule, ...] = tuple(r for r in PREPROCESS_RULES if r.is_shell)

_SHELL_NAMES: dict[str, str] = {r.rule_id: r.name for r in SHELL_RULES}


def preprocess(text: str) -> PreprocessResult:
    """按 12 条规则依次净化（顺序固定：先删壳，最后归一空白）。"""
    counts: dict[str, int] = {}
    for rule in PREPROCESS_RULES:
        text, hits = rule.apply(text)
        if hits:
            counts[rule.rule_id] = hits
    return PreprocessResult(text=text, rule_counts=counts)


def detect_residual_shells(text: str) -> list[str]:
    """检测文本里还残留哪些低价值壳（返回规则 id 列表）。

    用途：验收「低价值元数据壳残留 = 0」——确认预处理把壳剥干净（见方案 §9.2 第 4 条），
    P2 起还用于对 LLM 输出做终检。

    **只统计真壳规则**（`SHELL_RULES` = M01~M10）：M11/M12 是「编码·换行·空白归一」，
    对任何文本都可能命中（比如一份完全合规、仅结尾带换行的文档必然命中空白归一），
    把它们算作残留会让正常文档被误判。
    """
    return [rule.rule_id for rule in SHELL_RULES if rule.apply(text)[1] > 0]


def describe_shells(rule_ids: list[str]) -> str:
    """把残留规则 id 渲染成可读说明（规则名），供面向用户的报错 / 报告使用。"""
    return "、".join(_SHELL_NAMES.get(rid, rid) for rid in rule_ids)


@dataclass
class PreprocessedSource:
    """一个来源预处理后的事实：文本 + 体积 + 逐规则命中。"""

    path: str
    kind: str
    text: str
    raw_bytes: int
    rule_counts: dict[str, int]
    summarized: bool = False   # 是否经过「分块摘要」（超限来源才会有）

    @property
    def clean_bytes(self) -> int:
        return len(self.text.encode("utf-8"))

    @property
    def saved_bytes(self) -> int:
        return max(self.raw_bytes - self.clean_bytes, 0)

    @property
    def removed_total(self) -> int:
        return sum(self.rule_counts.values())

    @property
    def oversized(self) -> bool:
        """净化后仍超过分块阈值 → 需要分块摘要（见 §6.2 第 3 步）。"""
        return self.clean_bytes > CHUNK_THRESHOLD_BYTES

    @property
    def residual_shells(self) -> list[str]:
        return detect_residual_shells(self.text)


def preprocess_source(path: str, kind: str, raw: str) -> PreprocessedSource:
    """把原始文件内容过一遍预处理，产出可进 prompt 的来源事实。"""
    result = preprocess(raw)
    return PreprocessedSource(
        path=path, kind=kind, text=result.text,
        raw_bytes=len(raw.encode("utf-8")), rule_counts=result.rule_counts,
    )
