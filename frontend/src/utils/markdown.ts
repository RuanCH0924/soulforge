/**
 * Markdown 渲染与回写工具：
 * - markdown → 安全 HTML（marked + DOMPurify），供 WYSIWYG 预览使用
 * - HTML → markdown（turndown），用户在预览中直接编辑后回写为源文本
 */
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import TurndownService from 'turndown';

marked.setOptions({
  gfm: true,
  breaks: true,
  async: false,
});

const turndown = new TurndownService({
  headingStyle: 'atx',
  bulletListMarker: '-',
  codeBlockStyle: 'fenced',
  emDelimiter: '*',
  strongDelimiter: '**',
  blankReplacement: (content: string) => (content ? '\n\n' : '\n'),
});

/** 读取单元格对齐信息（marked 可能写到 align 属性或 text-align 行内样式） */
function cellAlign(cell: Element): string {
  const attr = (cell.getAttribute('align') ?? '').toLowerCase();
  const style = ((cell as HTMLElement).style?.textAlign ?? '').toLowerCase();
  const v = attr || style;
  if (v === 'center') return ':---:';
  if (v === 'right') return '---:';
  if (v === 'left') return ':---';
  return '---';
}

// GFM 表格：marked 渲染出的 <table> 回写为 markdown 表格语法
turndown.addRule('tables', {
  filter: 'table',
  replacement: (_content, node) => {
    const table = node as HTMLTableElement;
    const rows: string[][] = [];
    // 保留列对齐（marked 可能输出 align 属性或 text-align 行内样式）
    let aligns: string[] = [];
    table.querySelectorAll('tr').forEach((tr, rowIndex) => {
      const cells: string[] = [];
      tr.querySelectorAll('th, td').forEach((cell) => {
        cells.push(cell.textContent?.trim() ?? '');
        if (rowIndex === 0) aligns.push(cellAlign(cell));
      });
      if (cells.length > 0) rows.push(cells);
    });
    if (rows.length === 0) return '\n\n';
    const cols = Math.max(...rows.map((r) => r.length));
    const pad = (r: string[]) =>
      Array.from({ length: cols }, (_, i) => r[i] ?? '')
        .map((c) => c.replace(/\|/g, '\\|').replace(/\n/g, ' '))
        .join(' | ');
    const separator = Array.from({ length: cols }, (_, i) => aligns[i] ?? '---').join(' | ');
    const lines = [pad(rows[0]), separator];
    for (const r of rows.slice(1)) lines.push(pad(r));
    return '\n\n' + lines.join('\n') + '\n\n';
  },
});

// GFM 任务列表：保留 `- [ ]` / `- [x]` 标记（turndown 默认会丢弃 checkbox）
turndown.addRule('taskListItems', {
  filter: (node) =>
    node.nodeName === 'LI' && (node as HTMLElement).querySelector('input[type="checkbox"]') !== null,
  replacement: (content, node) => {
    const input = (node as HTMLElement).querySelector('input[type="checkbox"]');
    const box = input?.hasAttribute('checked') ? '[x]' : '[ ]';
    // 去掉 checkbox 自身残留文本，并保持多行内容缩进
    const text = content.replace(/^\s*(✓|✔)?\s*/, '').trim().replace(/\n/g, '\n  ');
    return `- ${box} ${text}\n`;
  },
});

// GFM 删除线
turndown.addRule('strikethrough', {
  filter: ['del', 's'],
  replacement: (content: string) => `~~${content}~~`,
});

// 换行：marked(breaks) 会产出 <br>，回写为 markdown 换行
turndown.addRule('br', {
  filter: 'br',
  replacement: () => '\n',
});

/** 渲染 markdown 为经过白名单过滤的安全 HTML 字符串。 */
export function renderMarkdown(markdown: string): string {
  if (!markdown) return '';
  const raw = marked.parse(markdown, { async: false }) as string;
  // ADD_ATTR: 保留表格列对齐属性，供回写时还原 `:---:` / `---:`
  return DOMPurify.sanitize(raw, { ADD_ATTR: ['align'] });
}

/** 把预览 DOM 的 HTML 转换回 markdown 源文本。 */
export function markdownFromHtml(html: string): string {
  if (!html || !html.trim()) return '';
  return turndown.turndown(html);
}
