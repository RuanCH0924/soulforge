"""单元测试：8 条 lint 规则（核心规则必须有单测）。"""
from __future__ import annotations

from pathlib import Path

from app.config import Config
from app.services.lint_service import LintService


def _svc() -> LintService:
    return LintService(Config(data_dir=Path("."), openclaw_dir=Path(".")))


def _rule_ids(warnings) -> set[str]:
    return {w.rule_id for w in warnings}


def test_l4_timestamp_detected():
    svc = _svc()
    content = "# SOUL\n\n*最后更新：2026-08-06*\n## 更新记录\n- 改了一行\n"
    ws = svc.lint_file("alpha", "SOUL.md", content)
    assert "L4-TIMESTAMP" in _rule_ids(ws)
    # 行号应指向时间戳行
    ts = [w for w in ws if w.rule_id == "L4-TIMESTAMP"]
    assert any(w.line_number == 3 for w in ts)


def test_l4_version_detected():
    svc = _svc()
    content = "## v1.0\n\nSkill 版本：v2.3\n"
    ws = svc.lint_file("alpha", "SOUL.md", content)
    assert "L4-VERSION" in _rule_ids(ws)


def test_l4_narrative_detected():
    svc = _svc()
    content = "起因：上次误判事故后，我们调整了流程。\n"
    ws = svc.lint_file("alpha", "AGENTS.md", content)
    assert "L4-NARRATIVE" in _rule_ids(ws)


def test_clean_file_no_warnings():
    svc = _svc()
    content = "# SOUL\n\n原则：诚实、克制。\n"
    ws = svc.lint_file("alpha", "SOUL.md", content)
    assert ws == []


def test_boundary_violate_in_agents():
    svc = _svc()
    content = "老板偏好：周末不要打扰。\n"
    ws = svc.lint_file("alpha", "AGENTS.md", content)
    assert "BOUNDARY-VIOLATE" in _rule_ids(ws)


def test_boundary_ok_in_user():
    svc = _svc()
    content = "老板偏好：周末不要打扰。\n"
    ws = svc.lint_file("alpha", "USER.md", content)
    assert "BOUNDARY-VIOLATE" not in _rule_ids(ws)


def test_empty_file_detected():
    svc = _svc()
    ws = svc.lint_file("alpha", "EMPTY.md", "")
    assert "EMPTY-FILE" in _rule_ids(ws)
    # 占位文件不算
    ws2 = svc.lint_file("alpha", "EMPTY.md", "<!-- 占位 -->")
    assert "EMPTY-FILE" not in _rule_ids(ws2)


def test_large_file_detected():
    svc = _svc()
    content = "x" * (51 * 1024)
    ws = svc.lint_file("alpha", "BIG.md", content)
    assert "LARGE-FILE" in _rule_ids(ws)


def test_core_missing_rule():
    from app.services.lint_service import AgentContext

    svc = _svc()
    ctx = AgentContext(agent_id="beta", file_paths={"AGENTS.md"}, read=lambda p: "", all_agent_files={})
    from app.services.lint_service import CoreMissingRule

    ws = CoreMissingRule().check_agent(ctx)
    assert any(w.file_path == "SOUL.md" for w in ws)
    assert any(w.file_path == "IDENTITY.md" for w in ws)
