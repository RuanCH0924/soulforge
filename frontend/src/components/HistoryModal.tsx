import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import { ConfirmDialog } from './ConfirmDialog';
import { Modal } from './Modal';
import type { BackupEntry } from '../types';
import { formatBytes, formatTime } from '../utils/format';

interface HistoryModalProps {
  agentId: string;
  path: string;
  onClose: () => void;
  onRolledBack: () => void;
}

export function HistoryModal({ agentId, path, onClose, onRolledBack }: HistoryModalProps) {
  const { push: toast } = useToast();
  const [history, setHistory] = useState<BackupEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState<BackupEntry | null>(null);
  const [rolling, setRolling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await api.fileHistory(agentId, path);
        if (!cancelled) setHistory(list);
      } catch (e) {
        if (!cancelled) toast(`加载历史失败：${(e as Error).message}`, 'error');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentId, path, toast]);

  async function doRollback() {
    if (!confirm) return;
    setRolling(true);
    try {
      const res = await api.rollback(agentId, path, confirm.backup_id);
      toast(`已回滚到 ${formatTime(confirm.created_at)} 的版本（新备份 #${res.new_backup_id}）`, 'success');
      onRolledBack();
      onClose();
    } catch (e) {
      toast(`回滚失败：${(e as Error).message}`, 'error');
    } finally {
      setRolling(false);
    }
  }

  return (
    <Modal title={`备份历史 — ${path}`} onClose={onClose} width={640}>
      {loading ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>正在加载备份历史...</div>
        </div>
      ) : history.length === 0 ? (
        <div className="state-block">
          <div>这个文件还没有备份记录（每次保存都会自动备份）</div>
        </div>
      ) : (
        <div className="item-list">
          {history.map((b) => (
            <div key={b.backup_id} className="item" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ flex: 1 }}>
                <div className="item-title">
                  <span className="mono">#{b.backup_id}</span>
                  <span>{formatTime(b.created_at)}</span>
                  <span className="muted">{formatBytes(b.size_bytes)}</span>
                </div>
                <div className="item-sub">{b.reason || 'auto-write'}</div>
              </div>
              <button className="btn btn-danger btn-sm" onClick={() => setConfirm(b)}>
                回滚到此版本
              </button>
            </div>
          ))}
        </div>
      )}

      {confirm && (
        <ConfirmDialog
          title="确认回滚"
          danger
          busy={rolling}
          confirmText="确认回滚"
          cancelText="取消"
          onConfirm={doRollback}
          onCancel={() => setConfirm(null)}
          message={
            <>
              <p>
                将把 <b className="mono">{path}</b> 回滚到{' '}
                <b>{formatTime(confirm.created_at)}</b> 的备份版本（备份 #{confirm.backup_id}）。
              </p>
              <p className="hint">回滚前会先自动备份当前内容，避免丢失任何修改。</p>
            </>
          }
        />
      )}
    </Modal>
  );
}
