import { useState } from 'react';
import { LLMProvidersModal } from '../components/LLMProvidersModal';
import { SettingsModal } from '../components/SettingsModal';

type Tab = 'general' | 'llm';

interface SettingsPageProps {
  onBack: () => void;
}

/** 系统配置页（P2）：设置 / LLM Provider 两块，页面级承载（文档预设已迁到「业务工具」） */
export function SettingsPage({ onBack }: SettingsPageProps) {
  const [tab, setTab] = useState<Tab>('general');

  return (
    <div className="page">
      <div className="page-tabs">
        {(
          [
            ['general', '常规设置'],
            ['llm', 'LLM Provider'],
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
        {tab === 'general' && <SettingsModal onClose={onBack} embedded />}
        {tab === 'llm' && <LLMProvidersModal onClose={onBack} embedded />}
      </div>
    </div>
  );
}
