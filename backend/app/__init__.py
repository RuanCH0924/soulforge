"""Soulforge 后端入口包。

`__version__` 是**全项目版本号的唯一事实源**（single source of truth）：
- HTTP 响应：`app/api/common.py` 的响应包装 `meta.version`（经 `schemas.Meta` 引用本值）；
- OpenAPI 文档：`backend/main.py` 的 `FastAPI(version=...)`；
- 健康检查：`GET /api/health` 的 `version` 字段（前端状态栏据此显示）；
- 导出包：`MANIFEST.json` 的 `soulforge_version`；
- 包元数据与前端：`backend/pyproject.toml` 的 `project.version` 与
  `frontend/package.json` 的 `version` 为静态字段（无法动态读取），必须手工保持一致，
  由 `backend/tests/test_version.py` 自动校验防漂移。

发版流程（详见根目录 CHANGELOG.md）：改本值 → 同步 pyproject.toml / package.json
→ 在 CHANGELOG 追加条目 → 打 git tag `v<版本>` → 跑 `pytest` 确认版本校验通过。
"""

__version__ = "0.5.0"
