import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import {
  DEFAULT_FORMAT_RULES,
  type Preset,
  type PresetFormatRules,
  type PresetOverride,
  type PresetTargetType,
} from '../types';
import { scanHeadings } from '../utils/markdown';
import { Modal } from './Modal';
import { PresetTemplateEditor } from './PresetTemplateEditor';

/** 「可新建 / 编辑」的适用类型全集（文档预设统一承载全部预设，含大模型专用） */
const TARGET_TYPES: PresetTargetType[] = [
  'SOUL', 'AGENTS', 'MEMORY', 'USER', 'IDENTITY', 'TOOLS', 'WORKLOG', 'SUMMARY', 'ANY',
];

/** 调用预设前确认窗的回传：presetId 覆盖 = 「设为新预设」后的新 id；override = 「仅本次生效」 */
export interface PresetConfirmResult {
  presetId?: string;
  override?: PresetOverride;
}

interface PresetConfirmModalProps {
  /** 待确认 / 编辑的预设 id */
  presetId: string;
  /** 弹窗标题 */
  title?: string;
  /** 开始任务的按钮文案（如「生成计划」/「开始整理」），用于「…并开始」按钮 */
  actionLabel?: string;
  /** 顶部说明（可选） */
  notice?: ReactNode;
  /** 父组件正在执行任务（提交中） */
  busy?: boolean;
  onCancel: () => void;
  onConfirm: (result: PresetConfirmResult) => void;
}

function styleRulesToText(rules: string[]): string {
  return rules.join('\n');
}

function textToStyleRules(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

/**
 * 预设确认与编辑窗（所有「调用文档预设」的功能在开始任务前都必须经过它）。
 *
 * 作用：① 让用户再次确认即将使用的预设；② 允许现场编辑 5 个核心类目
 * （预设名 / 使用文件类别 / 用途说明 / 预设参考文档 / 预设修改要求）；
 * ③ 编辑后可选择去向 ——「仅本次生效」/「更新预设」/「设为新预设」。
 *
 * 未编辑 → 直接「确认并开始」（用原预设）；编辑后 → 三选一（不能只做本次而不落库之外的取巧）。
 */
export function PresetConfirmModal({
  presetId,
  title = '确认预设',
  actionLabel = '开始',
  notice,
  busy,
  onCancel,
  onConfirm,
}: PresetConfirmModalProps) {
  const { push: toast } = useToast();
  const [preset, setPreset] = useState<Preset | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 表单（5 个核心类目）
  const [name, setName] = useState('');
  const [targetType, setTargetType] = useState<PresetTargetType>('ANY');
  const [description, setDescription] = useState('');
  const [templateMd, setTemplateMd] = useState('');
  const [styleRules, setStyleRules] = useState('');
  const [formatRules, setFormatRules] = useState<PresetFormatRules>(DEFAULT_FORMAT_RULES);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getPreset(presetId)
      .then((p) => {
        setPreset(p);
        setName(p.name);
        setTargetType(p.target_file_type);
        setDescription(p.description ?? '');
        setTemplateMd(p.template_md ?? '');
        setStyleRules(styleRulesToText(p.style_rules));
        setFormatRules(p.format_rules ?? DEFAULT_FORMAT_RULES);
      })
      .catch((e) => setError(`加载预设失败：${(e as Error).message}`))
      .finally(() => setLoading(false));
  }, [presetId]);

  const dirty =
    preset !== null &&
    (name !== preset.name ||
      targetType !== preset.target_file_type ||
      description !== (preset.description ?? '') ||
      templateMd !== (preset.template_md ?? '') ||
      styleRules !== styleRulesToText(preset.style_rules));

  const buildOverride = (): PresetOverride => ({
    name: name.trim(),
    target_file_type: targetType,
    description: description.trim() || null,
    template_md: templateMd,
    format_rules: formatRules,
    style_rules: textToStyleRules(styleRules),
  });

  const validate = (): boolean => {
    if (!name.trim()) {
      setError('预设名不能为空。');
      return false;
    }
    const level = formatRules.section_heading_level ?? 2;
    if (!templateMd.trim() || !scanHeadings(templateMd).some((h) => h.level === level)) {
      setError(`预设参考文档不能为空，且需包含至少一个「${'#'.repeat(level)}」开头的章节标题。`);
      return false;
    }
    return true;
  };

  const run = async (fn: () => Promise<void>) => {
    setActing(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(`操作失败：${(e as Error).message}`);
    } finally {
      setActing(false);
    }
  };

  const confirmAsIs = () => onConfirm({});

  const confirmThisOnly = () => {
    if (!validate()) return;
    onConfirm({ override: buildOverride() });
  };

  const confirmUpdate = () =>
    run(async () => {
      if (!validate()) return;
      await api.updatePreset(presetId, {
        name: name.trim(),
        target_file_type: targetType,
        description: description.trim(),
        template_md: templateMd,
        format_rules: formatRules,
        style_rules: textToStyleRules(styleRules),
      });
      toast('预设已更新（版本 +1），本次任务使用更新后的预设', 'success');
      onConfirm({ presetId });
    });

  const confirmAsNew = () =>
    run(async () => {
      if (!validate()) return;
      const newName =
        preset && name.trim() === preset.name ? `${name.trim()}（副本）` : name.trim();
      const created = await api.createPreset({
        name: newName,
        target_file_type: targetType,
        description: description.trim() || undefined,
        template_md: templateMd,
        format_rules: formatRules,
        style_rules: textToStyleRules(styleRules),
      });
      toast(`已设为新预设「${created.name}」（v1）`, 'success');
      onConfirm({ presetId: created.id });
    });

  const disabled = acting || Boolean(busy) || loading || Boolean(error && !preset);

  const footer = dirty ? (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
      <button className="btn" onClick={onCancel} disabled={disabled}>
        取消
      </button>
      <button className="btn" onClick={confirmThisOnly} disabled={disabled} title="改动只作用于本次任务，不改动预设本身">
        仅本次生效并{actionLabel}
      </button>
      <button className="btn" onClick={() => void confirmUpdate()} disabled={disabled} title="把改动保存回原预设（版本 +1）后再开始">
        更新预设并{actionLabel}
      </button>
      <button className="btn btn-primary" onClick={() => void confirmAsNew()} disabled={disabled} title="把改动存为一个新预设后再开始">
        设为新预设并{actionLabel}
      </button>
    </div>
  ) : (
    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
      <button className="btn" onClick={onCancel} disabled={disabled}>
        取消
      </button>
      <button className="btn btn-primary" onClick={confirmAsIs} disabled={disabled}>
        {busy && <span className="spinner" />}
        确认并{actionLabel}
      </button>
    </div>
  );

  return (
    <Modal title={title} onClose={onCancel} width={900} footer={footer}>
      <div className="alert-banner info">
        {notice ?? (
          <>
            下面是要用于本次任务的预设。可直接确认，也可<b>现场编辑</b>——
            编辑后若不落库，改动<b>仅本次生效</b>；需要长期生效则选「更新预设」或「设为新预设」。
          </>
        )}
      </div>

      {error && (
        <div className="alert-banner danger mt-8">
          {error}
        </div>
      )}

      {loading ? (
        <div className="state-block">
          <div className="spinner-lg" />
          <div>正在加载预设…</div>
        </div>
      ) : !preset ? null : (
        <>
          <div className="field">
            <label>预设名</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label>使用文件类别</label>
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
          </div>
          <div className="field">
            <label>用途说明</label>
            <input
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="一句话说明这个预设做什么"
            />
          </div>

          <PresetTemplateEditor
            reference={templateMd}
            onReferenceChange={setTemplateMd}
            styleRules={styleRules}
            onStyleRulesChange={setStyleRules}
          />

          {dirty && (
            <div className="hint mt-8">
              已修改（未落库）：直接「仅本次生效并{actionLabel}」不会改动预设本身。
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
