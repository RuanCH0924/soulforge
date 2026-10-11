interface TopBarProps {
  agentCount: number;
  scanning: boolean;
  onOpenSearch: () => void;
  onRescan: () => void;
  onExportAll: () => void;
}

/**
 * 顶栏（M-01）：仅保留与页面无关的全局动作（命令面板入口 + 重新扫描 + 导出全部）。
 * 跨页导航统一由 SideNav 承担，顶栏不再承载导航类按钮。
 */
export function TopBar(props: TopBarProps) {
  const { agentCount, scanning, onOpenSearch, onRescan, onExportAll } = props;

  return (
    <header className="topbar">
      <div className="topbar-title">SoulForge</div>
      <span className="topbar-sub">{agentCount > 0 ? `${agentCount} 个 Agent` : ''}</span>

      <div className="topbar-search" onClick={onOpenSearch} role="button" tabIndex={0}>
        搜索或执行命令…
        <span className="kbd">Ctrl K</span>
      </div>

      <div className="topbar-actions">
        <button
          className="btn"
          onClick={onExportAll}
          title="将所有 Agent 导出为 Prompt Pack（.tar.gz）"
        >
          导出全部
        </button>
        <button className="btn" onClick={onRescan} disabled={scanning} title="重新扫描 OpenClaw workspace，发现新增/变更的 Agent">
          {scanning && <span className="spinner" />}
          重新扫描
        </button>
      </div>
    </header>
  );
}
