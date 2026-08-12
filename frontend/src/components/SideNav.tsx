import type { AppRoute } from '../hooks/useHashRoute';

interface SideNavProps {
  route: AppRoute;
  onNavigate: (r: AppRoute) => void;
}

const NAV: { route: AppRoute; label: string; icon: string; hint: string }[] = [
  { route: 'workbench', label: '主工作台', icon: '⌂', hint: '日常编辑：Agent / 文件 / 编辑器' },
  { route: 'tools', label: '业务工具', icon: '⇄', hint: '跨 Agent 协同：同步 / 对比 / 批量编辑 / 导入导出' },
  { route: 'data', label: '数据中心', icon: '◇', hint: '统计 / 审计 / 健康检查报告' },
  { route: 'settings', label: '系统配置', icon: '⚙', hint: '设置 / LLM Provider / 文档预设' },
];

/** 左侧全局导航（P2）：固定 4 项，替代顶栏 12+ 入口 */
export function SideNav({ route, onNavigate }: SideNavProps) {
  return (
    <nav className="side-nav" aria-label="主导航">
      {NAV.map((n) => (
        <button
          key={n.route}
          className={`side-nav-item${route === n.route ? ' active' : ''}`}
          onClick={() => onNavigate(n.route)}
          title={n.hint}
        >
          <span className="side-nav-icon">{n.icon}</span>
          <span className="side-nav-label">{n.label}</span>
        </button>
      ))}
    </nav>
  );
}
