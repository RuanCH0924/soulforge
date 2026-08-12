interface TopBarProps {
  agentCount: number;
  scanning: boolean;
  onOpenSearch: () => void;
  onRescan: () => void;
  /** 前往业务工具（同步/对比/跨编辑/导入导出/新建，P3 页面化） */
  onNavigateTools: () => void;
  /** 前往数据中心（统计/审计/健康检查，P2 页面化） */
  onNavigateData: () => void;
  /** 前往系统配置（设置/预设/LLM，P2 页面化） */
  onNavigateSettings: () => void;
}

/**
 * 顶栏（P3 版）：仅保留全局动作，工具/数据/管理收敛为页面入口。
 */
export function TopBar(props: TopBarProps) {
  const { agentCount, scanning, onOpenSearch, onRescan, onNavigateTools, onNavigateData, onNavigateSettings } = props;

  return (
    <header className="topbar">
      <div className="topbar-title">Soulforge</div>
      <span className="topbar-sub">{agentCount > 0 ? `${agentCount} 个 Agent` : ''}</span>

      <div className="topbar-search" onClick={onOpenSearch} role="button" tabIndex={0}>
        搜索命令、文件内容…
        <span className="kbd">Ctrl K</span>
      </div>

      <div className="topbar-actions">
        <button className="btn" onClick={onRescan} disabled={scanning} title="重新扫描 OpenClaw workspace，发现新增/变更的 Agent">
          {scanning && <span className="spinner" />}
          重新扫描
        </button>
        <button className="btn" onClick={onNavigateTools} title="同步 / 对比 / 跨Agent编辑 / 导入导出 / 新建 Agent（业务工具）">
          业务工具
        </button>
        <button className="btn" onClick={onNavigateData} title="统计 / 审计 / 健康检查报告（数据中心）">
          数据中心
        </button>
        <button className="btn" onClick={onNavigateSettings} title="设置 / 文档预设 / LLM Provider（系统配置）">
          系统配置
        </button>
      </div>
    </header>
  );
}
