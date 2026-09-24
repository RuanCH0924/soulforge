import { formatRelativeTime } from '../utils/format';

interface StatusBarProps {
  connected: boolean;
  agentsTotal: number;
  filesTotal: number;
  lastScanAt?: number | null;
  /** lint 警告总数（实时计算，来自 GET /api/lint/all）；null = 尚未取到，不谎报「无警告」 */
  warningsTotal: number | null;
  /** 后端版本号（来自 GET /api/health，事实源为 backend/app/__init__.py） */
  version?: string;
}

export function StatusBar({
  connected,
  agentsTotal,
  filesTotal,
  lastScanAt,
  warningsTotal,
  version,
}: StatusBarProps) {
  return (
    <footer className="statusbar">
      <span>
        <span className={`conn-dot${connected ? '' : ' offline'}`} />
        {connected ? `已连接到 ${agentsTotal} 个 Agent` : '未连接后端'}
      </span>
      <span className="metric-secondary">索引 {filesTotal} 个文件</span>
      <span className="metric-secondary">上次扫描：{formatRelativeTime(lastScanAt)}</span>
      <span className="right">
        {warningsTotal === null ? (
          <span className="metric-secondary">lint 检查中…</span>
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
