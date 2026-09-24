"""集成测试：单日「多来源 → 1 文件」归并（M15 · P1）。

覆盖方案 §7.1 的 4 个场景：
① 单个已精简的日文件（只规范标题，不强制重写）
② 单个 session 导出（剥壳 → 改写 → 命名归并）
③ 主文件 + 主题文件（合并为新的关键事件小节）
④ 同日 3 个碎片（无 A 类主骨架 → 新建）

外加护栏：超限来源分块摘要、块数超上限转人工复核、无来源日期报错。
LLM 调用全部 mock；**P1 只出计划，必须验证原文件与目标文件都没被动过**。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import BadRequestError, DailySourceTooLargeError
from app.services import daily_merge_service as dms
from app.services import daily_preprocessor
from app.services.llm_registry import LLMResponse, LLMTokenUsage

PROVIDER = {
    "id": "daily-test-provider",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-test-000",
    "model": "gpt-4o",
    "protocol": "openai-completions",
}
PRESET_ID = "preset-wlog-daily-std"   # 内置预设：章节含序号，强规则精确匹配

CHUNK_MARKER = "【本段原文】"


def _doc(date: str) -> str:
    """合规输出的最小骨架（5 章节齐全、顺序正确、无 emoji、无 HTML）。"""
    return (
        f"# 工作日志 - {date}\n\n"
        "## 一、今日概览\n\n"
        "- **日期**：" + date + "\n"
        "- **核心活动**：端口仪表盘刷新完成；8420 内存水位纳入观察\n\n"
        "## 二、关键事件\n\n"
        "### 事件 1\n\n"
        "- 事实：端口仪表盘已刷新，22 个端口、RSS 总 2832 MB\n"
        "- 结果：tdai-gateway RSS 涨到 467MB，接近警示位\n\n"
        "## 三、关键决策\n\n"
        "| 决策项 | 内容 |\n"
        "|--------|------|\n"
        "| 8420 水位 | 纳入观察，暂不重启 |\n\n"
        "## 四、待办事项\n\n"
        "- [ ] 复核 8420 的 GC 后水位是否合理\n\n"
        "## 五、明日计划\n\n"
        "- 观察 8420 GC 后水位，必要时重启\n"
    )


CALLS: list[list[dict]] = []


async def _fake_chat(self, messages, max_tokens=None, temperature=None):
    """分块摘要调用返回短清单，归并调用返回合规文档；同时记录 messages。"""
    CALLS.append(messages)
    user = messages[-1]["content"]
    if CHUNK_MARKER in user:
        content = "- 事实：端口仪表盘已刷新（摘要）\n- 事实：8420 水位接近警示位（摘要）"
    elif OUTPUT_OVERRIDE[0] is not None:
        content = OUTPUT_OVERRIDE[0]
    else:
        content = _doc(_CURRENT_DATE[0])
    return LLMResponse(
        content=content,
        usage=LLMTokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost_estimate_usd=0.0025,
    )


_CURRENT_DATE: list[str] = [""]
OUTPUT_OVERRIDE: list[str | None] = [None]


# ---------- 夹具辅助 ----------


def _root(registry) -> Path:
    return Path(registry.discovery.require("alpha").workspace)


def _write(registry, rel: str, content: str) -> Path:
    full = _root(registry) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


@pytest.fixture()
def prepared(client, registry, monkeypatch):
    """建 provider + 打桩 LLM，返回 (client, registry, calls)。"""
    client.post("/api/llm/providers", json=PROVIDER)
    monkeypatch.setattr("app.services.llm_registry.LLMClient.chat", _fake_chat)
    CALLS.clear()
    OUTPUT_OVERRIDE[0] = None
    return client, registry, CALLS


def _plan(registry, date: str, delivery: str = dms.DEFAULT_DELIVERY):
    _CURRENT_DATE[0] = date
    import asyncio

    return asyncio.run(registry.daily_merge.plan_day(
        "alpha", date, PRESET_ID, PROVIDER["id"], delivery=delivery))


def _messages(calls) -> tuple[str, str]:
    """最后一次调用的 `(system 内容, user 内容)`。"""
    messages = calls[-1]
    return messages[0]["content"], messages[1]["content"]


# ---------- 场景 ①：单个已精简的日文件 ----------


def test_scenario_single_clean_daily_file(prepared):
    _, registry, calls = prepared
    _write(registry, "memory/2026-10-10.md", "# 2026-10-10\n\n- 已精简的事实：端口正常\n")

    plan = _plan(registry, "2026-10-10")

    assert plan.target_path == "memory/2026-10-10.md"
    assert plan.has_standard is True
    assert plan.fragments_to_delete == []          # 单 A 文件：没有碎片要删
    assert [s.kind for s in plan.sources] == ["A"]
    assert plan.format_ok is True
    assert plan.output_content.startswith("# 工作日志 - 2026-10-10")
    assert plan.prompt_tokens == 100 and plan.total_tokens == 150
    assert len(calls) == 1                          # 未超限 → 只有 1 次归并调用
    # 原文件没被改动（P1 只出计划）
    assert (_root(registry) / "memory/2026-10-10.md").read_text(encoding="utf-8").startswith("# 2026-10-10")


# ---------- 场景 ②：单个 session 导出 ----------


def test_scenario_single_session_export(prepared):
    _, registry, calls = prepared
    _write(registry, "memory/2026-10-11-1415.md", (
        "# Session: 2026-10-11 14:15:00 Asia/Shanghai\n"
        "\n"
        "- **Session Key**: agent:alpha:main\n"
        "- **Session ID**: 11111111\n"
        "- **Source**: gateway:sessions.reset\n"
        "\n"
        "## Conversation Summary\n"
        "\n"
        'assistant: "让我检查一下。"\n'
        'assistant: "端口仪表盘已刷新：22 个端口、RSS 总 2832 MB；8420 涨到 467MB。"\n'
    ))

    plan = _plan(registry, "2026-10-11")

    assert plan.target_path == "memory/2026-10-11.md"   # 命名归并到 YYYY-MM-DD.md
    assert plan.has_standard is False
    assert plan.fragments_to_delete == ["memory/2026-10-11-1415.md"]
    assert plan.format_ok is True

    prompt = calls[-1][-1]["content"]
    # 剥壳后的高价值事实必须进 prompt
    assert "端口仪表盘已刷新" in prompt
    assert "8420 涨到 467MB" in prompt
    # 元数据壳一个都不能进「来源」段（注意预设的 style_rules 里本身会提到 Session Key 等字样，
    # 那是给模型的删除指令，所以要只看来源段）
    source_block = prompt.split("【本日来源", 1)[1]
    for shell in ("Session Key", "Session ID", "gateway:sessions.reset", "# Session:"):
        assert shell not in source_block
    # 来源标签与优先级说明在 prompt 内，但输出要求明确禁止把来源写进结果
    assert "【来源：memory/2026-10-11-1415.md（同日 session / 时间戳导出）】" in prompt
    assert "输出中不得出现任何来源说明" in prompt

    report = plan.sources[0]
    assert report.kind == "B"
    assert report.removed_total > 0                 # 剥壳计数进报告
    assert report.raw_bytes > report.clean_bytes


# ---------- 场景 ③：主文件 + 主题文件 ----------


def test_scenario_standard_plus_topic_file(prepared):
    _, registry, _ = prepared
    _write(registry, "memory/2026-10-12.md", "# 2026-10-12\n\n- 主骨架事实：日常巡检完成\n")
    _write(registry, "memory/2026-10-12-feishu-card-timeout.md", (
        "# 飞书卡片超时排查\n\n- 根因：卡片回调地址未加白名单\n- 修复：加白名单后恢复\n"))

    plan = _plan(registry, "2026-10-12")

    assert plan.has_standard is True
    assert [s.kind for s in plan.sources] == ["A", "C"]      # 优先级 A > C
    assert plan.fragments_to_delete == ["memory/2026-10-12-feishu-card-timeout.md"]
    assert plan.format_ok is True
    assert plan.sources[1].kind == "C"


# ---------- 场景 ④：同日 3 个碎片（无主骨架） ----------


def test_scenario_three_fragments_without_standard(prepared):
    _, registry, _ = prepared
    _write(registry, "memory/2026-10-13-0900.md", "# Session: 2026-10-13 09:00:00\n\n- 早间：巡检\n")
    _write(registry, "memory/2026-10-13-2200.md", "# Session: 2026-10-13 22:00:00\n\n- 晚间：加固\n")
    _write(registry, "memory/2026-10-13-weekend-summary.md", "# 汇总\n\n- 主题：周末总结\n")

    plan = _plan(registry, "2026-10-13")

    assert plan.has_standard is False
    assert sorted(plan.fragments_to_delete) == [
        "memory/2026-10-13-0900.md",
        "memory/2026-10-13-2200.md",
        "memory/2026-10-13-weekend-summary.md",
    ]
    assert len(plan.sources) == 3
    assert plan.format_ok is True
    # 强规则校验过「4 章节 + 顺序」：无违规项
    assert plan.format_report.violations == []


# ---------- 护栏：只读 / 分块摘要 / 转人工复核 ----------


def test_plan_never_writes_or_deletes(prepared):
    _, registry, _ = prepared
    b_file = _write(registry, "memory/2026-10-14-1010.md", "# Session: 2026-10-14 10:10:00\n\n- 事实 A\n")
    original = b_file.read_text(encoding="utf-8")

    plan = _plan(registry, "2026-10-14")

    assert plan.fragments_to_delete == ["memory/2026-10-14-1010.md"]
    assert b_file.exists()                                   # 碎片没被删
    assert b_file.read_text(encoding="utf-8") == original     # 内容也没被改
    assert not (_root(registry) / plan.target_path).exists()  # 目标文件没被创建


def test_oversized_source_goes_through_chunk_summary(prepared, monkeypatch):
    _, registry, calls = prepared
    # 把两个阈值都压小，避免测试里造几百 KB 的样本（阈值都在运行时读取）
    monkeypatch.setattr(daily_preprocessor, "CHUNK_THRESHOLD_BYTES", 4 * 1024)
    monkeypatch.setattr(dms, "CHUNK_TARGET_BYTES", 4 * 1024)
    body = "".join(f"- 事实 {i}：一行用于撑体积的普通内容。\n" for i in range(300))  # ≈ 12KB
    _write(registry, "memory/2026-10-15.md", "# 2026-10-15\n\n" + body)

    plan = _plan(registry, "2026-10-15")

    chunks = plan.sources[0].chunks
    assert plan.sources[0].summarized is True
    assert 2 <= chunks <= dms.MAX_CHUNKS_PER_SOURCE
    assert len(calls) == chunks + 1                    # N 次分块摘要 + 1 次归并
    assert plan.notes and "超限" in plan.notes[0] and "摘要" in plan.notes[0]
    assert plan.needs_review is True                   # 有备注即需人工留意
    assert plan.total_tokens == 150 * len(calls)       # token 全量记账（含摘要）


def test_too_many_chunks_raises_for_manual_review(prepared, monkeypatch):
    _, registry, _ = prepared
    monkeypatch.setattr(daily_preprocessor, "CHUNK_THRESHOLD_BYTES", 1024)
    monkeypatch.setattr(dms, "CHUNK_TARGET_BYTES", 1024)
    monkeypatch.setattr(dms, "MAX_CHUNKS_PER_SOURCE", 2)
    body = "".join(f"- 事实 {i}：一行用于撑体积的普通内容。\n" for i in range(300))
    _write(registry, "memory/2026-10-16.md", "# 2026-10-16\n\n" + body)

    with pytest.raises(DailySourceTooLargeError) as err:
        _plan(registry, "2026-10-16")
    assert err.value.details["path"] == "memory/2026-10-16.md"
    assert err.value.details["max_chunks"] == 2


def test_day_without_sources_raises_bad_request(prepared):
    _, registry, _ = prepared
    with pytest.raises(BadRequestError):
        _plan(registry, "2026-10-17")


# ---------- 规则投递形态（P3 效率对比） ----------
#
# 三种形态只差在「规则放哪里、放多少」，任务与来源部分必须完全一致，
# 否则测出来的差异无法归因到形态本身。


def test_delivery_default_is_system_embedded(prepared):
    """默认形态由 P3 实测定稿：规则全文进 system prompt（见 docs/M15-EFFICIENCY-REPORT.md §4）。"""
    _, registry, calls = prepared
    _write(registry, "memory/2026-10-20.md", "# 2026-10-20\n\n- 主骨架事实：巡检完成\n")

    _plan(registry, "2026-10-20")

    system, user = _messages(calls)
    assert dms.DEFAULT_DELIVERY == dms.DELIVERY_SYSTEM
    assert "你是 Soulforge 的工作日志整理助手" in system
    assert "【格式化规则（来自模板文档" in system      # 规则在 system
    assert "【格式化规则（来自模板文档" not in user     # user 侧不留规则
    assert "已在上方系统提示中给出" in user


def test_delivery_doc_full_puts_rules_in_user_prompt(prepared):
    """① 形态（对照基线）：规则与模板全文都进 user prompt。"""
    _, registry, calls = prepared
    _write(registry, "memory/2026-10-19.md", "# 2026-10-19\n\n- 主骨架事实：巡检完成\n")

    _plan(registry, "2026-10-19", dms.DELIVERY_DOC_FULL)

    system, user = _messages(calls)
    assert "【格式化规则（来自模板文档" in user
    assert "【模板文档全文" in user
    assert "schema: soulforge.template/v1" in user      # 模板全文（含 frontmatter 规则块）
    assert "你是 Soulforge 的工作日志整理助手" in system    # 基础 system 提示（无规则）


def test_delivery_trimmed_drops_b_only_rules_without_b_source(prepared):
    """A+C 日没有 session 导出：B 类专属规则（元数据删除清单 / 对话腔改写）不注入。"""
    _, registry, calls = prepared
    _write(registry, "memory/2026-10-21.md", "# 2026-10-21\n\n- 主骨架事实：巡检完成\n")
    _write(registry, "memory/2026-10-21-feishu-card-timeout.md", "# 飞书卡片超时\n\n- 根因：白名单\n")

    _plan(registry, "2026-10-21", dms.DELIVERY_TRIMMED)

    _, user = _messages(calls)
    body = user.split("【本日来源", 1)[0]
    assert "对话腔" not in body and "喵呜" not in body     # B 类专属规则被裁掉
    assert "保留：明确问题与根因" in body                    # 通用规则仍在
    assert "默认不做敏感信息脱敏" in body


def test_delivery_trimmed_keeps_b_only_rules_with_b_source(prepared):
    """存在 B 类（session 导出）来源时，B 类专属规则必须保留。"""
    _, registry, calls = prepared
    _write(registry, "memory/2026-10-22-1010.md", "# Session: 2026-10-22 10:10:00\n\n- 事实 A\n")

    _plan(registry, "2026-10-22", dms.DELIVERY_TRIMMED)

    _, user = _messages(calls)
    body = user.split("【本日来源", 1)[0]
    assert "对话腔" in body
    assert "Session Key" in body                         # 元数据删除清单也保留


def test_delivery_trimmed_uses_headings_only_skeleton(prepared):
    """裁剪形态只给章节骨架，不给模板全文（frontmatter 规则块与解释性正文都不进 prompt）。"""
    _, registry, calls = prepared
    _write(registry, "memory/2026-10-23.md", "# 2026-10-23\n\n- 主骨架事实：巡检完成\n")

    _plan(registry, "2026-10-23", dms.DELIVERY_TRIMMED)
    _, trimmed_user = _messages(calls)
    assert "【模板章节骨架" in trimmed_user
    assert "schema: soulforge.template/v1" not in trimmed_user
    assert "## 一、今日概览" in trimmed_user               # 章节标题留下
    assert "逐日归并当日全部来源" not in trimmed_user        # 模板正文说明被去掉

    calls.clear()
    _plan(registry, "2026-10-23", dms.DELIVERY_DOC_FULL)
    _, full_user = _messages(calls)
    assert len(trimmed_user) < len(full_user)            # 这就是②省 token 的来源


def test_delivery_system_embedded_moves_rules_into_system_prompt(prepared):
    """③ 形态：user prompt 里不再有规则块，规则全文进 system prompt。"""
    _, registry, calls = prepared
    _write(registry, "memory/2026-10-24.md", "# 2026-10-24\n\n- 主骨架事实：巡检完成\n")

    _plan(registry, "2026-10-24", dms.DELIVERY_SYSTEM)

    system, user = _messages(calls)
    assert "【格式化规则（来自模板文档" in system
    assert "【风格与内容规则（来自预设" in system
    assert "schema: soulforge.template/v1" in system
    assert "【格式化规则（来自模板文档" not in user
    assert "【模板文档全文" not in user
    assert "已在上方系统提示中给出" in user
    # 任务与来源部分不受形态影响（保证对比可归因）
    assert "【本日来源" in user and "只输出归并后的 Markdown 文档正文本身" in user


def test_user_prompt_task_section_identical_across_deliveries(prepared):
    """三种形态的「任务头 + 目标 + 来源 + 输出要求」必须逐字一致（差异只允许出现在规则块）。"""
    _, registry, calls = prepared
    _write(registry, "memory/2026-10-25.md", "# 2026-10-25\n\n- 主骨架事实：巡检完成\n")

    heads, tails = {}, {}
    for delivery in dms.DELIVERIES:
        calls.clear()
        _plan(registry, "2026-10-25", delivery)
        _, user = _messages(calls)
        heads[delivery] = user.split("【本次归并目标】", 1)[0]
        tails[delivery] = user.split("【附加指令】", 1)[1]

    assert len({heads[d] for d in dms.DELIVERIES}) == 1
    assert len({tails[d] for d in dms.DELIVERIES}) == 1


def test_unknown_delivery_rejected(prepared):
    _, registry, _ = prepared
    with pytest.raises(BadRequestError) as err:
        _plan(registry, "2026-10-26", "nope")
    assert err.value.details["allowed"] == list(dms.DELIVERIES)


# ---------- 「本日无可归档内容」出口（模型可决策不产出日文件） ----------
# 回归：此前 prompt 写死「第一行必须是 # 工作日志 - <date>」+ 强规则必填章节齐全，
# 模型没有合法出口，全天噪音时只能硬凑一篇。


@pytest.mark.parametrize("text,expected", [
    ("无可归档内容", ""),
    ("无可归档内容：全天只有心跳与状态轮询", "全天只有心跳与状态轮询"),
    ("**无可归档内容**：只有心跳", "只有心跳"),
    ("无可归档内容: only heartbeats", "only heartbeats"),
    ("  无可归档内容：只有心跳  \n", "只有心跳"),
    # 以下都不算空判定（保守：交给强规则按普通输出处理）
    ("", None),
    ("# 工作日志 - 2026-10-10\n\n无可归档内容：只有心跳", None),
    ("- 无可归档内容：只有心跳", None),
    ("本节提到：无可归档内容", None),
    ("无可归档内容：只有心跳\n\n补充第二行\n\n补充第三行\n\n补充第四行", None),
])
def test_parse_empty_verdict(text, expected):
    assert dms.parse_empty_verdict(text) == expected


def test_prompt_offers_empty_verdict_exit(prepared):
    """prompt 必须给出「无可归档内容」这个合法出口，并强调判定从严。"""
    _, registry, calls = prepared
    _write(registry, "memory/2026-10-11.md", "# 2026-10-11\n\n- 今天没什么事\n")

    _plan(registry, "2026-10-11")

    _, user = _messages(calls)
    assert dms.EMPTY_VERDICT in user
    assert "判定从严" in user


def test_empty_verdict_plan_has_no_output_and_only_cleans_fragments(prepared):
    """模型判定无可归档内容：不产出内容与 diff，只保留碎片清理清单。"""
    _, registry, _ = prepared
    a_file = _write(registry, "memory/2026-10-12.md", "# 2026-10-12\n\n- 只有心跳\n")
    b_file = _write(registry, "memory/2026-10-12-0930.md", "HEARTBEAT_OK\n")
    c_file = _write(registry, "memory/2026-10-12-ports.md", "- 端口正常\n")
    OUTPUT_OVERRIDE[0] = "无可归档内容：全天只有心跳与端口轮询，无任何结论"

    plan = _plan(registry, "2026-10-12")

    assert plan.is_empty is True
    assert plan.empty_reason == "全天只有心跳与端口轮询，无任何结论"
    assert plan.output_content == ""
    assert plan.unified_diff == ""
    assert plan.format_ok is True            # 没有产出文档 → 强规则不适用，不算失败
    assert plan.needs_review is False
    # 碎片只含 B/C；A 类是主文件，永不删（来源按 A > C > B 优先级排序）
    assert plan.fragments_to_delete == [
        "memory/2026-10-12-ports.md", "memory/2026-10-12-0930.md"]
    # 计划阶段仍然只读
    assert a_file.read_text(encoding="utf-8").startswith("# 2026-10-12")
    assert b_file.exists() and c_file.exists()
