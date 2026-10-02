"""无意义日志备份归档（M15 · 大模型无意义日志自动删除）。

职责：把「被大模型判定为无意义、即将被删除」的日志在删除**之前**留存一份副本，
提供 7 天可追溯记录。不依赖系统回收站（回收站可能被清空、且跨平台行为不一致），
归档落在独立的 `<data_dir>/meaningless-log-backups/` 下，与常规写前备份（`backups/`）分离，
避免 30 天的常规备份保留策略与这里的 7 天策略互相干扰。

目录结构：

```
<data_dir>/meaningless-log-backups/
├── index.jsonl                                   # 每次归档追加一行（可追溯：谁、何时、为什么）
└── <agent_id>/<sanitized_path>/<name>.<Ymd-HMS>.bak   # 原始日志内容副本
```

设计要点：
- **删除前备份**：调用方必须先 `archive()` 成功，再 `FileManager.delete()`；
  `archive()` 抛错时不删除（宁可留文件，不可无备份地删）。
- **7 天保留**：`cleanup_old()` 删除超过 `MEANINGLESS_LOG_RETENTION_DAYS` 的归档
  与索引行；启动时执行一次，与既有备份清理同一入口（`Registry.startup()`）。
- 索引为 append-only JSONL，读时容忍坏行（损坏行跳过，不影响其余记录）。
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from app.config import Config

# 归档保留期（天）：需求明确 7 天可追溯
MEANINGLESS_LOG_RETENTION_DAYS = 7

INDEX_NAME = "index.jsonl"


@dataclass
class ArchiveEntry:
    """一次归档的记录（也是 index.jsonl 的一行）。"""

    id: int
    agent_id: str
    path: str              # Agent 相对路径，如 memory/2026-09-13-1623.md
    reason: str            # 大模型给出的删除理由
    dimension: str         # 命中的判定维度 id（见 daily_log_filter.MEANINGLESS_DIMENSIONS）
    backup_path: str       # 归档副本的绝对路径
    sha256: str
    size_bytes: int
    created_at: int


class MeaninglessLogArchive:
    """无意义日志的删除前备份归档（7 天保留）。"""

    def __init__(self, config: Config):
        self.config = config
        self.root = config.data_dir / "meaningless-log-backups"
        self.index_file = self.root / INDEX_NAME

    # ---------- 写 ----------

    def _next_id(self) -> int:
        entries = self.entries()
        return (max((e.id for e in entries), default=0)) + 1

    def _backup_path(self, agent_id: str, path: str, now: int) -> Path:
        ts = datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M%S")
        name = Path(path).name
        base = self.root / agent_id / path.replace("/", "_")
        base.mkdir(parents=True, exist_ok=True)
        candidate = base / f"{name}.{ts}.bak"
        n = 1
        while candidate.exists():  # 同秒多份（同路径重复归档）→ 追加序号
            candidate = base / f"{name}.{ts}-{n}.bak"
            n += 1
        return candidate

    def archive(self, agent_id: str, path: str, content: str, *,
                reason: str = "", dimension: str = "", now: int | None = None) -> ArchiveEntry:
        """把 `content` 写入归档副本并登记索引，返回归档记录。

        调用方必须在本方法返回后（成功）才删除源文件；本方法抛错则应放弃删除。
        """
        created = int(time.time()) if now is None else now
        backup_path = self._backup_path(agent_id, path, created)
        backup_path.write_text(content, encoding="utf-8")
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        entry = ArchiveEntry(
            id=self._next_id(), agent_id=agent_id, path=path, reason=reason,
            dimension=dimension, backup_path=str(backup_path), sha256=sha,
            size_bytes=backup_path.stat().st_size, created_at=created,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        with self.index_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        logger.info(f"无意义日志已归档：{agent_id}/{path} → {backup_path}")
        return entry

    # ---------- 读 ----------

    def entries(self, agent_id: str | None = None) -> list[ArchiveEntry]:
        """读取归档索引（按创建时间升序）；坏行跳过。"""
        if not self.index_file.is_file():
            return []
        out: list[ArchiveEntry] = []
        for line in self.index_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entry = ArchiveEntry(**data)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue  # 损坏行不影响其余记录
            if agent_id is None or entry.agent_id == agent_id:
                out.append(entry)
        out.sort(key=lambda e: (e.created_at, e.id))
        return out

    # ---------- 清理 ----------

    def cleanup_old(self, now: int | None = None) -> int:
        """删除超过保留期的归档文件与索引行，返回清理条数。"""
        current = int(time.time()) if now is None else now
        cutoff = int((datetime.fromtimestamp(current)
                      - timedelta(days=MEANINGLESS_LOG_RETENTION_DAYS)).timestamp())
        kept: list[ArchiveEntry] = []
        removed = 0
        for entry in self.entries():
            if entry.created_at >= cutoff:
                kept.append(entry)
                continue
            try:
                Path(entry.backup_path).unlink(missing_ok=True)
            except OSError:
                pass
            removed += 1
        if removed:
            self.root.mkdir(parents=True, exist_ok=True)
            self.index_file.write_text(
                "".join(json.dumps(asdict(e), ensure_ascii=False) + "\n" for e in kept),
                encoding="utf-8")
            logger.info(f"清理过期无意义日志归档：{removed} 条")
        return removed
