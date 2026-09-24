"""单元测试：工作日志来源预处理器（M15 · P1）。

验收口径（方案 §7.1）：12 类元数据各 1 个样本 + 混合样本 + **正文中合法 JSON 示例（不得误删）**，
剥壳后残留 = 0，且不误删正文合法内容。
"""
from __future__ import annotations

import pytest

from app.services.daily_preprocessor import (
    PREPROCESS_RULES,
    PreprocessResult,
    describe_shells,
    detect_residual_shells,
    preprocess,
    preprocess_source,
)

# ---------- 12 条规则各自的最小样本 ----------

SAMPLES: dict[str, tuple[str, str]] = {
    # rule_id: (原始文本, 净化后必须消失的片段)
    "M01": (
        (
            "- **Session Key**: agent:xiaowei-ops:main\n"
            "- **Session ID**: ce2b3f77-a459-4363-87bf-76a2d3c4894f\n"
            "- **Source**: gateway:sessions.reset\n"
            "\n端口仪表盘已刷新。"
        ),
        "Session Key",
    ),
    "M02": (
        "# Session: 2026-09-23 09:16:04 Asia/Shanghai\n\n正文保留。",
        "# Session:",
    ),
    "M03": (
        (
            "Conversation info (untrusted metadata):\n"
            "```json\n"
            '{"chat_id": "oc_x", "message_id": "om_y"}\n'
            "```\n"
            "\n正文保留。"
        ),
        "chat_id",
    ),
    "M04": (
        (
            "Sender (untrusted metadata):\n"
            '{"id": "ou_e24e178cff0196a23335ab9ec3a47108", "name": "老板"}\n'
            "\n正文保留。"
        ),
        "ou_e24e",
    ),
    "M05": (
        (
            "Reply target of current user message:\n"
            "> 老板：把端口仪表盘刷新一下\n"
            "\n正文保留。"
        ),
        "端口仪表盘刷新一下",
    ),
    "M06": (
        (
            "Queued messages while agent was busy:\n"
            "- 老板：第一条\n"
            "- 老板：第二条\n"
            "\n正文保留。"
        ),
        "第一条",
    ),
    "M07": (
        "- Possible Lasting Truths: No strong candidate truths surfaced\n\n正文保留。",
        "No strong candidate truths surfaced",
    ),
    "M08": (
        "- Reflections: 12\n- Themes: 3\n\n正文保留。",
        "Reflections: 12",
    ),
    "M09": (
        (
            'assistant: "让我检查一下。"\n'
            "我来看看\n"
            "- 任务还在运行中\n"
            "结论：已修复端口问题。"
        ),
        "让我检查一下",
    ),
    "M10": (
        "- **HEARTBEAT_OK**\n\n结论：一切正常。",
        "HEARTBEAT_OK",
    ),
    "M11": (
        "\ufeff结论：换行与 BOM 归一。\r\n第二行\r\n",
        "\r",
    ),
    "M12": (
        "第一行   \n\n\n\n第二行\n",
        "第一行   ",
    ),
}


@pytest.mark.parametrize("rule_id", list(SAMPLES))
def test_each_rule_hits_and_removes_shell(rule_id: str):
    raw, gone = SAMPLES[rule_id]
    result = preprocess(raw)
    assert result.hits(rule_id) > 0, f"{rule_id} 未命中"
    assert gone not in result.text, f"{rule_id} 剥壳不干净：{gone!r}"


def test_rule_catalog_has_twelve_stable_ids():
    ids = [r.rule_id for r in PREPROCESS_RULES]
    assert ids == [f"M{i:02d}" for i in range(1, 13)]
    assert all(r.name and r.description for r in PREPROCESS_RULES)


# ---------- 混合样本：残留 = 0 ----------

MIXED_SAMPLE = """# Session: 2026-09-23 09:16:04 Asia/Shanghai

- **Session Key**: agent:xiaowei-ops:main
- **Session ID**: 11111111-2222-3333-4444-555555555555
- **Source**: gateway:sessions.reset

Conversation info (untrusted metadata):
```json
{"chat_id": "oc_x", "message_id": "om_y"}
```

Sender (untrusted metadata):
```json
{"id": "ou_z"}
```

Reply target of current user message:
> 老板：刷新端口仪表盘

Queued messages while agent was busy:
- 老板：顺便看下 8420 的水位

## Conversation Summary

user: "刷新端口仪表盘"
assistant: "让我检查一下。"
assistant: "端口仪表盘已刷新：22 个端口，RSS 总 2832 MB。tdai-gateway 涨到 467MB。"

- Possible Lasting Truths: No strong candidate truths surfaced
- Reflections: 12

HEARTBEAT_OK

决策：8420 的 467MB 接近警示位，纳入观察。
"""


def test_mixed_sample_leaves_no_residue():
    result = preprocess(MIXED_SAMPLE)
    assert detect_residual_shells(result.text) == []

    # 高价值事实必须全部留下
    assert "端口仪表盘已刷新" in result.text
    assert "8420 的 467MB 接近警示位" in result.text
    assert "Conversation Summary" in result.text
    # 壳必须全部消失
    for gone in ("Session Key", "chat_id", "ou_z", "Queued messages", "Reflections: 12", "HEARTBEAT_OK"):
        assert gone not in result.text


def test_preprocess_reports_counts_and_shrinks():
    result = preprocess(MIXED_SAMPLE)
    assert isinstance(result, PreprocessResult)
    assert result.removed_total > 0
    assert {"M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09", "M10"} <= set(result.rule_counts)


# ---------- 回归：归一规则（M11/M12）不算「残留壳」 ----------

COMPLIANT_DOC = """# 2026-09-15 工作日志

## 一、今日概览

端口仪表盘已刷新。

## 二、关键事件

- 8420 水位 467MB，纳入观察。

## 三、关键决策

- **明确**：先观察，不扩容。

## 四、待办事项

- 周四复查 8420 水位。

## 五、明日计划

- 复盘端口扩容方案。
"""


def test_only_true_shell_rules_are_detected():
    assert [r.rule_id for r in PREPROCESS_RULES if r.is_shell] == [f"M{i:02d}" for i in range(1, 11)]


def test_compliant_doc_with_trailing_newline_has_no_residue():
    """回归（真实事故）：完全合规的 5 章节文档只要结尾带换行，M12 空白归一必然命中。

    M12 是「归一」不是「壳」——若把它算作残留，任何正常文档都会被写前验收判成 blocked。
    """
    assert COMPLIANT_DOC.endswith("\n")
    assert detect_residual_shells(COMPLIANT_DOC) == []


def test_real_shell_still_detected_after_excluding_normalizers():
    """排除归一规则不能把检测能力一起削掉：真壳仍须命中，且报错给可读名称。"""
    dirty = COMPLIANT_DOC + "\n- **Session Key**: agent:xiaowei-ops:main   \n"
    assert detect_residual_shells(dirty) == ["M01"]
    assert describe_shells(["M01"]) == "会话元数据行"


# ---------- 反例：正文合法内容不得误删 ----------

def test_legal_json_in_body_is_kept():
    """正文里合法的 ```json 代码块没有元数据标题行引导 → 必须原样保留。"""
    text = (
        "## 配置示例\n"
        "\n"
        "```json\n"
        '{"schema": "soulforge.preset/v1", "owner": "user"}\n'
        "```\n"
        "\n"
        "以上是预设的最小配置。\n"
    )
    result = preprocess(text)
    assert '"schema": "soulforge.preset/v1"' in result.text
    assert result.hits("M03") == 0
    assert result.hits("M04") == 0


def test_quote_block_without_metadata_header_is_kept():
    """没有被 M05 标题行引导的引用块是正文 → 必须保留。"""
    text = "## 审核结论\n\n> 本文质量高，仅一处 AI 痕迹。\n\n结论：可直接发布。\n"
    result = preprocess(text)
    assert "> 本文质量高，仅一处 AI 痕迹。" in result.text
    assert result.hits("M05") == 0


def test_transition_phrase_inside_sentence_is_kept():
    """M09 只匹配「整行就是过渡语」，句中出现不删。"""
    text = "结论：先让我检查一下端口再决定是否重启。\n"
    result = preprocess(text)
    assert result.hits("M09") == 0
    assert "先让我检查一下端口" in result.text


def test_heartbeat_inside_sentence_is_kept():
    text = "决策：本轮判定为 HEARTBEAT_OK，无异常。\n"
    result = preprocess(text)
    assert result.hits("M10") == 0
    assert "HEARTBEAT_OK" in result.text


# ---------- 体积统计 ----------


def test_preprocess_source_metrics_and_oversized_flag():
    raw = SAMPLES["M01"][0]
    source = preprocess_source("memory/2026-09-23.md", "A", raw)
    assert source.kind == "A"
    assert source.raw_bytes == len(raw.encode("utf-8"))
    assert source.clean_bytes < source.raw_bytes
    assert source.saved_bytes == source.raw_bytes - source.clean_bytes
    assert source.oversized is False

    big = "## 段落\n\n" + ("" .join("- 一行内容，用于撑体积。\n" for _ in range(2000)))
    assert preprocess_source("memory/2026-09-24.md", "A", big).oversized is True
