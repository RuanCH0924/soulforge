import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react';
import type { FileInfo, FileRole } from '../types';
import { isRoleVisible } from '../hooks/useSettings';
import { formatBytes } from '../utils/format';
import { PaneTools } from './PaneTools';

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

/**
 * 组内的目录树：把同一 role 的文件按「目录 → 文件」组织，供文件树折叠渲染。
 * 目的：memory/ 下存在多级子目录（memory/dreaming/rem/*.md、memory/<主题>/*.md），
 * 这些目录必须在 MEMORY 组里看得见，而不是把路径拍平成一行行。
 */
interface DirNode {
  /** 目录名（根节点为空，不代表可视行） */
  name: string;
  /** 该目录的完整相对路径（根为容器前缀，如 'memory/'），兼作折叠状态与 React key */
  path: string;
  dirs: DirNode[];
  files: FileInfo[];
}

/** 各组在 workspace 里的容器前缀；CORE / OTHER 是散落文件，没有统一容器 */
const GROUP_ROOT: Partial<Record<FileRole, string>> = {
  MEMORY: 'memory/',
  SKILL: 'skills/',
};

function buildDirTree(items: FileInfo[], rootPrefix: string): DirNode {
  const root: DirNode = { name: '', path: rootPrefix, dirs: [], files: [] };
  const byPath = new Map<string, DirNode>([[rootPrefix, root]]);

  for (const f of items) {
    const rel = rootPrefix && f.path.startsWith(rootPrefix) ? f.path.slice(rootPrefix.length) : f.path;
    const segs = rel.split('/');
    segs.pop(); // 去掉文件名，剩下的才是目录层级
    let node = root;
    let acc = rootPrefix;
    for (const seg of segs) {
      acc = `${acc}${seg}/`;
      let child = byPath.get(acc);
      if (!child) {
        child = { name: seg, path: acc, dirs: [], files: [] };
        byPath.set(acc, child);
        node.dirs.push(child);
      }
      node = child;
    }
    node.files.push(f);
  }

  const sortNode = (n: DirNode) => {
    n.dirs.sort((a, b) => a.name.localeCompare(b.name));
    n.files.sort((a, b) => a.path.localeCompare(b.path));
    n.dirs.forEach(sortNode);
  };
  sortNode(root);
  return root;
}

/** 目录下的文件总数（含更深层），用于目录行的计数 */
function countFiles(node: DirNode): number {
  return node.files.length + node.dirs.reduce((n, d) => n + countFiles(d), 0);
}

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
  /** 子目录折叠状态（按目录完整路径记录）；默认折叠，避免 memory/ 下上百个文件一屏铺满 */
  const [dirCollapsed, setDirCollapsed] = useState<Record<string, boolean>>({});
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
  // 过滤时强制展开目录：否则命中项会藏在默认折叠的子目录里，看起来像「没查到」
  const filterActive = q.length > 0;
  /** 目录默认折叠（memory/ 下可能有上百个文件），过滤时一律展开 */
  const isDirCollapsed = useCallback(
    (path: string) => !filterActive && (dirCollapsed[path] ?? true),
    [filterActive, dirCollapsed],
  );

  /** 子目录展开 / 收起（默认折叠，所以取反时按「未记录 = 折叠」判断） */
  const toggleDir = useCallback((path: string) => {
    setDirCollapsed((c) => ({ ...c, [path]: !(c[path] ?? true) }));
  }, []);

  // 可见的扁平文件列表（顺序与渲染一致），供键盘导航使用
  const { groups, flatPaths } = useMemo(() => {
    const gs: { role: FileRole; label: string; items: FileInfo[]; tree: DirNode | null }[] = [];
    const flat: string[] = [];
    // 与渲染同序：先递归子目录，再本级文件
    const walk = (node: DirNode) => {
      node.dirs.forEach((d) => {
        if (isDirCollapsed(d.path)) return;
        walk(d);
      });
      node.files.forEach((f) => flat.push(f.path));
    };
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
          if (isCollapsed) {
            gs.push({ role: group.role, label: group.label, items: [], tree: null });
            return;
          }
          const tree = buildDirTree(items, GROUP_ROOT[group.role] ?? '');
          gs.push({ role: group.role, label: group.label, items, tree });
          walk(tree);
        },
      );
    }
    return { groups: gs, flatPaths: flat };
  }, [
    agentId,
    files,
    collapsed,
    q,
    warnOnly,
    showSkills,
    showMeta,
    showMemory,
    showOther,
    isDirCollapsed,
  ]);

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

  /** 递归渲染组内的目录 / 文件行（深度决定缩进；与 flatPaths 保持同序） */
  const renderTree = (node: DirNode, depth: number): ReactNode[] => {
    const rows: ReactNode[] = [];
    node.dirs.forEach((d) => {
      const collapsedDir = isDirCollapsed(d.path);
      rows.push(
        <div
          key={d.path}
          className={`tree-dir${collapsedDir ? ' collapsed' : ''}`}
          style={{ paddingLeft: 10 + depth * 12 }}
          onClick={() => toggleDir(d.path)}
          title={d.path}
        >
          <span className="caret">▼</span>
          <span className="tree-dir-name">{d.name}</span>
          <span className="count">{countFiles(d)}</span>
        </div>,
      );
      if (!collapsedDir) rows.push(...renderTree(d, depth + 1));
    });
    node.files.forEach((f) => {
      // 行内只显示「相对当前目录」的文件名（前缀已由目录层级表达），完整路径放在 title
      const label = node.path && f.path.startsWith(node.path) ? f.path.slice(node.path.length) : f.path;
      rows.push(
        <div
          key={f.path}
          className={`tree-file${f.path === selectedPath ? ' selected' : ''}${
            flatPaths[kbIndex] === f.path ? ' kb-active' : ''
          }`}
          style={{ paddingLeft: 22 + depth * 12 }}
          onClick={() => onSelect(f.path)}
          title={f.path}
        >
          <span className="file-icon">M↓</span>
          <span className={`file-name${f.role === 'CORE' ? ' core' : ''}`}>{highlight(label, q)}</span>
          {f.role === 'META' && <span className="meta-dot" title="META 文件，修改需谨慎" />}
          {f.lint_warnings > 0 && (
            <span className="warn-dot" title={`${f.lint_warnings} 条 lint 警告`} />
          )}
          <span className="file-size">{formatBytes(f.size_bytes)}</span>
        </div>,
      );
    });
    return rows;
  };

  return (
    <>
      <div className="pane-header">
        <span className="pane-header-title">{agentId ? agentId : '文件'}</span>
        {agentId && (
          <PaneTools
            onCreate={onCreate}
            createHint="新建文档（文件名可含子目录，如 notes/周报.md）"
            onDelete={selectedPath ? () => onDelete(selectedPath) : undefined}
            deleteHint={
              selectedPath ? `删除 ${selectedPath}（移入回收站）` : '先在下方选择一个文件'
            }
          />
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
                {/* 组内按目录树渲染：memory/ 下的子目录显示为可折叠的目录行 */}
                {group.tree && renderTree(group.tree, 0)}
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
