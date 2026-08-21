export type BrowseMode = 'agent' | 'core';

interface ViewToggleProps {
  mode: BrowseMode;
  onChange: (m: BrowseMode) => void;
}

/** 文件浏览模式切换控件（Agent 原有模式 / CORE 分类模式） */
export function ViewToggle({ mode, onChange }: ViewToggleProps) {
  return (
    <span className="view-toggle" role="tablist" aria-label="文件浏览模式">
      <button
        type="button"
        className={mode === 'agent' ? 'active' : ''}
        onClick={() => onChange('agent')}
        title="按 Agent 浏览（原有模式）"
      >
        Agent
      </button>
      <button
        type="button"
        className={mode === 'core' ? 'active' : ''}
        onClick={() => onChange('core')}
        title="按 CORE 分类浏览：CORE 文件 → Agent"
      >
        CORE 分类
      </button>
    </span>
  );
}
