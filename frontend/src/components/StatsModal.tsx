import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import { Modal } from './Modal';
import type { StatsResult } from '../types';
import { formatBytes, formatTime } from '../utils/format';

interface StatsModalProps {
  onClose: () => void;
}

export function StatsModal({ onClose }: StatsModalProps) {
  const { push: toast } = useToast();
  const [stats, setStats] = useState<StatsResult | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setStats(await api.stats());
    } catch (e) {
      toast(`加载统计失败：${(e as Error).message}`, 'error');
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
      title="统计仪表盘"
      onClose={onClose}
      width={720}
      footer={
        <button className="btn" onClick={load} disabled={loading}>
          {loading && <span className="spinner" />}
          刷新
        </button>
      }
    >
      {loading || !stats ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>正在汇总数据...</div>
        </div>
      ) : (
        <>
          <div className="stat-grid">
            <div className="stat-card">
              <div className="stat-value">{stats.agents_total}</div>
              <div className="stat-label">Agent 数</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.files_total}</div>
              <div className="stat-label">文件总数</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.core_files}</div>
              <div className="stat-label">CORE 文件</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.memory_files}</div>
              <div className="stat-label">MEMORY 文件</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.backup_total}</div>
              <div className="stat-label">备份总数</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{formatBytes(stats.backup_size_bytes)}</div>
              <div className="stat-label">备份占用</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ color: stats.lint_warnings_total > 0 ? 'var(--warning)' : 'var(--success)' }}>
                {stats.lint_warnings_total}
              </div>
              <div className="stat-label">lint 警告</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{formatBytes(stats.disk_usage_bytes)}</div>
              <div className="stat-label">磁盘占用</div>
            </div>
          </div>
          <div className="hint" style={{ marginTop: 16 }}>
            上次扫描：{formatTime(stats.last_scan_at)}
          </div>
        </>
      )}
    </Modal>
  );
}
