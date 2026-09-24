import { useState } from 'react';
import { AuditModal } from '../components/AuditModal';
import { GlobalLintModal } from '../components/GlobalLintModal';
import { StatsModal } from '../components/StatsModal';

export type DataTab = 'stats' | 'lint' | 'audit';

interface DataPageProps {
  onBack: () => void;
  onOpenResult: (agentId: string, path: string, line?: number) => void;
  /** 初始选中的 tab（从编辑器 lint 面板「查看规则」跳入时指定 lint） */
  initialTab?: DataTab;
}

/** 数据中心页（P2）：统计面板 / 检查报告 / 审计日志，页面级只读视角 */
export function DataPage({ onBack, onOpenResult, initialTab }: DataPageProps) {
  const [tab, setTab] = useState<DataTab>(initialTab ?? 'stats');

  return (
    <div className="page">
      <div className="page-tabs">
        {(
          [
            ['stats', '统计面板'],
            ['lint', '检查报告'],
            ['audit', '审计日志'],
          ] as [DataTab, string][]
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
        {tab === 'stats' && <StatsModal onClose={onBack} embedded />}
        {tab === 'lint' && <GlobalLintModal onClose={onBack} onOpenResult={onOpenResult} embedded />}
        {tab === 'audit' && <AuditModal onClose={onBack} embedded />}
      </div>
    </div>
  );
}
