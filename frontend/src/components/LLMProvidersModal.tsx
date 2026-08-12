import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import type { LLMProtocol, LLMProvider } from '../types';
import { ConfirmDialog } from './ConfirmDialog';
import { Modal } from './Modal';

interface LLMProvidersModalProps {
  onClose: () => void;
  /** 页面内嵌模式（P2 页面化） */
  embedded?: boolean;
}

const PROTOCOLS: { value: LLMProtocol; label: string }[] = [
  { value: 'openai-completions', label: 'OpenAI 兼容（/chat/completions）' },
  { value: 'anthropic-messages', label: 'Anthropic（/v1/messages）' },
];

interface FormState {
  id: string;
  base_url: string;
  api_key: string;
  model: string;
  protocol: LLMProtocol;
  enabled: boolean;
  max_tokens: number;
  temperature: number;
  timeout_seconds: number;
}

const EMPTY_FORM: FormState = {
  id: '', base_url: '', api_key: '', model: '', protocol: 'openai-completions',
  enabled: true, max_tokens: 4096, temperature: 0.3, timeout_seconds: 60,
};

/** LLM Provider 管理页（Step 2 UI）：列表 + 新增/编辑/删除 + 测试连通性，key 永远掩码 */
export function LLMProvidersModal({ onClose, embedded }: LLMProvidersModalProps) {
  const { push: toast } = useToast();
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null); // null=列表，'__new__'=新建
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<LLMProvider | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; text: string }>>({});

  const load = () => {
    setLoading(true);
    api
      .listLLMProviders()
      .then(setProviders)
      .catch((e) => toast(`加载 Provider 失败：${(e as Error).message}`, 'error'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditing('__new__');
  };

  const openEdit = (p: LLMProvider) => {
    setForm({
      id: p.id, base_url: p.base_url, api_key: '', model: p.model, protocol: p.protocol,
      enabled: p.enabled, max_tokens: p.max_tokens, temperature: p.temperature, timeout_seconds: p.timeout_seconds,
    });
    setEditing(p.id);
  };

  const save = async () => {
    if (!form.base_url.trim() || !form.model.trim()) {
      toast('base_url 和 model 不能为空', 'warning');
      return;
    }
    setSaving(true);
    try {
      if (editing === '__new__') {
        if (!form.id.trim()) {
          toast('Provider ID 不能为空', 'warning');
          return;
        }
        await api.createLLMProvider({
          id: form.id.trim(), base_url: form.base_url.trim(), api_key: form.api_key.trim(),
          model: form.model.trim(), protocol: form.protocol, enabled: form.enabled,
          max_tokens: form.max_tokens, temperature: form.temperature, timeout_seconds: form.timeout_seconds,
        });
        toast('Provider 已创建（已热加载）', 'success');
      } else if (editing) {
        await api.updateLLMProvider(editing, {
          base_url: form.base_url.trim(),
          api_key: form.api_key.trim() || undefined,
          model: form.model.trim(),
          protocol: form.protocol,
          enabled: form.enabled,
          max_tokens: form.max_tokens,
          temperature: form.temperature,
          timeout_seconds: form.timeout_seconds,
        });
        toast('Provider 已更新（已热加载）', 'success');
      }
      setEditing(null);
      load();
    } catch (e) {
      toast(`保存失败：${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const doDelete = async () => {
    if (!confirmDelete) return;
    try {
      await api.deleteLLMProvider(confirmDelete.id);
      toast(`已删除 Provider「${confirmDelete.id}」`, 'success');
      setConfirmDelete(null);
      load();
    } catch (e) {
      toast(`删除失败：${(e as Error).message}`, 'error');
    }
  };

  const testProvider = async (id: string) => {
    setTesting(id);
    try {
      const r = await api.testLLMProvider(id);
      setTestResults((prev) => ({
        ...prev,
        [id]: r.ok
          ? { ok: true, text: `连通 OK（${r.latency_ms}ms）：${r.response_preview || '(空回复)'}` }
          : { ok: false, text: `失败：${r.error ?? '未知错误'}` },
      }));
    } catch (e) {
      setTestResults((prev) => ({ ...prev, [id]: { ok: false, text: `测试失败：${(e as Error).message}` } }));
    } finally {
      setTesting(null);
    }
  };

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <Modal
      title="LLM Provider 管理"
      onClose={onClose}
      width={820}
      embedded={embedded}
      footer={
        editing !== null ? (
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn" onClick={() => setEditing(null)} disabled={saving}>
              取消
            </button>
            <button className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? '保存中…' : '保存'}
            </button>
          </div>
        ) : (
          <button className="btn btn-primary" onClick={openCreate}>
            新增 Provider
          </button>
        )
      }
    >
      {editing !== null ? (
        <>
          <div className="alert-banner info">
            协议兼容 OpenAI 标准；API key 以 Fernet 加密存储，任何接口都不会回显明文。
          </div>
          {editing === '__new__' ? (
            <div className="field">
              <label>Provider ID（业务唯一，如 openai-main / ollama-local）</label>
              <input className="input mono" value={form.id} onChange={(e) => set('id', e.target.value)} />
            </div>
          ) : (
            <div className="field">
              <label>Provider ID（不可修改）</label>
              <input className="input mono" value={form.id} disabled />
            </div>
          )}
          <div className="field">
            <label>Base URL</label>
            <input
              className="input mono"
              placeholder="https://api.openai.com/v1"
              value={form.base_url}
              onChange={(e) => set('base_url', e.target.value)}
            />
          </div>
          <div className="field">
            <label>API Key{editing === '__new__' ? '' : '（留空 = 保留旧 key）'}</label>
            <input
              type="password"
              className="input mono"
              placeholder={editing === '__new__' ? 'sk-...' : '留空则保留现有密钥'}
              value={form.api_key}
              onChange={(e) => set('api_key', e.target.value)}
            />
          </div>
          <div className="field">
            <label>模型名</label>
            <input
              className="input mono"
              placeholder="gpt-4o"
              value={form.model}
              onChange={(e) => set('model', e.target.value)}
            />
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="field" style={{ flex: 1 }}>
              <label>协议</label>
              <select className="select" value={form.protocol} onChange={(e) => set('protocol', e.target.value as LLMProtocol)}>
                {PROTOCOLS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>温度</label>
              <input
                type="number" className="input" step={0.1} min={0} max={2}
                value={form.temperature}
                onChange={(e) => set('temperature', Number(e.target.value) || 0)}
              />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="field" style={{ flex: 1 }}>
              <label>Max Tokens</label>
              <input
                type="number" className="input" min={1}
                value={form.max_tokens}
                onChange={(e) => set('max_tokens', Number(e.target.value) || 1)}
              />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>超时（秒）</label>
              <input
                type="number" className="input" min={1}
                value={form.timeout_seconds}
                onChange={(e) => set('timeout_seconds', Number(e.target.value) || 60)}
              />
            </div>
          </div>
          <label className="checkbox-row">
            <input type="checkbox" checked={form.enabled} onChange={(e) => set('enabled', e.target.checked)} />
            启用（禁用的 Provider 不可被调用）
          </label>
        </>
      ) : loading ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>正在加载 Provider...</div>
        </div>
      ) : providers.length === 0 ? (
        <div className="state-block">
          <div>还没有配置 LLM Provider，点击右下角「新增 Provider」。</div>
        </div>
      ) : (
        <div className="item-list">
          {providers.map((p) => (
            <div key={p.id} className="item" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ flex: 1, minWidth: 0 }} onClick={() => openEdit(p)}>
                <div className="item-title">
                  <span className="mono">{p.id}</span>
                  <span className="badge-warn" style={{ background: p.enabled ? 'rgba(16,185,129,.15)' : 'var(--bg-hover)', color: p.enabled ? 'var(--success)' : 'var(--text-secondary)' }}>
                    {p.enabled ? '启用' : '禁用'}
                  </span>
                  <span className="muted" style={{ fontSize: 11 }}>
                    {p.protocol}
                  </span>
                </div>
                <div className="item-sub">
                  {p.base_url} · {p.model} · key: {p.api_key_masked}
                </div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => testProvider(p.id)} disabled={testing === p.id}>
                {testing === p.id && <span className="spinner" />}
                测试连通
              </button>
              <button
                className="btn btn-ghost btn-sm"
                style={{ color: 'var(--danger)' }}
                onClick={() => setConfirmDelete(p)}
              >
                删除
              </button>
            </div>
          ))}
          {Object.entries(testResults).map(([id, r]) => (
            <div key={id} className={`item-sub ${r.ok ? '' : ''}`} style={{ marginTop: 6, color: r.ok ? 'var(--success)' : 'var(--danger)' }}>
              [{id}] {r.text}
            </div>
          ))}
        </div>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="确认删除 Provider"
          danger
          confirmText="删除"
          cancelText="取消"
          onConfirm={doDelete}
          onCancel={() => setConfirmDelete(null)}
          message={
            <>
              <p>
                将删除 <b className="mono">{confirmDelete.id}</b>（{confirmDelete.base_url} · {confirmDelete.model}）。
              </p>
              <p className="hint">被 AI 任务引用的 Provider 会被后端拒绝删除。</p>
            </>
          }
        />
      )}
    </Modal>
  );
}
