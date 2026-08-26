import Editor from '@monaco-editor/react';
import type { OnMount } from '@monaco-editor/react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useSettings } from '../hooks/useSettings';
import { useToast } from '../hooks/useToast';
import type { FileContent, LintWarning } from '../types';
import '../monaco'; // 本地化加载 monaco（不依赖 CDN，避免加载转圈）
import { MarkdownPreview } from './MarkdownPreview';

type MonacoEditor = Parameters<OnMount>[0];
type EditorMode = 'edit' | 'preview';

interface EditorPaneProps {
  agentId: string | null;
  file: FileContent | null;
  content: string;
  onChange: (value: string) => void;
  dirty: boolean;
  saving: boolean;
  /** 文件标识（agent/path），变化时强制重建编辑器 */
  fileKey: string;
  /** 打开文件后要定位到的行号（搜索结果 / lint 跳转） */
  reveal: { line: number; nonce: number } | undefined;
  /** 当前窗口是否为激活窗口（多窗口平铺高亮） */
  active: boolean;
  /** 点击窗口任意位置时激活该窗口 */
  onFocus: () => void;
  /** 关闭该窗口的文档（仅影响当前窗口） */
  onClose: () => void;
  onSave: () => void;
  onHistory: () => void;
  onExport: () => void;
  onApplyPreset: () => void;
  onApplyAI: () => void;
  onLintDone: (count: number) => void;
}

export function EditorPane({
  agentId,
  file,
  content,
  onChange,
  dirty,
  saving,
  fileKey,
  reveal,
  active,
  onFocus,
  onClose,
  onSave,
  onHistory,
  onExport,
  onApplyPreset,
  onApplyAI,
  onLintDone,
}: EditorPaneProps) {
  const { resolvedTheme } = useSettings();
  const { push: toast } = useToast();
  const editorRef = useRef<MonacoEditor | null>(null);
  const [lintOpen, setLintOpen] = useState(false);
  const [linting, setLinting] = useState(false);
  const [warnings, setWarnings] = useState<LintWarning[]>([]);
  const [mode, setMode] = useState<EditorMode>('preview');

  // 打开文件后定位到指定行
  useEffect(() => {
    if (!reveal || !fileKey || !editorRef.current) return;
    const line = reveal.line;
    const ed = editorRef.current;
    ed.setPosition({ lineNumber: line, column: 1 });
    ed.revealPositionInCenter({ lineNumber: line, column: 1 });
    ed.focus();
  }, [reveal, fileKey]);

  // 切换文件时重置 lint 面板，并默认回到预览模式
  useEffect(() => {
    setLintOpen(false);
    setWarnings([]);
    setMode('preview');
  }, [fileKey]);

  const handleMount: OnMount = (ed) => {
    editorRef.current = ed;
    if (reveal && fileKey && reveal.line) {
      ed.setPosition({ lineNumber: reveal.line, column: 1 });
      ed.revealPositionInCenter({ lineNumber: reveal.line, column: 1 });
    }
  };

  async function runLint() {
    if (!agentId || !file) return;
    setLinting(true);
    setLintOpen(true);
    try {
      const res = await api.lintFile(agentId, file.path);
      setWarnings(res.warnings);
      onLintDone(res.warnings.length);
      if (res.warnings.length === 0) {
        toast('检查完成：没有发现 lint 警告', 'success');
      }
    } catch (e) {
      toast(`检查失败：${(e as Error).message}`, 'error');
    } finally {
      setLinting(false);
    }
  }

  function jumpTo(line?: number | null) {
    if (line == null || !editorRef.current) return;
    const ed = editorRef.current;
    ed.setPosition({ lineNumber: line, column: 1 });
    ed.revealPositionInCenter({ lineNumber: line, column: 1 });
    ed.focus();
  }

  if (!agentId || !file) {
    return (
      <section className="editor-window" onClick={onFocus}>
        <div className="pane-header">编辑器</div>
        <div className="editor-empty">在左侧选择 Agent 和文件开始编辑</div>
      </section>
    );
  }

  return (
    <section className={`editor-window${active ? ' active' : ''}`} onClick={onFocus}>
      <div className="editor-pathbar">
        <span className="path" title={file.path}>{file.path}</span>
        <span className={`role-badge role-${file.role}`}>{file.role}</span>
        {dirty && <span className="dirty-mark">● 未保存</span>}
        <button
          type="button"
          className="editor-close"
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
          title="关闭文档"
          aria-label="关闭文档"
        >
          ×
        </button>
      </div>

      <div className="editor-toolbar">
        <button className="btn btn-primary" onClick={onSave} disabled={!dirty || saving}>
          {saving && <span className="spinner" />}
          保存
        </button>
        <button className="btn" onClick={onHistory}>
          历史
        </button>
        <button className="btn" onClick={onApplyPreset} title="应用文档预设：按预设结构补齐缺失章节，生成 diff 预览后确认写入">
          应用预设
        </button>
        <button className="btn" onClick={onApplyAI} title="AI 自动整理：选预设+LLM Provider，AI 重写后生成 diff 预览，确认后写入">
          AI 整理
        </button>
        <button className="btn" onClick={runLint} disabled={linting}>
          {linting && <span className="spinner" />}
          检查
        </button>
        <button className="btn" onClick={onExport}>
          导出
        </button>
        <div className="mode-toggle" role="tablist" aria-label="编辑器模式">
          <button
            type="button"
            className={mode === 'edit' ? 'active' : ''}
            onClick={() => setMode('edit')}
          >
            编辑
          </button>
          <button
            type="button"
            className={mode === 'preview' ? 'active' : ''}
            onClick={() => setMode('preview')}
          >
            预览
          </button>
        </div>
        <div className="right">
          {warnings.length > 0 && (
            <button className="btn" onClick={() => setLintOpen(true)}>
              警告 {warnings.length}
            </button>
          )}
          {mode === 'preview' && (
            <span className="muted" style={{ fontSize: 11 }}>
              预览中可直接编辑，实时同步 Markdown
            </span>
          )}
          <span className="muted" style={{ fontSize: 11 }}>
            Ctrl+S 保存
          </span>
        </div>
      </div>

      <div className="editor-host">
        {mode === 'edit' ? (
          <Editor
            key={fileKey}
            height="100%"
            language="markdown"
            theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
            value={content}
            onChange={(v) => onChange(v ?? '')}
            onMount={handleMount}
            loading={<div className="state-block"><div className="spinner-lg" /><div>正在加载编辑器...</div></div>}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              wordWrap: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
              tabSize: 2,
              scrollbar: { verticalScrollbarSize: 9 },
            }}
          />
        ) : (
          <MarkdownPreview markdown={content} onChange={onChange} />
        )}

        {lintOpen && (
          <div className="lint-panel">
            <div className="lint-panel-header">
              <span>Lint 检查{warnings.length > 0 ? `（${warnings.length} 条警告）` : ''}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setLintOpen(false)}>
                收起
              </button>
            </div>
            <div className="lint-panel-body">
              {linting ? (
                <div className="state-block">
                  <div className="spinner-lg" />
                  <div>正在检查...</div>
                </div>
              ) : warnings.length === 0 ? (
                <div className="lint-empty">✓ 没有发现 lint 警告</div>
              ) : (
                warnings.map((w, i) => (
                  <div
                    key={`${w.rule_id}-${i}`}
                    className="lint-item"
                    onClick={() => jumpTo(w.line_number)}
                    title="点击跳转到对应行"
                  >
                    <div className="lint-rule">
                      <span>{w.rule_name}</span>
                      <span className="muted" style={{ fontWeight: 400 }}>({w.rule_id})</span>
                    </div>
                    <div className="lint-loc">
                      {w.file_path}
                      {w.line_number != null ? ` : 第 ${w.line_number} 行` : ''}
                    </div>
                    {w.line_content && <div className="lint-line">{w.line_content}</div>}
                    <div className="lint-sugg">建议：{w.suggestion}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
