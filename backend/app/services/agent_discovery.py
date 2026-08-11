"""AgentDiscovery：读 openclaw.json 的 agents.list，自动发现 workspace 目录。

路径映射策略（解决 Linux 配置 + 本地 syncthing 镜像的场景）：
1. 配置里给的 workspace 路径本地存在 → 直接用
2. 不存在（如 /root/.openclaw/workspace-xiaowei-ops）→ 尝试 openclaw 根目录下同名子目录
3. 都不存在 → 保留原路径，扫描时跳过（目录不存在）
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config import Config
from app.models.schemas import AgentInfo

DEFAULT_WORKSPACE_NAME = "workspace"


class AgentDiscovery:
    def __init__(self, config: Config):
        self.config = config

    def _resolve_workspace(self, workspace: str | Path) -> Path:
        p = Path(workspace).expanduser()
        if not p.is_absolute():
            # 相对路径按 openclaw 根解析
            p = self.config.openclaw_dir / p
        if p.exists():
            return p.resolve()
        candidate = self.config.openclaw_dir / p.name
        if candidate.exists():
            return candidate.resolve()
        return p

    def _build(self, agent_id: str, display_name: str | None, workspace: str | Path) -> AgentInfo:
        ws = self._resolve_workspace(workspace)
        return AgentInfo(id=agent_id, workspace=str(ws), display_name=display_name or agent_id)

    def discover(self) -> list[AgentInfo]:
        """读配置 + 自动发现，返回全部 Agent（去重）。"""
        agents: dict[str, AgentInfo] = {}

        config_path = self.config.openclaw_config_file
        if config_path.exists():
            try:
                raw = json.loads(config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                raw = {}

            agents_raw = raw.get("agents", {}) or {}
            defaults_ws = (agents_raw.get("defaults", {}) or {}).get("workspace")
            for entry in agents_raw.get("list", []) or []:
                agent_id = entry.get("id", "")
                if not agent_id:
                    continue
                workspace = entry.get("workspace") or defaults_ws or self.config.openclaw_dir / DEFAULT_WORKSPACE_NAME
                agents[agent_id] = self._build(agent_id, entry.get("name"), workspace)

        # 兜底：自动发现 openclaw 根下 workspace* 目录
        root = self.config.openclaw_dir
        if root.is_dir():
            for sub in sorted(root.iterdir()):
                if not sub.is_dir() or not sub.name.startswith("workspace"):
                    continue
                agent_id = "main" if sub.name == "workspace" else sub.name.removeprefix("workspace-")
                if agent_id and agent_id not in agents:
                    agents[agent_id] = self._build(agent_id, agent_id, sub)

        return list(agents.values())

    def get(self, agent_id: str) -> AgentInfo | None:
        for a in self.discover():
            if a.id == agent_id:
                return a
        return None

    def require(self, agent_id: str) -> AgentInfo:
        agent = self.get(agent_id)
        if agent is None:
            from app.core.errors import AgentNotFoundError

            raise AgentNotFoundError(f"Agent 不存在：{agent_id}", details={"agent_id": agent_id})
        return agent
