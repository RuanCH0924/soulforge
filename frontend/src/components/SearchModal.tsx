import { useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import { Modal } from './Modal';
import type { AgentInfo, SearchHit } from '../types';

interface SearchModalProps {
  agents: AgentInfo[];
  onClose: () => void;
  onOpenResult: (agentId: string, path: string, line: number) => void;
}

function Highlight({ text, query, regex }: { text: string; query: string; regex: boolean }) {
  if (!query || regex) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark>{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  );
}

export function SearchModal({ agents, onClose, onOpenResult }: SearchModalProps) {
  const { push: toast } = useToast();
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filePatterns, setFilePatterns] = useState('');
  const [regex, setRegex] = useState(false);
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [results, setResults] = useState<SearchHit[]>([]);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  function toggleAgent(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function doSearch(e?: FormEvent) {
    e?.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setSearched(true);
    try {
      const patterns = filePatterns
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await api.search({
        query: q,
        agent_ids: selected.size > 0 ? [...selected] : undefined,
        file_patterns: patterns.length > 0 ? patterns : undefined,
        regex,
        case_sensitive: caseSensitive,
        limit: 100,
      });
      setResults(res.hits);
      setTotal(res.total);
    } catch (err) {
      toast(`搜索失败：${(err as Error).message}`, 'error');
    } finally {
      setSearching(false);
    }
  }

  return (
    <Modal title="搜索文件内容" onClose={onClose} width={720}>
      <form onSubmit={doSearch}>
        <div className="field">
          <input
            className="input"
            placeholder="输入搜索词（支持正则）"
            value={query}
            autoFocus
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className="section-title">限定 Agent（不勾选 = 全部）</div>
        <div className="checkbox-grid">
          {agents.map((a) => (
            <label key={a.id} className="checkbox-row">
              <input
                type="checkbox"
                checked={selected.has(a.id)}
                onChange={() => toggleAgent(a.id)}
              />
              {a.display_name || a.id}
            </label>
          ))}
        </div>

        <div className="section-title">限定文件名（逗号分隔，如 SOUL.md, AGENTS.md）</div>
        <div className="field">
          <input
            className="input"
            placeholder="可选，留空搜索全部文件"
            value={filePatterns}
            onChange={(e) => setFilePatterns(e.target.value)}
          />
        </div>

        <div style={{ display: 'flex', gap: 20, alignItems: 'center', marginBottom: 12 }}>
          <label className="checkbox-row">
            <input type="checkbox" checked={regex} onChange={(e) => setRegex(e.target.checked)} />
            正则匹配
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={caseSensitive}
              onChange={(e) => setCaseSensitive(e.target.checked)}
            />
            区分大小写
          </label>
          <button className="btn btn-primary" type="submit" disabled={searching || !query.trim()}>
            {searching && <span className="spinner" />}
            搜索
          </button>
        </div>
      </form>

      {searched && (
        <>
          <div className="section-title">
            搜索结果：共 {total} 条{searching && '（搜索中...）'}
          </div>
          {searching ? (
            <div className="state-block">
              <div className="spinner-lg" />
              <div>正在搜索...</div>
            </div>
          ) : results.length === 0 ? (
            <div className="state-block">
              <div>没有匹配的内容</div>
            </div>
          ) : (
            <div className="item-list">
              {results.map((h, i) => (
                <div
                  key={`${h.agent_id}-${h.file_path}-${h.line_number}-${i}`}
                  className="item"
                  onClick={() => onOpenResult(h.agent_id, h.file_path, h.line_number)}
                  title="点击打开文件并定位到该行"
                >
                  <div className="item-title">
                    <span className="badge-warn" style={{ background: 'var(--accent)' }}>
                      {h.agent_id}
                    </span>
                    <span className="mono" title={h.file_path}>{h.file_path}</span>
                    <span className="muted">第 {h.line_number} 行</span>
                  </div>
                  <div className="item-sub">
                    <Highlight text={h.line_content} query={query.trim()} regex={regex} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
