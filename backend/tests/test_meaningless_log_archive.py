"""单元测试：无意义日志的删除前备份归档（7 天保留）。"""
from __future__ import annotations

import json
import time
from pathlib import Path

from app.services.meaningless_log_archive import (
    MEANINGLESS_LOG_RETENTION_DAYS,
    MeaninglessLogArchive,
)

DAY = 24 * 3600


def test_retention_constant_is_seven_days():
    assert MEANINGLESS_LOG_RETENTION_DAYS == 7


def test_archive_writes_copy_and_index(config):
    arc = MeaninglessLogArchive(config)
    content = "# Session\n\n只有心跳 HEARTBEAT_OK\n"
    entry = arc.archive("alpha", "memory/2026-12-01-1415.md", content,
                        reason="只有心跳轮询", dimension="debug_noise")

    backup = Path(entry.backup_path)
    assert backup.is_file()
    assert backup.read_text(encoding="utf-8") == content     # 内容逐字留存
    assert entry.path == "memory/2026-12-01-1415.md"
    assert entry.dimension == "debug_noise"

    listed = arc.entries()
    assert [e.path for e in listed] == ["memory/2026-12-01-1415.md"]
    assert listed[0].sha256 == entry.sha256


def test_entries_filter_by_agent(config):
    arc = MeaninglessLogArchive(config)
    arc.archive("alpha", "memory/a.md", "x", dimension="empty_content")
    arc.archive("beta", "memory/b.md", "y", dimension="empty_content")
    assert [e.path for e in arc.entries("alpha")] == ["memory/a.md"]
    assert [e.path for e in arc.entries("beta")] == ["memory/b.md"]
    assert len(arc.entries()) == 2


def test_same_second_same_path_gets_unique_files(config):
    arc = MeaninglessLogArchive(config)
    now = int(time.time())
    first = arc.archive("alpha", "memory/a.md", "1", dimension="empty_content", now=now)
    second = arc.archive("alpha", "memory/a.md", "2", dimension="empty_content", now=now)
    assert first.backup_path != second.backup_path
    assert Path(first.backup_path).read_text(encoding="utf-8") == "1"
    assert Path(second.backup_path).read_text(encoding="utf-8") == "2"


def test_cleanup_old_removes_expired_keeps_recent(config):
    arc = MeaninglessLogArchive(config)
    now = int(time.time())
    old = arc.archive("alpha", "memory/old.md", "old",
                      dimension="empty_content", now=now - 8 * DAY)
    fresh = arc.archive("alpha", "memory/fresh.md", "fresh",
                        dimension="empty_content", now=now - 1 * DAY)

    removed = arc.cleanup_old(now=now)
    assert removed == 1
    assert not Path(old.backup_path).exists()               # 超过 7 天 → 删除
    assert Path(fresh.backup_path).exists()                 # 1 天内 → 保留
    assert [e.path for e in arc.entries()] == ["memory/fresh.md"]


def test_cleanup_keeps_exactly_at_boundary(config):
    arc = MeaninglessLogArchive(config)
    now = int(time.time())
    edge = arc.archive("alpha", "memory/edge.md", "edge",
                       dimension="empty_content", now=now - MEANINGLESS_LOG_RETENTION_DAYS * DAY)
    assert arc.cleanup_old(now=now) == 0                    # 恰好 7 天 → 仍在保留窗口内
    assert Path(edge.backup_path).exists()


def test_corrupted_index_line_is_tolerated(config):
    arc = MeaninglessLogArchive(config)
    arc.archive("alpha", "memory/a.md", "a", dimension="empty_content")
    with arc.index_file.open("a", encoding="utf-8") as f:
        f.write("{ this is not json }\n")
    arc.archive("alpha", "memory/b.md", "b", dimension="empty_content")
    assert [e.path for e in arc.entries()] == ["memory/a.md", "memory/b.md"]


def test_cleanup_noop_when_index_missing(config):
    arc = MeaninglessLogArchive(config)
    assert arc.cleanup_old() == 0
    assert arc.entries() == []


def test_index_is_jsonl(config):
    arc = MeaninglessLogArchive(config)
    arc.archive("alpha", "memory/a.md", "a", dimension="empty_content")
    lines = [ln for ln in arc.index_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["path"] == "memory/a.md"
