import { formatRelativeTime } from '../utils/format';

interface StatusBarProps {
  connected: boolean;
  agentsTotal: number;
  filesTotal: number;
  lastScanAt?: number | null;
  warningsTotal: number;
}

export function StatusBar({ connected, agentsTotal, filesTotal, lastScanAt, warningsTotal }: StatusBarProps) {
  return (
    <footer className="statusbar">
      <span>
        <span className={`conn-dot${connected ? '' : ' offline'}`} />
        {connected ? `已连接到 ${agentsTotal} 个 Agent` : '未连接后端'}
      </span>
      <span>索引 {filesTotal} 个文件</span>
      <span>上次扫描：{formatRelativeTime(lastScanAt)}</span>
      <span className="right">
        {warningsTotal > 0 ? (
          <span style={{ color: 'var(--warning)' }}>lint 警告 {warningsTotal} 条</span>
        ) : (
          'lint 无警告'
        )}
      </span>
    </footer>
  );
}
