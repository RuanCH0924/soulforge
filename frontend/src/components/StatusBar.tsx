import { formatRelativeTime } from '../utils/format';
import type { LintScanStatus } from '../hooks/useLintScan';

interface StatusBarProps {
  connected: boolean;
  agentsTotal: number;
  filesTotal: number;
  lastScanAt?: number | null;
  /** 全量 lint 扫描状态（进度 / 取消），来自共享的 LintScanProvider */
  lintStatus?: LintScanStatus;
  /** 已完成的 Agent 数 */
  lintDone?: number;
  /** 本轮总 Agent 数（0 = 尚未取到列表） */
  lintTotal?: number;
  /** lint 警告总数（实时计算）；null = 尚未取到，不谎报「无警告」 */
  warningsTotal: number | null;
  /** 请求取消进行中的 lint 扫描 */
  onCancelLint?: () => void;
  /** 断连时的手动重连入口 */
  onReconnect?: () => void;
  /** 后端版本号（来自 GET /api/health，事实源为 backend/app/__init__.py） */
  version?: string;
}

export function StatusBar({
  connected,
  agentsTotal,
  filesTotal,
  lastScanAt,
  lintStatus = 'idle',
  lintDone = 0,
  lintTotal = 0,
  warningsTotal,
  onCancelLint,
  onReconnect,
  version,
}: StatusBarProps) {
  const scanning = lintStatus === 'running' || lintStatus === 'idle';
  return (
    <footer className="statusbar">
      <span>
        <span className={`conn-dot${connected ? '' : ' offline'}`} />
        {connected ? (
          `已连接到 ${agentsTotal} 个 Agent`
        ) : (
          <span className="statusbar-inline">
            未连接后端
            {onReconnect && (
              <button type="button" className="statusbar-action" onClick={onReconnect}>
                重连
              </button>
            )}
          </span>
        )}
      </span>
      <span className="metric-secondary">索引 {filesTotal} 个文件</span>
      <span className="metric-secondary">上次扫描：{formatRelativeTime(lastScanAt)}</span>
      <span className="right">
        {scanning ? (
          <span className="statusbar-inline">
            <span className="metric-secondary">
              lint 检查中…{lintTotal > 0 ? ` ${lintDone}/${lintTotal}` : ''}
            </span>
            {lintStatus === 'running' && onCancelLint && (
              <button type="button" className="statusbar-action" onClick={onCancelLint}>
                取消
              </button>
            )}
          </span>
        ) : lintStatus === 'error' ? (
          <span className="metric-secondary">lint 检查失败</span>
        ) : lintStatus === 'cancelled' ? (
          <span className="metric-secondary">lint 检查已取消</span>
        ) : warningsTotal === null ? (
          <span className="metric-secondary">lint 状态未知</span>
        ) : warningsTotal > 0 ? (
          <span style={{ color: 'var(--warning)' }}>lint 警告 {warningsTotal} 条</span>
        ) : (
          'lint 无警告'
        )}
        {version ? <span className="statusbar-version">v{version}</span> : null}
      </span>
    </footer>
  );
}
