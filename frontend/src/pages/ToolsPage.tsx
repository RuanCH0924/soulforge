import { useState } from 'react';
import { CrossEditModal } from '../components/CrossEditModal';
import { DiffModal } from '../components/DiffModal';
import { PresetModal } from '../components/PresetModal';
import { SuperSyncPanel } from '../components/SuperSyncPanel';
import { SyncModal } from '../components/SyncModal';
import type { AgentInfo } from '../types';

export type ToolsTab = 'sync' | 'diff' | 'cross-edit' | 'presets';

/** 「同步」下的两种模式（原先是两个并列 tab，同名近似难区分，故收成一个入口 + 模式切换） */
type SyncMode = 'normal' | 'super';

interface ToolsPageProps {
  agents: AgentInfo[];
  initialPath?: string;
  initialContent?: string;
  onBack: () => void;
  onDone: () => void;
  /** 初始选中的 tab（用于跨页跳转，如编辑器「管理预设」直接落到「文档预设」） */
  initialTab?: ToolsTab;
}

/** 业务工具页（P3）：跨 Agent 文件协作（同步 / 对比 / 批量编辑）+ 文档预设管理 */
export function ToolsPage({
  agents,
  initialPath,
  initialContent,
  onBack,
  onDone,
  initialTab,
}: ToolsPageProps) {
  const [tab, setTab] = useState<ToolsTab>(initialTab ?? 'sync');
  const [syncMode, setSyncMode] = useState<SyncMode>('normal');

  return (
    <div className="page">
      <div className="page-tabs">
        {(
          [
            ['sync', '同步'],
            ['diff', '对比'],
            ['cross-edit', '跨Agent编辑'],
            ['presets', '文档预设'],
          ] as [ToolsTab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            className={`page-tab${tab === key ? ' active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="page-content">
        {tab === 'sync' && (
          <>
            <div className="sync-mode-bar">
              <div className="mode-toggle" role="group" aria-label="同步模式">
                <button
                  type="button"
                  className={syncMode === 'normal' ? 'active' : ''}
                  onClick={() => setSyncMode('normal')}
                  title="两两 Agent 之间按文件对比后选择性同步"
                >
                  普通同步
                </button>
                <button
                  type="button"
                  className={syncMode === 'super' ? 'active' : ''}
                  onClick={() => setSyncMode('super')}
                  title="一次对所有 Agent 做全局一致性对齐"
                >
                  超级同步
                </button>
              </div>
              <span className="hint">
                {syncMode === 'normal'
                  ? '两两 Agent 之间按文件对比后选择性同步（写入前自动备份）'
                  : '全局对齐：一次把同一份 CORE 文档收敛到所有 Agent，适合批量统一'}
              </span>
            </div>
            {syncMode === 'normal' ? (
              <SyncModal agents={agents} onClose={onBack} onDone={onDone} embedded />
            ) : (
              <SuperSyncPanel agents={agents} />
            )}
          </>
        )}
        {tab === 'diff' && <DiffModal agents={agents} initialAgent={null} onClose={onBack} embedded />}
        {tab === 'cross-edit' && (
          <CrossEditModal
            agents={agents}
            initialPath={initialPath}
            initialContent={initialContent}
            onClose={onBack}
            onDone={onDone}
            embedded
          />
        )}
        {tab === 'presets' && <PresetModal onClose={onBack} embedded />}
      </div>
    </div>
  );
}
