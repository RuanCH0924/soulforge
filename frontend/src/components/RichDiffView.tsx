/**
 * 富文本差异视图：把 unified diff 渲染成「文档前后变化」。
 *
 * - `identical=true` → 不渲染空差异框，给出明确结论，并在仅存在格式噪声时列出被忽略的噪声类型；
 * - 否则按 hunk 渲染：新增块（绿）/ 删除块（红）/ 上下文块（原样），内容按 Markdown 渲染；
 * - diff 记法（`@@` 等）不直接展示，「原始差异」默认折叠，需要时可展开。
 */
import { useMemo, useState } from 'react';
import { buildRichDiff } from '../utils/markdownDiff';
import type { RichBlock } from '../utils/markdownDiff';

/** 噪声类型 → 可读名称（与 backend diff_service._NOISE_STAGES 对应） */
const NOISE_LABELS: Record<string, string> = {
  bom: 'UTF-8 BOM',
  line_ending: '换行符风格（CRLF/LF）',
  invisible_char: '零宽 / 不可见字符',
  space_like_char: '全角空格 / 不换行空格',
  trailing_whitespace: '行尾空白',
  multiple_spaces: '连续空白 / Tab 缩进',
  blank_lines: '多余空行',
  edge_blank_lines: '文首 / 文末空行',
};

export function noiseLabel(kinds: string[]): string {
  return kinds.map((k) => NOISE_LABELS[k] ?? k).join('、');
}

/** 渲染一组富文本差异块（新增 / 删除 / 上下文）。供 RichDiffView 与 DiffHunkPicker 复用。 */
export function RichDiffBlocks({ blocks }: { blocks: RichBlock[] }) {
  return (
    <>
      {blocks.map((b, i) => (
        <div key={i} className={`rich-diff-block ${b.kind}`}>
          <span className="rich-diff-gutter" aria-hidden="true">
            {b.kind === 'add' ? '+' : b.kind === 'del' ? '−' : ''}
          </span>
          <div
            className="md-preview md-preview-flow rich-diff-content"
            dangerouslySetInnerHTML={{ __html: b.html }}
          />
        </div>
      ))}
    </>
  );
}

interface RichDiffViewProps {
  /** 后端给出的 unified diff（空字符串 = 无差异） */
  unifiedDiff: string;
  /** 有效内容是否一致（一致时不渲染差异框） */
  identical?: boolean;
  noiseKinds?: string[];
  /** 一致时的结论文案 */
  identicalText?: string;
  /** 无差异内容时的占位文案 */
  emptyText?: string;
  /** 内容区高度上限（超出滚动），默认 55vh */
  maxHeight?: string;
  /** 隐藏「原始差异」开关（窄场景如回滚确认） */
  hideRaw?: boolean;
}

export function RichDiffView({
  unifiedDiff,
  identical = false,
  noiseKinds = [],
  identicalText = '内容完全一致，无差异',
  emptyText = '无差异内容',
  maxHeight = '55vh',
  hideRaw = false,
}: RichDiffViewProps) {
  const [showRaw, setShowRaw] = useState(false);
  const hunks = useMemo(() => buildRichDiff(unifiedDiff), [unifiedDiff]);

  if (identical) {
    return (
      <div className="diff-identical">
        <span className="diff-identical-badge">✓ {identicalText}</span>
        {noiseKinds.length > 0 && (
          <span className="diff-noise-note">
            原始文件仅存在格式噪声差异（已忽略）：{noiseLabel(noiseKinds)}
          </span>
        )}
      </div>
    );
  }

  if (hunks.length === 0) {
    return (
      <div className="diff-identical">
        <span className="hint">{emptyText}</span>
      </div>
    );
  }

  const changedBlocks = hunks.reduce(
    (n, h) => n + h.blocks.filter((b) => b.kind !== 'equal').length,
    0,
  );

  return (
    <div className="rich-diff">
      <div className="rich-diff-bar">
        <span className="muted text-xs">
          {hunks.length} 处改动 · {changedBlocks} 个变更块
        </span>
        {!hideRaw && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setShowRaw((v) => !v)}
          >
            {showRaw ? '收起原始差异' : '原始差异'}
          </button>
        )}
      </div>
      <div className="rich-diff-body" style={{ maxHeight }}>
        {hunks.map((h, i) => (
          <div key={i} className="rich-diff-hunk">
            {i > 0 && <div className="rich-diff-hunk-label">⋯ 第 {h.startLine} 行起</div>}
            <RichDiffBlocks blocks={h.blocks} />
          </div>
        ))}
        {showRaw && <pre className="diff-view rich-diff-raw">{unifiedDiff}</pre>}
      </div>
    </div>
  );
}
