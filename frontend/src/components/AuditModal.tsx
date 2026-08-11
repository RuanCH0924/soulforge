import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import { Modal } from './Modal';
import type { AuditEntry } from '../types';
import { formatTime } from '../utils/format';

interface AuditModalProps {
  onClose: () => void;
}

export function AuditModal({ onClose }: AuditModalProps) {
  const { push: toast } = useToast();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .audit(100)
      .then((list) => {
        if (!cancelled) setEntries(list);
      })
      .catch((e) => {
        if (!cancelled) toast(`加载审计日志失败：${(e as Error).message}`, 'error');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [toast]);

  return (
    <Modal title="审计日志（最近 100 条）" onClose={onClose} width={880}>
      {loading ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>正在加载审计日志...</div>
        </div>
      ) : entries.length === 0 ? (
        <div className="state-block">
          <div>还没有操作记录</div>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="audit-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>操作</th>
                <th>Agent</th>
                <th>目标文件</th>
                <th>结果</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}>
                  <td className="mono">{formatTime(e.timestamp)}</td>
                  <td>{e.action}</td>
                  <td>{e.agent_id ?? '—'}</td>
                  <td className="mono">{e.target_path ?? '—'}</td>
                  <td>
                    <span style={{ color: e.result === 'ok' ? 'var(--success)' : 'var(--danger)' }}>
                      {e.result}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
