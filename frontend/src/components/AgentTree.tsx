import type { AgentInfo } from '../types';

interface AgentTreeProps {
  agents: AgentInfo[];
  loading: boolean;
  selectedAgentId: string | null;
  warningCounts: Record<string, number>;
  onSelect: (agentId: string) => void;
  onRefresh: () => void;
}

export function AgentTree({
  agents,
  loading,
  selectedAgentId,
  warningCounts,
  onSelect,
  onRefresh,
}: AgentTreeProps) {
  return (
    <>
      <div className="agent-tree">
        {loading ? (
          <div className="state-block">
            <div className="spinner-lg" />
            <div>正在发现 Agent...</div>
          </div>
        ) : agents.length === 0 ? (
          <div className="state-block">
            <div>未找到任何 Agent，请检查 openclaw.json 配置</div>
            <button className="btn btn-primary" onClick={onRefresh}>
              重新扫描
            </button>
          </div>
        ) : (
          agents.map((agent) => {
            const warn = warningCounts[agent.id] ?? 0;
            return (
              <div
                key={agent.id}
                className={`agent-node${agent.id === selectedAgentId ? ' selected' : ''}`}
                onClick={() => onSelect(agent.id)}
                title={`${agent.id}\n${agent.workspace}`}
              >
                <span className="agent-icon">{agent.id.charAt(0).toUpperCase()}</span>
                <span className="agent-name">{agent.display_name || agent.id}</span>
                <span className="agent-meta">
                  {warn > 0 && (
                    <span className="badge-warn" title={`${warn} 条 lint 警告`}>
                      {warn}
                    </span>
                  )}
                  <span>{agent.file_count}</span>
                </span>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
