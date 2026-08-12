import Editor from '@monaco-editor/react';
import { useState } from 'react';
import { api } from '../api';
import { useSettings } from '../hooks/useSettings';
import { useToast } from '../hooks/useToast';
import { ConfirmDialog } from './ConfirmDialog';
import { Modal } from './Modal';
import type { AgentInfo } from '../types';

interface CrossEditModalProps {
  agents: AgentInfo[];
  /** 当前打开文件的路径（预填） */
  initialPath?: string;
  /** 当前打开文件的内容（预填） */
  initialContent?: string;
  onClose: () => void;
  onDone: () => void;
  /** 页面内嵌模式（P3 页面化） */
  embedded?: boolean;
}

export function CrossEditModal({
  agents,
  initialPath = '',
  initialContent = '',
  onClose,
  onDone,
  embedded,
}: CrossEditModalProps) {
  const { push: toast } = useToast();
  const { resolvedTheme } = useSettings();
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set());
  const [path, setPath] = useState(initialPath);
  const [content, setContent] = useState(initialContent);
  const [step, setStep] = useState<1 | 2>(1);
  const [confirm, setConfirm] = useState(false);
  const [saving, setSaving] = useState(false);

  function toggleAgent(id: string) {
    setSelectedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function next() {
    const p = path.trim();
    if (!p) {
      toast('请填写要编辑的文件路径（如 SOUL.md）', 'warning');
      return;
    }
    if (selectedAgents.size === 0) {
      toast('请至少选择一个 Agent', 'warning');
      return;
    }
    setStep(2);
  }

  async function doWrite() {
    if (!path.trim() || selectedAgents.size === 0) return;
    setSaving(true);
    try {
      const files = [...selectedAgents].map((agentId) => ({ agent_id: agentId, path: path.trim() }));
      const res = await api.crossWrite(files, content);
      toast(`已写入 ${res.agents} 个 Agent（文件：${path.trim()}）`, 'success');
      onDone();
      onClose();
    } catch (e) {
      toast(`写入失败：${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
      setConfirm(false);
    }
  }

  return (
    <Modal
      title="跨 Agent 编辑"
      onClose={onClose}
      width={820}
      embedded={embedded}
      footer={
        step === 1 ? (
          <button className="btn btn-primary" onClick={next}>
            下一步
          </button>
        ) : (
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn" onClick={() => setStep(1)} disabled={saving}>
              返回
            </button>
            <button
              className="btn btn-danger"
              onClick={() => setConfirm(true)}
              disabled={saving || content.length === 0}
            >
              {saving && <span className="spinner" />}
              保存到 {selectedAgents.size} 个 Agent
            </button>
          </div>
        )
      }
    >
      {step === 1 ? (
        <>
          <div className="alert-banner warning">跨 Agent 编辑会把同一份内容写入多个 Agent，请谨慎操作。</div>
          <div className="field">
            <label>文件路径（相对 Agent workspace，如 SOUL.md 或 memory/2026-08-05.md）</label>
            <input
              className="input mono"
              placeholder="SOUL.md"
              value={path}
              autoFocus
              onChange={(e) => setPath(e.target.value)}
            />
          </div>
          <div className="section-title">选择要写入的 Agent（{selectedAgents.size} 个）</div>
          <div className="checkbox-grid">
            {agents.map((a) => (
              <label key={a.id} className="checkbox-row">
                <input
                  type="checkbox"
                  checked={selectedAgents.has(a.id)}
                  onChange={() => toggleAgent(a.id)}
                />
                {a.display_name || a.id}
              </label>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="alert-banner danger">
            将同时写入 <b>{selectedAgents.size}</b> 个 Agent（{path.trim()}）：{[...selectedAgents].join('、')}
          </div>
          <div style={{ height: 380, border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
            <Editor
              height="100%"
              language="markdown"
              theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
              value={content}
              onChange={(v) => setContent(v ?? '')}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                wordWrap: 'on',
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
            />
          </div>
        </>
      )}

      {confirm && (
        <ConfirmDialog
          title="确认跨 Agent 写入"
          danger
          busy={saving}
          confirmText="确认写入"
          cancelText="取消"
          onConfirm={doWrite}
          onCancel={() => setConfirm(false)}
          message={
            <>
              <p>以下 Agent 将被写入文件 <b className="mono">{path.trim()}</b>：</p>
              <ul style={{ paddingLeft: 20 }}>
                {[...selectedAgents].map((id) => (
                  <li key={id}>{id}</li>
                ))}
              </ul>
              <p className="hint">每个 Agent 写入前会自动备份当前版本。</p>
            </>
          }
        />
      )}
    </Modal>
  );
}
