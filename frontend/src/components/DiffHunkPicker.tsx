import { hunkBlocks } from '../utils/markdownDiff';
import type { DiffHunk } from '../utils/unifiedDiff';
import { RichDiffBlocks } from './RichDiffView';

interface DiffHunkPickerProps {
  hunks: DiffHunk[];
  /** 与 hunks 等长：每一项表示该块是否接受 */
  accepted: boolean[];
  onChange: (next: boolean[]) => void;
  /** 无 hunk 时的占位文案 */
  emptyText?: string;
  maxHeight?: string;
}

/**
 * 差异「按块接受」视图：每个 hunk 一个复选框，可整块接受 / 拒绝。
 * 视觉上被拒绝的块整体降低不透明度；每个块的内容按 Markdown 渲染（不展示 @@ 记法）。
 */
export function DiffHunkPicker({
  hunks,
  accepted,
  onChange,
  emptyText = '（内容已一致，无需改动）',
  maxHeight = '55vh',
}: DiffHunkPickerProps) {
  if (hunks.length === 0) {
    return (
      <div className="diff-identical">
        <span className="hint">{emptyText}</span>
      </div>
    );
  }

  const acceptedCount = accepted.filter(Boolean).length;

  const toggle = (i: number) => {
    const next = accepted.slice();
    next[i] = !next[i];
    onChange(next);
  };

  return (
    <div className="hunk-picker" style={{ maxHeight }}>
      <div className="hunk-picker-bar">
        <span className="muted text-sm">
          已接受 {acceptedCount} / 共 {hunks.length} 块
        </span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange(hunks.map(() => true))}>
          全部接受
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange(hunks.map(() => false))}>
          全部拒绝
        </button>
      </div>
      {hunks.map((h, i) => (
        <div key={i} className={`hunk-item${accepted[i] ? ' accepted' : ''}`}>
          <label className="hunk-head">
            <input type="checkbox" checked={accepted[i]} onChange={() => toggle(i)} />
            <span className="muted text-xs">第 {h.oldStart} 行起</span>
          </label>
          <div className="hunk-body">
            <RichDiffBlocks blocks={hunkBlocks(h)} />
          </div>
        </div>
      ))}
    </div>
  );
}
