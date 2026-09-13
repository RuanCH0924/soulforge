import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import { ConfirmDialog } from './ConfirmDialog';
import { DiffView } from './DiffView';
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
  const [pending, setPending] = useState<BackupEntry | null>(null);
  const [rolling, setRolling] = useState(false);
  /** 回滚前的「当前 vs 该备份」差异（后端已提供 /api/diff/history） */
  const [diffHtml, setDiffHtml] = useState<string | null>(null);
  const [diffIdentical, setDiffIdentical] = useState(false);
  const [diffNoise, setDiffNoise] = useState<string[]>([]);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);

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

  /** 打开回滚确认，并先加载「当前 vs 该备份」的差异供确认 */
  async function openRollback(b: BackupEntry) {
    setPending(b);
    setDiffHtml(null);
    setDiffIdentical(false);
    setDiffNoise([]);
    setDiffError(null);
    setDiffLoading(true);
    try {
      const res = await api.diffHistory(agentId, path, b.backup_id);
      setDiffHtml(res.html_diff);
      setDiffIdentical(res.identical);
      setDiffNoise(res.noise_kinds);
    } catch (e) {
      setDiffError((e as Error).message);
    } finally {
      setDiffLoading(false);
    }
  }

  async function doRollback() {
    if (!pending) return;
    setRolling(true);
    try {
      const res = await api.rollback(agentId, path, pending.backup_id);
      toast(`已回滚到 ${formatTime(pending.created_at)} 的版本（新备份 #${res.new_backup_id}）`, 'success');
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
              <button className="btn btn-danger btn-sm" onClick={() => void openRollback(b)}>
                回滚到此版本
              </button>
            </div>
          ))}
        </div>
      )}

      {pending && (
        <ConfirmDialog
          title="确认回滚"
          danger
          busy={rolling || diffLoading}
          confirmText="确认回滚"
          cancelText="取消"
          onConfirm={doRollback}
          onCancel={() => setPending(null)}
          message={
            <>
              <p>
                将把 <b className="mono">{path}</b> 回滚到{' '}
                <b>{formatTime(pending.created_at)}</b> 的备份版本（备份 #{pending.backup_id}）。
              </p>
              <p className="hint">回滚前会先自动备份当前内容，避免丢失任何修改。</p>
              <div className="rollback-diff-label">差异预览（当前内容 → 该备份版本）：</div>
              {diffLoading ? (
                <div className="state-block">
                  <div className="spinner-lg" />
                  <div>正在生成差异…</div>
                </div>
              ) : diffError ? (
                <div className="hint">差异加载失败（{diffError}）；确认后将按该备份整篇覆盖。</div>
              ) : diffHtml !== null ? (
                <div className="rollback-diff">
                  <DiffView
                    htmlDiff={diffHtml}
                    identical={diffIdentical}
                    noiseKinds={diffNoise}
                    identicalText="该备份与当前内容一致，回滚不会改变业务内容"
                  />
                </div>
              ) : null}
            </>
          }
        />
      )}
    </Modal>
  );
}
