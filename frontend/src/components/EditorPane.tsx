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
  onSave: () => void;
  onHistory: () => void;
  onExport: () => void;
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
  onSave,
  onHistory,
  onExport,
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
      <section className="editor-pane">
        <div className="pane-header">编辑器</div>
        <div className="editor-empty">在左侧选择 Agent 和文件开始编辑</div>
      </section>
    );
  }

  return (
    <section className="editor-pane">
      <div className="editor-pathbar">
        <span className="path" title={file.path}>{file.path}</span>
        <span className={`role-badge role-${file.role}`}>{file.role}</span>
        {dirty && <span className="dirty-mark">● 未保存</span>}
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

      <div className="editor-toolbar">
        <button className="btn btn-primary" onClick={onSave} disabled={!dirty || saving}>
          {saving && <span className="spinner" />}
          保存
        </button>
        <button className="btn" onClick={onHistory}>
          历史
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
    </section>
  );
}
