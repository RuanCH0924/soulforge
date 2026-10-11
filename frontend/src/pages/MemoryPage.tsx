import { useState } from 'react';
import { DailyStandardizerPanel } from '../components/DailyStandardizerPanel';
import { SummaryPanel } from '../components/SummaryPanel';
import type { AgentInfo } from '../types';

export type MemoryTab = 'daily' | 'summary';

interface MemoryPageProps {
  agents: AgentInfo[];
  /** 初始选中的 tab（用于跨页跳转，如某处直接落「日志总结」） */
  initialTab?: MemoryTab;
}

/**
 * 记忆加工页（P2）：把「AI 加工日志」从业务工具里提级为一级菜单。
 * 这两项与「同步 / 对比」不是一族——前者由大模型改文档（批次 / 计划 / 验收 / 预算 / 重试），
 * 后者是确定性搬文件；共用一个页面反而让高价值能力被平铺 tab 淹没。
 */
export function MemoryPage({ agents, initialTab }: MemoryPageProps) {
  const [tab, setTab] = useState<MemoryTab>(initialTab ?? 'daily');

  return (
    <div className="page">
      <div className="page-tabs">
        {(
          [
            ['daily', '日志标准化'],
            ['summary', '日志总结'],
          ] as [MemoryTab, string][]
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
        {tab === 'daily' && <DailyStandardizerPanel agents={agents} />}
        {tab === 'summary' && <SummaryPanel agents={agents} />}
      </div>
    </div>
  );
}
