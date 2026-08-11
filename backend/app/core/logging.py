"""日志：loguru 统一格式（DEVELOPMENT.md 开发风格约束）。

控制台 + 文件双输出；文件按天滚动，保留 14 天。
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    """配置 loguru：控制台 + 文件（{data_dir}/logs/soulforge-YYYYMMDD.log）。"""
    logger.remove()
    logger.add(sys.stderr, level=level, format=_FORMAT, colorize=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "soulforge-{time:YYYYMMDD}.log",
        level=level,
        format=_FORMAT,
        rotation="10 MB",
        retention="14 days",
        encoding="utf-8",
        enqueue=True,
    )
