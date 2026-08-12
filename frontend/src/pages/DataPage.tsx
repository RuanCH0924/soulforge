import { useState } from 'react';
import { AuditModal } from '../components/AuditModal';
import { GlobalLintModal } from '../components/GlobalLintModal';
import { StatsModal } from '../components/StatsModal';

type Tab = 'stats' | 'lint' | 'audit';

interface DataPageProps {
  onBack: () => void;
  onOpenResult: (agentId: string, path: string, line?: number) => void;
}

/** 数据中心页（P2）：统计 / 健康检查报告 / 审计日志，页面级只读视角 */
export function DataPage({ onBack, onOpenResult }: DataPageProps) {
  const [tab, setTab] = useState<Tab>('stats');

  return (
    <div className="page">
      <div className="page-tabs">
        {(
          [
            ['stats', '统计仪表盘'],
            ['lint', '健康检查报告'],
            ['audit', '审计日志'],
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
      </div>
      <div className="page-content">
        {tab === 'stats' && <StatsModal onClose={onBack} embedded />}
        {tab === 'lint' && <GlobalLintModal onClose={onBack} onOpenResult={onOpenResult} embedded />}
        {tab === 'audit' && <AuditModal onClose={onBack} embedded />}
      </div>
    </div>
  );
}
