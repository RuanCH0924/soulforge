"""Soulforge 应用入口：FastAPI 单进程 serve API + React 静态文件。

启动：uvicorn main:app --host 127.0.0.1 --port 8848
安全（docs/SECURITY.md）：只监听 127.0.0.1；CORS 仅本地；无外部网络调用。
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import agents, ai, audit, backups, config, diff, export_import, files, lint, llm, presets, search, stats, sync, templates
from app.core.errors import SoulforgeError
from app.core.logging import setup_logging
from app.deps import init_registry
from app.services.registry import Registry

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app(registry: Registry | None = None) -> FastAPI:
    """创建应用。测试可传入自定义 Registry（其 config 已指向临时目录）。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import app.deps as deps

        if registry is None:
            init_registry()
        else:
            deps.registry = registry  # 测试场景：全局挂载测试 registry
        setup_logging(deps.registry.config.data_dir / "logs")  # loguru：控制台 + 文件
        deps.registry.startup()
        yield

    app = FastAPI(
        title="Soulforge",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # 安全：CORS 仅本地（SECURITY 10.2）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8848", "http://127.0.0.1:8848"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 统一错误响应（SECURITY 4 / API.md 2.2）
    @app.exception_handler(SoulforgeError)
    async def soulforge_error_handler(request: Request, exc: SoulforgeError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": {"code": exc.code, "message": str(exc), "details": exc.details}},
        )

    # API 路由
    app.include_router(agents.router)
    app.include_router(files.router)
    app.include_router(search.router)
    app.include_router(diff.router)
    app.include_router(sync.router)
    app.include_router(export_import.router)
    app.include_router(backups.router)
    app.include_router(lint.router)
    app.include_router(templates.router)
    app.include_router(stats.router)
    app.include_router(audit.router)
    app.include_router(config.router)
    app.include_router(presets.router)
    app.include_router(llm.router)
    app.include_router(ai.router)

    # 健康检查（不发外部请求）
    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    # 前端静态托管（若已 build）
    if FRONTEND_DIST.is_dir():
        assets = FRONTEND_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if not FRONTEND_DIST.is_dir() or not (FRONTEND_DIST / "index.html").is_file():
            return JSONResponse(
                {"error": {"code": "FRONTEND_NOT_BUILT",
                           "message": "前端尚未构建：请先运行 cd frontend && npm run build 后再访问"}},
                status_code=503,
            )
        file = FRONTEND_DIST / path
        if path and file.is_file():
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    from app.config import load_config

    cfg = load_config()
    uvicorn.run(app, host=cfg.server.host, port=cfg.server.port, log_level="info")
