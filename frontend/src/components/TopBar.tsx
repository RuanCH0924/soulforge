interface TopBarProps {
  agentCount: number;
  resolvedTheme: 'light' | 'dark';
  scanning: boolean;
  onOpenSearch: () => void;
  onRescan: () => void;
  onCrossEdit: () => void;
  onDiff: () => void;
  onSync: () => void;
  onExportAll: () => void;
  onImport: () => void;
  onNewAgent: () => void;
  onLintAll: () => void;
  onStats: () => void;
  onAudit: () => void;
  onSettings: () => void;
  onToggleTheme: () => void;
}

export function TopBar(props: TopBarProps) {
  const {
    agentCount,
    resolvedTheme,
    scanning,
    onOpenSearch,
    onRescan,
    onCrossEdit,
    onDiff,
    onSync,
    onExportAll,
    onImport,
    onNewAgent,
    onLintAll,
    onStats,
    onAudit,
    onSettings,
    onToggleTheme,
  } = props;

  return (
    <header className="topbar">
      <div className="topbar-title">Soulforge</div>
      <span className="topbar-sub">{agentCount > 0 ? `${agentCount} 个 Agent` : ''}</span>

      <div className="topbar-search" onClick={onOpenSearch} role="button" tabIndex={0}>
        搜索文件内容…
        <span className="kbd">Ctrl K</span>
      </div>

      <div className="topbar-actions">
        <button className="btn" onClick={onRescan} disabled={scanning}>
          {scanning && <span className="spinner" />}
          重新扫描
        </button>
        <button className="btn" onClick={onCrossEdit}>
          跨Agent编辑
        </button>
        <button className="btn" onClick={onDiff}>
          对比
        </button>
        <button className="btn" onClick={onSync}>
          同步
        </button>
        <button className="btn" onClick={onExportAll}>
          导出全部
        </button>
        <button className="btn" onClick={onImport}>
          导入
        </button>
        <button className="btn" onClick={onNewAgent}>
          新建Agent
        </button>
        <button className="btn" onClick={onLintAll}>
          健康检查
        </button>
        <button className="btn" onClick={onStats}>
          统计
        </button>
        <button className="btn" onClick={onAudit}>
          审计
        </button>
        <button className="btn" onClick={onToggleTheme} title="切换浅色/深色主题">
          {resolvedTheme === 'dark' ? '浅色' : '深色'}
        </button>
        <button className="btn" onClick={onSettings}>
          设置
        </button>
      </div>
    </header>
  );
}
