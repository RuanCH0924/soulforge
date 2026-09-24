import { useState } from 'react';
import { CrossEditModal } from '../components/CrossEditModal';
import { DailyStandardizerPanel } from '../components/DailyStandardizerPanel';
import { DiffModal } from '../components/DiffModal';
import { SuperSyncPanel } from '../components/SuperSyncPanel';
import { SyncModal } from '../components/SyncModal';
import type { AgentInfo } from '../types';

type Tab = 'sync' | 'super-sync' | 'cross-edit' | 'diff' | 'daily';

interface ToolsPageProps {
  agents: AgentInfo[];
  initialPath?: string;
  initialContent?: string;
  onBack: () => void;
  onDone: () => void;
  onExportAll: () => void;
}

/** 业务工具页（P3）：跨 Agent 协同与批处理工具集 */
export function ToolsPage({ agents, initialPath, initialContent, onBack, onDone, onExportAll }: ToolsPageProps) {
  const [tab, setTab] = useState<Tab>('sync');

  return (
    <div className="page">
      <div className="page-tabs">
        {(
          [
            ['sync', '同步'],
            ['super-sync', '超级同步'],
            ['cross-edit', '跨Agent编辑'],
            ['diff', '对比'],
            ['daily', '日志标准化'],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            className={`page-tab${tab === key ? ' active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
        <div style={{ marginLeft: 'auto', paddingBottom: 8 }}>
          <button className="btn btn-sm" onClick={onExportAll} title="将所有 Agent 导出为 Prompt Pack（.tar.gz）">
            导出全部
          </button>
        </div>
      </div>
      <div className="page-content">
        {tab === 'sync' && <SyncModal agents={agents} onClose={onBack} onDone={onDone} embedded />}
        {tab === 'super-sync' && <SuperSyncPanel agents={agents} />}
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
        {tab === 'diff' && <DiffModal agents={agents} initialAgent={null} onClose={onBack} embedded />}
        {tab === 'daily' && <DailyStandardizerPanel agents={agents} />}
      </div>
    </div>
  );
}
