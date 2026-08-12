import { useEffect, useMemo, useRef, useState } from 'react';
import type { SearchHit } from '../types';

export interface CommandItem {
  type: 'action';
  id: string;
  label: string;
  keywords?: string;
  group: string;
  hint?: string;
  danger?: boolean;
  onSelect: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  items: CommandItem[];
  onSearchFiles: (q: string) => Promise<SearchHit[]>;
  onOpenFile: (agentId: string, path: string, line?: number) => void;
}

function match(q: string, text: string): boolean {
  const t = text.toLowerCase();
  return q.toLowerCase().split(/\s+/).filter(Boolean).every((part) => t.includes(part));
}

/** Cmd+K 命令面板：可搜索 功能动作 / 文件 / 设置项 */
export function CommandPalette({ open, onClose, items, onSearchFiles, onOpenFile }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [files, setFiles] = useState<SearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const q = query.trim();

  const matchedItems = useMemo(
    () =>
      q
        ? items.filter((it) => match(q, `${it.label} ${it.keywords ?? ''} ${it.group}`))
        : items,
    [items, q],
  );

  // 文件搜索（防抖）
  useEffect(() => {
    if (!open) return;
    if (!q) {
      setFiles([]);
      return;
    }
    setSearching(true);
    const t = window.setTimeout(async () => {
      try {
        setFiles(await onSearchFiles(q));
      } finally {
        setSearching(false);
      }
    }, 220);
    return () => window.clearTimeout(t);
  }, [q, open, onSearchFiles]);

  // 打开时聚焦并重置
  useEffect(() => {
    if (open) {
      setQuery('');
      setActive(0);
      window.setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const flat: (CommandItem | { type: 'file'; hit: SearchHit })[] = [
    ...matchedItems,
    ...files.map((f) => ({ type: 'file' as const, hit: f })),
  ];
  const total = flat.length;

  const selectAt = (idx: number) => {
    const it = flat[idx];
    if (!it) return;
    if (it.type === 'file') {
      onOpenFile(it.hit.agent_id, it.hit.file_path, it.hit.line_number);
      onClose();
    } else {
      it.onSelect();
      onClose();
    }
  };

  // 分组渲染（动作按 group；文件单独一组）
  const groups = useMemo(() => {
    const gs: { name: string; items: { idx: number }[] }[] = [];
    const seen = new Set<string>();
    matchedItems.forEach((it, idx) => {
      if (!seen.has(it.group)) {
        seen.add(it.group);
        gs.push({ name: it.group, items: [] });
      }
      gs[gs.length - 1].items.push({ idx });
    });
    if (files.length > 0) {
      gs.push({ name: '文件', items: files.map((_, idx) => ({ idx: matchedItems.length + idx })) });
    }
    return gs;
  }, [matchedItems, files]);

  return (
    <div className="command-overlay" onMouseDown={onClose}>
      <div className="command-palette" onMouseDown={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="command-input"
          placeholder="输入命令、功能、设置或搜索文件内容…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault();
              setActive((a) => Math.min(total - 1, a + 1));
            } else if (e.key === 'ArrowUp') {
              e.preventDefault();
              setActive((a) => Math.max(0, a - 1));
            } else if (e.key === 'Enter') {
              e.preventDefault();
              selectAt(active);
            }
          }}
        />
        <div className="command-body">
          {total === 0 && !searching && (
            <div className="command-empty">
              {q ? `没有匹配「${q}」的功能或文件` : '输入关键词开始搜索'}
            </div>
          )}
          {groups.map((g) => (
            <div key={g.name} className="command-group">
              <div className="command-group-title">
                {g.name}
                {g.name === '文件' && searching ? '（搜索中…）' : ''}
              </div>
              {g.items.map(({ idx }) => {
                const it = flat[idx];
                if (it.type === 'file') {
                  return (
                    <div
                      key={`${it.hit.agent_id}-${it.hit.file_path}-${it.hit.line_number}`}
                      className={`command-item${idx === active ? ' active' : ''}`}
                      onMouseEnter={() => setActive(idx)}
                      onClick={() => selectAt(idx)}
                    >
                      <span className="command-item-label mono" title={it.hit.file_path}>
                        {it.hit.file_path}
                      </span>
                      <span className="command-item-meta">
                        {it.hit.agent_id} · L{it.hit.line_number} · {it.hit.line_content.slice(0, 28)}
                      </span>
                    </div>
                  );
                }
                return (
                  <div
                    key={it.id}
                    className={`command-item${idx === active ? ' active' : ''}${it.danger ? ' danger' : ''}`}
                    onMouseEnter={() => setActive(idx)}
                    onClick={() => selectAt(idx)}
                  >
                    <span className="command-item-label">{it.label}</span>
                    <span className="command-item-meta">{it.hint}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div className="command-footer">
          <span>
            <b>↑↓</b> 选择
          </span>
          <span>
            <b>Enter</b> 执行
          </span>
          <span>
            <b>Esc</b> 关闭
          </span>
        </div>
      </div>
    </div>
  );
}
