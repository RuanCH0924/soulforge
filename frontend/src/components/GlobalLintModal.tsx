import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import { Modal } from './Modal';
import type { LintWarning } from '../types';

interface GlobalLintModalProps {
  onClose: () => void;
  onOpenResult: (agentId: string, path: string, line?: number) => void;
}

export function GlobalLintModal({ onClose, onOpenResult }: GlobalLintModalProps) {
  const { push: toast } = useToast();
  const [warnings, setWarnings] = useState<LintWarning[]>([]);
  const [checkedFiles, setCheckedFiles] = useState(0);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await api.lintAll();
      const flat: LintWarning[] = [];
      let files = 0;
      res.results.forEach((r) => {
        files += r.stats.files_checked;
        r.warnings.forEach((w) => flat.push(w));
      });
      setWarnings(flat);
      setCheckedFiles(files);
    } catch (e) {
      toast(`健康检查失败：${(e as Error).message}`, 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Modal
      title="全局健康检查"
      onClose={onClose}
      width={820}
      footer={
        <button className="btn" onClick={load} disabled={loading}>
          {loading && <span className="spinner" />}
          重新检查
        </button>
      }
    >
      {loading ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>正在检查所有 Agent（遍历 {warnings.length ? '...' : ''}）...</div>
        </div>
      ) : warnings.length === 0 ? (
        <div className="state-block">
          <div className="lint-empty">✓ 检查了 {checkedFiles} 个文件，没有发现 lint 警告</div>
        </div>
      ) : (
        <>
          <div className="alert-banner warning">
            共发现 {warnings.length} 条 lint 警告（检查 {checkedFiles} 个文件）。点击警告可跳转到对应文件。
          </div>
          <div className="item-list">
            {warnings.map((w, i) => (
              <div
                key={`${w.agent_id}-${w.file_path}-${w.rule_id}-${i}`}
                className="item"
                onClick={() => onOpenResult(w.agent_id, w.file_path, w.line_number ?? undefined)}
              >
                <div className="item-title">
                  <span className="badge-warn" style={{ background: 'var(--accent)' }}>
                    {w.agent_id}
                  </span>
                  <span className="mono">{w.file_path}</span>
                  {w.line_number != null && <span className="muted">第 {w.line_number} 行</span>}
                  <span className="muted" style={{ marginLeft: 'auto', fontWeight: 600, color: 'var(--danger)' }}>
                    {w.rule_name}
                  </span>
                </div>
                {w.line_content && (
                  <div className="item-sub" style={{ fontFamily: 'var(--font-mono)' }}>
                    {w.line_content}
                  </div>
                )}
                <div className="item-sub" style={{ color: 'var(--warning)', fontFamily: 'var(--font-main)' }}>
                  建议：{w.suggestion}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </Modal>
  );
}
