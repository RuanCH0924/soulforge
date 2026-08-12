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
        <button className="btn" onClick={onRescan} disabled={scanning} title="重新扫描 OpenClaw workspace，发现新增/变更的 Agent">
          {scanning && <span className="spinner" />}
          重新扫描
        </button>
        <button className="btn" onClick={onCrossEdit} title="在多个 Agent 间批量编辑相同路径的文件">
          跨Agent编辑
        </button>
        <button className="btn" onClick={onDiff} title="对比两个 Agent 的文件内容与目录差异">
          对比
        </button>
        <button className="btn" onClick={onSync} title="将当前 Agent 的文件变更同步到其他 Agent">
          同步
        </button>
        <button className="btn" onClick={onExportAll} title="将所有 Agent 导出为 Prompt Pack（.tar.gz）">
          导出全部
        </button>
        <button className="btn" onClick={onImport} title="从 Prompt Pack（.tar.gz）导入，导入前自动备份现有文件">
          导入
        </button>
        <button className="btn" onClick={onNewAgent} title="基于模板创建新的 Agent">
          新建Agent
        </button>
        <button className="btn" onClick={onLintAll} title="对所有 Agent 执行全局 Lint 健康检查">
          健康检查
        </button>
        <button className="btn" onClick={onStats} title="查看文件与 Agent 统计仪表盘">
          统计
        </button>
        <button className="btn" onClick={onAudit} title="查看最近 100 条操作审计日志">
          审计
        </button>
        <button className="btn" onClick={onToggleTheme} title="切换浅色/深色主题">
          {resolvedTheme === 'dark' ? '浅色' : '深色'}
        </button>
        <button className="btn" onClick={onSettings} title="打开应用设置">
          设置
        </button>
      </div>
    </header>
  );
}
