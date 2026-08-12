import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';
import { api } from './api';
import { ApiError } from './api/client';
import { AgentTree } from './components/AgentTree';
import { ApplyAIModal } from './components/ApplyAIModal';
import { ApplyPresetModal } from './components/ApplyPresetModal';
import { CommandPalette } from './components/CommandPalette';
import type { CommandItem } from './components/CommandPalette';
import { FileTree } from './components/FileTree';
import { HistoryModal } from './components/HistoryModal';
import { SearchModal } from './components/SearchModal';
import { StatusBar } from './components/StatusBar';
import { TopBar } from './components/TopBar';
import { SideNav } from './components/SideNav';
import { DataPage } from './pages/DataPage';
import { SettingsPage } from './pages/SettingsPage';
import { ToolsPage } from './pages/ToolsPage';
import { useHashRoute } from './hooks/useHashRoute';
import { useSettings } from './hooks/useSettings';
import { useToast } from './hooks/useToast';
import type { AgentInfo, FileContent, FileInfo, StatsResult } from './types';

// 懒加载编辑器：monaco 体积较大，按需分包，避免阻塞应用首屏
const EditorPane = lazy(() =>
  import('./components/EditorPane').then((m) => ({ default: m.EditorPane })),
);

// Workbench 弹窗收敛：仅保留与当前文件上下文相关的弹窗
type ModalState =
  | null
  | 'search'
  | 'history'
  | 'apply-preset'
  | 'ai-cleanup';

/** 拖拽调整分栏宽度 */
function startDrag(e: ReactMouseEvent, onMove: (dx: number) => void): void {
  e.preventDefault();
  const startX = e.clientX;
  const onMouseMove = (ev: MouseEvent) => onMove(ev.clientX - startX);
  const onMouseUp = () => {
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

export default function App() {
  const { settings } = useSettings();
  const { push: toast } = useToast();

  // ---- 全局数据 ----
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [warningCounts, setWarningCounts] = useState<Record<string, number>>({});
  const [stats, setStats] = useState<StatsResult | null>(null);

  // ---- 选择状态 ----
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const filesAgentIdRef = useRef<string | null>(null);
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<FileContent | null>(null);
  const selectedFileRef = useRef<FileContent | null>(null);
  const [editorContent, setEditorContent] = useState('');
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  const [saving, setSaving] = useState(false);
  const [fileKey, setFileKey] = useState('');
  const [reveal, setReveal] = useState<{ line: number; nonce: number } | undefined>(undefined);

  // ---- 布局 ----
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [leftWidth, setLeftWidth] = useState(240);
  const [midWidth, setMidWidth] = useState(280);
  const leftStartRef = useRef(0);
  const midStartRef = useRef(0);

  // ---- 弹窗 ----
  const [modal, setModal] = useState<ModalState>(null);
  // ---- 命令面板（Cmd+K，P1 收敛） ----
  const [paletteOpen, setPaletteOpen] = useState(false);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  // ---- 路由（P2：四页面） ----
  const [route, navigate] = useHashRoute();
  const goWorkbench = useCallback(() => navigate('workbench'), [navigate]);
  // ---- 首次使用引导（P5：一次性提示快捷键） ----
  const [showIntro, setShowIntro] = useState(
    () => !window.localStorage.getItem('soulforge.intro-v1'),
  );
  const dismissIntro = useCallback(() => {
    try {
      window.localStorage.setItem('soulforge.intro-v1', '1');
    } catch {
      // ignore
    }
    setShowIntro(false);
  }, []);

  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty]);
  useEffect(() => {
    selectedFileRef.current = selectedFile;
  }, [selectedFile]);

  // ---- 数据加载 ----
  const refreshFiles = useCallback(async (agentId: string) => {
    if (filesAgentIdRef.current !== agentId) return;
    try {
      const fs = await api.listFiles(agentId);
      setFiles(fs);
    } catch {
      // 静默失败，保持现有列表
    }
  }, []);

  const refreshStats = useCallback(async () => {
    try {
      setStats(await api.stats());
    } catch {
      // 静默失败
    }
  }, []);

  const selectAgent = useCallback(
    async (agentId: string) => {
      setSelectedAgentId(agentId);
      filesAgentIdRef.current = agentId;
      setSelectedFile(null);
      setFileKey('');
      setFilesLoading(true);
      try {
        const fs = await api.listFiles(agentId);
        setFiles(fs);
      } catch (e) {
        toast(`加载文件失败：${(e as Error).message}`, 'error');
      } finally {
        setFilesLoading(false);
      }
    },
    [toast],
  );

  const openFile = useCallback(
    async (agentId: string, path: string, line?: number) => {
      if (dirtyRef.current && !window.confirm('当前文件有未保存的修改，确定切换？')) return;
      setSelectedAgentId(agentId);
      if (filesAgentIdRef.current !== agentId) {
        await selectAgent(agentId);
      }
      try {
        const content = await api.readFile(agentId, path);
        setSelectedFile(content);
        setEditorContent(content.content);
        setDirty(false);
        setFileKey(`${agentId}/${path}`);
        if (line) setReveal({ line, nonce: Date.now() });
        else setReveal(undefined);
      } catch (e) {
        toast(`打开文件失败：${(e as Error).message}`, 'error');
      }
    },
    [selectAgent, toast],
  );

  // 初始加载
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await api.listAgents();
        if (cancelled) return;
        setAgents(list);
        setConnected(true);
        if (list.length > 0) {
          void selectAgent(list[0].id);
        }
      } catch (e) {
        if (!cancelled) {
          setConnected(false);
          toast(`连接失败：${(e as Error).message}`, 'error');
        }
      } finally {
        if (!cancelled) setAgentsLoading(false);
      }
    })();
    void refreshStats();
    // 后台跑 lint，填充 Agent 警告角标
    api
      .lintAll()
      .then((r) => {
        const counts: Record<string, number> = {};
        r.results.forEach((x) => {
          counts[x.agent_id] = x.stats.warnings;
        });
        setWarningCounts(counts);
      })
      .catch(() => {
        // lint 失败不阻塞界面
      });
    return () => {
      cancelled = true;
    };
  }, [selectAgent, refreshStats, toast]);

  // ---- 保存 ----
  const saveFile = useCallback(async () => {
    if (!selectedAgentId || !selectedFile) return;
    if (editorContent.length === 0) {
      if (!window.confirm('内容为空，将清空文件，确认保存？')) return;
    }
    if (editorContent.length > 50 * 1024 && !window.confirm('文件较大（超过 50KB），确认保存？')) {
      return;
    }
    setSaving(true);
    try {
      const result = await api.writeFile(selectedAgentId, selectedFile.path, editorContent, selectedFile.sha256);
      setSelectedFile((prev) =>
        prev
          ? { ...prev, size_bytes: result.size_bytes, mtime: result.mtime, sha256: result.sha256 }
          : prev,
      );
      setDirty(false);
      toast(`已保存 ${selectedFile.path}`, 'success');
      void refreshFiles(selectedAgentId);
      void refreshStats();
    } catch (e) {
      const err = e as ApiError;
      if (err.code === 'CONFLICT') {
        toast('保存失败：文件已被外部修改，请刷新后再试', 'error');
      } else {
        toast(`保存失败：${err.message}`, 'error');
      }
    } finally {
      setSaving(false);
    }
  }, [selectedAgentId, selectedFile, editorContent, refreshFiles, refreshStats, toast]);

  // ---- 扫描 / 导出 ----
  const rescan = useCallback(async () => {
    setScanning(true);
    try {
      await api.scanAgents();
      const list = await api.listAgents();
      setAgents(list);
      if (selectedAgentId && list.some((a) => a.id === selectedAgentId)) {
        await selectAgent(selectedAgentId);
      } else if (list.length > 0) {
        await selectAgent(list[0].id);
      }
      toast('扫描完成', 'success');
      void refreshStats();
    } catch (e) {
      toast(`扫描失败：${(e as Error).message}`, 'error');
    } finally {
      setScanning(false);
    }
  }, [selectedAgentId, selectAgent, refreshStats, toast]);

  const exportCurrent = useCallback(async () => {
    if (!selectedAgentId) return;
    try {
      await api.exportAgent(selectedAgentId);
    } catch (e) {
      toast(`导出失败：${(e as Error).message}`, 'error');
    }
  }, [selectedAgentId, toast]);

  const exportAll = useCallback(async () => {
    try {
      await api.exportAll();
    } catch (e) {
      toast(`导出失败：${(e as Error).message}`, 'error');
    }
  }, [toast]);

  // ---- 写操作完成后的统一刷新 ----
  const handleDataChanged = useCallback(async () => {
    const agentId = filesAgentIdRef.current;
    if (agentId) void refreshFiles(agentId);
    const cur = selectedFileRef.current;
    if (agentId && cur) {
      try {
        const content = await api.readFile(agentId, cur.path);
        setSelectedFile(content);
        setEditorContent(content.content);
        setDirty(false);
      } catch {
        // 忽略读取失败
      }
    }
    void refreshStats();
  }, [refreshFiles, refreshStats]);

  const handleSelectFile = useCallback(
    (path: string) => {
      if (!selectedAgentId) return;
      if (dirtyRef.current && !window.confirm('当前文件有未保存的修改，确定切换？')) return;
      void openFile(selectedAgentId, path);
    },
    [selectedAgentId, openFile],
  );

  const handleSelectAgent = useCallback(
    (agentId: string) => {
      if (agentId === selectedAgentId) return;
      if (dirtyRef.current && !window.confirm('当前文件有未保存的修改，确定切换？')) return;
      void selectAgent(agentId);
    },
    [selectedAgentId, selectAgent],
  );

  // ---- 自动保存（P5：开启后编辑暂停 2s 自动写入） ----
  const autoSaveTimerRef = useRef<number | null>(null);
  useEffect(() => {
    if (!settings.autoSave || !dirtyRef.current || !selectedAgentId || !selectedFile) return;
    if (autoSaveTimerRef.current) window.clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = window.setTimeout(() => {
      void saveFile();
    }, 2000);
    return () => {
      if (autoSaveTimerRef.current) window.clearTimeout(autoSaveTimerRef.current);
    };
  }, [editorContent, settings.autoSave, selectedAgentId, selectedFile, saveFile]);

  // ---- 快捷键 ----
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();
      if (mod && key === 's') {
        e.preventDefault();
        if (dirtyRef.current) void saveFile();
      } else if (mod && key === 'k') {
        e.preventDefault();
        setPaletteOpen(true);
      } else if (mod && key === 'b') {
        e.preventDefault();
        setLeftCollapsed((c) => !c);
      } else if (mod && e.shiftKey && key === 'e') {
        e.preventDefault();
        navigate('tools');
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [saveFile]);

  // 关闭页面前提示未保存
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  // ---- 分栏拖拽 ----
  const startLeftResize = (e: ReactMouseEvent) => {
    leftStartRef.current = leftWidth;
    startDrag(e, (dx) => setLeftWidth(clamp(leftStartRef.current + dx, 180, 360)));
  };
  const startMidResize = (e: ReactMouseEvent) => {
    midStartRef.current = midWidth;
    startDrag(e, (dx) => setMidWidth(clamp(midStartRef.current + dx, 200, 400)));
  };

  const agentsTotal = stats?.agents_total ?? agents.length;
  const filesTotal = stats?.files_total ?? agents.reduce((s, a) => s + a.file_count, 0);
  const closeModal = useCallback(() => setModal(null), []);

  // ---- 命令面板索引（P1：功能动作；P2：页面导航） ----
  const paletteItems = useMemo<CommandItem[]>(
    () => [
      // 页面导航
      { type: 'action', id: 'nav-workbench', label: '前往主工作台', keywords: 'editor edit', group: '导航', onSelect: () => navigate('workbench') },
      { type: 'action', id: 'nav-tools', label: '前往业务工具', keywords: 'sync diff batch import', group: '导航', onSelect: () => navigate('tools') },
      { type: 'action', id: 'nav-data', label: '前往数据中心', keywords: 'stats audit lint', group: '导航', onSelect: () => navigate('data') },
      { type: 'action', id: 'nav-settings', label: '前往系统配置', keywords: 'setting preset llm', group: '导航', onSelect: () => navigate('settings') },
      // 操作
      { type: 'action', id: 'rescan', label: '重新扫描 workspace', keywords: 'scan', group: '操作', onSelect: () => void rescan() },
      { type: 'action', id: 'search', label: '高级搜索文件内容', keywords: 'find', hint: 'Ctrl+K', group: '操作', onSelect: () => setModal('search') },
      { type: 'action', id: 'sync', label: '跨 Agent 同步文件', group: '操作', onSelect: () => navigate('tools') },
      { type: 'action', id: 'cross-edit', label: '跨 Agent 批量编辑', keywords: 'batch', hint: 'Ctrl+Shift+E', group: '操作', onSelect: () => navigate('tools') },
      { type: 'action', id: 'diff', label: '对比两个 Agent', group: '操作', onSelect: () => navigate('tools') },
      { type: 'action', id: 'import', label: '导入 Prompt Pack', group: '操作', onSelect: () => navigate('tools') },
      { type: 'action', id: 'export-all', label: '导出全部 Agent', group: '操作', onSelect: () => void exportAll() },
      { type: 'action', id: 'new-agent', label: '新建 Agent', keywords: 'template', group: '操作', onSelect: () => navigate('tools') },
      { type: 'action', id: 'lint-all', label: '健康检查（全量 Lint）', group: '数据', onSelect: () => navigate('data') },
      { type: 'action', id: 'stats', label: '统计仪表盘', group: '数据', onSelect: () => navigate('data') },
      { type: 'action', id: 'audit', label: '审计日志', group: '数据', onSelect: () => navigate('data') },
      { type: 'action', id: 'preset', label: '管理文档预设', group: '管理', onSelect: () => navigate('settings') },
      { type: 'action', id: 'settings', label: '打开系统设置', group: '管理', onSelect: () => navigate('settings') },
    ],
    // 回调均为稳定引用或空依赖动作，使用 eslint 豁免
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const searchFilesForPalette = useCallback(async (q: string) => {
    const res = await api.search({ query: q, limit: 30 });
    return res.hits;
  }, []);

  return (
    <div className="app">
      <TopBar
        agentCount={agentsTotal}
        scanning={scanning}
        onOpenSearch={() => setPaletteOpen(true)}
        onRescan={() => void rescan()}
        onNavigateTools={() => navigate('tools')}
        onNavigateData={() => navigate('data')}
        onNavigateSettings={() => navigate('settings')}
      />

      <div className="app-body">
        <SideNav route={route} onNavigate={navigate} />

        {route === 'workbench' ? (
          <div className="workbench">
            {showIntro && (
              <div className="intro-banner">
                <span>
                  <b>Ctrl+K</b> 命令面板（搜索功能 / 文件 / 页面） · <b>Ctrl+S</b> 保存 ·{' '}
                  <b>Ctrl+B</b> 折叠左侧 · 左侧导航切换页面
                </span>
                <button className="btn btn-ghost btn-sm" onClick={dismissIntro}>
                  知道了
                </button>
              </div>
            )}
            <div className="main">
            {!leftCollapsed && (
              <>
                <div className="pane" style={{ width: leftWidth, flex: 'none' }}>
                  <AgentTree
                    agents={agents}
                    loading={agentsLoading}
                    selectedAgentId={selectedAgentId}
                    warningCounts={warningCounts}
                    onSelect={handleSelectAgent}
                    onRefresh={() => void rescan()}
                  />
                </div>
                <div className="divider" onMouseDown={startLeftResize} />
              </>
            )}

            <div className="pane" style={{ width: midWidth, flex: 'none' }}>
              <FileTree
                agentId={selectedAgentId}
                files={files}
                loading={filesLoading}
                selectedPath={selectedFile?.path ?? null}
                showSkills={settings.showSkills}
                showMeta={settings.showMeta}
                showMemory={settings.showMemory}
                showOther={settings.showOther}
                onSelect={handleSelectFile}
              />
            </div>

            <div className="divider" onMouseDown={startMidResize} />

            <Suspense
              fallback={
                <section className="editor-pane">
                  <div className="pane-header">编辑器</div>
                  <div className="state-block">
                    <div className="spinner-lg" />
                    <div>正在加载编辑器…</div>
                  </div>
                </section>
              }
            >
              <EditorPane
                agentId={selectedAgentId}
                file={selectedFile}
                content={editorContent}
                onChange={(v) => {
                  setEditorContent(v);
                  setDirty(true);
                }}
                dirty={dirty}
                saving={saving}
                fileKey={fileKey}
                reveal={reveal}
                onSave={() => void saveFile()}
                onHistory={() => setModal('history')}
                onExport={() => void exportCurrent()}
                onApplyPreset={() => setModal('apply-preset')}
                onApplyAI={() => setModal('ai-cleanup')}
                onLintDone={(count) => {
                  if (selectedAgentId) {
                    setFiles((prev) =>
                      prev.map((f) =>
                        f.path === selectedFile?.path ? { ...f, lint_warnings: count } : f,
                      ),
                    );
                  }
                }}
              />
            </Suspense>
          </div>
          </div>
        ) : route === 'settings' ? (
          <SettingsPage onBack={goWorkbench} />
        ) : route === 'data' ? (
          <DataPage
            onBack={goWorkbench}
            onOpenResult={(a, p, line) => {
              void openFile(a, p, line);
              navigate('workbench');
            }}
          />
        ) : (
          <ToolsPage
            agents={agents}
            initialPath={selectedFile?.path}
            initialContent={editorContent}
            onBack={goWorkbench}
            onDone={() => void handleDataChanged()}
            onExportAll={() => void exportAll()}
          />
        )}
      </div>

      <StatusBar
        connected={connected}
        agentsTotal={agentsTotal}
        filesTotal={filesTotal}
        lastScanAt={stats?.last_scan_at}
        warningsTotal={stats?.lint_warnings_total ?? 0}
      />

      {/* ---- 弹窗 ---- */}
      {modal === 'search' && (
        <SearchModal
          agents={agents}
          onClose={closeModal}
          onOpenResult={(a, p, l) => {
            void openFile(a, p, l);
            closeModal();
          }}
        />
      )}
      {modal === 'history' && selectedAgentId && selectedFile && (
        <HistoryModal
          agentId={selectedAgentId}
          path={selectedFile.path}
          onClose={closeModal}
          onRolledBack={() => void handleDataChanged()}
        />
      )}
      {modal === 'apply-preset' && selectedAgentId && selectedFile && (
        <ApplyPresetModal
          agentId={selectedAgentId}
          filePath={selectedFile.path}
          onClose={closeModal}
          onDone={() => void handleDataChanged()}
        />
      )}
      {modal === 'ai-cleanup' && selectedAgentId && selectedFile && (
        <ApplyAIModal
          agentId={selectedAgentId}
          filePath={selectedFile.path}
          onClose={closeModal}
          onDone={() => void handleDataChanged()}
        />
      )}

      {/* ---- 命令面板（Ctrl+K） ---- */}
      <CommandPalette
        open={paletteOpen}
        onClose={closePalette}
        items={paletteItems}
        onSearchFiles={searchFilesForPalette}
        onOpenFile={(a, p, line) => {
          void openFile(a, p, line);
        }}
      />
    </div>
  );
}
