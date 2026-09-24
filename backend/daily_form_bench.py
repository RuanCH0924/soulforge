"""M15 效率对比台（P3）：同一批真实样本 × 三种规则投递形态 × N 次重复。

用法（在 backend 目录下）：

    .venv/Scripts/python.exe daily_form_bench.py                 # 默认 3 次重复
    .venv/Scripts/python.exe daily_form_bench.py --repeats 3 --out ..\\docs\\bench.json

**只读**：真实 workspace 只被读取；真实 `index.db` 会被复制到沙箱目录后再用（形态对比不会
写任何 workspace 文件、也不改真实库）。每跑一次真实 LLM 都会产生费用，`--token-budget`
是硬中止线（越线立即停，不把预算打满）。

结论与报告见 [docs/M15-EFFICIENCY-REPORT.md](../docs/M15-EFFICIENCY-REPORT.md)。
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import difflib
import json
import os
import shutil
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import load_config  # noqa: E402
from app.models.schemas import PresetUpdate  # noqa: E402
from app.services import daily_merge_service as dms  # noqa: E402
from app.services.llm_registry import LLMClient  # noqa: E402
from app.services.registry import Registry  # noqa: E402

PRESET_ID = "preset-wlog-daily-std"

# 样本日：刻意覆盖三种来源构成（方案 §7.2「同一样本集」）
SAMPLE_DAYS: list[tuple[str, str]] = [
    ("main", "2026-07-03"),   # A+B：主骨架 + 一个 session 导出
    ("main", "2026-07-14"),   # B  ：纯 session 导出（单来源质量差）
    ("main", "2026-07-06"),   # A+C：主骨架 + 主题文件
]
# 真实工作量：132 天需要整理（2026-09-24 实测），用于把单日耗时外推成整月耗时
REAL_WORKLOAD_DAYS = 132


@dataclasses.dataclass
class Call:
    delivery: str
    agent: str
    date: str
    repeat: int
    seconds: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_estimate_usd: float
    system_bytes: int
    user_bytes: int
    format_ok: bool
    violations: int
    lint_warnings: int
    notes: int
    output_sha256: str
    output: str
    violation_details: list[str] = dataclasses.field(default_factory=list)
    lint_details: list[str] = dataclasses.field(default_factory=list)
    error: str | None = None


class Budget:
    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    def add(self, tokens: int) -> None:
        self.used += tokens

    @property
    def exhausted(self) -> bool:
        return self.limit > 0 and self.used >= self.limit


def _prepare_sandbox() -> tuple[object, Path]:
    """把真实 data_dir 复制到沙箱（密钥在内），ws 只读指向真实 OpenClaw 根。"""
    real = load_config()
    sandbox = Path(os.environ.get("TEMP", "/tmp")) / "sf-p3-bench" / "data"
    if sandbox.exists():
        shutil.rmtree(sandbox)
    sandbox.mkdir(parents=True)
    shutil.copy2(real.data_dir / "index.db", sandbox / "index.db")
    shutil.copy2(real.data_dir / "config.toml", sandbox / "config.toml")
    (sandbox / "secrets").mkdir()
    shutil.copy2(real.data_dir / "secrets" / "key", sandbox / "secrets" / "key")
    return dataclasses.replace(real, data_dir=sandbox), sandbox


def _pairwise_similarity(outputs: list[str]) -> tuple[float, float]:
    """同一样本重复 N 次输出的两两相似度均值与方差（1.0 = 完全一致）。"""
    if len(outputs) < 2:
        return 1.0, 0.0
    scores = [
        difflib.SequenceMatcher(None, outputs[i], outputs[j]).ratio()
        for i in range(len(outputs)) for j in range(i + 1, len(outputs))
    ]
    return statistics.fmean(scores), (statistics.pvariance(scores) if len(scores) > 1 else 0.0)


async def bench(reg: Registry, provider_id: str, repeats: int, budget: Budget,
                day_filter: set[tuple[str, str]] | None = None,
                deliveries_filter: set[str] | None = None) -> list[Call]:
    calls: list[Call] = []
    sizes: list[tuple[int, int]] = []        # (system 字节, user 字节)
    original_chat = LLMClient.chat

    async def sized_chat(self, messages, max_tokens=None, temperature=None):
        resp = await original_chat(self, messages, max_tokens, temperature)
        sizes.append((len(messages[0]["content"].encode("utf-8")),
                      len(messages[-1]["content"].encode("utf-8"))))
        return resp

    LLMClient.chat = sized_chat  # type: ignore[method-assign]
    try:
        for delivery in dms.DELIVERIES:
            for agent, date in SAMPLE_DAYS:
                for repeat in range(1, repeats + 1):
                    if budget.exhausted:
                        print(f"!! token 预算用尽（{budget.used}），提前结束")
                        return calls
                    sizes.clear()
                    if deliveries_filter and delivery not in deliveries_filter:
                        continue
                    if day_filter and (agent, date) not in day_filter:
                        continue
                    label = f"{delivery:16s} {agent}/{date} #{repeat}"
                    started = time.perf_counter()
                    try:
                        plan = await reg.daily_merge.plan_day(
                            agent, date, PRESET_ID, provider_id, delivery=delivery)
                    except Exception as exc:  # 单次失败不影响整轮对比
                        print(f"{label}  FAILED: {exc}")
                        calls.append(Call(delivery, agent, date, repeat, 0, 0, 0, 0, 0.0,
                                          0, 0, False, 0, 0, 0, "", "", error=str(exc)))
                        continue
                    seconds = time.perf_counter() - started
                    system_bytes, user_bytes = sizes[-1] if sizes else (0, 0)
                    violations = [f"{v.rule_id} L{v.line}: {v.message}"
                                  for v in plan.format_report.violations]
                    lint = [f"{w.rule_id} {w.rule_name}: {w.suggestion}" for w in plan.lint_warnings]
                    calls.append(Call(
                        delivery=delivery, agent=agent, date=date, repeat=repeat,
                        seconds=seconds, prompt_tokens=plan.prompt_tokens,
                        completion_tokens=plan.completion_tokens, total_tokens=plan.total_tokens,
                        cost_estimate_usd=plan.cost_estimate_usd,
                        system_bytes=system_bytes, user_bytes=user_bytes,
                        format_ok=plan.format_report.ok,
                        violations=len(violations), lint_warnings=len(lint), notes=len(plan.notes),
                        output_sha256=dms.sha256_text(plan.output_content),
                        output=plan.output_content,
                        violation_details=violations, lint_details=lint,
                    ))
                    budget.add(plan.total_tokens)
                    print(f"{label}  {seconds:5.1f}s  prompt={plan.prompt_tokens:5d} "
                          f"completion={plan.completion_tokens:5d}  ok={plan.format_report.ok}  "
                          f"累计={budget.used}")
                    for row in violations[:4]:
                        print(f"      ! {row}")
                    for row in lint[:2]:
                        print(f"      ~ {row}")
    finally:
        LLMClient.chat = original_chat  # type: ignore[method-assign]
    return calls


async def rule_change_probe(reg: Registry) -> dict:
    """「改一条规则后的生效成本」：改预设 → 下一次调用即生效（不重启、不发版）。"""
    preset = reg.presets.get(PRESET_ID)
    original = list(preset.style_rules)
    marker = "【BENCH 临时规则】本条仅用于测量规则改动的生效延迟"
    try:
        reg.presets.update(PRESET_ID, PresetUpdate(style_rules=[*original, marker]))
        seen_before = marker in _user_prompt_of(reg, PRESET_ID)
        reg.presets.update(PRESET_ID, PresetUpdate(style_rules=original))
        seen_after = marker in _user_prompt_of(reg, PRESET_ID)
    finally:
        current = reg.presets.get(PRESET_ID)
        if current.style_rules != original:
            reg.presets.update(PRESET_ID, PresetUpdate(style_rules=original))
    return {
        "applied_immediately": seen_before,      # 改完立刻可见 → 无需重启
        "reverted_immediately": not seen_after,  # 改回也立刻生效
        "needs_restart": not seen_before,
        "needs_release": False,                  # 预设存 DB，不走发版
        "note": "预设与 style_rules 存 DB，进程内每次调用现读；只有改代码/改阈值常量才需要发版",
    }


def _user_prompt_of(reg: Registry, preset_id: str) -> str:
    preset = reg.presets.get(preset_id)
    group = reg.daily_scanner.day("main", "2026-07-03")
    prepared = [(s, type("P", (), {"text": "", "summarized": False})()) for s in group.sources]
    _, user = reg.daily_merge._build_prompts(preset, group, prepared, None)
    return user


def summarize(calls: list[Call], repeats: int) -> dict:
    ok_calls = [c for c in calls if c.error is None]
    by_delivery: dict[str, dict] = {}
    for delivery in dms.DELIVERIES:
        group = [c for c in ok_calls if c.delivery == delivery]
        if not group:
            by_delivery[delivery] = {"calls": 0}
            continue
        per_day_sim, per_day_dev = [], []
        for _, date in SAMPLE_DAYS:
            outputs = [c.output for c in group if c.date == date]
            mean_sim, var = _pairwise_similarity(outputs)
            per_day_sim.append(mean_sim)
            per_day_dev.append(var)
        by_delivery[delivery] = {
            "calls": len(group),
            "prompt_tokens_avg": round(statistics.fmean(c.prompt_tokens for c in group)),
            "completion_tokens_avg": round(statistics.fmean(c.completion_tokens for c in group)),
            "total_tokens_avg": round(statistics.fmean(c.total_tokens for c in group)),
            "system_bytes_avg": round(statistics.fmean(c.system_bytes for c in group)),
            "user_bytes_avg": round(statistics.fmean(c.user_bytes for c in group)),
            "seconds_avg": round(statistics.fmean(c.seconds for c in group), 2),
            "seconds_total": round(sum(c.seconds for c in group), 2),
            "cost_estimate_avg": round(statistics.fmean(c.cost_estimate_usd for c in group), 6),
            "format_ok_rate": round(sum(1 for c in group if c.format_ok) / len(group), 3),
            "lint_warnings_avg": round(statistics.fmean(c.lint_warnings for c in group), 2),
            "similarity_mean": round(statistics.fmean(per_day_sim), 4),
            "similarity_variance_avg": round(statistics.fmean(per_day_dev), 6),
            "distinct_outputs": len({c.output_sha256 for c in group}),
        }
    total_seconds = sum(c.seconds for c in ok_calls)
    mean_day_seconds = total_seconds / len(ok_calls) if ok_calls else 0.0
    return {
        "repeats": repeats,
        "calls": len(calls),
        "failed_calls": len(calls) - len(ok_calls),
        "tokens_used": sum(c.total_tokens for c in calls),
        "cost_estimate_usd": round(sum(c.cost_estimate_usd for c in calls), 4),
        "by_delivery": by_delivery,
        "extrapolation": {
            "real_workload_days": REAL_WORKLOAD_DAYS,
            "mean_seconds_per_day": round(mean_day_seconds, 2),
            "month_minutes_per_form": {
                d: round(by_delivery[d]["seconds_avg"] * REAL_WORKLOAD_DAYS / 60, 1)
                for d in dms.DELIVERIES if by_delivery[d].get("calls")
            },
            "note": "按「逐日串行生成」外推；批次日归并是串行的，未计入并发",
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="M15 三种规则投递形态效率对比")
    parser.add_argument("--repeats", type=int, default=3, help="每个样本重复次数")
    parser.add_argument("--token-budget", type=int, default=400_000, help="总 token 硬中止线")
    parser.add_argument("--out", type=Path, default=None, help="结果 JSON 落盘路径")
    parser.add_argument("--days", default="", help="只跑这些样本日（1-based 下标，逗号分隔；空 = 全部）")
    parser.add_argument("--forms", default="", help="只跑这些形态（逗号分隔；空 = 全部）")
    args = parser.parse_args()

    day_filter = ({(SAMPLE_DAYS[int(i) - 1][0], SAMPLE_DAYS[int(i) - 1][1])
                   for i in args.days.split(",") if i.strip()}
                  if args.days.strip() else None)
    deliveries_filter = ({f.strip() for f in args.forms.split(",") if f.strip()}
                         if args.forms.strip() else None)

    config, sandbox = _prepare_sandbox()
    print(f"沙箱 data_dir = {sandbox}")
    print(f"真实 workspace = {config.openclaw_dir}")
    reg = Registry(config)
    reg.startup()

    enabled = [p for p in reg.llm._providers.values() if p.enabled]
    if not enabled:
        raise SystemExit("没有启用中的 LLM Provider，无法对比——请先在应用里配置一个")
    provider_id = enabled[0].id
    print(f"provider = {provider_id}（{enabled[0].model}）")

    budget = Budget(args.token_budget)
    print(f"样本 {len(SAMPLE_DAYS)} 天 × 形态 {len(dms.DELIVERIES)} 种 × 重复 {args.repeats} 次 "
          f"= {len(SAMPLE_DAYS) * len(dms.DELIVERIES) * args.repeats} 次调用；"
          f"token 预算 {args.token_budget}")

    calls = await bench(reg, provider_id, args.repeats, budget, day_filter, deliveries_filter)
    report = summarize(calls, args.repeats)
    report["rule_change_probe"] = await rule_change_probe(reg)
    report["sample_days"] = [{"agent": a, "date": d} for a, d in SAMPLE_DAYS]
    report["provider"] = provider_id
    report["preset"] = PRESET_ID
    report["generated_at"] = int(time.time())

    if args.out:
        args.out.write_text(json.dumps(
            {"summary": report, "calls": [dataclasses.asdict(c) for c in calls]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n原始明细已写入 {args.out}")

    print("\n" + "=" * 78)
    print(json.dumps(report, ensure_ascii=False, indent=2))


asyncio.run(main())
