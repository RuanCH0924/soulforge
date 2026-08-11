/**
 * Markdown 所见即所得预览。
 *
 * 以 contentEditable 承载渲染后的 HTML：
 * - 输入时把 DOM 内容经 turndown 转回 markdown 并回调 onChange（实时同步源文本），
 *   期间不重设 innerHTML，避免光标跳动；
 * - 外部内容变化（切换文件 / 保存回填 / 回滚）时才会重新渲染 DOM。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { markdownFromHtml, renderMarkdown } from '../utils/markdown';

interface MarkdownPreviewProps {
  markdown: string;
  onChange: (md: string) => void;
}

export function MarkdownPreview({ markdown, onChange }: MarkdownPreviewProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [html, setHtml] = useState<string>(() => renderMarkdown(markdown));
  // 最近一次推给父组件的 markdown（用于识别“外部变化”，避免自己触发重渲染）
  const lastPushedRef = useRef<string>(markdown);

  // 外部内容变化时重新渲染
  useEffect(() => {
    if (markdown !== lastPushedRef.current) {
      setHtml(renderMarkdown(markdown));
      lastPushedRef.current = markdown;
    }
  }, [markdown]);

  const handleInput = useCallback(() => {
    const el = hostRef.current;
    if (!el) return;
    const md = markdownFromHtml(el.innerHTML);
    lastPushedRef.current = md;
    onChange(md);
  }, [onChange]);

  return (
    <div
      ref={hostRef}
      className="md-preview"
      contentEditable
      suppressContentEditableWarning
      spellCheck={false}
      data-placeholder="暂无内容，开始输入 Markdown…"
      dangerouslySetInnerHTML={{ __html: html }}
      onInput={handleInput}
    />
  );
}
