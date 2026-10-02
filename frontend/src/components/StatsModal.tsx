import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import { useLintScan } from '../hooks/useLintScan';
import { Modal } from './Modal';
import type { StatsResult } from '../types';
import { formatBytes, formatTime } from '../utils/format';

interface StatsModalProps {
  onClose: () => void;
  /** 页面内嵌模式（P2 页面化） */
  embedded?: boolean;
}

export function StatsModal({ onClose, embedded }: StatsModalProps) {
  const { push: toast } = useToast();
  const [stats, setStats] = useState<StatsResult | null>(null);
  // lint 警告数是实时指标，与「检查报告」「状态栏」共享同一轮扫描（LintScanProvider），口径一致
  // （报告中列出的每一条，含 error 级，都算一条）；不复用 /api/stats 的索引值——索引里的 lint 计数恒为 0。
  // 全量扫描大库需 1~2 分钟：这里只展示进度，不阻塞其余卡片，并可经状态栏「取消」中止。
  const lint = useLintScan();
  const { start: startLintScan } = lint;
  const lintRunning = lint.status === 'running' || lint.status === 'idle';
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
    void startLintScan(); // 单飞：若已有扫描在跑则复用，不重复全量扫描
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Modal
      title="统计面板"
      onClose={onClose}
      width={720}
      embedded={embedded}
      headerless={embedded}
      footer={
        <>
          {lint.status === 'running' && (
            <button className="btn" onClick={lint.cancel}>
              取消 lint 检查
            </button>
          )}
          <button className="btn" onClick={load} disabled={loading}>
            {loading && <span className="spinner" />}
            刷新
          </button>
        </>
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
            <div className="stat-card" title="实时统计（与「检查报告」「状态栏」同源）：需全量扫一遍，大库要 1~2 分钟，可在状态栏取消">
              <div
                className="stat-value"
                style={{
                  color:
                    lintRunning || lint.warningsTotal === null
                      ? 'var(--text-tertiary)'
                      : lint.warningsTotal > 0
                        ? 'var(--warning)'
                        : 'var(--success)',
                }}
              >
                {lintRunning ? '…' : lint.warningsTotal === null ? '—' : lint.warningsTotal}
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
            {lint.status === 'running'
              ? ` · lint 警告实时统计中（${lint.total > 0 ? `${lint.done}/${lint.total}` : '全量扫描'}，可在状态栏取消）`
              : lint.status === 'cancelled'
                ? ' · lint 检查已取消（结果不完整）'
                : lint.warningsTotal === null && ' · lint 统计失败'}
          </div>
        </>
      )}
    </Modal>
  );
}
