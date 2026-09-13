import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react';
import type { FileInfo, FileRole } from '../types';
import { isRoleVisible } from '../hooks/useSettings';
import { formatBytes } from '../utils/format';

interface FileTreeProps {
  agentId: string | null;
  files: FileInfo[];
  loading: boolean;
  selectedPath: string | null;
  showSkills: boolean;
  showMeta: boolean;
  showMemory: boolean;
  showOther: boolean;
  onSelect: (path: string) => void;
  /** 新建文档 */
  onCreate: () => void;
  /** 删除文档 */
  onDelete: (path: string) => void;
}

const GROUPS: { role: FileRole; label: string }[] = [
  { role: 'CORE', label: 'CORE' },
  { role: 'MEMORY', label: 'MEMORY' },
  { role: 'SKILL', label: 'SKILL' },
  { role: 'META', label: 'META' },
  { role: 'OTHER', label: 'OTHER' },
];

const COLLAPSED_KEY = 'soulforge.filetree.collapsed';
const WARN_ONLY_KEY = 'soulforge.filetree.warnOnly';

/** 分组折叠状态持久化（跨 Agent 共享，切 Agent 不再重置） */
function loadCollapsed(): Record<string, boolean> {
  try {
    const raw = window.localStorage.getItem(COLLAPSED_KEY);
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

export function FileTree({
  agentId,
  files,
  loading,
  selectedPath,
  showSkills,
  showMeta,
  showMemory,
  showOther,
  onSelect,
  onCreate,
  onDelete,
}: FileTreeProps) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(loadCollapsed);
  const [filter, setFilter] = useState('');
  const [warnOnly, setWarnOnly] = useState(() => {
    try {
      return window.localStorage.getItem(WARN_ONLY_KEY) === '1';
    } catch {
      return false;
    }
  });
  const [kbIndex, setKbIndex] = useState(-1);
  const listRef = useRef<HTMLDivElement | null>(null);

  // 高级开关变化时自动展开对应分组
  useEffect(() => {
    if (showSkills) setCollapsed((c) => ({ ...c, SKILL: false }));
  }, [showSkills]);
  useEffect(() => {
    if (showMeta) setCollapsed((c) => ({ ...c, META: false }));
  }, [showMeta]);

  const toggle = useCallback((role: string) => {
    setCollapsed((c) => {
      const next = { ...c, [role]: !c[role] };
      try {
        window.localStorage.setItem(COLLAPSED_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const toggleWarnOnly = useCallback(() => {
    setWarnOnly((v) => {
      try {
        window.localStorage.setItem(WARN_ONLY_KEY, v ? '0' : '1');
      } catch {
        // ignore
      }
      return !v;
    });
  }, []);

  const q = filter.trim().toLowerCase();

  // 可见的扁平文件列表（顺序与渲染一致），供键盘导航使用
  const { groups, flatPaths } = useMemo(() => {
    const gs: { role: FileRole; label: string; items: FileInfo[] }[] = [];
    const flat: string[] = [];
    if (agentId && files.length > 0) {
      GROUPS.filter((g) => isRoleVisible(g.role, { showSkills, showMeta, showMemory, showOther })).forEach(
        (group) => {
          const items = files
            .filter((f) => f.role === group.role)
            .filter((f) => (warnOnly ? f.lint_warnings > 0 : true))
            .filter((f) => (q ? f.path.toLowerCase().includes(q) : true))
            .sort((a, b) => a.path.localeCompare(b.path));
          if (items.length === 0) return;
          const isCollapsed = collapsed[group.role] ?? false;
          gs.push({ role: group.role, label: group.label, items: isCollapsed ? [] : items });
          if (!isCollapsed) items.forEach((f) => flat.push(f.path));
        },
      );
    }
    return { groups: gs, flatPaths: flat };
  }, [agentId, files, collapsed, q, warnOnly, showSkills, showMeta, showMemory, showOther]);

  // 过滤结果变化时重置键盘选中
  useEffect(() => {
    setKbIndex(-1);
  }, [q, warnOnly, agentId]);

  // 键盘选中项滚动到可视区
  useEffect(() => {
    if (kbIndex < 0) return;
    listRef.current?.querySelector('.kb-active')?.scrollIntoView({ block: 'nearest' });
  }, [kbIndex]);

  const onKeyDown = (e: ReactKeyboardEvent) => {
    if (flatPaths.length === 0) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const dir = e.key === 'ArrowDown' ? 1 : -1;
      const start = kbIndex < 0 ? (dir > 0 ? -1 : 0) : kbIndex;
      let next = start + dir;
      if (next < 0) next = flatPaths.length - 1;
      if (next >= flatPaths.length) next = 0;
      setKbIndex(next);
      onSelect(flatPaths[next]);
    } else if (e.key === 'Enter' && kbIndex >= 0) {
      e.preventDefault();
      onSelect(flatPaths[kbIndex]);
    } else if (e.key === 'Escape') {
      setFilter('');
      setKbIndex(-1);
    }
  };

  const hasFiles = agentId && files.length > 0;

  return (
    <>
      <div className="pane-header">
        <span className="pane-header-title">{agentId ? agentId : '文件'}</span>
        {agentId && (
          <span className="filetree-tools">
            <button type="button" className="tree-tool" onClick={onCreate} title="新建文档">
              ＋ 新建
            </button>
            <button
              type="button"
              className="tree-tool"
              disabled={!selectedPath}
              onClick={() => selectedPath && onDelete(selectedPath)}
              title={selectedPath ? `删除 ${selectedPath}（移入回收站）` : '先在下方选择一个文件'}
            >
              删除
            </button>
          </span>
        )}
      </div>

      {hasFiles && (
        <div className="filetree-filter">
          <input
            className="filter-input"
            placeholder="过滤文件…（Esc 清空）"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <button
            type="button"
            className={`tree-tool${warnOnly ? ' active' : ''}`}
            onClick={toggleWarnOnly}
            title="仅显示存在 lint 警告的文件"
          >
            仅警告
          </button>
        </div>
      )}

      <div className="file-tree" ref={listRef} tabIndex={hasFiles ? 0 : -1} onKeyDown={onKeyDown}>
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
        ) : groups.length === 0 ? (
          <div className="state-block">
            <div>{warnOnly ? '没有存在警告的文件' : `没有匹配「${filter}」的文件`}</div>
          </div>
        ) : (
          groups.map((group) => {
            const roleFiles = files.filter((f) => f.role === group.role);
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
                  <span className="count">{group.items.length || roleFiles.length}</span>
                </div>
                {group.items.map((f) => (
                  <div
                    key={f.path}
                    className={`tree-file${f.path === selectedPath ? ' selected' : ''}${
                      flatPaths[kbIndex] === f.path ? ' kb-active' : ''
                    }`}
                    onClick={() => onSelect(f.path)}
                    title={f.path}
                  >
                    <span className="file-icon">M↓</span>
                    <span className={`file-name${f.role === 'CORE' ? ' core' : ''}`}>
                      {highlight(f.path, q)}
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

/** 过滤命中片段高亮 */
function highlight(path: string, q: string): ReactNode {
  if (!q) return path;
  const idx = path.toLowerCase().indexOf(q);
  if (idx < 0) return path;
  return (
    <>
      {path.slice(0, idx)}
      <mark className="filter-hit">{path.slice(idx, idx + q.length)}</mark>
      {path.slice(idx + q.length)}
    </>
  );
}
