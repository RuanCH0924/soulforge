"""LintService：8 条 lint 规则。

规则清单（见 DEVELOPMENT.md 2.4 / ARCHITECTURE.md 3.5）：
L4-TIMESTAMP / L4-VERSION / L4-NARRATIVE / BOUNDARY-VIOLATE
CORE-MISSING / CROSS-AGENT-DRIFT / EMPTY-FILE / LARGE-FILE

lint 只警告，不自动修改。严格模式（config.lint.strict_mode）下 API 层阻止保存。
"""
from __future__ import annotations

import difflib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Config
from app.models.schemas import LintAgentResult, LintStats, LintWarning

LARGE_FILE_THRESHOLD = 50 * 1024  # 50KB
EMPTY_FILE_THRESHOLD = 10  # 字节
DRIFT_SIMILARITY_THRESHOLD = 0.30

REQUIRED_CORE_FILES = ["SOUL.md", "AGENTS.md", "IDENTITY.md", "USER.md", "MEMORY.md", "TOOLS.md"]


@dataclass
class FileContext:
    agent_id: str
    file_path: str
    content: str
    size_bytes: int


@dataclass
class AgentContext:
    agent_id: str
    file_paths: set[str]
    read: object  # Callable[[str], str]
    all_agent_files: dict[str, set[str]] = field(default_factory=dict)  # agent_id -> set(path)


def _warning(rule_id: str, rule_name: str, severity: str, ctx: FileContext | AgentContext,
             file_path: str, suggestion: str, line_number: int | None = None,
             line_content: str | None = None) -> LintWarning:
    return LintWarning(
        rule_id=rule_id, rule_name=rule_name, severity=severity,  # type: ignore[arg-type]
        agent_id=ctx.agent_id, file_path=file_path, line_number=line_number,
        line_content=line_content, suggestion=suggestion,
    )


def _find_lines(content: str, pattern: re.Pattern) -> list[tuple[int, str]]:
    """返回所有匹配的 (行号, 行内容)。"""
    hits = []
    for i, line in enumerate(content.splitlines(), start=1):
        if pattern.search(line):
            hits.append((i, line.strip()))
    return hits


class LintRule(ABC):
    rule_id: str
    rule_name: str
    severity: str = "warning"

    def check_file(self, ctx: FileContext) -> list[LintWarning]:
        return []

    def check_agent(self, ctx: AgentContext) -> list[LintWarning]:
        return []


class L4TimestampRule(LintRule):
    rule_id = "L4-TIMESTAMP"
    rule_name = "L4 反模式 — 时间戳"
    _pattern = re.compile(r"最后修订|最后更新|最后修改|##\s*更新记录|##\s*Changelog|更新日志")

    def check_file(self, ctx: FileContext) -> list[LintWarning]:
        out = []
        for lineno, line in _find_lines(ctx.content, self._pattern):
            out.append(_warning(
                self.rule_id, self.rule_name, self.severity, ctx, ctx.file_path,
                "删除该行 —— 时间戳不应进入 L4 文件（" + line + "）", lineno, line,
            ))
        return out


class L4VersionRule(LintRule):
    rule_id = "L4-VERSION"
    rule_name = "L4 反模式 — 版本号"
    _pattern = re.compile(r"##\s*v\d+\.\d+|版本[：:]\s*v?\d+\.\d+|Skill\s*版本|首次验证[：:]\s*\d{4}-\d{2}-\d{2}")

    def check_file(self, ctx: FileContext) -> list[LintWarning]:
        out = []
        for lineno, line in _find_lines(ctx.content, self._pattern):
            out.append(_warning(
                self.rule_id, self.rule_name, self.severity, ctx, ctx.file_path,
                "删除版本号/首次验证标记 —— L4 文件禁止版本叙述（" + line + "）", lineno, line,
            ))
        return out


class L4NarrativeRule(LintRule):
    rule_id = "L4-NARRATIVE"
    rule_name = "L4 反模式 — 修复叙述"
    _pattern = re.compile(r"用户(指出|反馈|提出|提醒|发现)|起因[：:]|误判事故|修复叙述|触发.*误判")

    def check_file(self, ctx: FileContext) -> list[LintWarning]:
        out = []
        for lineno, line in _find_lines(ctx.content, self._pattern):
            out.append(_warning(
                self.rule_id, self.rule_name, self.severity, ctx, ctx.file_path,
                "删除事件叙述 —— 只保留最终规则，不写「修复过程」（" + line + "）", lineno, line,
            ))
        return out


class BoundaryViolateRule(LintRule):
    """5 大文档边界违规：老板个人偏好/习惯只能进 USER.md。"""
    rule_id = "BOUNDARY-VIOLATE"
    rule_name = "5 大文档边界违规"
    _pattern = re.compile(r"老板.{0,8}(偏好|喜欢|习惯|不爱|讨厌)|(偏好|喜欢|习惯).{0,8}老板")

    def check_file(self, ctx: FileContext) -> list[LintWarning]:
        if Path(ctx.file_path).name in {"USER.md"}:
            return []
        out = []
        for lineno, line in _find_lines(ctx.content, self._pattern):
            out.append(_warning(
                self.rule_id, self.rule_name, self.severity, ctx, ctx.file_path,
                f"老板个人偏好应写入 USER.md，不应出现在 {Path(ctx.file_path).name}（" + line + "）",
                lineno, line,
            ))
        return out


class CoreMissingRule(LintRule):
    rule_id = "CORE-MISSING"
    rule_name = "CORE 必填文件缺失"
    severity = "error"

    def check_agent(self, ctx: AgentContext) -> list[LintWarning]:
        out = []
        missing = [name for name in REQUIRED_CORE_FILES if name not in ctx.file_paths]
        for name in missing:
            out.append(LintWarning(
                rule_id=self.rule_id, rule_name=self.rule_name, severity="error",
                agent_id=ctx.agent_id, file_path=name,
                suggestion=f"该 Agent 缺少 CORE 文件 {name} —— 用模板系统补全",
            ))
        return out


class CrossAgentDriftRule(LintRule):
    """跨 Agent 同名 CORE 文件相似度过低（< 30%）→ 警告。

    需要跨 Agent 读取文件，实际逻辑在 LintService._drift_rule()。
    """
    rule_id = "CROSS-AGENT-DRIFT"
    rule_name = "跨 Agent 同名文件 drift 过大"

    def check_agent(self, ctx: AgentContext) -> list[LintWarning]:
        return []


class EmptyFileRule(LintRule):
    rule_id = "EMPTY-FILE"
    rule_name = "空文件"

    def check_file(self, ctx: FileContext) -> list[LintWarning]:
        if ctx.size_bytes < EMPTY_FILE_THRESHOLD:
            placeholder = ("占位", "placeholder", "TODO")
            if not any(k in ctx.content for k in placeholder):
                return [_warning(self.rule_id, self.rule_name, self.severity, ctx, ctx.file_path,
                                 "文件近乎为空 —— 若非有意占位，请补内容或删除")]
        return []


class LargeFileRule(LintRule):
    rule_id = "LARGE-FILE"
    rule_name = "超大文件"

    def check_file(self, ctx: FileContext) -> list[LintWarning]:
        if ctx.size_bytes > LARGE_FILE_THRESHOLD:
            return [_warning(self.rule_id, self.rule_name, self.severity, ctx, ctx.file_path,
                             f"文件 {ctx.size_bytes // 1024}KB 超过 50KB —— 建议拆分")]
        return []


class LintService:
    def __init__(self, config: Config):
        self.config = config
        self.file_rules: list[LintRule] = [
            L4TimestampRule(), L4VersionRule(), L4NarrativeRule(),
            BoundaryViolateRule(), EmptyFileRule(), LargeFileRule(),
        ]
        self.agent_rules: list[LintRule] = [CoreMissingRule(), CrossAgentDriftRule()]

    def lint_file(self, agent_id: str, file_path: str, content: str, size_bytes: int | None = None) -> list[LintWarning]:
        if not self.config.lint.enabled:
            return []
        ctx = FileContext(agent_id=agent_id, file_path=file_path, content=content,
                          size_bytes=size_bytes if size_bytes is not None else len(content.encode("utf-8")))
        out: list[LintWarning] = []
        for rule in self.file_rules:
            out.extend(rule.check_file(ctx))
        return out

    def lint_agent(self, agent_id: str, file_manager) -> LintAgentResult:
        """对整个 Agent 跑 lint（含 CORE-MISSING / CROSS-AGENT-DRIFT）。"""
        files = file_manager.list(agent_id)
        warnings: list[LintWarning] = []

        def _read(path: str) -> str:
            return file_manager.read_text(agent_id, path)

        # 只取路径集合（避免全量哈希 2463 个文件）
        all_files = {a.id: set(file_manager.list_paths(a.id)) for a in file_manager.discovery.discover()}

        for f in files:
            content = _read(f.path)
            warnings.extend(self.lint_file(agent_id, f.path, content, f.size_bytes))

        ctx = AgentContext(agent_id=agent_id, file_paths={f.path for f in files},
                           read=_read, all_agent_files=all_files)
        for rule in self.agent_rules:
            warnings.extend(self._run_agent_rule(rule, ctx, file_manager))

        warnings = self._dedupe(warnings)
        stats = LintStats(
            files_checked=len(files),
            warnings=sum(1 for w in warnings if w.severity == "warning"),
            errors=sum(1 for w in warnings if w.severity == "error"),
        )
        return LintAgentResult(agent_id=agent_id, warnings=warnings, stats=stats)

    def _run_agent_rule(self, rule: LintRule, ctx: AgentContext, file_manager) -> list[LintWarning]:
        if rule.rule_id == "CORE-MISSING":
            return rule.check_agent(ctx)
        if rule.rule_id == "CROSS-AGENT-DRIFT":
            return self._drift_rule(ctx, file_manager)
        return rule.check_agent(ctx)

    def _drift_rule(self, ctx: AgentContext, file_manager) -> list[LintWarning]:
        """跨 Agent 同名 CORE 文件相似度 < 30% → 警告。"""
        out: list[LintWarning] = []
        for name in REQUIRED_CORE_FILES:
            if name not in ctx.file_paths:
                continue
            content = ctx.read(name)
            for other_agent, paths in ctx.all_agent_files.items():
                if other_agent == ctx.agent_id or name not in paths:
                    continue
                other_content = file_manager.read_text(other_agent, name)
                ratio = difflib.SequenceMatcher(None, content, other_content).ratio()
                if ratio < DRIFT_SIMILARITY_THRESHOLD:
                    out.append(LintWarning(
                        rule_id="CROSS-AGENT-DRIFT", rule_name="跨 Agent 同名文件 drift 过大",
                        severity="warning", agent_id=ctx.agent_id, file_path=name,
                        line_content=f"与 {other_agent} 的 {name} 相似度仅 {ratio:.0%}",
                        suggestion=f"同名 CORE 文件 {name} 与 {other_agent} 差异过大（{ratio:.0%}），建议同步对齐",
                    ))
        return out

    def _dedupe(self, warnings: list[LintWarning]) -> list[LintWarning]:
        seen: set[tuple] = set()
        out = []
        for w in warnings:
            key = (w.rule_id, w.file_path, w.line_number)
            if key in seen:
                continue
            seen.add(key)
            out.append(w)
        return out
