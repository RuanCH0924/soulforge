import type { AgentInfo, FileInfo } from '../types';

/** CORE 类型固定优先顺序，其余按字母序 */
export const CORE_PRIORITY = ['SOUL.md', 'AGENTS.md', 'IDENTITY.md', 'USER.md', 'MEMORY.md', 'TOOLS.md'];

export interface CoreEntry {
  agentId: string;
  path: string;
}

/**
 * 由「agentId → 文件列表」缓存构建 CORE 目录（纯函数，便于测试）：
 * - coreTypes：出现过的 CORE 文件名（按优先级排序）
 * - agentsByCore：每个 CORE 文件 → 包含它的 Agent 条目
 */
export function buildCoreCatalog(cache: Record<string, FileInfo[]>): {
  coreTypes: string[];
  agentsByCore: Map<string, CoreEntry[]>;
} {
  const byCore = new Map<string, CoreEntry[]>();
  const seen = new Set<string>();
  Object.entries(cache).forEach(([agentId, files]) => {
    files
      .filter((f) => f.role === 'CORE')
      .forEach((f) => {
        if (!byCore.has(f.path)) byCore.set(f.path, []);
        byCore.get(f.path)!.push({ agentId, path: f.path });
        seen.add(f.path);
      });
  });
  const coreTypes = [...seen].sort((a, b) => {
    const ia = CORE_PRIORITY.indexOf(a);
    const ib = CORE_PRIORITY.indexOf(b);
    if (ia >= 0 && ib >= 0) return ia - ib;
    if (ia >= 0) return -1;
    if (ib >= 0) return 1;
    return a.localeCompare(b);
  });
  return { coreTypes, agentsByCore: byCore };
}

interface CoreCategoryListProps {
  coreTypes: string[];
  agentsByCore: Map<string, CoreEntry[]>;
  activeCore: string | null;
  onSelect: (type: string) => void;
}

/** 一级菜单（左栏）：CORE 分类列表 */
export function CoreCategoryList({ coreTypes, agentsByCore, activeCore, onSelect }: CoreCategoryListProps) {
  return (
    <div className="core-category-list">
      {coreTypes.length === 0 ? (
        <div className="hint" style={{ padding: '6px 10px' }}>
          暂未发现 CORE 文件
        </div>
      ) : (
        coreTypes.map((type) => {
          const count = agentsByCore.get(type)?.length ?? 0;
          return (
            <div
              key={type}
              className={`core-item${activeCore === type ? ' active' : ''}`}
              onClick={() => onSelect(type)}
              title={`${type} · 包含该文件的 Agent：${count} 个`}
            >
              <span className="core-item-name">{type}</span>
              <span className="core-item-count">{count}</span>
            </div>
          );
        })
      )}
    </div>
  );
}

interface CoreAgentListProps {
  activeCore: string | null;
  agents: AgentInfo[];
  agentsByCore: Map<string, CoreEntry[]>;
  selectedAgentId: string | null;
  selectedPath: string | null;
  onOpenFile: (agentId: string, path: string) => void;
}

/** 二级菜单（中栏）：包含「XXX.md」的 Agent 列表；点击 → 打开该 Agent 下的关联文件 */
export function CoreAgentList({
  activeCore,
  agents,
  agentsByCore,
  selectedAgentId,
  selectedPath,
  onOpenFile,
}: CoreAgentListProps) {
  const displayName = (id: string) => agents.find((a) => a.id === id)?.display_name || id;
  const entries = activeCore ? agentsByCore.get(activeCore) ?? [] : [];

  return (
    <div className="core-agent-list">
      <div className="pane-header">
        {activeCore ? `包含「${activeCore}」的 Agent` : '选择 CORE 分类'}
        <span className="pane-header-title" style={{ marginLeft: 'auto', flex: 'none' }}>
          {entries.length} 个
        </span>
      </div>
      {!activeCore ? (
        <div className="hint" style={{ padding: '8px 12px' }}>
          请先在左侧选择 CORE 分类
        </div>
      ) : entries.length === 0 ? (
        <div className="hint" style={{ padding: '8px 12px' }}>
          没有 Agent 包含该文件
        </div>
      ) : (
        entries.map((entry) => (
          <div
            key={entry.agentId}
            className={`core-agent-item${
              selectedAgentId === entry.agentId && selectedPath === entry.path ? ' selected' : ''
            }`}
            onClick={() => onOpenFile(entry.agentId, entry.path)}
            title={`打开 ${entry.agentId} 的 ${entry.path}`}
          >
            <span className="core-agent-name">{displayName(entry.agentId)}</span>
            <span className="core-agent-path">{entry.path}</span>
          </div>
        ))
      )}
    </div>
  );
}
