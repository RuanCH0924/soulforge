import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Preset } from '../types';
import { Modal } from './Modal';

interface DailyPresetEditorProps {
  presetId: string;
  /** 保存成功回调：父组件负责刷新列表、提示生效时机 */
  onSaved: (saved: Preset) => void;
  onClose: () => void;
}

/**
 * 工作日志标准化预设编辑器（M15 页内）。
 *
 * 为什么不复用设置页的 PresetModal：① WORKLOG 类预设按边界不在设置页展示；
 * ② 它需要比「模板文档」更全的编辑面 —— 多一个「风格与内容规则」（`style_rules`，
 * 逐行）字段，设置页表单没有这个字段，而它正是注入大模型 prompt 的弱规则。
 *
 * 保存走 `PUT /api/presets/{id}`：version +1 并留版本快照；改 `template_md` 时后端会
 * 重新派生 `sections_json`，所以章节列表不需要（也不应该）在这里单独编辑。
 */
export function DailyPresetEditor({ presetId, onSaved, onClose }: DailyPresetEditorProps) {
  const [preset, setPreset] = useState<Preset | null>(null);
  const [description, setDescription] = useState('');
  const [templateMd, setTemplateMd] = useState('');
  const [styleRules, setStyleRules] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getPreset(presetId)
      .then((p) => {
        setPreset(p);
        setDescription(p.description ?? '');
        setTemplateMd(p.template_md ?? '');
        setStyleRules(p.style_rules.join('\n'));
      })
      .catch((e) => setError(`加载预设失败：${(e as Error).message}`))
      .finally(() => setLoading(false));
  }, [presetId]);

  const save = async () => {
    if (!templateMd.trim() || !templateMd.includes('## ')) {
      setError('模板文档不能为空，且需包含至少一个「## 」章节标题（章节列表由它派生）。');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await api.updatePreset(presetId, {
        description: description.trim(),
        template_md: templateMd,
        style_rules: styleRules
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
      });
      onSaved(saved);
      onClose();
    } catch (e) {
      setError(`保存失败：${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={`编辑工作日志预设 — ${preset?.name ?? presetId}`}
      onClose={onClose}
      width={900}
      footer={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose} disabled={saving}>
            取消
          </button>
          <button className="btn btn-primary" onClick={() => void save()} disabled={saving || loading}>
            {saving && <span className="spinner" />}
            保存{preset ? `（v${preset.version + 1}）` : ''}
          </button>
        </div>
      }
    >
      <div className="alert-banner info">
        本预设<b>专供大模型归并工作日志</b>使用（不出现在主工作台与文档预设页）。
        保存后 <b>version +1</b> 并写入版本历史；<b>重新生成批次即生效</b>，已生成的计划不会重算。
      </div>

      {error && (
        <div className="alert-banner danger" style={{ marginTop: 8 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>正在加载预设…</div>
        </div>
      ) : (
        <>
          <div className="hint" style={{ marginTop: 8 }}>
            来源：{preset?.is_builtin ? '内置预设（随版本分发，升级时可能被刷新）' : '用户自建'} · 当前
            v{preset?.version} · 适用类型 {preset?.target_file_type}
          </div>

          <div className="field">
            <label>用途说明（显示在预设选择处）</label>
            <input
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="用一句话说明这个预设归并出的日志长什么样"
            />
          </div>

          <div className="field">
            <label>模板文档（YAML 格式化规则 + Markdown 章节骨架）</label>
            <textarea
              className="input"
              rows={16}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
              value={templateMd}
              onChange={(e) => setTemplateMd(e.target.value)}
              spellCheck={false}
            />
            <div className="hint" style={{ marginTop: 4 }}>
              上半段 <span className="mono">---</span> 之间的 YAML 是强规则（必填章节、顺序、禁
              emoji / 原始 HTML 等），会机械校验并拦截；下半段是给模型看的章节骨架。改这里会重新派生章节列表。
            </div>
          </div>

          <div className="field">
            <label>风格与内容规则（每行一条，注入大模型 prompt）</label>
            <textarea
              className="input"
              rows={8}
              style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
              value={styleRules}
              onChange={(e) => setStyleRules(e.target.value)}
              spellCheck={false}
              placeholder={'例如：按时间倒序归档\n只保留结论，不保留过程'}
            />
            <div className="hint" style={{ marginTop: 4 }}>
              共 {styleRules.split('\n').filter((l) => l.trim()).length} 条 · 空行会被忽略；这些规则不参与机械校验，由模型遵守。
            </div>
          </div>
        </>
      )}
    </Modal>
  );
}
