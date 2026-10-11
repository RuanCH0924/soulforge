import { useSlidingIndicator } from '../hooks/useSlidingIndicator';
import { SlidingIndicator } from './SlidingIndicator';

export type BrowseMode = 'agent' | 'core';

interface ViewToggleProps {
  mode: BrowseMode;
  onChange: (m: BrowseMode) => void;
}

/** 文件浏览模式切换控件（Agent 原有模式 / CORE 分类模式） */
export function ViewToggle({ mode, onChange }: ViewToggleProps) {
  // 二级菜单的滑动底色块（与一级导航同一套动效）
  const indicator = useSlidingIndicator<HTMLSpanElement>(mode, '.view-toggle button.active', 'x');

  return (
    <span className="view-toggle" role="tablist" aria-label="文件浏览模式" ref={indicator.containerRef}>
      <SlidingIndicator axis="x" variant="seg" box={indicator.box} ready={indicator.ready} />
      <button
        type="button"
        className={mode === 'agent' ? 'active' : ''}
        onClick={() => onChange('agent')}
        title="按 WorkSpace 浏览：Agent → 其文件（原有模式）"
      >
        WorkSpace
      </button>
      <button
        type="button"
        className={mode === 'core' ? 'active' : ''}
        onClick={() => onChange('core')}
        title="按 CORE 分类浏览：CORE 文件 → Agent"
      >
        CORE
      </button>
    </span>
  );
}
