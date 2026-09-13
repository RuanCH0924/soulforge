import Editor from '@monaco-editor/react';
import type { OnMount } from '@monaco-editor/react';
import { KeyCode, KeyMod, MarkerSeverity, Selection, editor as monacoEditor } from 'monaco-editor';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import { useSettings } from '../hooks/useSettings';
import { useToast } from '../hooks/useToast';
import type { FileContent, LintWarning } from '../types';
import { formatClock } from '../utils/format';
import '../monaco'; // 本地化加载 monaco（不依赖 CDN，避免加载转圈）
import { Dropdown } from './Dropdown';
import { MarkdownPreview } from './MarkdownPreview';

type MonacoEditor = Parameters<OnMount>[0];
type EditorMode = 'edit' | 'preview';

/** 视图模式偏好（全局记忆，不再每次切文件重置） */
const VIEW_MODE_KEY = 'soulforge.editor.view';

/** 文档 token 估算的提示阈值（超过则状态条转为警告色） */
const TOKEN_WARN_THRESHOLD = 2000;

interface EditorPaneProps {
  agentId: string | null;
  file: FileContent | null;
  content: string;
  onChange: (value: string) => void;
  dirty: boolean;
  saving: boolean;
  /** 最近一次成功保存的时间戳（M-04：路径栏展示「已保存 HH:mm:ss」） */
  savedAt?: number | undefined;
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
  /** 放弃未保存修改，重新从磁盘加载该文档 */
  onReload: () => void;
  onHistory: () => void;
  onExport: () => void;
  onApplyPreset: () => void;
  onApplyAI: () => void;
  onLintDone: (count: number) => void;
}

/** 读取视图模式偏好；默认 edit（源码编辑），避免预览往返静默改写 Markdown 格式 */
function loadViewMode(): EditorMode {
  try {
    return window.localStorage.getItem(VIEW_MODE_KEY) === 'preview' ? 'preview' : 'edit';
  } catch {
    return 'edit';
  }
}

/** 粗略估算 token 数：CJK 字符约 1 token/字，其余按 4 字符/token */
function estimateTokens(text: string): number {
  const cjk = (text.match(/[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\uAC00-\uD7AF]/g) ?? []).length;
  return Math.round(cjk + (text.length - cjk) / 4);
}

interface OutlineItem {
  level: number;
  text: string;
  line: number;
}

/** 解析 Markdown 标题大纲（跳过围栏代码块内的 `#`） */
function parseOutline(md: string): OutlineItem[] {
  const out: OutlineItem[] = [];
  let inFence = false;
  md.split('\n').forEach((raw, i) => {
    const line = raw.trimEnd();
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence;
      return;
    }
    if (inFence) return;
    const m = /^(#{1,6})\s+(.+)$/.exec(line);
    if (m) out.push({ level: m[1].length, text: m[2].replace(/\s*#+\s*$/, '').trim(), line: i + 1 });
  });
  return out;
}

/** 用标记包裹/取消包裹选区（加粗、斜体） */
function toggleWrap(ed: MonacoEditor, marker: string): void {
  const model = ed.getModel();
  const sel = ed.getSelection();
  if (!model || !sel) return;
  const text = model.getValueInRange(sel);
  const m = marker.length;
  const already = text.length >= m * 2 && text.startsWith(marker) && text.endsWith(marker);
  const next = already ? text.slice(m, text.length - m) : `${marker}${text}${marker}`;
  ed.executeEdits('soulforge-format', [{ range: sel, text: next, forceMoveMarkers: true }]);
  const line = sel.startLineNumber;
  const col = sel.startColumn;
  if (text.length === 0) {
    ed.setPosition({ lineNumber: line, column: col + m });
  } else {
    const offset = already ? 0 : m;
    ed.setSelection(new Selection(line, col + offset, line, col + offset + text.length));
  }
  ed.focus();
}

export function EditorPane({
  agentId,
  file,
  content,
  onChange,
  dirty,
  saving,
  savedAt,
  fileKey,
  reveal,
  active,
  onFocus,
  onClose,
  onSave,
  onReload,
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
  const [mode, setMode] = useState<EditorMode>(loadViewMode);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const [cursor, setCursor] = useState({ line: 1, column: 1, selected: 0 });

  const modeRef = useRef<EditorMode>(mode);
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);
  /** 切模式后需要补跳的行号 / 是否补开查找框 */
  const pendingJumpRef = useRef<number | null>(null);
  const pendingFindRef = useRef(false);
  const warnIdxRef = useRef(-1);
  /** 预览模式 DOM 宿主（供大纲在预览中滚动定位） */
  const previewHostRef = useRef<HTMLDivElement | null>(null);

  const outline = useMemo(() => parseOutline(content), [content]);
  const tokens = useMemo(() => estimateTokens(content), [content]);

  function switchMode(next: EditorMode) {
    setMode(next);
    try {
      window.localStorage.setItem(VIEW_MODE_KEY, next);
    } catch {
      // localStorage 不可用时静默降级
    }
  }

  /** 在编辑器中定位到指定行 */
  const applyJump = useCallback((line: number) => {
    const ed = editorRef.current;
    if (!ed) return;
    ed.setPosition({ lineNumber: line, column: 1 });
    ed.revealPositionInCenter({ lineNumber: line, column: 1 });
    ed.focus();
  }, []);

  /** 预览模式：滚动到第 index 个标题（顺序与大纲一致）；DOM 对不上时回退为切回编辑模式补跳 */
  const scrollPreviewTo = useCallback((index: number, line: number) => {
    const heads = previewHostRef.current?.querySelectorAll('h1, h2, h3, h4, h5, h6');
    const el = heads?.[index];
    if (el instanceof HTMLElement) {
      el.scrollIntoView({ block: 'start', behavior: 'smooth' });
      return;
    }
    pendingJumpRef.current = line;
    switchMode('edit');
  }, []);

  /** 跳转到某行；预览模式下传 outlineIndex 时直接在预览内滚动，不切回编辑模式 */
  const jumpTo = useCallback(
    (line?: number | null, outlineIndex?: number) => {
      if (line == null) return;
      if (modeRef.current !== 'edit') {
        if (outlineIndex != null) {
          scrollPreviewTo(outlineIndex, line);
          return;
        }
        pendingJumpRef.current = line;
        switchMode('edit');
        return;
      }
      applyJump(line);
    },
    [applyJump, scrollPreviewTo],
  );

  // 打开文件后定位到指定行
  useEffect(() => {
    if (!reveal || !fileKey || !editorRef.current) return;
    applyJump(reveal.line);
  }, [reveal, fileKey, applyJump]);

  // 切换文件时重置 lint / 大纲面板（不再重置视图模式，尊重用户偏好）
  useEffect(() => {
    setLintOpen(false);
    setOutlineOpen(false);
    setWarnings([]);
    warnIdxRef.current = -1;
  }, [fileKey]);

  const handleMount: OnMount = (ed) => {
    editorRef.current = ed;
    ed.onDidChangeCursorPosition((e) =>
      setCursor((c) => ({ ...c, line: e.position.lineNumber, column: e.position.column })),
    );
    ed.onDidChangeCursorSelection((e) => {
      const model = ed.getModel();
      setCursor((c) => ({ ...c, selected: model ? model.getValueLengthInRange(e.selection) : 0 }));
    });
    // Markdown 格式化快捷键（Ctrl/Cmd+B 加粗、Ctrl/Cmd+I 斜体）
    ed.addCommand(KeyMod.CtrlCmd | KeyCode.KeyB, () => toggleWrap(ed, '**'));
    ed.addCommand(KeyMod.CtrlCmd | KeyCode.KeyI, () => toggleWrap(ed, '*'));
    const pending = pendingJumpRef.current ?? reveal?.line ?? null;
    if (pending != null) {
      pendingJumpRef.current = null;
      applyJump(pending);
    }
    if (pendingFindRef.current) {
      pendingFindRef.current = false;
      void ed.getAction('actions.find')?.run();
    }
  };

  // lint 警告 → Monaco 行内标记（波浪线 + 悬浮提示 + 滚动条标记）
  useEffect(() => {
    const model = editorRef.current?.getModel();
    if (!model) return;
    const markers = warnings.map((w) => {
      const line = w.line_number ?? 1;
      return {
        severity: MarkerSeverity.Warning,
        message: `${w.rule_name}（${w.rule_id}）：${w.suggestion}`,
        startLineNumber: line,
        startColumn: 1,
        endLineNumber: line,
        endColumn: Math.max(1, (w.line_content?.length ?? 0) + 1),
        source: 'soulforge-lint',
      };
    });
    monacoEditor.setModelMarkers(model, 'soulforge-lint', markers);
  }, [warnings, mode, fileKey]);

  // F8 / Shift+F8：在 lint 警告间跳转（仅激活窗口响应）
  useEffect(() => {
    if (!active) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'F8' && warnings.length > 0) {
        e.preventDefault();
        const dir = e.shiftKey ? -1 : 1;
        let idx = warnIdxRef.current + dir;
        if (idx < 0) idx = warnings.length - 1;
        if (idx >= warnings.length) idx = 0;
        warnIdxRef.current = idx;
        jumpTo(warnings[idx].line_number);
        return;
      }
      // 预览模式下 Ctrl/Cmd+F：切回编辑模式并打开查找框（预览是 contentEditable，无查找能力）
      if (e.key.toLowerCase() === 'f' && (e.ctrlKey || e.metaKey) && modeRef.current === 'preview') {
        e.preventDefault();
        pendingFindRef.current = true;
        switchMode('edit');
        return;
      }
      // Ctrl/Cmd+Shift+O：切换文档大纲
      if (e.key.toLowerCase() === 'o' && (e.ctrlKey || e.metaKey) && e.shiftKey) {
        e.preventDefault();
        setOutlineOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [active, warnings, jumpTo]);

  async function runLint() {
    if (!agentId || !file) return;
    setLinting(true);
    setLintOpen(true);
    try {
      const res = await api.lintFile(agentId, file.path);
      setWarnings(res.warnings);
      onLintDone(res.warnings.length);
      warnIdxRef.current = -1;
      if (res.warnings.length === 0) {
        toast('检查完成：没有发现 lint 警告', 'success');
      }
    } catch (e) {
      toast(`检查失败：${(e as Error).message}`, 'error');
    } finally {
      setLinting(false);
    }
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
        {dirty ? (
          <span className="dirty-mark">● 未保存</span>
        ) : (
          savedAt != null && <span className="saved-mark">已保存 {formatClock(savedAt)}</span>
        )}
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
        <button
          className="btn"
          onClick={onReload}
          disabled={saving}
          title="放弃未保存的修改，重新从磁盘加载该文档"
        >
          重新加载
        </button>
        <button className="btn" onClick={onHistory}>
          历史
        </button>
        <button className="btn" onClick={runLint} disabled={linting} title="检查当前文档（可选，警告会标在正文行内）">
          {linting && <span className="spinner" />}
          检查
        </button>
        <Dropdown
          trigger={<button className="btn" type="button">整理 ▾</button>}
          items={[
            { label: '应用预设', hint: '补齐缺失章节', onSelect: onApplyPreset },
            { label: 'AI 整理', hint: 'LLM 重写后 diff 确认', onSelect: onApplyAI },
            { label: '导出当前文件', onSelect: onExport },
          ]}
        />
        <button
          className="btn"
          onClick={() => setOutlineOpen((v) => !v)}
          title="文档大纲：按标题跳转（Ctrl+Shift+O）"
        >
          大纲
        </button>
        <div className="mode-toggle" role="tablist" aria-label="编辑器模式">
          <button
            type="button"
            className={mode === 'edit' ? 'active' : ''}
            onClick={() => switchMode('edit')}
            title="源码编辑：所见即所存，不会改动 Markdown 格式"
          >
            编辑
          </button>
          <button
            type="button"
            className={mode === 'preview' ? 'active' : ''}
            onClick={() => switchMode('preview')}
            title="预览编辑：可视化编辑，保存时会规范化 Markdown 格式"
          >
            预览
          </button>
        </div>
        <div className="right">
          {warnings.length > 0 && (
            <button className="btn" onClick={() => setLintOpen(true)} title="查看警告列表（F8 跳到下一条）">
              警告 {warnings.length}
            </button>
          )}
          {mode === 'preview' ? (
            <span
              className="preview-warn"
              title="可视化编辑会把 DOM 转回 Markdown：列表符号/强调符号会被规范化，HTML 注释无法保留；表格对齐与任务列表已尽量保真。需要完全保真请切到「编辑」。"
            >
              预览保存会规范化 Markdown 格式
            </span>
          ) : (
            <span className="muted" style={{ fontSize: 11 }}>
              Ctrl+B 加粗 · Ctrl+I 斜体 · Ctrl+S 保存
            </span>
          )}
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
              insertSpaces: true,
              formatOnPaste: true,
              scrollbar: { verticalScrollbarSize: 9 },
            }}
          />
        ) : (
          <MarkdownPreview markdown={content} onChange={onChange} hostRef={previewHostRef} />
        )}

        {outlineOpen && (
          <div className="outline-panel">
            <div className="lint-panel-header">
              <span>文档大纲{outline.length > 0 ? `（${outline.length}）` : ''}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setOutlineOpen(false)}>
                收起
              </button>
            </div>
            <div className="outline-body">
              {outline.length === 0 ? (
                <div className="lint-empty">未发现标题（# / ## / ###）</div>
              ) : (
                outline.map((h, i) => (
                  <div
                    key={`${h.line}-${i}`}
                    className={`outline-item outline-level-${h.level}`}
                    onClick={() => jumpTo(h.line, i)}
                    title={`跳转到第 ${h.line} 行`}
                  >
                    {h.text}
                  </div>
                ))
              )}
            </div>
          </div>
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

      <div className="editor-statusline">
        {mode === 'edit' && (
          <span>
            第 {cursor.line} 行, 第 {cursor.column} 列
          </span>
        )}
        <span>{content.length.toLocaleString()} 字符</span>
        <span className={tokens > TOKEN_WARN_THRESHOLD ? 'token-warn' : undefined}>
          ≈{tokens.toLocaleString()} tokens
        </span>
        {cursor.selected > 0 && <span>已选 {cursor.selected.toLocaleString()} 字符</span>}
        {warnings.length > 0 && <span>警告 {warnings.length}（F8 跳转）</span>}
      </div>
    </section>
  );
}
