import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
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
  // lint 警告数是实时指标，取自与「检查报告」同一个接口（保证两处数字一致）；
  // 不复用 /api/stats 的索引值——索引里的 lint 计数恒为 0，是假数据。
  // 该接口要全量扫一遍（大库需 1~2 分钟），因此单独异步加载，不阻塞其余卡片。
  const [lintWarnings, setLintWarnings] = useState<number | null>(null);
  const [lintLoading, setLintLoading] = useState(true);
  const [loading, setLoading] = useState(true);

  /** lint 计数：计数口径与「检查报告」一致——报告中列出的每一条（含 error 级）都算一条 */
  async function loadLint() {
    setLintLoading(true);
    try {
      const lint = await api.lintAll();
      setLintWarnings(lint.results.reduce((n, r) => n + r.warnings.length, 0));
    } catch {
      setLintWarnings(null); // 取不到就显示「—」，不用 0 冒充「无警告」
    } finally {
      setLintLoading(false);
    }
  }

  async function load() {
    setLoading(true);
    try {
      setStats(await api.stats());
    } catch (e) {
      toast(`加载统计失败：${(e as Error).message}`, 'error');
    } finally {
      setLoading(false);
    }
    void loadLint();
  }

  useEffect(() => {
    load();
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
            <div className="stat-card" title="实时统计（与「检查报告」同源）：需全量扫一遍，大库要 1~2 分钟">
              <div
                className="stat-value"
                style={{
                  color:
                    lintLoading || lintWarnings === null
                      ? 'var(--text-tertiary)'
                      : lintWarnings > 0
                        ? 'var(--warning)'
                        : 'var(--success)',
                }}
              >
                {lintLoading ? '…' : lintWarnings === null ? '—' : lintWarnings}
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
            {lintLoading
              ? ' · lint 警告实时统计中（全量扫描，请稍候）'
              : lintWarnings === null && ' · lint 统计失败，可点「刷新」重试'}
          </div>
        </>
      )}
    </Modal>
  );
}
