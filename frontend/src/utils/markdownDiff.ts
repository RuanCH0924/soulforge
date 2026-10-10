/**
 * 把 unified diff 转成「块级富文本」差异序列。
 *
 * 背景：后端 diff 走 difflib 的 unified 格式，直接展示 `--- / +++ / @@ / +/-`
 * 对非技术用户不友好。这里把它解析后**按 Markdown 渲染**：连续新增行渲染为一个
 * 绿色 HTML 块、删除行渲染为红色块、上下文行原样渲染，用户看到的是「文档前后变化」
 * 而不是 diff 记法。
 *
 * 纯函数、无副作用；Markdown → HTML 统一走 utils/markdown（marked + DOMPurify）。
 */
import { renderMarkdown } from './markdown';
import { parseUnifiedDiff } from './unifiedDiff';
import type { DiffHunk } from './unifiedDiff';

export type RichBlockKind = 'equal' | 'del' | 'add';

export interface RichBlock {
  kind: RichBlockKind;
  /** 原始 markdown 片段（已剥离 diff 前导字符） */
  text: string;
  /** 渲染后的安全 HTML */
  html: string;
}

export interface RichHunk {
  /** 旧侧起始行号（1-based），用于「第 N 行起」定位提示 */
  startLine: number;
  blocks: RichBlock[];
}

const PREFIX_KIND: Record<string, RichBlockKind> = { '+': 'add', '-': 'del', ' ': 'equal' };

/** 把一个 hunk 的正文行按「同类型连续」分组，逐组按 Markdown 渲染为 HTML 块。 */
export function hunkBlocks(hunk: DiffHunk): RichBlock[] {
  const groups: { kind: RichBlockKind; lines: string[] }[] = [];
  for (const line of hunk.lines) {
    const kind = PREFIX_KIND[line[0] ?? ' '] ?? 'equal';
    const last = groups[groups.length - 1];
    if (last && last.kind === kind) last.lines.push(line.slice(1));
    else groups.push({ kind, lines: [line.slice(1)] });
  }
  return (
    groups
      .map((g) => {
        const text = g.lines.join('\n');
        return { kind: g.kind, text, html: text.trim() ? renderMarkdown(text) : '' };
      })
      // 纯空行组不渲染：它只影响排版，不承载信息，渲染出来就是一条空色带
      .filter((b) => b.html !== '')
  );
}

/** 把整份 unified diff 渲染为按 hunk 分组的富文本序列；空 diff → 空数组。 */
export function buildRichDiff(unifiedDiff: string): RichHunk[] {
  if (!unifiedDiff) return [];
  return parseUnifiedDiff(unifiedDiff).hunks.map((h) => ({
    startLine: h.oldStart,
    blocks: hunkBlocks(h),
  }));
}
