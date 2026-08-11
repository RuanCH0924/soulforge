"""FastAPI 依赖注入：全局 Registry 的访问入口。"""
from __future__ import annotations

from app.config import Config, load_config
from app.services.registry import Registry

registry: Registry | None = None


def init_registry(config: Config | None = None) -> Registry:
    """应用启动时调用（测试可传入自己的 config）。"""
    global registry
    registry = Registry(config or load_config())
    return registry


def get_registry() -> Registry:
    if registry is None:
        raise RuntimeError("Registry 未初始化：请先调用 init_registry()")
    return registry


def get_config() -> Config:
    return get_registry().config
