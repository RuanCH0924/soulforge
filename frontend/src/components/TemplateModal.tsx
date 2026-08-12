import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import { Modal } from './Modal';
import type { TemplateInfo } from '../types';

interface TemplateModalProps {
  onClose: () => void;
  /** 应用成功后回调（重新扫描 Agent 列表） */
  onDone: () => void;
  /** 页面内嵌模式（P3 页面化） */
  embedded?: boolean;
}

export function TemplateModal({ onClose, onDone, embedded }: TemplateModalProps) {
  const { push: toast } = useToast();
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<TemplateInfo | null>(null);
  const [newAgentId, setNewAgentId] = useState('');
  const [targetWorkspace, setTargetWorkspace] = useState('');
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .listTemplates()
      .then((ts) => {
        if (!cancelled) {
          setTemplates(ts);
          setSelected(ts[0] ?? null);
        }
      })
      .catch((e) => {
        if (!cancelled) toast(`加载模板失败：${(e as Error).message}`, 'error');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [toast]);

  async function apply() {
    const id = newAgentId.trim();
    if (!selected || !id) {
      toast('请填写新 Agent 的 ID', 'warning');
      return;
    }
    const ws = targetWorkspace.trim() || `~/.openclaw/workspace-agents/${id}`;
    setApplying(true);
    try {
      const res = await api.applyTemplate(selected.id, id, ws);
      toast(`已创建新 Agent「${res.agent_id}」（${res.files_created.length} 个文件）`, 'success');
      onDone();
      onClose();
    } catch (e) {
      toast(`创建失败：${(e as Error).message}`, 'error');
    } finally {
      setApplying(false);
    }
  }

  return (
    <Modal
      title="新建 Agent（从模板）"
      onClose={onClose}
      width={680}
      embedded={embedded}
      footer={
        <button className="btn btn-primary" onClick={apply} disabled={applying || !selected}>
          {applying && <span className="spinner" />}
          应用模板并创建
        </button>
      }
    >
      {loading ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>正在加载模板...</div>
        </div>
      ) : (
        <>
          <div className="section-title">选择模板</div>
          <div className="template-list">
            {templates.map((t) => (
              <div
                key={t.id}
                className={`template-card${selected?.id === t.id ? ' selected' : ''}`}
                onClick={() => setSelected(t)}
              >
                <div className="tpl-name">{t.name}</div>
                <div className="tpl-desc">{t.description}</div>
                <div className="tpl-meta">{t.file_count} 个文件</div>
              </div>
            ))}
          </div>

          <div className="divider-h" />

          <div className="field">
            <label>新 Agent 的 ID（必填）</label>
            <input
              className="input"
              placeholder="例如 xiaoxi-lawyer-v2"
              value={newAgentId}
              autoFocus
              onChange={(e) => setNewAgentId(e.target.value)}
            />
          </div>
          <div className="field">
            <label>目标 workspace 路径（留空自动生成）</label>
            <input
              className="input mono"
              placeholder={`~/.openclaw/workspace-agents/${newAgentId || 'new-agent'}`}
              value={targetWorkspace}
              onChange={(e) => setTargetWorkspace(e.target.value)}
            />
          </div>
        </>
      )}
    </Modal>
  );
}
