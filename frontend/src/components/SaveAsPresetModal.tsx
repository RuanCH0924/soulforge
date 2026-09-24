import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { useToast } from '../hooks/useToast';
import type { PresetTargetType } from '../types';
import { scanHeadings } from '../utils/markdown';
import { Modal } from './Modal';

interface SaveAsPresetModalProps {
  agentId: string;
  filePath: string;
  /** 编辑器当前内容（含未保存修改），作为预设模板正文 */
  content: string;
  onClose: () => void;
}

const TARGET_TYPES: PresetTargetType[] = [
  'SOUL', 'AGENTS', 'MEMORY', 'USER', 'IDENTITY', 'TOOLS', 'WORKLOG', 'ANY',
];

/** 后端 MAX_TEMPLATE_BYTES：模板全文会注入 AI 提示词，超限由前后端双重拦截 */
const MAX_TEMPLATE_BYTES = 30 * 1024;

const HEADING_LEVELS = [1, 2, 3, 4];

/** 文件名 / 路径 → 推断适用文件类型 */
function inferTargetType(filePath: string): PresetTargetType {
  const base = (filePath.split('/').pop() ?? filePath).toLowerCase();
  if (/^\d{4}-\d{2}-\d{2}\.md$/.test(base) || filePath.startsWith('memory/')) return 'WORKLOG';
  const upper = base.replace(/\.md$/, '').toUpperCase();
  return (TARGET_TYPES as string[]).includes(upper) && upper !== 'ANY'
    ? (upper as PresetTargetType)
    : 'ANY';
}

/** 从文档标题推断章节层级：出现次数最多的层级（并列时取更靠前/更浅的层级） */
function inferSectionLevel(content: string): number {
  const counts = new Map<number, number>();
  scanHeadings(content).forEach((h) => counts.set(h.level, (counts.get(h.level) ?? 0) + 1));
  let best = 2;
  let bestCount = 0;
  [...counts.entries()]
    .sort((a, b) => a[0] - b[0])
    .forEach(([level, count]) => {
      if (count > bestCount) {
        best = level;
        bestCount = count;
      }
    });
  return best;
}

/** 各级标题清单（按文档顺序去重） */
function headingsAtLevel(content: string, level: number): string[] {
  const out: string[] = [];
  scanHeadings(content).forEach((h) => {
    if (h.level === level && !out.includes(h.text)) out.push(h.text);
  });
  return out;
}

function utf8Size(text: string): number {
  return new TextEncoder().encode(text).length;
}

/** 「设为预设」：把当前文档存为文档预设（模板正文 = 当前文档，规则参数由用户填写） */
export function SaveAsPresetModal({
  agentId,
  filePath,
  content,
  onClose,
}: SaveAsPresetModalProps) {
  const { push: toast } = useToast();
  const [name, setName] = useState(() => {
    const base = (filePath.split('/').pop() ?? filePath).replace(/\.md$/i, '');
    return `${base} 结构`;
  });
  const [targetType, setTargetType] = useState<PresetTargetType>(() => inferTargetType(filePath));
  const [description, setDescription] = useState('');
  const [level, setLevel] = useState(() => inferSectionLevel(content));
  const [checked, setChecked] = useState<string[]>(() => headingsAtLevel(content, inferSectionLevel(content)));
  const [strictOrder, setStrictOrder] = useState(true);
  const [requireFrontmatter, setRequireFrontmatter] = useState(false);
  const [saving, setSaving] = useState(false);

  const detected = useMemo(() => headingsAtLevel(content, level), [content, level]);
  // 与 detected 取交集后再计数：切换层级的那一帧 checked 仍是旧层级的值
  const selected = useMemo(
    () => detected.filter((t) => checked.includes(t)).length,
    [detected, checked],
  );
  const size = useMemo(() => utf8Size(content), [content]);
  const tooLarge = size > MAX_TEMPLATE_BYTES;

  // 切换章节层级 → 重新扫描，默认全选
  useEffect(() => {
    setChecked(headingsAtLevel(content, level));
  }, [content, level]);

  const toggle = (title: string) => {
    setChecked((prev) => (prev.includes(title) ? prev.filter((t) => t !== title) : [...prev, title]));
  };

  const canSubmit = name.trim().length > 0 && selected > 0 && !tooLarge && !saving;

  const submit = async () => {
    if (!canSubmit) return;
    setSaving(true);
    try {
      const preset = await api.createPresetFromDocument({
        name: name.trim(),
        target_file_type: targetType,
        content,
        description: description.trim() || undefined,
        section_heading_level: level,
        required_sections: checked,
        section_order: strictOrder ? 'strict' : 'loose',
        require_frontmatter: requireFrontmatter,
      });
      toast(`已保存预设「${preset.name}」（${preset.sections_json.length} 个必填章节）`, 'success');
      onClose();
    } catch (e) {
      toast(`保存预设失败：${(e as Error).message}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="设为预设"
      onClose={onClose}
      width={720}
      footer={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose} disabled={saving}>
            取消
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={!canSubmit}>
            {saving && <span className="spinner" />}
            保存预设
          </button>
        </div>
      }
    >
      <div className="alert-banner info">
        把当前文档保存为文档预设（结构模板）：内容将作为模板正文与章节骨架，
        之后可在「应用预设 / AI 整理」中复用它统一其他 Agent 的同名文档。
      </div>

      <div className="field">
        <label>来源文档</label>
        <div className="mono" style={{ fontSize: 12 }}>
          {agentId}/{filePath}
          <span className="muted" style={{ marginLeft: 8 }}>
            {size.toLocaleString()} 字节 · {level} 级标题 {detected.length} 个
          </span>
        </div>
      </div>

      {tooLarge && (
        <div className="alert-banner danger">
          文档 {Math.round(size / 1024)}KB 超过 {MAX_TEMPLATE_BYTES / 1024}KB 上限：模板全文会注入 AI
          提示词，Tokens 成本与质量风险过高，请先精简文档。
        </div>
      )}

      <div className="field">
        <label>预设名称</label>
        <input
          className="input"
          placeholder="如：SOUL.md 标准结构"
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
      </div>

      <div className="field">
        <label>用途说明（可选）</label>
        <input
          className="input"
          placeholder="如：由 main/SOUL.md 提取的四段式结构"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      <div className="field">
        <label>章节标题层级</label>
        <select className="select" value={level} onChange={(e) => setLevel(Number(e.target.value))}>
          {HEADING_LEVELS.map((lv) => (
            <option key={lv} value={lv}>
              {'#'.repeat(lv)}（{lv} 级标题）
            </option>
          ))}
        </select>
        <div className="hint">该层级的标题构成预设的章节清单；切换层级会重新扫描文档标题。</div>
      </div>

      <div className="section-title">
        必填章节（{selected}/{detected.length}）
      </div>
      {detected.length === 0 ? (
        <div className="alert-banner warning">
          文档中未发现该层级的标题，请改用其他「章节标题层级」（或先给文档补上标题）。
        </div>
      ) : (
        <div className="checkbox-grid" style={{ maxHeight: 220 }}>
          {detected.map((title) => (
            <label key={title} className="checkbox-row" title={title}>
              <input
                type="checkbox"
                checked={checked.includes(title)}
                onChange={() => toggle(title)}
              />
              <span className="mono" style={{ minWidth: 0 }}>{title}</span>
            </label>
          ))}
        </div>
      )}
      <div className="hint">勾选的章节会写入预设规则：应用该预设时缺失的章节会被补齐；未勾选的不作要求。</div>

      <div className="field" style={{ marginTop: 12 }}>
        <label className="checkbox-row" style={{ fontWeight: 400 }}>
          <input
            type="checkbox"
            checked={strictOrder}
            onChange={(e) => setStrictOrder(e.target.checked)}
          />
          <span>严格要求章节顺序（勾选后顺序错误会被格式校验拦下）</span>
        </label>
        <label className="checkbox-row" style={{ fontWeight: 400 }}>
          <input
            type="checkbox"
            checked={requireFrontmatter}
            onChange={(e) => setRequireFrontmatter(e.target.checked)}
          />
          <span>要求文档带 YAML frontmatter（以 --- 开头）</span>
        </label>
      </div>

      <div className="hint">保存后可在「系统配置 → 文档预设」中查看、编辑版本与回溯。</div>
    </Modal>
  );
}
