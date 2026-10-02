"""单元测试：无意义日志的判定维度、筛选 prompt 与结论解析（M15 扩展）。

覆盖：
- 判定维度文案（含需求点名的四类：空内容 / 重复冗余 / 无业务价值调试信息 / 无效格式）
- 筛选 prompt 组装（含日期、候选路径、维度清单、超长截断）
- 结论解析的**从严**与**失败安全**（脏输出一律不删除任何日志）
"""
from __future__ import annotations

import asyncio
import json

from app.services.daily_log_filter import (
    MEANINGLESS_DIMENSIONS,
    MeaninglessFinding,
    ScreeningCandidate,
    build_screening_prompt,
    dimension_name,
    dimensions_summary,
    parse_screening_result,
    screen_meaningless,
)


def test_dimensions_cover_required_categories_and_ids_unique():
    ids = [d.id for d in MEANINGLESS_DIMENSIONS]
    assert len(ids) == len(set(ids))                       # id 唯一
    # 需求点名的四类判定标准必须齐全
    assert {"empty_content", "duplicate_redundant", "debug_noise", "invalid_format"} <= set(ids)
    for d in MEANINGLESS_DIMENSIONS:
        assert d.name and d.criteria                       # 每维都有名称与判定标准


def test_dimension_name_and_summary():
    assert dimension_name("debug_noise") == "无业务价值的调试信息"
    assert dimension_name("unknown") == "unknown"           # 未知 id 原样返回
    summary = dimensions_summary()
    for d in MEANINGLESS_DIMENSIONS:
        assert f"{d.id}（{d.name}）" in summary


def test_build_prompt_contains_date_paths_and_dimensions():
    candidates = [
        ScreeningCandidate("memory/2026-12-01-1415.md", "B", "只有心跳"),
        ScreeningCandidate("memory/2026-12-01-topic.md", "C", "真实结论：修复了 X"),
    ]
    prompt = build_screening_prompt("2026-12-01", candidates)
    assert "2026-12-01" in prompt
    assert "memory/2026-12-01-1415.md" in prompt
    assert "memory/2026-12-01-topic.md" in prompt
    assert "empty_content" in prompt and "invalid_format" in prompt
    assert "共 2 个" in prompt


def test_build_prompt_truncates_oversized_source():
    big = "x" * 20000
    prompt = build_screening_prompt("2026-12-02", [ScreeningCandidate("memory/a.md", "C", big)])
    assert "超长已截断" in prompt
    assert len(prompt) < 20000 + 2000                        # 未把全文塞进去


# ---------- 结论解析 ----------


VALID = {"memory/2026-12-01-1415.md"}


def test_parse_valid_json():
    raw = json.dumps({"meaningless": [
        {"path": "memory/2026-12-01-1415.md", "dimension": "debug_noise", "reason": "只有轮询"}
    ]})
    findings = parse_screening_result(raw, VALID)
    assert findings == [MeaninglessFinding("memory/2026-12-01-1415.md", "debug_noise", "只有轮询")]


def test_parse_tolerates_code_fence_and_preamble():
    raw = (
        "好的，结论如下：\n```json\n"
        '{"meaningless": [{"path": "memory/2026-12-01-1415.md",'
        ' "dimension": "empty_content", "reason": "空"}]}\n```'
    )
    findings = parse_screening_result(raw, VALID)
    assert len(findings) == 1 and findings[0].dimension == "empty_content"


def test_parse_empty_list():
    assert parse_screening_result('{"meaningless": []}', VALID) == []


def test_parse_drops_unknown_path():
    raw = json.dumps({"meaningless": [
        {"path": "memory/not-a-candidate.md", "dimension": "debug_noise", "reason": "x"}
    ]})
    assert parse_screening_result(raw, VALID) == []


def test_parse_drops_unknown_dimension():
    raw = json.dumps({"meaningless": [
        {"path": "memory/2026-12-01-1415.md", "dimension": "made_up", "reason": "x"}
    ]})
    assert parse_screening_result(raw, VALID) == []


def test_parse_dedupes_same_path():
    raw = json.dumps({"meaningless": [
        {"path": "memory/2026-12-01-1415.md", "dimension": "debug_noise", "reason": "a"},
        {"path": "memory/2026-12-01-1415.md", "dimension": "empty_content", "reason": "b"},
    ]})
    assert len(parse_screening_result(raw, VALID)) == 1


def test_parse_malformed_returns_empty():
    for raw in ("", "not json", "[1,2,3]", '{"meaningless": "x"}',
                '{"meaningless": [{"path": 123}]}', "```json\n```"):
        assert parse_screening_result(raw, VALID) == []


# ---------- screen_meaningless 不空转 ----------


class _BoomClient:
    async def chat(self, *args, **kwargs):  # pragma: no cover - 不应被调用
        raise AssertionError("候选为空时不应调用大模型")


def test_screen_meaningless_with_no_candidates_skips_llm():
    findings, resp = asyncio.run(screen_meaningless(_BoomClient(), "2026-12-03", []))
    assert findings == []
    assert resp.usage.total_tokens == 0
