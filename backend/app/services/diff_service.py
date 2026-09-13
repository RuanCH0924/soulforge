"""DiffService：文本归一化 + 差异计算 + 相似度 + HTML 高亮。

修复背景（「完全相同的有效内容被误判为不同」）：
真实数据中大量文件在**视觉上完全一致**，但字符层面存在不可见差异，例如
文件末尾多出 ``\\n\\n\\u200d``（零宽连接符）、UTF-8 BOM、行尾空白、
全角空格 / 不换行空格、Tab 缩进、连续空行、文末无换行等。
旧实现直接对原始字符串做 ``difflib`` 比较，导致这些「格式噪声」被当成业务差异，
既污染差异视图，又把相似度压到 99% 让人误以为内容不同。

本实现的口径：

1. **两级快路径**：字节级相同 → 直接判定一致；归一化后相同 → 判定「有效内容一致，
   差异仅来自格式噪声」，两种情况都跳过全部 diff 计算（性能与准确性同时受益）。
2. **两种归一化口径**（``mode``）：
   - ``strict``：只去除绝对无意义的噪声（BOM / 换行风格 / 零宽与不可见字符）；
   - ``ignore_whitespace``（默认）：在 strict 基础上再忽略行尾空白、连续空白、
     连续空行与首尾空白，用于判定「有效业务内容」是否一致。
3. **相似度在归一化文本上计算**，保证「内容一致 ⇒ 相似度 1.0」，
   不再出现「看起来一样却显示 99%」的误导。

所有对外函数保持向后兼容，便于其他调用方（AI 整理 / 预设 / 同步）无感迁移。
"""
from __future__ import annotations

import difflib
import html as html_mod
import re
from dataclasses import dataclass, field

from app.models.schemas import DiffResult
from app.services.backup_service import BackupService
from app.services.file_manager import FileManager

MODE_STRICT = "strict"
MODE_IGNORE_WHITESPACE = "ignore_whitespace"
VALID_MODES = (MODE_STRICT, MODE_IGNORE_WHITESPACE)

# 超过该字符数改用「行级」相似度：字符级 SequenceMatcher 在长文本上是 O(n²)，
# 2000+ 行的文档会明显变慢；行级相似度对文档语义更贴切且快一个量级。
LINE_SIMILARITY_THRESHOLD = 20000

# 零宽与不可见字符：视觉上不存在，绝对无意义，strict 口径即移除
_INVISIBLE_RE = re.compile("[\u200b-\u200f\u2028\u2029\u2060\ufeff\ufe0f]")

# 「看起来像空格」的字符：视觉等同普通空格，仅在 ignore_whitespace 口径下归一
_SPACE_LIKE_TABLE = str.maketrans({
    "\u00a0": " ",  # NBSP
    "\u1680": " ",
    "\u2000": " ",
    "\u2001": " ",
    "\u2002": " ",
    "\u2003": " ",
    "\u2004": " ",
    "\u2005": " ",
    "\u2006": " ",
    "\u2007": " ",
    "\u2008": " ",
    "\u2009": " ",
    "\u200a": " ",
    "\u202f": " ",
    "\u205f": " ",
    "\u3000": " ",  # 全角空格
})

_CRLF_RE = re.compile("\r\n?")
_MULTI_SPACE_RE = re.compile("[ \t]+")
_TRAILING_WS_RE = re.compile("[ \t]+(?=\n)")
_MULTI_BLANK_RE = re.compile("\n{2,}")


# ---------------------------------------------------------------- 归一化

def strip_bom(text: str) -> str:
    """去掉 UTF-8 BOM（编辑器通常不可见）。"""
    return text[1:] if text.startswith("\ufeff") else text


def normalize_newlines(text: str) -> str:
    """统一换行为 \\n（CRLF / CR → LF）。"""
    return _CRLF_RE.sub("\n", text)


def remove_invisible(text: str) -> str:
    """移除零宽 / 不可见字符。"""
    return _INVISIBLE_RE.sub("", text)


def canonical(text: str, mode: str = MODE_IGNORE_WHITESPACE) -> str:
    """把文本归一化为「用于比较的有效内容」（比较口径）。

    在展示口径基础上，进一步忽略空白数量、空行数量与首尾空行。
    结果统一以单个换行结尾，避免 ``splitlines(keepends=True)`` 因末行缺少换行
    而把「删除行 + 新增行」粘连成一行。
    """
    s = display_text(text, mode)
    if mode == MODE_STRICT:
        return s
    s = _MULTI_SPACE_RE.sub(" ", s)   # 连续空白折叠
    s = _MULTI_BLANK_RE.sub("\n", s)  # 连续空行折叠
    lines = s.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def display_text(text: str, mode: str = MODE_IGNORE_WHITESPACE) -> str:
    """展示用归一化（差异视图口径）。

    只清除绝对无意义的噪声（BOM / 换行风格 / 零宽字符）与行尾空白，
    **保留行结构、缩进与空行**，保证差异视图与真实文件结构一致、可读。
    """
    s = remove_invisible(normalize_newlines(strip_bom(text)))
    if mode == MODE_STRICT:
        return s
    s = s.translate(_SPACE_LIKE_TABLE)  # 伪空格 → 普通空格
    return _TRAILING_WS_RE.sub("", s)   # 行尾空白


def _strip_edge_blank_lines(s: str) -> str:
    lines = s.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + ("\n" if lines else "")


# 噪声分级：名称 → 变换函数（顺序即「从最无害到最宽松」）
_NOISE_STAGES: list[tuple[str, object]] = [
    ("bom", strip_bom),
    ("line_ending", normalize_newlines),
    ("invisible_char", remove_invisible),
    ("space_like_char", lambda s: s.translate(_SPACE_LIKE_TABLE)),
    ("trailing_whitespace", lambda s: _TRAILING_WS_RE.sub("", s)),
    ("multiple_spaces", lambda s: _MULTI_SPACE_RE.sub(" ", s)),
    ("blank_lines", lambda s: _MULTI_BLANK_RE.sub("\n", s)),
    ("edge_blank_lines", _strip_edge_blank_lines),
]

_STRICT_SKIPPED_STAGES = {
    "space_like_char", "trailing_whitespace", "multiple_spaces",
    "blank_lines", "edge_blank_lines",
}


def detect_noise(a_text: str, b_text: str, mode: str = MODE_IGNORE_WHITESPACE) -> list[str]:
    """返回「完整解释了本次差异」的噪声类型。

    仅当归一化后两侧确实一致（即差异纯属格式噪声）时才逐级归因；
    若存在真实业务差异，直接返回空列表——避免把与差异无关的噪声误报为原因。
    """
    if canonical(a_text, mode) != canonical(b_text, mode):
        return []
    kinds: list[str] = []
    ca, cb = a_text, b_text
    for name, fn in _NOISE_STAGES:
        if mode == MODE_STRICT and name in _STRICT_SKIPPED_STAGES:
            break
        if ca == cb:
            break
        na, nb = fn(ca), fn(cb)  # type: ignore[operator]
        if (na != ca) or (nb != cb):
            kinds.append(name)
        ca, cb = na, nb
    return kinds


# ---------------------------------------------------------------- 差异与相似度

def unified_diff(a_text: str, b_text: str, fromfile: str = "a", tofile: str = "b") -> str:
    """标准 unified diff（保持旧签名，供 AI 整理 / 预设等调用方复用）。"""
    return "".join(difflib.unified_diff(
        a_text.splitlines(keepends=True), b_text.splitlines(keepends=True),
        fromfile=fromfile, tofile=tofile,
    ))


def similarity(a_text: str, b_text: str) -> float:
    """文本相似度；长文本自动降级为行级比较以保证性能。"""
    ratio, _ = _similarity_with_mode(a_text, b_text)
    return ratio


def _similarity_with_mode(a_text: str, b_text: str) -> tuple[float, str]:
    if a_text == b_text:
        return 1.0, "none"
    # autojunk=False：关闭「高频元素视为垃圾」的启发式，避免长文档相似度失真
    if max(len(a_text), len(b_text)) > LINE_SIMILARITY_THRESHOLD:
        la, lb = a_text.splitlines(), b_text.splitlines()
        if not la and not lb:
            return 1.0, "lines"
        if not la or not lb:
            return 0.0, "lines"
        return round(difflib.SequenceMatcher(None, la, lb, autojunk=False).ratio(), 4), "lines"
    return round(difflib.SequenceMatcher(None, a_text, b_text, autojunk=False).ratio(), 4), "chars"


def render_html_diff(ud: str) -> str:
    """把已算好的 unified diff 渲染为带行类名的 <pre>（不重复计算 diff）。"""
    if not ud:
        return ""
    lines = []
    for line in ud.rstrip("\n").splitlines():
        cls = "diff-line"
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            cls += " diff-hunk"
        elif line.startswith("+"):
            cls += " diff-add"
        elif line.startswith("-"):
            cls += " diff-del"
        lines.append(f'<span class="{cls}">{html_mod.escape(line)}</span>')
    return "<pre class='diff-view'>" + "\n".join(lines) + "</pre>"


def html_diff(a_text: str, b_text: str, fromfile: str = "a", tofile: str = "b") -> str:
    """兼容旧签名：内部只计算一次 diff。"""
    return render_html_diff(unified_diff(a_text, b_text, fromfile, tofile))


@dataclass(frozen=True)
class DiffOutcome:
    """一次对比的完整结果。"""
    #: 有效内容（归一化后）是否一致
    identical: bool
    #: 原始字节是否一致
    raw_identical: bool
    #: 在归一化文本上计算的相似度（一致时为 1.0）
    similarity: float
    unified_diff: str
    html_diff: str
    #: 解释本次差异的格式噪声类型（空表示差异是真实业务差异）
    noise_kinds: list[str] = field(default_factory=list)
    similarity_mode: str = "chars"
    mode: str = MODE_IGNORE_WHITESPACE

    @property
    def noise_only(self) -> bool:
        """仅存在格式噪声差异（原始不同、有效内容相同）。"""
        return self.identical and not self.raw_identical


def build_diff(
    a_text: str,
    b_text: str,
    *,
    fromfile: str = "a",
    tofile: str = "b",
    mode: str = MODE_IGNORE_WHITESPACE,
) -> DiffOutcome:
    """核心入口：先归一化判定，再按需计算差异（避免无谓的重计算）。"""
    norm_mode = mode if mode in VALID_MODES else MODE_IGNORE_WHITESPACE
    # 快路径 1：字节级完全相同 → 无需任何归一化与 diff 计算
    if a_text == b_text:
        return DiffOutcome(True, True, 1.0, "", "", [], "none", norm_mode)
    ca = canonical(a_text, norm_mode)
    cb = canonical(b_text, norm_mode)
    # 快路径 2：有效内容一致（差异仅来自格式噪声）→ 跳过 diff 计算
    if ca == cb:
        return DiffOutcome(
            True, False, 1.0, "", "", detect_noise(a_text, b_text, norm_mode), "none", norm_mode,
        )
    # 差异视图使用「展示口径」：保留空行与缩进，只清掉不可见噪声，保证可读
    ud = unified_diff(
        display_text(a_text, norm_mode), display_text(b_text, norm_mode),
        fromfile=fromfile, tofile=tofile,
    )
    ratio, smode = _similarity_with_mode(ca, cb)
    return DiffOutcome(False, False, ratio, ud, render_html_diff(ud), [], smode, norm_mode)


# ---------------------------------------------------------------- 服务

class DiffService:
    def __init__(self, file_manager: FileManager, backup_service: BackupService):
        self.file_manager = file_manager
        self.backup_service = backup_service

    @staticmethod
    def _to_result(
        outcome: DiffOutcome, *, agent_a: str, agent_b: str, file: str,
    ) -> DiffResult:
        return DiffResult(
            agent_a=agent_a,
            agent_b=agent_b,
            file=file,
            similarity=outcome.similarity,
            unified_diff=outcome.unified_diff,
            html_diff=outcome.html_diff,
            identical=outcome.identical,
            noise_kinds=outcome.noise_kinds,
            mode=outcome.mode,
        )

    def diff_agents(
        self, agent_a: str, agent_b: str, file_path: str, mode: str = MODE_IGNORE_WHITESPACE,
    ) -> DiffResult:
        a = self.file_manager.read(agent_a, file_path)
        b = self.file_manager.read(agent_b, file_path)
        outcome = build_diff(
            a.content, b.content,
            fromfile=f"{agent_a}/{file_path}", tofile=f"{agent_b}/{file_path}", mode=mode,
        )
        return self._to_result(outcome, agent_a=agent_a, agent_b=agent_b, file=file_path)

    def diff_history(
        self, agent: str, file_path: str, against: int, mode: str = MODE_IGNORE_WHITESPACE,
    ) -> DiffResult:
        current = self.file_manager.read(agent, file_path)
        old = self.backup_service.read_content(against)
        outcome = build_diff(
            old, current.content,
            fromfile=f"backup#{against}", tofile=f"{agent}/{file_path}", mode=mode,
        )
        return self._to_result(outcome, agent_a=agent, agent_b=agent, file=file_path)
