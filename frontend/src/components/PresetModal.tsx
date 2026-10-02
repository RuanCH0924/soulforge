import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import {
  DEFAULT_FORMAT_RULES,
  type Preset,
  type PresetFormatRules,
  type PresetSummary,
  type PresetTargetType,
  type PresetVersionInfo,
} from '../types';
import { formatTime } from '../utils/format';
import { scanHeadings } from '../utils/markdown';
import { ConfirmDialog } from './ConfirmDialog';
import { Modal } from './Modal';
import { PresetTemplateEditor } from './PresetTemplateEditor';

interface PresetModalProps {
  onClose: () => void;
  /** 页面内嵌模式（P2 页面化） */
  embedded?: boolean;
}

/**
 * 可在本页新建 / 编辑的适用类型：**不含 WORKLOG**。
 * WORKLOG 类预设专供大模型处理工作日志（M15 日志标准化），只在
 * 业务工具 → 日志标准化 界面里可见与编辑；本页列表也会排除它们（见 load()）。
 */
const TARGET_TYPES: PresetTargetType[] = [
  'SOUL', 'AGENTS', 'MEMORY', 'USER', 'IDENTITY', 'TOOLS', 'ANY',
];

/** 默认预设参考文档（新建预设时使用；规则走 DEFAULT_FORMAT_RULES） */
const DEFAULT_TEMPLATE = `# 我的预设

## 章节一

- 在此填写内容

## 章节二

- 在此填写内容
`;

/** 旧预设（只有 sections_json 无参考文档）→ 反推纯 Markdown */
function templateFromPreset(p: Preset): string {
  const secs = [...p.sections_json].sort((a, b) => a.order - b.order);
  const body = secs
    .map((s) => `## ${s.title}\n\n${s.hint ? `> ${s.hint}\n\n` : ''}- 在此填写${s.title}内容\n`)
    .join('\n');
  return `# ${p.name}\n\n${body}`;
}

// ---------- 草稿实时保存（localStorage，按编辑上下文隔离） ----------

interface PresetDraft {
  name: string;
  targetType: PresetTargetType;
  description: string;
  templateMd: string;
  formatRules: PresetFormatRules;
}

const DRAFT_PREFIX = 'soulforge.preset-draft.';

function readDraft(ctx: string): PresetDraft | null {
  try {
    const raw = localStorage.getItem(`${DRAFT_PREFIX}${ctx}`);
    return raw ? (JSON.parse(raw) as PresetDraft) : null;
  } catch {
    return null;
  }
}

function writeDraft(ctx: string, d: PresetDraft): void {
  try {
    localStorage.setItem(`${DRAFT_PREFIX}${ctx}`, JSON.stringify(d));
  } catch {
    // localStorage 不可用时静默降级
  }
}

function clearDraft(ctx: string): void {
  try {
    localStorage.removeItem(`${DRAFT_PREFIX}${ctx}`);
  } catch {
    // ignore
  }
}

type View = 'list' | 'edit' | 'history';

/** 预设管理页：列表 + 在线编辑（模板 Markdown + 草稿实时保存）+ 版本历史回溯 */
export function PresetModal({ onClose, embedded }: PresetModalProps) {
  const { push: toast } = useToast();
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>('list');
  const [editing, setEditing] = useState<Preset | null>(null); // 编辑中的预设（系统预设受保护）
  const [creating, setCreating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<PresetSummary | null>(null);
  const [saving, setSaving] = useState(false);
  const draftCtxRef = useRef<string | null>(null);

  // 版本历史
  const [historyPreset, setHistoryPreset] = useState<PresetSummary | null>(null);
  const [versions, setVersions] = useState<PresetVersionInfo[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [confirmRestore, setConfirmRestore] = useState<PresetVersionInfo | null>(null);
  const [restoring, setRestoring] = useState(false);

  // 表单
  const [name, setName] = useState('');
  const [targetType, setTargetType] = useState<PresetTargetType>('ANY');
  const [description, setDescription] = useState('');
  const [templateMd, setTemplateMd] = useState(DEFAULT_TEMPLATE);
  const [formatRules, setFormatRules] = useState<PresetFormatRules>(DEFAULT_FORMAT_RULES);

  const load = () => {
    setLoading(true);
    api
      // scope=workbench：排除「专供大模型处理工作日志」的预设（WORKLOG 类）
      .listPresets(undefined, 'workbench')
      .then(setPresets)
      .catch((e) => toast(`加载预设失败：${(e as Error).message}`, 'error'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 编辑状态实时保存：表单任何变化都写入草稿
  useEffect(() => {
    if (!draftCtxRef.current || view !== 'edit') return;
    writeDraft(draftCtxRef.current, { name, targetType, description, templateMd, formatRules });
  }, [name, targetType, description, templateMd, formatRules, view]);

  const applyDraft = (ctx: string, fallback: () => void) => {
    fallback();
    const d = readDraft(ctx);
    if (d) {
      setName(d.name);
      setTargetType(d.targetType);
      setDescription(d.description);
      setTemplateMd(d.templateMd);
      if (d.formatRules) setFormatRules(d.formatRules);
      toast('已恢复上次未保存的编辑内容', 'info');
    }
  };

  const openCreate = () => {
    setCreating(true);
    setEditing({} as Preset);
    setView('edit');
    draftCtxRef.current = '__new__';
    applyDraft('__new__', () => {
      setName('');
      setTargetType('ANY');
      setDescription('');
      setTemplateMd(DEFAULT_TEMPLATE);
      setFormatRules(DEFAULT_FORMAT_RULES);
    });
  };

  const openEdit = async (p: PresetSummary) => {
    try {
      const detail = await api.getPreset(p.id);
      setCreating(false);
      setEditing(detail);
      setView('edit');
      draftCtxRef.current = p.id;
      applyDraft(p.id, () => {
        setName(detail.name);
        setTargetType(detail.target_file_type);
        setDescription(detail.description ?? '');
        setTemplateMd(detail.template_md ?? templateFromPreset(detail));
        setFormatRules(detail.format_rules ?? DEFAULT_FORMAT_RULES);
      });
    } catch (e) {
      toast(`读取预设失败：${(e as Error).message}`, 'error');
    }
  };

  const cancelEdit = () => {
    // 草稿保留：误关后仍可恢复
    setEditing(null);
    setCreating(false);
    draftCtxRef.current = null;
    setConfirmDelete(null);
    setView('list');
  };

  const discardDraft = () => {
    if (draftCtxRef.current) clearDraft(draftCtxRef.current);
    if (creating) {
      openCreate();
    } else if (editing) {
      void openEdit(editing);
    }
  };

  const save = async () => {
    if (!name.trim()) {
      toast('预设名不能为空', 'warning');
      return;
    }
    const level = formatRules.section_heading_level ?? 2;
    if (!templateMd.trim() || !scanHeadings(templateMd).some((h) => h.level === level)) {
      toast(`预设参考文档不能为空，且需包含至少一个「${'#'.repeat(level)}」开头的章节标题`, 'error');
      return;
    }
    setSaving(true);
    try {
      const body = {
        name: name.trim(),
        target_file_type: targetType,
        description: description.trim() || undefined,
        template_md: templateMd,
        format_rules: formatRules,
      };
      if (creating) {
        await api.createPreset(body);
        toast('预设已创建（v1）', 'success');
      } else if (editing) {
        await api.updatePreset(editing.id, body);
        toast('预设已更新（版本 +1）', 'success');
      }
      if (draftCtxRef.current) clearDraft(draftCtxRef.current);
      draftCtxRef.current = null;
      setEditing(null);
      setCreating(false);
      setView('list');
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
      await api.deletePreset(confirmDelete.id);
      toast(`已删除预设「${confirmDelete.name}」`, 'success');
      setConfirmDelete(null);
      load();
    } catch (e) {
      toast(`删除失败：${(e as Error).message}`, 'error');
    }
  };

  const openHistory = async (p: PresetSummary) => {
    setHistoryPreset(p);
    setView('history');
    setHistoryLoading(true);
    try {
      setVersions(await api.listPresetVersions(p.id));
    } catch (e) {
      toast(`读取版本历史失败：${(e as Error).message}`, 'error');
    } finally {
      setHistoryLoading(false);
    }
  };

  const doRestore = async () => {
    if (!historyPreset || !confirmRestore) return;
    setRestoring(true);
    try {
      await api.restorePresetVersion(historyPreset.id, confirmRestore.id);
      toast(`已回溯到 v${confirmRestore.version}（当前版本 +1）`, 'success');
      setConfirmRestore(null);
      setView('list');
      load();
    } catch (e) {
      toast(`回溯失败：${(e as Error).message}`, 'error');
    } finally {
      setRestoring(false);
    }
  };

  return (
    <Modal
      title={view === 'history' ? `版本历史 — ${historyPreset?.name ?? ''}` : '文档预设'}
      onClose={onClose}
      width={view === 'edit' ? 760 : 700}
      embedded={embedded}
      headerless={embedded}
      footer={
        view === 'edit' ? (
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn" onClick={discardDraft} disabled={saving} title="放弃草稿并重置为原始内容">
              放弃草稿
            </button>
            <button className="btn" onClick={cancelEdit} disabled={saving}>
              取消
            </button>
            <button className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? '保存中…' : '保存版本'}
            </button>
          </div>
        ) : view === 'history' ? (
          <button className="btn" onClick={() => setView('list')}>
            返回列表
          </button>
        ) : (
          <button className="btn btn-primary" onClick={openCreate}>
            新建预设
          </button>
        )
      }
    >
      {view === 'edit' ? (
        <>
          <div className="alert-banner info">
            编辑内容会自动存为草稿；点「保存版本」即可保存，并可随时回溯历史版本。
          </div>
          <div className="field">
            <label>预设名</label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <label>适用文件类型</label>
            <select
              className="select"
              value={targetType}
              onChange={(e) => setTargetType(e.target.value as PresetTargetType)}
            >
              {TARGET_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <div className="hint" style={{ marginTop: 4 }}>
              工作日志（WORKLOG）类预设专供大模型归并日志使用，请在「业务工具 → 日志标准化」界面查看与编辑。
            </div>
          </div>
          <div className="field">
            <label>用途说明</label>
            <input
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <PresetTemplateEditor
            reference={templateMd}
            onReferenceChange={setTemplateMd}
          />
        </>
      ) : view === 'history' ? (
        historyLoading ? (
          <div className="state-block">
            <div className="spinner-lg" />
            <div>正在加载版本历史...</div>
          </div>
        ) : versions.length === 0 ? (
          <div className="state-block">
            <div>该预设暂无历史版本（保存过「保存版本」后才会生成）。</div>
          </div>
        ) : (
          <div className="item-list">
            {versions.map((v) => (
              <div key={v.id} className="item" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="item-title">
                    <span className="mono">v{v.version}</span>
                    <span className="muted text-xs">
                      {formatTime(v.created_at)} · {v.user}
                    </span>
                  </div>
                  <div className="item-sub">
                    {v.name} · {v.target_file_type}
                    {v.description ? ` · ${v.description}` : ''}
                  </div>
                </div>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setConfirmRestore(v)}
                  title="回溯到此版本（恢复为该版本的完整内容）"
                >
                  回溯版本
                </button>
              </div>
            ))}
            <div className="hint mt-8">
              回溯会用该版本覆盖当前预设，并另存一份新快照。
            </div>
          </div>
        )
      ) : loading ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>正在加载预设...</div>
        </div>
      ) : presets.length === 0 ? (
        <div className="state-block">
          <div>还没有预设，点击右下角「新建预设」开始。</div>
        </div>
      ) : (
        <div className="item-list">
          {presets.map((p) => (
            <div key={p.id} className="item" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ flex: 1, minWidth: 0 }} onClick={() => openEdit(p)}>
                <div className="item-title">
                  <span className="mono">{p.name}</span>
                  <span className="muted text-xs">
                    v{p.version}
                  </span>
                </div>
                <div className="item-sub">
                  {p.target_file_type} {p.description ? ` · ${p.description}` : ''}
                </div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => openHistory(p)} title="查看版本历史并可回溯">
                版本
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setConfirmDelete(p)}
                style={{ color: 'var(--danger)' }}
              >
                删除
              </button>
            </div>
          ))}
        </div>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="确认删除预设"
          danger
          confirmText="删除"
          cancelText="取消"
          onConfirm={doDelete}
          onCancel={() => setConfirmDelete(null)}
          message={
            <>
              <p>
                将永久删除预设 <b className="mono">{confirmDelete.name}</b>，此操作不可恢复。
              </p>
              <p className="hint">删除后不会在下次启动时被重建。</p>
            </>
          }
        />
      )}

      {confirmRestore && historyPreset && (
        <ConfirmDialog
          title={`确认回溯到 v${confirmRestore.version}`}
          danger
          busy={restoring}
          confirmText="确认回溯"
          cancelText="取消"
          onConfirm={doRestore}
          onCancel={() => setConfirmRestore(null)}
          message={
            <>
              <p>
                将把预设 <b className="mono">{historyPreset.name}</b> 的内容恢复为{' '}
                <b className="mono">v{confirmRestore.version}</b>（{formatTime(confirmRestore.created_at)} 保存）。
              </p>
              <p className="hint">回溯后当前版本 +1，历史快照保留，可再回溯回去。</p>
            </>
          }
        />
      )}
    </Modal>
  );
}
