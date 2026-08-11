import { useEffect, useState } from 'react';
import type { FileInfo, FileRole } from '../types';
import { formatBytes } from '../utils/format';

interface FileTreeProps {
  agentId: string | null;
  files: FileInfo[];
  loading: boolean;
  selectedPath: string | null;
  showSkills: boolean;
  showMeta: boolean;
  onSelect: (path: string) => void;
}

const GROUPS: { role: FileRole; label: string }[] = [
  { role: 'CORE', label: 'CORE' },
  { role: 'MEMORY', label: 'MEMORY' },
  { role: 'SKILL', label: 'SKILL' },
  { role: 'META', label: 'META' },
  { role: 'OTHER', label: 'OTHER' },
];

export function FileTree({
  agentId,
  files,
  loading,
  selectedPath,
  showSkills,
  showMeta,
  onSelect,
}: FileTreeProps) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  // 高级开关变化时自动展开对应分组
  useEffect(() => {
    if (showSkills) setCollapsed((c) => ({ ...c, SKILL: false }));
  }, [showSkills]);
  useEffect(() => {
    if (showMeta) setCollapsed((c) => ({ ...c, META: false }));
  }, [showMeta]);

  const toggle = (role: string) => setCollapsed((c) => ({ ...c, [role]: !c[role] }));

  return (
    <>
      <div className="pane-header">{agentId ? agentId : '文件'}</div>
      <div className="file-tree">
        {loading ? (
          <div className="state-block">
            <div className="spinner-lg" />
            <div>正在加载文件...</div>
          </div>
        ) : !agentId ? (
          <div className="state-block">
            <div>在左侧选择一个 Agent</div>
          </div>
        ) : files.length === 0 ? (
          <div className="state-block">
            <div>这个 Agent 的 workspace 是空的</div>
          </div>
        ) : (
          GROUPS.filter((g) => {
            if (g.role === 'SKILL' && !showSkills) return false;
            if (g.role === 'META' && !showMeta) return false;
            return true;
          }).map((group) => {
            const groupFiles = files
              .filter((f) => f.role === group.role)
              .sort((a, b) => a.path.localeCompare(b.path));
            if (groupFiles.length === 0) return null;
            const isCollapsed = collapsed[group.role] ?? false;
            return (
              <div key={group.role} className="tree-group">
                <div
                  className={`tree-group-header${isCollapsed ? ' collapsed' : ''}`}
                  onClick={() => toggle(group.role)}
                >
                  <span className="caret">▼</span>
                  <span className={group.role === 'META' ? 'meta-warn' : ''}>
                    {group.label}
                    {group.role === 'META' && '（谨慎）'}
                  </span>
                  <span className="count">{groupFiles.length}</span>
                </div>
                {!isCollapsed &&
                  groupFiles.map((f) => (
                    <div
                      key={f.path}
                      className={`tree-file${f.path === selectedPath ? ' selected' : ''}`}
                      onClick={() => onSelect(f.path)}
                      title={f.path}
                    >
                      <span className="file-icon">M↓</span>
                      <span className={`file-name${f.role === 'CORE' ? ' core' : ''}`}>
                        {f.path}
                      </span>
                      {f.role === 'META' && <span className="meta-dot" title="META 文件，修改需谨慎" />}
                      {f.lint_warnings > 0 && (
                        <span className="warn-dot" title={`${f.lint_warnings} 条 lint 警告`} />
                      )}
                      <span className="file-size">{formatBytes(f.size_bytes)}</span>
                    </div>
                  ))}
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
