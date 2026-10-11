import type { AppRoute } from '../hooks/useHashRoute';

type NavIconName = 'workbench' | 'tools' | 'memory' | 'data' | 'settings';

interface SideNavProps {
  route: AppRoute;
  onNavigate: (r: AppRoute) => void;
}

const NAV: { route: AppRoute; label: string; icon: NavIconName; hint: string }[] = [
  { route: 'workbench', label: '主工作台', icon: 'workbench', hint: '日常编辑：Agent / 文件 / 编辑器' },
  { route: 'tools', label: '业务工具', icon: 'tools', hint: '跨 Agent 文件协作：同步 / 对比 / 批量编辑 / 文档预设' },
  { route: 'memory', label: '记忆加工', icon: 'memory', hint: '大模型加工日志：日志标准化 / 日志总结' },
  { route: 'data', label: '数据中心', icon: 'data', hint: '统计 / 检查报告 / 审计日志' },
  { route: 'settings', label: '系统配置', icon: 'settings', hint: '设置 / LLM Provider' },
];

/**
 * 内联 SVG 图标（零依赖）。
 * 描边用 `currentColor`，会自动跟随导航项的常态 / 悬停 / 激活配色；
 * 相比原先的字符字形（⌂ ⇄ ◇ ⚙），跨系统字体渲染更一致、大小更可控。
 */
function NavIcon({ name }: { name: NavIconName }) {
  const common = {
    viewBox: '0 0 24 24',
    width: 18,
    height: 18,
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    focusable: 'false' as const,
  };
  switch (name) {
    case 'workbench':
      // 三栏布局：对应「Agent 树 / 文件树 / 编辑器」
      return (
        <svg {...common}>
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <line x1="9" y1="4" x2="9" y2="20" />
          <line x1="15" y1="4" x2="15" y2="20" />
        </svg>
      );
    case 'tools':
      // 双向箭头：对应跨 Agent 同步 / 对比
      return (
        <svg {...common}>
          <path d="M4 9h13" />
          <path d="m14 6 3 3-3 3" />
          <path d="M20 15H7" />
          <path d="m10 12-3 3 3 3" />
        </svg>
      );
    case 'memory':
      // 日志文档 + 星芒：对应「大模型加工日志」
      return (
        <svg {...common}>
          <rect x="3.5" y="4" width="12.5" height="16" rx="2" />
          <line x1="6.5" y1="8.5" x2="13" y2="8.5" />
          <line x1="6.5" y1="12" x2="13" y2="12" />
          <line x1="6.5" y1="15.5" x2="10.5" y2="15.5" />
          <path d="M19 4.5v4.5" />
          <path d="M16.75 6.75h4.5" />
        </svg>
      );
    case 'data':
      // 柱状图：对应统计 / 检查报告 / 审计
      return (
        <svg {...common}>
          <line x1="4" y1="20" x2="20" y2="20" />
          <rect x="6" y="11" width="3" height="6" rx="0.5" />
          <rect x="11" y="7" width="3" height="10" rx="0.5" />
          <rect x="16" y="13" width="3" height="4" rx="0.5" />
        </svg>
      );
    case 'settings':
    default:
      // 滑杆：对应系统配置
      return (
        <svg {...common}>
          <line x1="4" y1="8" x2="20" y2="8" />
          <circle cx="10" cy="8" r="2.4" />
          <line x1="4" y1="16" x2="20" y2="16" />
          <circle cx="15" cy="16" r="2.4" />
        </svg>
      );
  }
}

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
          aria-current={route === n.route ? 'page' : undefined}
        >
          <span className="side-nav-icon">
            <NavIcon name={n.icon} />
          </span>
          <span className="side-nav-label">{n.label}</span>
        </button>
      ))}
    </nav>
  );
}
