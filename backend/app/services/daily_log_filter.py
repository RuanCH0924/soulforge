"""无意义日志筛选（M15 · 大模型无意义日志自动删除）。

本模块只做「判定」这一件事：给出**无意义日志的判定维度**、组装筛选 prompt、
解析大模型返回的结构化结论。是否启用、以及删除前的备份，分别由
`DailyStandardizerConfig.auto_delete_meaningless_logs` 与
`app.services.meaningless_log_archive` 负责。

### 判定维度（文案唯一事实源 = `MEANINGLESS_DIMENSIONS`）

| id | 名称 | 参考判定标准 |
|---|---|---|
| `empty_content` | 空日志内容 | 剥壳后为空 / 只剩标题或空白 / 全是无信息量的占位符 |
| `duplicate_redundant` | 重复冗余日志 | 事实与同日其它来源完全重叠，删除后不损失任何独有信息 |
| `debug_noise` | 无业务价值的调试信息 | 纯状态轮询、中间态打印、重复失败重试等没有结论的调试流水 |
| `invalid_format` | 无效格式日志 | 乱码 / 截断 / 无法解析为工作日志的残片，提取不出任何事实 |
| `process_chatter` | 纯过程叙述 | 只有「让我检查一下」这类过程话与心跳，没有任何决策或结果 |

判定是**保守**的：只要一条日志里还有任何真实的事实 / 决策 / 待办 / 可复用数据，
就不能判为无意义（宁可漏删，不可误删）。解析失败时一律返回空结论（不额外删除）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.services.llm_registry import LLMResponse, LLMTokenUsage

# 空候选时的零用量占位（避免各处各造一个零值对象）
_ZERO_USAGE = LLMTokenUsage()

# 单个候选来源进筛选 prompt 的字符上限（超出截断；判定无意义不需要全文）
SCREENING_MAX_CHARS_PER_SOURCE = 8000


@dataclass(frozen=True)
class MeaninglessDimension:
    """无意义日志的一个判定维度。"""

    id: str
    name: str
    criteria: str


# 判定维度（需求列出的四类 + 纯过程叙述；文案即 prompt 与文档的唯一事实源）
MEANINGLESS_DIMENSIONS: tuple[MeaninglessDimension, ...] = (
    MeaninglessDimension(
        "empty_content", "空日志内容",
        "剥壳后为空、只剩标题或空白，或整篇都是无信息量的占位符（如 无 / N/A / 待补充）。"),
    MeaninglessDimension(
        "duplicate_redundant", "重复冗余日志",
        "记录的事实与同日其它来源完全重叠，删除后不损失任何独有信息。"),
    MeaninglessDimension(
        "debug_noise", "无业务价值的调试信息",
        "纯状态轮询、中间态打印、重复的失败重试等没有结论、没有产出、无法复用为业务信息的调试流水。"),
    MeaninglessDimension(
        "invalid_format", "无效格式日志",
        "乱码、被截断、结构损坏，无法解析为工作日志、提取不出任何事实的残片。"),
    MeaninglessDimension(
        "process_chatter", "纯过程叙述",
        "只有「让我检查一下」这类过程话与心跳记录，没有任何决策、结果或待办。"),
)

_DIMENSION_BY_ID = {d.id: d for d in MEANINGLESS_DIMENSIONS}
_VALID_DIMENSION_IDS = frozenset(_DIMENSION_BY_ID)


def dimension_name(dimension_id: str) -> str:
    """把维度 id 渲染成可读名称（未知 id 原样返回）。"""
    d = _DIMENSION_BY_ID.get(dimension_id)
    return d.name if d else dimension_id


def dimensions_summary() -> str:
    """判定维度的可读清单（进 prompt，也供文档/UI 复用）。"""
    return "\n".join(f"- {d.id}（{d.name}）：{d.criteria}" for d in MEANINGLESS_DIMENSIONS)


@dataclass
class ScreeningCandidate:
    """一个待判定的候选日志（已预处理）。"""

    path: str   # Agent 相对路径
    kind: str   # A / B / C
    text: str   # 预处理后的正文


@dataclass
class MeaninglessFinding:
    """一条「判定为无意义」的结论。"""

    path: str
    dimension: str
    reason: str


SCREENING_SYSTEM_PROMPT = (
    "你是 Soulforge 的工作日志清理助手，负责判断哪些日志是『无意义日志』。"
    "判定必须保守：只要一篇日志里还有任何真实的事实、决策、待办或可复用数据，就不得判为无意义。"
    "只输出一个 JSON 对象，不要输出任何解释、思考过程或 Markdown 代码围栏。"
)

_PROMPT_TEMPLATE = """【任务】判断下面这些 {date} 的工作日志碎片里，哪些属于「无意义日志」。

【无意义日志的判定维度（命中任一即算无意义）】
{dimensions}

【判定纪律】
1. 保守优先：只要日志里还有一条真实的事实 / 决策 / 待办 / 可复用数据，就**不得**判为无意义。
2. 只判定列出的文件；不要新增文件，不要修改文件内容。
3. 每条无意义结论必须给出维度 id 与一句话理由。

【输出格式】只输出如下 JSON（没有无意义日志时输出 {{"meaningless": []}}）：
{{"meaningless": [{{"path": "<原样照抄上面的文件路径>", "dimension": "<维度 id>",
  "reason": "<一句话理由>"}}]}}

【待判定日志（共 {count} 个）】
{candidates}"""


def build_screening_prompt(date: str, candidates: list[ScreeningCandidate]) -> str:
    """组装无意义日志筛选 prompt。"""
    blocks = []
    for c in candidates:
        text = c.text
        if len(text) > SCREENING_MAX_CHARS_PER_SOURCE:
            text = text[:SCREENING_MAX_CHARS_PER_SOURCE] + "\n…（超长已截断，仅用于无意义判定）"
        blocks.append(f"【文件：{c.path}】\n```markdown\n{text}\n```")
    return _PROMPT_TEMPLATE.format(
        date=date, dimensions=dimensions_summary(), count=len(candidates),
        candidates="\n\n".join(blocks),
    )


_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def _extract_json_object(raw: str) -> dict | None:
    """从模型输出里尽力提取一个 JSON 对象（容忍代码围栏 / 前后缀文字）。"""
    text = raw.strip()
    text = _FENCE_RE.sub("", text).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def parse_screening_result(raw: str, valid_paths: set[str]) -> list[MeaninglessFinding]:
    """解析模型返回的无意义判定结论。

    **从严**：只接受 `{"meaningless": [{"path", "dimension", "reason"}, ...]}` 形态，
    且 path 必须在候选集内、dimension 必须是已知维度 id；任何一条不合法就丢弃该条。
    整体解析失败返回空列表（= 不删除任何日志），绝不因解析问题误删。
    """
    data = _extract_json_object(raw)
    if not data:
        return []
    items = data.get("meaningless")
    if not isinstance(items, list):
        return []
    findings: list[MeaninglessFinding] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        dimension = item.get("dimension")
        reason = item.get("reason") or ""
        if not isinstance(path, str) or path not in valid_paths or path in seen:
            continue
        if not isinstance(dimension, str) or dimension not in _VALID_DIMENSION_IDS:
            continue
        seen.add(path)
        findings.append(MeaninglessFinding(
            path=path, dimension=dimension, reason=str(reason).strip()))
    return findings


async def screen_meaningless(
        client, date: str,
        candidates: list[ScreeningCandidate],
) -> tuple[list[MeaninglessFinding], LLMResponse]:
    """调用大模型判定候选日志里的无意义项，返回 `(结论, 用量)`。

    候选为空时不发起调用（返回空结论 + 零用量）。
    """
    if not candidates:
        return [], LLMResponse(content="", usage=_ZERO_USAGE)
    prompt = build_screening_prompt(date, candidates)
    resp = await client.chat([
        {"role": "system", "content": SCREENING_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ])
    findings = parse_screening_result(resp.content, {c.path for c in candidates})
    return findings, resp
