import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../api';
import { DEFAULT_FORMAT_RULES, type Preset, type PresetFormatRules } from '../types';
import { scanHeadings } from '../utils/markdown';
import { Modal } from './Modal';
import { PresetTemplateEditor } from './PresetTemplateEditor';

interface DailyPresetEditorProps {
  presetId: string;
  /** 保存成功回调：父组件负责刷新列表、提示生效时机 */
  onSaved: (saved: Preset) => void;
  onClose: () => void;
  /** 弹窗标题前缀（默认「编辑工作日志预设」）；日志总结界面会换成自己的口径 */
  titlePrefix?: string;
  /** 顶部说明（默认面向 M15 日志标准化；日志总结界面传入自己的说明） */
  notice?: ReactNode;
}

const DEFAULT_NOTICE = (
  <>
    <div className="alert-title">本预设专供大模型归并工作日志</div>
    <ul className="alert-points">
      <li>
        不出现在主工作台与「文档预设」页，只在日志标准化界面查看与编辑。
      </li>
      <li>
        保存后 <b>version +1</b> 并写入版本历史，可随时回溯。
      </li>
      <li>
        <b>重新生成批次即生效</b>；已生成的计划不会重算。
      </li>
    </ul>
  </>
);

/**
 * 工作日志标准化预设编辑器（M15 页内）。
 *
 * 为什么不复用设置页的 PresetModal：① WORKLOG 类预设按边界不在设置页展示；
 * ② 它需要比「预设参考文档」更全的编辑面 —— 多一个「修改要求」（`style_rules`，
 * 逐行）字段，设置页表单没有这个字段，而它正是注入大模型 prompt 的弱规则。
 *
 * 保存走 `PUT /api/presets/{id}`：version +1 并留版本快照；改 `template_md` 时后端会
 * 重新派生 `sections_json`，所以章节结构不需要在这里单独编辑。
 */
export function DailyPresetEditor({ presetId, onSaved, onClose, titlePrefix, notice }: DailyPresetEditorProps) {
  const [preset, setPreset] = useState<Preset | null>(null);
  const [description, setDescription] = useState('');
  const [templateMd, setTemplateMd] = useState('');
  const [formatRules, setFormatRules] = useState<PresetFormatRules>(DEFAULT_FORMAT_RULES);
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
        setFormatRules(p.format_rules ?? DEFAULT_FORMAT_RULES);
        setStyleRules(p.style_rules.join('\n'));
      })
      .catch((e) => setError(`加载预设失败：${(e as Error).message}`))
      .finally(() => setLoading(false));
  }, [presetId]);

  const save = async () => {
    const level = formatRules.section_heading_level ?? 2;
    const hasSection = scanHeadings(templateMd).some((h) => h.level === level);
    if (!templateMd.trim() || !hasSection) {
      setError(`预设参考文档不能为空，且需包含至少一个「${'#'.repeat(level)}」开头的章节标题。`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await api.updatePreset(presetId, {
        description: description.trim(),
        template_md: templateMd,
        format_rules: formatRules,
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
      title={`${titlePrefix ?? '编辑工作日志预设'} — ${preset?.name ?? presetId}`}
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
      <div className="alert-banner info intro">
        {notice ?? DEFAULT_NOTICE}
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
          <div className="field">
            <label>用途说明</label>
            <input
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="例：把一天的多份记录归并成一篇标准工作日志"
            />
          </div>

          <PresetTemplateEditor
            reference={templateMd}
            onReferenceChange={setTemplateMd}
            styleRules={styleRules}
            onStyleRulesChange={setStyleRules}
          />
        </>
      )}
    </Modal>
  );
}
