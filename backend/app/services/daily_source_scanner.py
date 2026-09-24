"""日志扫描模块 LogScanner（M15 · P1 单日归并）。

职责（对应 docs/MEMORY-DAILY-STANDARDIZER-PLAN.md §5.1）：
- 扫指定 Agent 的 `memory/` 顶层（**不递归**）下的 `*.md`
- 按日文件名模式分为 A / B / C 三类（纯正则，不允许模糊判定）
- 按日期分组，标出「同日多来源」与「单来源但内容质量差」

三条边界（**刻意的设计决策，改动前请先读方案文档**）：
1. **只扫 `memory/` 顶层**：`memory/archive/`、`memory/dreaming/`、`memory/cases/`、
   `memory/contacts/`、`memory/logs/`、`memory/iteration/` 等子目录都是独立的语义目录
   （历史归档 / dreaming 产物 / 案件资料 …），混进来会误改文件、误删碎片；
   方案已明确 dreaming / corpus 不在范围内。
2. **只有 3 种命名模式命中**：`YYYY-MM-DD.md`（A）/ `YYYY-MM-DD-HHMM.md`（B，
   允许 `-HHMM-2` 这类去重后缀）/ `YYYY-MM-DD-<topic>.md`（C）。其余一律不处理
   （`lessons.md`、`README.md`、`2026-5-6.md` 这类非补零日期、非法日期如 `2026-13-45.md`）。
3. **所有内部路径都是 Agent 相对路径**（如 `memory/2026-08-24.md`），与 `FileManager` 同一口径。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path

from app.core.errors import BadRequestError
from app.services.file_manager import FileManager

MEMORY_DIR = "memory"

KIND_A = "A"  # 标准日文件：当天主骨架
KIND_B = "B"  # 同日 session / 时间戳导出
KIND_C = "C"  # 同日主题文件

# 来源优先级：A（主骨架）> C（关键事件）> B（补充事件），见方案附录 A
KIND_PRIORITY = {KIND_A: 0, KIND_C: 1, KIND_B: 2}

# 「单来源但内容质量差」的确定性判据（方案 §5.1 / 坑 1：不能只看文件数量）
LOW_QUALITY_SIZE_BYTES = 24 * 1024   # 体积超过 24KB：大概率是流水账
HEARTBEAT_SPAM_LINES = 20            # 心跳块 / HEARTBEAT_OK 行数超过 20：典型轮询流水
REASON_SIZE = "size"
REASON_HEARTBEAT = "heartbeat-spam"
REASON_METADATA = "metadata-shell"

_DAY_NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
# B 类：日期 + 4 位时间，允许再跟一个去重后缀（如 2026-09-13-1623-2.md）
_TIME_NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{4})(?:-(.+))?$")
# C 类：日期 + 任意主题后缀
_TOPIC_NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)$")

# 质量判据用到的廉价信号（只在需要时读文件内容）
_HEARTBEAT_RE = re.compile(r"heartbeat|HEARTBEAT_OK", re.IGNORECASE)
_METADATA_SHELL_RE = re.compile(r"Session Key|Session ID|Conversation info|Sender \(|Queued messages while")


def classify_daily_filename(name: str) -> tuple[str, str] | None:
    """按文件名判定 (kind, date)；不是三种日文件名之一则返回 None。

    只认 `.md` 扩展名；日期必须是真实存在的日历日期（`2026-02-30` 会被排除）。
    """
    if not name.lower().endswith(".md"):
        return None
    stem = name[: -len(".md")]

    for pattern, kind in ((_DAY_NAME_RE, KIND_A), (_TIME_NAME_RE, KIND_B), (_TOPIC_NAME_RE, KIND_C)):
        m = pattern.match(stem)
        if not m:
            continue
        y, mo, d = m.group(1), m.group(2), m.group(3)
        try:
            _date(int(y), int(mo), int(d))
        except ValueError:
            return None  # 非法日期（2026-13-45 / 2026-02-30）→ 不处理
        return kind, f"{y}-{mo}-{d}"
    return None


@dataclass
class DailySource:
    """一个待归并的来源文件。"""

    path: str          # Agent 相对路径，如 memory/2026-09-13-1623.md
    kind: str          # A / B / C
    size_bytes: int
    mtime: int
    low_quality_reasons: list[str] = field(default_factory=list)

    @property
    def is_low_quality(self) -> bool:
        return bool(self.low_quality_reasons)


@dataclass
class DayGroup:
    """某一天的来源集合。"""

    date: str
    sources: list[DailySource]   # 已按来源优先级 A > C > B 排序

    @property
    def has_standard(self) -> bool:
        """当天是否已有标准日文件（A 类）——决定是「改写既有」还是「新建」。"""
        return any(s.kind == KIND_A for s in self.sources)

    @property
    def target_path(self) -> str:
        """归并目标：恒为 `memory/YYYY-MM-DD.md`。"""
        return f"{MEMORY_DIR}/{self.date}.md"

    @property
    def fragments(self) -> list[DailySource]:
        """归并成功后待删除的碎片（B / C 类；A 类是被改写的主体，不删）。"""
        return [s for s in self.sources if s.kind != KIND_A]

    @property
    def needs_rework(self) -> bool:
        """该日是否需要整理：多来源（有碎片），或唯一来源质量差。"""
        return bool(self.fragments) or any(s.is_low_quality for s in self.sources)


class DailySourceScanner:
    """扫描 Agent 的 memory/ 目录，产出按日分组的来源清单。"""

    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager

    # ---------- 扫描 ----------

    def _memory_dir(self, agent_id: str) -> Path:
        agent = self.file_manager.require_agent(agent_id)
        return Path(agent.workspace) / MEMORY_DIR

    def _source_of(self, rel: str, full: Path, kind: str) -> DailySource:
        stat = full.stat()
        return DailySource(
            path=rel, kind=kind, size_bytes=stat.st_size, mtime=int(stat.st_mtime),
            low_quality_reasons=self._quality_reasons(full, kind),
        )

    @staticmethod
    def _quality_reasons(full: Path, kind: str) -> list[str]:
        """「单来源但内容质量差」的确定性判据（读一遍内容，都是廉价信号）。

        B / C 类本身就是待归并的碎片，不再叠加「质量」理由。
        """
        if kind != KIND_A:
            return []
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        reasons: list[str] = []
        if len(text.encode("utf-8")) > LOW_QUALITY_SIZE_BYTES:
            reasons.append(REASON_SIZE)
        lines = text.splitlines()
        if sum(1 for line in lines if _HEARTBEAT_RE.search(line)) >= HEARTBEAT_SPAM_LINES:
            reasons.append(REASON_HEARTBEAT)
        if _METADATA_SHELL_RE.search(text):
            reasons.append(REASON_METADATA)
        return reasons

    def scan(self, agent_id: str) -> list[DayGroup]:
        """扫描整个 memory/（顶层），返回按日期升序的日分组。"""
        memory = self._memory_dir(agent_id)
        if not memory.is_dir():
            return []

        grouped: dict[str, list[DailySource]] = {}
        for entry in sorted(memory.glob("*.md")):  # 顶层非递归，天然跳过子目录与隐藏目录
            if not entry.is_file():
                continue
            classified = classify_daily_filename(entry.name)
            if classified is None:
                continue
            kind, day = classified
            rel = f"{MEMORY_DIR}/{entry.name}"
            grouped.setdefault(day, []).append(self._source_of(rel, entry, kind))

        return [
            DayGroup(date=day, sources=sorted(srcs, key=self._sort_key))
            for day, srcs in sorted(grouped.items())
        ]

    @staticmethod
    def _sort_key(source: DailySource) -> tuple[int, str]:
        """来源优先级 A > C > B；同优先级按文件名（确定性，保证 prompt 可复现）。"""
        return KIND_PRIORITY[source.kind], source.path

    # ---------- 筛选 ----------

    def scan_range(self, agent_id: str, date_from: str | None = None,
                   date_to: str | None = None, *, only_rework: bool = False) -> list[DayGroup]:
        """按日期范围（含端点，`YYYY-MM-DD`）过滤；`only_rework=True` 只留需要整理的日期。"""
        for label, value in (("date_from", date_from), ("date_to", date_to)):
            if value is not None and classify_daily_filename(f"{value}.md") is None:
                raise BadRequestError(
                    f"{label} 必须是合法的 YYYY-MM-DD 日期", details={label: value})
        if date_from and date_to and date_from > date_to:
            raise BadRequestError(
                "date_from 不能晚于 date_to", details={"date_from": date_from, "date_to": date_to})

        groups = self.scan(agent_id)
        return [
            g for g in groups
            if (date_from is None or g.date >= date_from)
            and (date_to is None or g.date <= date_to)
            and (not only_rework or g.needs_rework)
        ]

    def day(self, agent_id: str, date: str) -> DayGroup | None:
        """取指定日期的分组；当天无合规来源则返回 None。"""
        if classify_daily_filename(f"{date}.md") is None:
            raise BadRequestError("date 必须是合法的 YYYY-MM-DD 日期", details={"date": date})
        return next((g for g in self.scan(agent_id) if g.date == date), None)
