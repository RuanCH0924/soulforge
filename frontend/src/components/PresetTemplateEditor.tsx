import { useState } from 'react';
import { renderMarkdown } from '../utils/markdown';

/**
 * 共享的「预设模板编辑器」——只保留两项核心配置：
 *
 * 1. **预设参考文档**（Markdown）：承载示例与表格，可预览；大模型据此修改目标文档；
 * 2. **修改要求**（逐条自由文本，可选）：交给大模型遵守，不做机械校验。
 *
 * 章节以**参考文档的标题为唯一真相**（没有独立的章节清单 / 顺序 / 可选配置），
 * 也不暴露任何高级排版开关（排版键由后端全局默认承担）。
 */
interface PresetTemplateEditorProps {
  /** 预设参考文档（Markdown 正文） */
  reference: string;
  onReferenceChange: (value: string) => void;
  /** 可选：修改要求（大模型预设 WORKLOG / SUMMARY 使用） */
  styleRules?: string;
  onStyleRulesChange?: (value: string) => void;
  styleRulesLabel?: string;
}

export function PresetTemplateEditor({
  reference,
  onReferenceChange,
  styleRules,
  onStyleRulesChange,
  styleRulesLabel = '修改要求（每行一条）',
}: PresetTemplateEditorProps) {
  const [preview, setPreview] = useState(false);

  return (
    <>
      <div className="field">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <label style={{ marginBottom: 0 }}>预设参考文档</label>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setPreview((v) => !v)}
            title={preview ? '切换到 Markdown 编辑' : '渲染预览参考文档'}
          >
            {preview ? '编辑' : '预览'}
          </button>
        </div>
        {preview ? (
          <div
            className="md-preview md-preview-flow"
            style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '8px 12px', maxHeight: 320, overflowY: 'auto' }}
            dangerouslySetInnerHTML={{ __html: renderMarkdown(reference) }}
          />
        ) : (
          <textarea
            className="input"
            rows={14}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            value={reference}
            onChange={(e) => onReferenceChange(e.target.value)}
            spellCheck={false}
            placeholder={'# 文档标题\n\n## 一、第一个章节\n\n- 示例内容'}
          />
        )}
        <div className="hint" style={{ marginTop: 4 }}>
          写出期望的章节标题、示例内容与表格；大模型会照此结构与写法修改目标文档。
        </div>
      </div>

      {onStyleRulesChange && (
        <div className="field">
          <label>{styleRulesLabel}</label>
          <textarea
            className="input"
            rows={8}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}
            value={styleRules ?? ''}
            onChange={(e) => onStyleRulesChange(e.target.value)}
            spellCheck={false}
            placeholder={'例如：按时间倒序归档\n只保留结论，不保留过程'}
          />
          <div className="hint" style={{ marginTop: 4 }}>
            每行一条，空行会被忽略；这些要求会交给大模型遵守。
          </div>
        </div>
      )}
    </>
  );
}
