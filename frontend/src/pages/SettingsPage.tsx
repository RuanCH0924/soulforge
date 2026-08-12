import { useState } from 'react';
import { LLMProvidersModal } from '../components/LLMProvidersModal';
import { PresetModal } from '../components/PresetModal';
import { SettingsModal } from '../components/SettingsModal';

type Tab = 'general' | 'llm' | 'presets';

interface SettingsPageProps {
  onBack: () => void;
}

/** 系统配置页（P2）：设置 / LLM Provider / 文档预设 三块，页面级承载 */
export function SettingsPage({ onBack }: SettingsPageProps) {
  const [tab, setTab] = useState<Tab>('general');

  return (
    <div className="page">
      <div className="page-tabs">
        {(
          [
            ['general', '常规设置'],
            ['llm', 'LLM Provider'],
            ['presets', '文档预设'],
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
        {tab === 'presets' && <PresetModal onClose={onBack} embedded />}
      </div>
    </div>
  );
}
