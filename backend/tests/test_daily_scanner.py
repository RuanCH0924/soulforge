"""单元测试：工作日志来源扫描与 A/B/C 分类（M15 · P1）。

验收口径（方案 §7.1）：A/B/C 三类各 3 个样本 + 反例，命中与排除均 100% 正确。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import BadRequestError
from app.services.daily_source_scanner import (
    KIND_A,
    KIND_B,
    KIND_C,
    REASON_HEARTBEAT,
    REASON_METADATA,
    REASON_SIZE,
    DailySourceScanner,
    classify_daily_filename,
)

# ---------- 分类器：命中 ----------


@pytest.mark.parametrize(("name", "kind"), [
    ("2026-05-19.md", KIND_A), ("2026-05-26.md", KIND_A), ("2026-01-01.md", KIND_A),
    ("2026-05-20-1415.md", KIND_B), ("2026-05-24-1506.md", KIND_B),
    ("2026-09-13-1623-2.md", KIND_B),  # 时间去重后缀仍算 B
    ("2026-05-31-1818.md", KIND_B),
    ("2026-05-06-feishu-card-timeout.md", KIND_C), ("2026-07-14-im-ready.md", KIND_C),
    ("2026-07-12-weekend-summary.md", KIND_C),
])
def test_classify_hits(name: str, kind: str):
    result = classify_daily_filename(name)
    assert result is not None
    assert result[0] == kind
    assert result[1] == f"{name[:10]}"


# ---------- 分类器：排除（反例） ----------


@pytest.mark.parametrize("name", [
    "lessons.md",                    # 长期记忆类文件
    "README.md",
    "2026-5-6.md",                   # 非补零日期
    "2026-13-45.md",                 # 非法月份
    "2026-02-30.md",                 # 非法日历日
    "notes-2026-05-19.md",           # 日期不在开头
    "2026-05-19.md.bak",             # 扩展名不是 .md
    "2026-05-19",                    # 没有扩展名
])
def test_classify_excludes(name: str):
    assert classify_daily_filename(name) is None


def test_classify_case_insensitive_extension():
    assert classify_daily_filename("2026-05-19.MD") == (KIND_A, "2026-05-19")


# ---------- 扫描 / 分组 ----------

def _write(registry, rel: str, content: str = "# x\n\n- 内容\n") -> None:
    root = Path(registry.discovery.require("alpha").workspace)
    full = root / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


def test_scan_groups_by_day_with_priority_and_fragments(registry):
    _write(registry, "memory/2026-10-01.md", "# 2026-10-01\n\n- 主骨架事实\n")
    _write(registry, "memory/2026-10-01-topic.md", "# 主题\n\n- 主题事实\n")
    _write(registry, "memory/2026-10-01-1415.md", "# Session: 2026-10-01 14:15:00\n\n- session 事实\n")
    _write(registry, "memory/2026-10-02-0930.md", "# Session: 2026-10-02 09:30:00\n\n- 只有碎片\n")

    scanner = DailySourceScanner(registry.file_manager)
    groups = scanner.scan_range("alpha", "2026-10-01", "2026-10-02")
    assert [g.date for g in groups] == ["2026-10-01", "2026-10-02"]

    day1 = groups[0]
    # 来源优先级 A > C > B
    assert [s.kind for s in day1.sources] == [KIND_A, KIND_C, KIND_B]
    assert day1.has_standard is True
    assert day1.target_path == "memory/2026-10-01.md"
    assert [s.path for s in day1.fragments] == [
        "memory/2026-10-01-topic.md", "memory/2026-10-01-1415.md"]
    assert day1.needs_rework is True

    day2 = groups[1]
    assert day2.has_standard is False          # 只有碎片 → 需要新建
    assert day2.needs_rework is True
    assert [s.path for s in day2.fragments] == ["memory/2026-10-02-0930.md"]


def test_scan_excludes_non_daily_and_nested_files(registry):
    _write(registry, "memory/2026-10-03.md")
    _write(registry, "memory/lessons.md")
    _write(registry, "memory/README.md")
    _write(registry, "memory/2026-5-6.md")
    _write(registry, "memory/2026-13-45.md")
    _write(registry, "memory/archive/2026-10-03.md")   # 归档子目录：不处理
    _write(registry, "memory/.dreams/2026-10-03.md")   # 隐藏目录：不处理
    _write(registry, "memory/dreaming/2026-10-03.md")  # dreaming：明确不在范围

    scanner = DailySourceScanner(registry.file_manager)
    paths = {s.path for g in scanner.scan_range("alpha", "2026-10-01", "2026-10-31")
             for s in g.sources}
    assert paths == {"memory/2026-10-03.md"}


def test_scan_flags_low_quality_single_source(registry):
    # 大体积 + 心跳流水 → 判为「单来源但质量差」
    heartbeat = "".join(
        f"## {i:02d}:58 GMT+8 — heartbeat #{i} 增量\n- 业务: 正常\n- 决策: HEARTBEAT_OK\n\n"
        for i in range(1, 400))
    _write(registry, "memory/2026-10-04.md", heartbeat)
    # 夹带元数据壳的 A 文件
    _write(registry, "memory/2026-10-05.md",
           "# 2026-10-05\n\n- **Session Key**: agent:alpha:main\n\n- 正文\n")

    scanner = DailySourceScanner(registry.file_manager)
    days = {g.date: g for g in scanner.scan_range("alpha", "2026-10-04", "2026-10-05")}

    big = days["2026-10-04"].sources[0]
    assert big.is_low_quality is True
    assert REASON_SIZE in big.low_quality_reasons
    assert REASON_HEARTBEAT in big.low_quality_reasons
    assert days["2026-10-04"].needs_rework is True   # 单文件但质量差 → 仍需整理

    shell = days["2026-10-05"].sources[0]
    assert shell.low_quality_reasons == [REASON_METADATA]


def test_scan_only_rework_filters_clean_days(registry):
    _write(registry, "memory/2026-10-06.md", "# 2026-10-06\n\n- 已精简，无需整理\n")

    scanner = DailySourceScanner(registry.file_manager)
    assert scanner.scan_range("alpha", "2026-10-06", "2026-10-06", only_rework=True) == []
    assert len(scanner.scan_range("alpha", "2026-10-06", "2026-10-06")) == 1


def test_scan_range_rejects_bad_dates(registry):
    scanner = DailySourceScanner(registry.file_manager)
    with pytest.raises(BadRequestError):
        scanner.scan_range("alpha", "2026-5-1", None)
    with pytest.raises(BadRequestError):
        scanner.scan_range("alpha", None, "2026-13-45")
    with pytest.raises(BadRequestError):
        scanner.scan_range("alpha", "2026-10-02", "2026-10-01")


def test_day_returns_group_or_none(registry):
    _write(registry, "memory/2026-10-07.md")
    scanner = DailySourceScanner(registry.file_manager)
    assert scanner.day("alpha", "2026-10-07") is not None
    assert scanner.day("alpha", "2026-10-08") is None
    with pytest.raises(BadRequestError):
        scanner.day("alpha", "不是日期")
