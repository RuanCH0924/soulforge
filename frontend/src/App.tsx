import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';
import { api } from './api';
import { ApiError } from './api/client';
import { AgentTree } from './components/AgentTree';
import { ApplyAIModal } from './components/ApplyAIModal';
import { ApplyPresetModal } from './components/ApplyPresetModal';
import { CommandPalette } from './components/CommandPalette';
import type { CommandItem } from './components/CommandPalette';
import { CoreAgentList, CoreCategoryList } from './components/CoreBrowser';
import { FileTree } from './components/FileTree';
import { HistoryModal } from './components/HistoryModal';
import { SaveAsPresetModal } from './components/SaveAsPresetModal';
import { SearchModal } from './components/SearchModal';
import { StatusBar } from './components/StatusBar';
import { TopBar } from './components/TopBar';
import { SideNav } from './components/SideNav';
import { ViewToggle } from './components/ViewToggle';
import type { BrowseMode } from './components/ViewToggle';
import { DataPage } from './pages/DataPage';
import type { DataTab } from './pages/DataPage';
import { SettingsPage } from './pages/SettingsPage';
import { ToolsPage } from './pages/ToolsPage';
import { useHashRoute } from './hooks/useHashRoute';
import { useCoreCatalog } from './hooks/useCoreCatalog';
import { useSettings } from './hooks/useSettings';
import { useToast } from './hooks/useToast';
import type { AgentInfo, FileContent, FileInfo, StatsResult } from './types';

// 懒加载编辑器：monaco 体积较大，按需分包，避免阻塞应用首屏
const EditorPane = lazy(() =>
  import('./components/EditorPane').then((m) => ({ default: m.EditorPane })),
);

// Workbench 弹窗收敛：文件级弹窗需携带目标编辑窗口的 key
type ModalState =
  | null
  | 'search'
  | { type: 'history' | 'apply-preset' | 'ai-cleanup' | 'save-preset'; key: string };

/** 编辑栏内最多允许同时打开的编辑窗口数（固定横向平铺） */
const MAX_WINDOWS = 3;

/** 命令面板「最近使用」记录上限（M-05） */
const MAX_RECENT_COMMANDS = 8;

/** 一个编辑窗口对应一个已打开文档的完整编辑状态 */
interface EditorTab {
  /** 唯一标识：`agentId/path` */
  key: string;
  agentId: string;
  file: FileContent;
  /** 编辑缓冲区（未保存内容） */
  content: string;
  dirty: boolean;
  saving: boolean;
  /** 最近一次成功保存的时间戳（M-04：用于路径栏展示「已保存 HH:mm:ss」） */
  savedAt?: number;
  /** 打开文件后要定位到的行号（搜索结果 / lint 跳转） */
  reveal?: { line: number; nonce: number } | undefined;
}

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

/** ---- 布局持久化（M-03）：分栏宽度与折叠态，刷新后保持 ---- */
const LAYOUT_KEY = 'soulforge.layout';

/** 与拖拽边界保持一致（左栏 180–360 / 中栏 200–400） */
const LEFT_WIDTH_RANGE = { min: 180, max: 360 } as const;
const MID_WIDTH_RANGE = { min: 200, max: 400 } as const;

const LAYOUT_DEFAULT = {
  leftWidth: 240,
  midWidth: 280,
  leftCollapsed: false,
  midCollapsed: false,
};

type LayoutState = typeof LAYOUT_DEFAULT;

/** 读取持久化布局；JSON 损坏或 localStorage 不可用时回落默认值，越界值收敛到合法范围 */
function loadLayout(): LayoutState {
  try {
    const raw = window.localStorage.getItem(LAYOUT_KEY);
    if (!raw) return { ...LAYOUT_DEFAULT };
    const parsed = JSON.parse(raw) as Partial<LayoutState>;
    const num = (v: unknown, def: number, r: { min: number; max: number }): number =>
      typeof v === 'number' && Number.isFinite(v) ? clamp(v, r.min, r.max) : def;
    return {
      leftWidth: num(parsed.leftWidth, LAYOUT_DEFAULT.leftWidth, LEFT_WIDTH_RANGE),
      midWidth: num(parsed.midWidth, LAYOUT_DEFAULT.midWidth, MID_WIDTH_RANGE),
      leftCollapsed: parsed.leftCollapsed === true,
      midCollapsed: parsed.midCollapsed === true,
    };
  } catch {
    return { ...LAYOUT_DEFAULT };
  }
}

function saveLayout(next: LayoutState): void {
  try {
    window.localStorage.setItem(LAYOUT_KEY, JSON.stringify(next));
  } catch {
    // localStorage 不可用时静默降级
  }
}

/** ---- 会话恢复（重开应用还原打开的窗口）与草稿保护 ---- */
const SESSION_KEY = 'soulforge.session';
const DRAFTS_KEY = 'soulforge.drafts';
const RECENT_FILES_KEY = 'soulforge.recent.files';

/** 单条草稿体积上限：超过则不落盘，避免占满 localStorage */
const DRAFT_MAX_BYTES = 200 * 1024;
/** 最近打开文件记录上限 */
const MAX_RECENT_FILES = 8;

interface SessionState {
  openKeys: string[];
  activeKey: string | null;
  selectedAgentId: string | null;
}

type DraftMap = Record<string, { content: string; at: number }>;

export interface RecentFile {
  agentId: string;
  path: string;
  at: number;
}

function loadJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function saveJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage 不可用 / 配额满时静默降级
  }
}

function loadDrafts(): DraftMap {
  const raw = loadJson<unknown>(DRAFTS_KEY, {});
  return raw && typeof raw === 'object' ? (raw as DraftMap) : {};
}

function clearDrafts(keys: string[]): void {
  const map = loadDrafts();
  keys.forEach((k) => delete map[k]);
  saveJson(DRAFTS_KEY, map);
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
  // lint 警告总数：与「检查报告」同源（GET /api/lint/all），null = 还没跑完
  const [lintWarningsTotal, setLintWarningsTotal] = useState<number | null>(null);
  const [stats, setStats] = useState<StatsResult | null>(null);
  // 后端版本号（GET /api/health）：版本号链路末端展示，事实源见 backend/app/__init__.py
  const [version, setVersion] = useState<string>('');

  // ---- 浏览状态（左/中栏当前浏览的 Agent 与其文件列表） ----
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const filesAgentIdRef = useRef<string | null>(null);
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);

  // ---- 多文档编辑窗口（编辑栏内横向平铺，最多 MAX_WINDOWS 个） ----
  const [tabs, setTabs] = useState<EditorTab[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const tabsRef = useRef<EditorTab[]>([]);
  const activeKeyRef = useRef<string | null>(null);
  const [anyDirty, setAnyDirty] = useState(false);
  const anyDirtyRef = useRef(false);

  // ---- 编辑器模式：单窗口（打开文档即替换）/ 多窗口（横向平铺） ----
  const EDITOR_MODE_KEY = 'soulforge.editor.mode';
  const [editorMode, setEditorMode] = useState<'single' | 'multi'>(() => {
    try {
      return window.localStorage.getItem(EDITOR_MODE_KEY) === 'single' ? 'single' : 'multi';
    } catch {
      return 'multi';
    }
  });
  const editorModeRef = useRef<'single' | 'multi'>('multi');
  useEffect(() => {
    editorModeRef.current = editorMode;
  }, [editorMode]);

  useEffect(() => {
    tabsRef.current = tabs;
  }, [tabs]);
  useEffect(() => {
    activeKeyRef.current = activeKey;
  }, [activeKey]);
  useEffect(() => {
    anyDirtyRef.current = anyDirty;
  }, [anyDirty]);
  useEffect(() => {
    setAnyDirty(tabs.some((t) => t.dirty));
  }, [tabs]);

  // ---- 布局（M-03：全部持久化到 soulforge.layout，刷新后保持） ----
  const initialLayout = useMemo(loadLayout, []);
  const [leftCollapsed, setLeftCollapsed] = useState(initialLayout.leftCollapsed);
  const [midCollapsed, setMidCollapsed] = useState(initialLayout.midCollapsed);
  const [leftWidth, setLeftWidth] = useState(initialLayout.leftWidth);
  const [midWidth, setMidWidth] = useState(initialLayout.midWidth);
  const leftStartRef = useRef(0);
  const midStartRef = useRef(0);

  // 布局变更写回：拖拽期间高频触发，统一 300ms 防抖
  const layoutSaveTimerRef = useRef<number | null>(null);
  useEffect(() => {
    if (layoutSaveTimerRef.current !== null) window.clearTimeout(layoutSaveTimerRef.current);
    layoutSaveTimerRef.current = window.setTimeout(() => {
      saveLayout({ leftWidth, midWidth, leftCollapsed, midCollapsed });
      layoutSaveTimerRef.current = null;
    }, 300);
    return () => {
      if (layoutSaveTimerRef.current !== null) window.clearTimeout(layoutSaveTimerRef.current);
    };
  }, [leftWidth, midWidth, leftCollapsed, midCollapsed]);

  // ---- 弹窗 ----
  const [modal, setModal] = useState<ModalState>(null);
  // ---- 命令面板（Cmd+K，P1 收敛） ----
  const [paletteOpen, setPaletteOpen] = useState(false);
  const closePalette = useCallback(() => setPaletteOpen(false), []);

  // ---- 命令面板「最近使用」（M-05：MRU 去重，持久化到 localStorage，刷新后保留） ----
  const PALETTE_RECENT_KEY = 'soulforge.palette.recent';
  const [recentCommandIds, setRecentCommandIds] = useState<string[]>(() => {
    try {
      const parsed: unknown = JSON.parse(window.localStorage.getItem(PALETTE_RECENT_KEY) ?? '[]');
      return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : [];
    } catch {
      return [];
    }
  });
  const markCommandUsed = useCallback((id: string) => {
    setRecentCommandIds((prev) => {
      const next = [id, ...prev.filter((x) => x !== id)].slice(0, MAX_RECENT_COMMANDS);
      try {
        window.localStorage.setItem(PALETTE_RECENT_KEY, JSON.stringify(next));
      } catch {
        // localStorage 不可用时静默降级
      }
      return next;
    });
  }, []);
  // ---- 最近打开的文件（命令面板「最近打开」分组） ----
  const [recentFiles, setRecentFiles] = useState<RecentFile[]>(() =>
    loadJson<RecentFile[]>(RECENT_FILES_KEY, []).filter(
      (r) => r && typeof r.agentId === 'string' && typeof r.path === 'string',
    ),
  );
  const markFileOpened = useCallback((agentId: string, path: string) => {
    setRecentFiles((prev) => {
      const next = [
        { agentId, path, at: Date.now() },
        ...prev.filter((r) => !(r.agentId === agentId && r.path === path)),
      ].slice(0, MAX_RECENT_FILES);
      saveJson(RECENT_FILES_KEY, next);
      return next;
    });
  }, []);

  // ---- 路由（P2：四页面） ----
  const [route, navigate] = useHashRoute();
  const goWorkbench = useCallback(() => navigate('workbench'), [navigate]);
  // ---- 数据中心的初始 tab（仅用于跨页跳转，如编辑器 lint 面板「查看规则」直接落到检查报告）----
  const [dataTab, setDataTab] = useState<DataTab>('stats');
  useEffect(() => {
    // 离开数据中心即复位，避免下次进来落到非默认 tab
    if (route !== 'data') setDataTab('stats');
  }, [route]);
  // ---- 首次使用引导（P5：一次性提示快捷键；v3 起快捷键体系更新：Ctrl+B 让位给加粗） ----
  const [showIntro, setShowIntro] = useState(
    () => !window.localStorage.getItem('soulforge.intro-v3'),
  );
  const dismissIntro = useCallback(() => {
    try {
      window.localStorage.setItem('soulforge.intro-v3', '1');
    } catch {
      // ignore
    }
    setShowIntro(false);
  }, []);

  // ---- 文件浏览模式（Agent 原有 / CORE 分类）----
  const BROWSE_MODE_KEY = 'soulforge.browse.mode';
  const [browseMode, setBrowseMode] = useState<BrowseMode>(() => {
    try {
      return window.localStorage.getItem(BROWSE_MODE_KEY) === 'core' ? 'core' : 'agent';
    } catch {
      return 'agent';
    }
  });
  const switchBrowseMode = useCallback((m: BrowseMode) => {
    setBrowseMode(m);
    try {
      window.localStorage.setItem(BROWSE_MODE_KEY, m);
    } catch {
      // ignore
    }
  }, []);
  // CORE 分类目录：左栏一级分类 + 右栏二级 Agent（跨模式共享，状态保留）
  const coreCatalog = useCoreCatalog(agents);

  // 当前激活的编辑窗口（用于文件树高亮与快捷键）
  const activeTab = tabs.find((t) => t.key === activeKey) ?? null;

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

  // ---- 编辑窗口操作 ----
  /** 更新某个窗口的编辑缓冲区（仅影响该窗口） */
  const updateTab = useCallback((key: string, value: string) => {
    setTabs((prev) =>
      prev.map((t) =>
        t.key === key && value !== t.content ? { ...t, content: value, dirty: true } : t,
      ),
    );
  }, []);

  /** 从磁盘重新读取某窗口的文档内容（保存后 / 回滚 / 预设写入后同步） */
  const updateTabFromDisk = useCallback(async (key: string) => {
    const tab = tabsRef.current.find((t) => t.key === key);
    if (!tab) return;
    try {
      const content = await api.readFile(tab.agentId, tab.file.path);
      setTabs((prev) =>
        prev.map((t) =>
          t.key === key
            ? { ...t, file: content, content: content.content, dirty: false, saving: false }
            : t,
        ),
      );
    } catch {
      // 忽略读取失败
    }
  }, []);

  /**
   * 打开文档：
   * - 多窗口模式：已打开则激活对应窗口；未打开且窗口已满则拦截并提示（平铺并行编辑）；
   * - 单窗口模式：打开文档即替换当前窗口（有未保存修改时需确认）。
   */
  const openFile = useCallback(
    async (agentId: string, path: string, line?: number) => {
      const key = `${agentId}/${path}`;
      markFileOpened(agentId, path);
      // 单窗口模式：替换当前文档，不新增窗口
      if (editorModeRef.current === 'single') {
        const current = tabsRef.current.find((t) => t.key === key);
        if (current) {
          setActiveKey(key);
          if (line) {
            setTabs((prev) =>
              prev.map((t) =>
                t.key === key ? { ...t, reveal: { line, nonce: Date.now() } } : t,
              ),
            );
          }
          return;
        }
        const existing = tabsRef.current[0];
        if (existing?.dirty && !window.confirm('当前文件有未保存的修改，确定切换？')) return;
        if (filesAgentIdRef.current !== agentId) {
          await selectAgent(agentId);
        }
        try {
          const content = await api.readFile(agentId, path);
          const tab: EditorTab = {
            key,
            agentId,
            file: content,
            content: content.content,
            dirty: false,
            saving: false,
            reveal: line ? { line, nonce: Date.now() } : undefined,
          };
          setTabs([tab]);
          setActiveKey(key);
        } catch (e) {
          toast(`打开文件失败：${(e as Error).message}`, 'error');
        }
        return;
      }
      if (tabsRef.current.some((t) => t.key === key)) {
        setActiveKey(key);
        if (line) {
          setTabs((prev) =>
            prev.map((t) =>
              t.key === key ? { ...t, reveal: { line, nonce: Date.now() } } : t,
            ),
          );
        }
        return;
      }
      if (tabsRef.current.length >= MAX_WINDOWS) {
        toast(`最多同时打开 ${MAX_WINDOWS} 个编辑窗口，请先关闭一个文档`, 'warning');
        return;
      }
      if (filesAgentIdRef.current !== agentId) {
        await selectAgent(agentId);
      }
      try {
        const content = await api.readFile(agentId, path);
        const tab: EditorTab = {
          key,
          agentId,
          file: content,
          content: content.content,
          dirty: false,
          saving: false,
          reveal: line ? { line, nonce: Date.now() } : undefined,
        };
        setTabs((prev) => [...prev, tab]);
        setActiveKey(key);
      } catch (e) {
        toast(`打开文件失败：${(e as Error).message}`, 'error');
      }
    },
    [selectAgent, toast, markFileOpened],
  );

  /** 切换编辑器模式；多 → 单窗口时仅保留激活窗口（有未保存修改需确认） */
  const switchEditorMode = useCallback((mode: 'single' | 'multi') => {
    if (mode === editorModeRef.current) return;
    if (mode === 'single') {
      const current = tabsRef.current;
      if (current.length > 1) {
        const keep = current.find((t) => t.key === activeKeyRef.current) ?? current[current.length - 1];
        const others = current.filter((t) => t !== keep);
        const dirtyCount = others.filter((t) => t.dirty).length;
        if (
          dirtyCount > 0 &&
          !window.confirm(`有 ${dirtyCount} 个窗口存在未保存的修改，切换到单窗口模式将关闭它们，确定切换？`)
        ) {
          return;
        }
        setTabs([keep]);
        setActiveKey(keep.key);
      }
    }
    setEditorMode(mode);
    try {
      window.localStorage.setItem(EDITOR_MODE_KEY, mode);
    } catch {
      // ignore
    }
  }, []);

  /** 关闭某个编辑窗口；存在未保存修改时需确认（仅影响该窗口） */
  const closeTab = useCallback((key: string) => {
    const tab = tabsRef.current.find((t) => t.key === key);
    if (tab?.dirty && !window.confirm('该文档有未保存的修改，确定关闭？')) return;
    clearDrafts([key]);
    const remaining = tabsRef.current.filter((t) => t.key !== key);
    setTabs(remaining);
    setActiveKey((prev) => {
      if (prev !== key) return prev;
      return remaining.length > 0 ? remaining[remaining.length - 1].key : null;
    });
  }, []);

  /** 保存某个窗口的文档（仅影响该窗口） */
  const saveTab = useCallback(
    async (key: string) => {
      const tab = tabsRef.current.find((t) => t.key === key);
      if (!tab) return;
      if (tab.content.length === 0) {
        if (!window.confirm('内容为空，将清空文件，确认保存？')) return;
      }
      if (tab.content.length > 50 * 1024 && !window.confirm('文件较大（超过 50KB），确认保存？')) {
        return;
      }
      setTabs((prev) =>
        prev.map((t) => (t.key === key ? { ...t, saving: true } : t)),
      );
      try {
        const result = await api.writeFile(tab.agentId, tab.file.path, tab.content, tab.file.sha256);
        setTabs((prev) =>
          prev.map((t) =>
            t.key === key
              ? {
                  ...t,
                  file: {
                    ...t.file,
                    size_bytes: result.size_bytes,
                    mtime: result.mtime,
                    sha256: result.sha256,
                  },
                  dirty: false,
                  saving: false,
                  savedAt: Math.floor(Date.now() / 1000),
                }
              : t,
          ),
        );
        toast(`已保存 ${tab.file.path}`, 'success');
        clearDrafts([key]);
        void refreshFiles(tab.agentId);
        void refreshStats();
      } catch (e) {
        const err = e as ApiError;
        setTabs((prev) =>
          prev.map((t) => (t.key === key ? { ...t, saving: false } : t)),
        );
        if (err.code === 'CONFLICT') {
          toast('保存失败：文件已被外部修改，请刷新后再试', 'error');
        } else {
          toast(`保存失败：${err.message}`, 'error');
        }
      }
    },
    [refreshFiles, refreshStats, toast],
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
    // 读取后端版本号（失败不影响界面）
    api
      .health()
      .then((h) => setVersion(h.version))
      .catch(() => {
        // 版本号获取失败时状态栏不显示
      });
    // 后台跑 lint，填充 Agent 警告角标 + 状态栏警告总数（与「检查报告」同一数据源与口径）
    api
      .lintAll()
      .then((r) => {
        const counts: Record<string, number> = {};
        r.results.forEach((x) => {
          counts[x.agent_id] = x.warnings.length;
        });
        setWarningCounts(counts);
        setLintWarningsTotal(r.results.reduce((n, x) => n + x.warnings.length, 0));
      })
      .catch(() => {
        // lint 失败不阻塞界面；总数保持 null，状态栏显示「检查中…」而非谎报无警告
      });
    return () => {
      cancelled = true;
    };
  }, [selectAgent, refreshStats, toast]);

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

  const exportCurrent = useCallback(
    async (agentId: string) => {
      try {
        await api.exportAgent(agentId);
      } catch (e) {
        toast(`导出失败：${(e as Error).message}`, 'error');
      }
    },
    [toast],
  );

  const exportAll = useCallback(async () => {
    try {
      await api.exportAll();
    } catch (e) {
      toast(`导出失败：${(e as Error).message}`, 'error');
    }
  }, [toast]);

  // ---- 写操作完成后的统一刷新 ----
  // targetKey 明确时只刷新该窗口；否则刷新所有未处于编辑中的窗口（避免覆盖未保存内容）
  const handleDataChanged = useCallback(
    async (targetKey?: string) => {
      const agentId = filesAgentIdRef.current;
      if (agentId) void refreshFiles(agentId);
      if (targetKey) {
        await updateTabFromDisk(targetKey);
      } else {
        const snapshot = tabsRef.current;
        await Promise.all(
          snapshot.filter((t) => !t.dirty).map((t) => updateTabFromDisk(t.key)),
        );
      }
      void refreshStats();
    },
    [refreshFiles, refreshStats, updateTabFromDisk],
  );

  const handleSelectFile = useCallback(
    (path: string) => {
      if (!selectedAgentId) return;
      void openFile(selectedAgentId, path);
    },
    [selectedAgentId, openFile],
  );

  const handleSelectAgent = useCallback(
    (agentId: string) => {
      if (agentId === selectedAgentId) return;
      void selectAgent(agentId);
    },
    [selectedAgentId, selectAgent],
  );

  // ---- 自动保存（P5：开启后编辑暂停 2s 自动写入，按窗口独立计时） ----
  const autoSaveTimerRef = useRef<Map<string, number>>(new Map());
  useEffect(() => {
    if (!settings.autoSave) return;
    const timers = autoSaveTimerRef.current;
    timers.forEach((id) => window.clearTimeout(id));
    timers.clear();
    tabs.forEach((tab) => {
      if (tab.dirty && !tab.saving) {
        const id = window.setTimeout(() => void saveTab(tab.key), 2000);
        timers.set(tab.key, id);
      }
    });
    return () => {
      timers.forEach((id) => window.clearTimeout(id));
      timers.clear();
    };
  }, [tabs, settings.autoSave, saveTab]);

  // ---- 草稿保护：未保存内容防抖落盘（崩溃 / 强制关闭后仍可恢复） ----
  const draftsReadyRef = useRef(false);
  useEffect(() => {
    // 会话恢复完成前不写，避免把待恢复的草稿清空
    if (!draftsReadyRef.current) return;
    const timer = window.setTimeout(() => {
      // 只增量写入「本标签页中处于脏状态」的条目，绝不删除其他条：
      // 多标签页共用同一 localStorage，整体覆盖会清掉别处的草稿。
      // 草稿的清除只发生在明确节点：保存成功 / 关闭窗口 / 重新加载 / 删除文档。
      const map = loadDrafts();
      let changed = false;
      tabs.forEach((t) => {
        if (t.dirty && t.content.length <= DRAFT_MAX_BYTES) {
          map[t.key] = { content: t.content, at: Math.floor(Date.now() / 1000) };
          changed = true;
        }
      });
      if (changed) saveJson(DRAFTS_KEY, map);
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [tabs]);

  // ---- 会话保存：仅记录「打开了哪些窗口」，内容按需重读 ----
  useEffect(() => {
    if (!draftsReadyRef.current) return;
    const snapshot: SessionState = {
      openKeys: tabs.map((t) => t.key),
      activeKey,
      selectedAgentId,
    };
    const timer = window.setTimeout(() => saveJson(SESSION_KEY, snapshot), 300);
    return () => window.clearTimeout(timer);
  }, [tabs, activeKey, selectedAgentId]);

  // ---- 会话恢复：Agent 列表就绪后还原打开的编辑窗口（含草稿询问） ----
  const sessionRestoreRef = useRef(false);
  useEffect(() => {
    if (sessionRestoreRef.current || agents.length === 0) return;
    sessionRestoreRef.current = true;
    const saved = loadJson<SessionState | null>(SESSION_KEY, null);
    const keys = (saved?.openKeys ?? []).filter((k) => typeof k === 'string' && k.includes('/'));
    if (saved?.selectedAgentId && agents.some((a) => a.id === saved.selectedAgentId)) {
      void selectAgent(saved.selectedAgentId);
    }
    const drafts = loadDrafts();
    const draftKeys = keys.filter((k) => drafts[k]);
    let useDrafts = true;
    if (draftKeys.length > 0) {
      useDrafts = window.confirm(
        `发现 ${draftKeys.length} 个未保存的草稿（上次未正常保存）。\n\n「确定」= 恢复草稿\n「取消」= 丢弃草稿，使用磁盘版本`,
      );
      if (!useDrafts) clearDrafts(draftKeys);
    }
    void (async () => {
      const restored: EditorTab[] = [];
      for (const key of keys.slice(0, MAX_WINDOWS)) {
        const idx = key.indexOf('/');
        const agentId = key.slice(0, idx);
        const path = key.slice(idx + 1);
        try {
          const fc = await api.readFile(agentId, path);
          const draft = useDrafts ? drafts[key] : undefined;
          const content = draft && draft.content !== fc.content ? draft.content : fc.content;
          restored.push({
            key,
            agentId,
            file: fc,
            content,
            dirty: content !== fc.content,
            saving: false,
          });
        } catch {
          // 文件已被删除 / 移动：跳过该窗口
        }
      }
      if (restored.length > 0) {
        setTabs(restored);
        const active = restored.find((t) => t.key === saved?.activeKey) ?? restored[restored.length - 1];
        setActiveKey(active.key);
        toast(`已恢复 ${restored.length} 个编辑窗口`, 'info');
      }
      draftsReadyRef.current = true;
    })();
  }, [agents, selectAgent, toast]);

  // ---- 文档级操作（重新加载 / 新建 / 删除） ----
  /** 放弃未保存修改，重新从磁盘加载该窗口 */
  const reloadTab = useCallback(
    async (key: string) => {
      const tab = tabsRef.current.find((t) => t.key === key);
      if (!tab) return;
      if (tab.dirty && !window.confirm('放弃未保存的修改，重新从磁盘加载？')) return;
      clearDrafts([key]);
      await updateTabFromDisk(key);
      toast('已重新加载磁盘版本', 'success');
    },
    [toast, updateTabFromDisk],
  );

  /** 新建文档：复用 PUT 的创建能力（写入一个标题骨架后直接打开） */
  const createDoc = useCallback(
    async (agentId: string) => {
      const input = window.prompt('新文档文件名（可含子目录，建议带 .md 后缀）', 'NEW.md');
      if (!input) return;
      const path = input.trim().replace(/^[\\/]+/, '');
      if (!path) return;
      const base = path.split('/').pop() ?? path;
      try {
        await api.writeFile(agentId, path, `# ${base.replace(/\.md$/i, '')}\n\n`);
        await refreshFiles(agentId);
        await openFile(agentId, path);
        toast(`已创建 ${path}`, 'success');
        void refreshStats();
      } catch (e) {
        toast(`新建失败：${(e as Error).message}`, 'error');
      }
    },
    [openFile, refreshFiles, refreshStats, toast],
  );

  /** 删除文档（后端走回收站，可恢复）；若有未保存窗口先提示 */
  const deleteDoc = useCallback(
    async (agentId: string, path: string) => {
      const key = `${agentId}/${path}`;
      const tab = tabsRef.current.find((t) => t.key === key);
      if (tab?.dirty) {
        toast('该文档有未保存的修改，请先保存或关闭窗口', 'warning');
        return;
      }
      if (!window.confirm(`删除「${path}」？\n\n文件会移入回收站，可从系统回收站恢复。`)) return;
      try {
        await api.deleteFile(agentId, path);
        if (tab) {
          const remaining = tabsRef.current.filter((t) => t.key !== key);
          setTabs(remaining);
          setActiveKey((prev) =>
            prev === key ? (remaining.length > 0 ? remaining[remaining.length - 1].key : null) : prev,
          );
        }
        clearDrafts([key]);
        await refreshFiles(agentId);
        toast(`已删除 ${path}（已移入回收站）`, 'success');
        void refreshStats();
      } catch (e) {
        toast(`删除失败：${(e as Error).message}`, 'error');
      }
    },
    [refreshFiles, refreshStats, toast],
  );

  /** 保存全部未保存窗口 */
  const saveAll = useCallback(async () => {
    const dirtyTabs = tabsRef.current.filter((t) => t.dirty && !t.saving);
    if (dirtyTabs.length === 0) {
      toast('没有需要保存的文档', 'info');
      return;
    }
    for (const t of dirtyTabs) {
      await saveTab(t.key);
    }
  }, [saveTab, toast]);

  // ---- 快捷键 ----
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();
      if (mod && e.shiftKey && key === 's') {
        // 保存全部未保存窗口
        e.preventDefault();
        void saveAll();
      } else if (mod && key === 's') {
        e.preventDefault();
        const k = activeKeyRef.current;
        if (k) void saveTab(k);
      } else if (mod && key === 'k') {
        e.preventDefault();
        setPaletteOpen(true);
      } else if (mod && !e.shiftKey && !e.altKey && (key === '1' || key === '2' || key === '3')) {
        // 切换激活的编辑窗口（Ctrl/Cmd + 1/2/3）
        if (route !== 'workbench') return;
        const target = tabsRef.current[Number(key) - 1];
        if (target) {
          e.preventDefault();
          setActiveKey(target.key);
        }
      } else if (e.altKey && !mod && key === 'w') {
        // 关闭当前文档。不用 Ctrl+W：该组合被浏览器保留（关闭标签页），页面无法拦截
        if (route !== 'workbench') return;
        const k = activeKeyRef.current;
        if (k) {
          e.preventDefault();
          closeTab(k);
        }
      } else if (e.altKey && !mod && (key === '1' || key === '2')) {
        // M-03：布局折叠快捷键，仅工作台内生效（避免在 Tools/Data/Settings 页误触发）
        if (route !== 'workbench') return;
        e.preventDefault();
        if (key === '1') setLeftCollapsed((c) => !c);
        else setMidCollapsed((c) => !c);
      } else if (mod && e.shiftKey && key === 'e') {
        e.preventDefault();
        navigate('tools');
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [saveTab, saveAll, closeTab, route]);

  // 关闭页面前提示未保存
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (anyDirtyRef.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  // 目标窗口被关闭时，同步关闭其关联的文件级弹窗
  useEffect(() => {
    if (modal && modal !== 'search' && !tabs.some((t) => t.key === modal.key)) {
      setModal(null);
    }
  }, [modal, tabs]);

  // CORE 一级分类高亮跟随激活窗口：
  // 无论通过二级菜单、文件树、命令面板还是搜索打开文档，只要激活窗口的文档属于某 CORE 分类，
  // 一级菜单就自动高亮该分类（coreTypes 就绪时兜底重跑一次，避免缓存加载时序导致漏同步）。
  // 依赖不含 activeCore，避免覆盖用户手动切换一级分类的选择。
  useEffect(() => {
    if (!activeTab) return;
    if (activeTab.file.role === 'CORE' && coreCatalog.coreTypes.includes(activeTab.file.path)) {
      coreCatalog.setActiveCore(activeTab.file.path);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab?.key, coreCatalog.coreTypes]);

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
      { type: 'action', id: 'export-all', label: '导出全部 Agent', group: '操作', onSelect: () => void exportAll() },
      { type: 'action', id: 'lint-all', label: '健康检查（全量 Lint）', group: '数据', onSelect: () => navigate('data') },
      { type: 'action', id: 'stats', label: '统计面板', group: '数据', onSelect: () => navigate('data') },
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
      />

      <div className="app-body">
        <SideNav route={route} onNavigate={navigate} />

        {route === 'workbench' ? (
          <div className="workbench">
            {showIntro && (
              <div className="intro-banner">
                <span>
                  <b>Ctrl+K</b> 命令面板 · <b>Ctrl+S</b> 保存 · <b>Ctrl+Shift+S</b> 全部保存 ·{' '}
                  <b>Ctrl+1/2/3</b> 切换编辑窗口 · <b>Alt+W</b> 关闭当前文档 · <b>Alt+1</b>/<b>Alt+2</b> 折叠栏 ·{' '}
                  <b>Ctrl+B</b> 加粗 · <b>Ctrl+Shift+O</b> 大纲 · 页面切换用<b>左侧导航</b>（最多同时打开{' '}
                  <b>{MAX_WINDOWS}</b> 个窗口）
                </span>
                <button className="btn btn-ghost btn-sm" onClick={dismissIntro}>
                  知道了
                </button>
              </div>
            )}
            <div className="main">
            {leftCollapsed && (
              <button
                type="button"
                className="pane-collapsed-bar"
                onClick={() => setLeftCollapsed(false)}
                title="展开 Agent 栏（Alt+1）"
                aria-label="展开 Agent 栏"
              >
                ›
              </button>
            )}
            {!leftCollapsed && (
              <>
                <div className="pane" style={{ width: leftWidth, flex: 'none' }}>
                  <div className="pane-header">
                    <ViewToggle mode={browseMode} onChange={switchBrowseMode} />
                    <span className="pane-header-title">
                      {browseMode === 'core' ? 'CORE 分类' : 'Agent'}
                    </span>
                  </div>
                  {browseMode === 'core' ? (
                    coreCatalog.loading && coreCatalog.coreTypes.length === 0 ? (
                      <div className="state-block">
                        <div className="spinner-lg" />
                        <div>正在加载文件清单...</div>
                      </div>
                    ) : (
                      <CoreCategoryList
                        coreTypes={coreCatalog.coreTypes}
                        agentsByCore={coreCatalog.agentsByCore}
                        activeCore={coreCatalog.activeCore}
                        onSelect={coreCatalog.setActiveCore}
                      />
                    )
                  ) : (
                    <AgentTree
                      agents={agents}
                      loading={agentsLoading}
                      selectedAgentId={selectedAgentId}
                      warningCounts={warningCounts}
                      onSelect={handleSelectAgent}
                      onRefresh={() => void rescan()}
                    />
                  )}
                </div>
                <div className="divider" onMouseDown={startLeftResize} />
              </>
            )}

            {midCollapsed && (
              <button
                type="button"
                className="pane-collapsed-bar"
                onClick={() => setMidCollapsed(false)}
                title="展开文件栏（Alt+2）"
                aria-label="展开文件栏"
              >
                ›
              </button>
            )}

            {!midCollapsed && (
              <>
            <div className="pane" style={{ width: midWidth, flex: 'none' }}>
              {browseMode === 'core' ? (
                <CoreAgentList
                  activeCore={coreCatalog.activeCore}
                  coreTypes={coreCatalog.coreTypes}
                  agents={agents}
                  agentsByCore={coreCatalog.agentsByCore}
                  selectedAgentId={activeTab?.agentId ?? null}
                  selectedPath={activeTab?.file?.path ?? null}
                  onSelectCore={coreCatalog.setActiveCore}
                  onOpenFile={(a, p) => {
                    void openFile(a, p);
                  }}
                />
              ) : (
                <FileTree
                  agentId={selectedAgentId}
                  files={files}
                  loading={filesLoading}
                  selectedPath={activeTab?.file?.path ?? null}
                  showSkills={settings.showSkills}
                  showMeta={settings.showMeta}
                  showMemory={settings.showMemory}
                  showOther={settings.showOther}
                  onSelect={handleSelectFile}
                  onCreate={() => {
                    if (selectedAgentId) void createDoc(selectedAgentId);
                  }}
                  onDelete={(p) => {
                    if (selectedAgentId) void deleteDoc(selectedAgentId, p);
                  }}
                />
              )}
            </div>

            <div className="divider" onMouseDown={startMidResize} />
              </>
            )}

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
              <section className="editor-pane">
                <div className="pane-header">
                  <span className="pane-header-title">编辑器</span>
                  <div className="editor-mode-toggle">
                    <div className="mode-toggle" role="group" aria-label="编辑窗口模式">
                      <button
                        type="button"
                        className={editorMode === 'single' ? 'active' : ''}
                        onClick={() => switchEditorMode('single')}
                        title="单窗口模式：打开文档时替换当前窗口"
                      >
                        单窗口
                      </button>
                      <button
                        type="button"
                        className={editorMode === 'multi' ? 'active' : ''}
                        onClick={() => switchEditorMode('multi')}
                        title={`多窗口模式：横向平铺，最多同时打开 ${MAX_WINDOWS} 个编辑窗口`}
                      >
                        多窗口
                      </button>
                    </div>
                  </div>
                </div>
                {tabs.length === 0 ? (
                  <div className="editor-empty">
                    {editorMode === 'multi'
                      ? `在左侧选择文件开始编辑（多窗口模式：最多同时打开 ${MAX_WINDOWS} 个编辑窗口）`
                      : '在左侧选择文件开始编辑（单窗口模式：打开新文档将替换当前窗口）'}
                  </div>
                ) : (
                  <div className="editor-windows">
                    {tabs.map((tab) => (
                      <EditorPane
                        key={tab.key}
                        agentId={tab.agentId}
                        file={tab.file}
                        content={tab.content}
                        onChange={(v) => updateTab(tab.key, v)}
                        dirty={tab.dirty}
                        saving={tab.saving}
                        savedAt={tab.savedAt}
                        fileKey={tab.key}
                        reveal={tab.reveal}
                        active={tab.key === activeKey}
                        onFocus={() => {
                          setActiveKey(tab.key);
                          // 点击窗口时，左侧一/二级侧边栏跳转到该窗口的文档；
                          // CORE 一级分类同步需在此显式执行：点击“已激活窗口”时 activeTab.key 不变，
                          // 下方跟随 effect 不会重跑，只有此处能把手动选择的分类拉回到窗口所属分类
                          if (filesAgentIdRef.current !== tab.agentId) {
                            void selectAgent(tab.agentId);
                          }
                          if (tab.file.role === 'CORE' && coreCatalog.coreTypes.includes(tab.file.path)) {
                            coreCatalog.setActiveCore(tab.file.path);
                          }
                        }}
                        onClose={() => closeTab(tab.key)}
                        onSave={() => void saveTab(tab.key)}
                        onReload={() => void reloadTab(tab.key)}
                        onHistory={() => setModal({ type: 'history', key: tab.key })}
                        onExport={() => void exportCurrent(tab.agentId)}
                        onApplyPreset={() => setModal({ type: 'apply-preset', key: tab.key })}
                        onApplyAI={() => setModal({ type: 'ai-cleanup', key: tab.key })}
                        onSaveAsPreset={() => setModal({ type: 'save-preset', key: tab.key })}
                        onOpenLintRules={() => {
                          setDataTab('lint');
                          navigate('data');
                        }}
                        onLintDone={(count) => {
                          setFiles((prev) =>
                            prev.map((f) =>
                              f.path === tab.file.path ? { ...f, lint_warnings: count } : f,
                            ),
                          );
                        }}
                      />
                    ))}
                  </div>
                )}
              </section>
            </Suspense>
          </div>
          </div>
        ) : route === 'settings' ? (
          <SettingsPage onBack={goWorkbench} />
        ) : route === 'data' ? (
          <DataPage
            onBack={goWorkbench}
            initialTab={dataTab}
            onOpenResult={(a, p, line) => {
              void openFile(a, p, line);
              navigate('workbench');
            }}
          />
        ) : (
          <ToolsPage
            agents={agents}
            initialPath={activeTab?.file?.path}
            initialContent={activeTab?.content}
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
        warningsTotal={lintWarningsTotal}
        version={version}
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
      {modal && modal !== 'search' && (() => {
        const tab = tabs.find((t) => t.key === modal.key);
        if (!tab) return null;
        const base = {
          agentId: tab.agentId,
          onClose: closeModal,
        };
        switch (modal.type) {
          case 'history':
            return (
              <HistoryModal
                {...base}
                path={tab.file.path}
                onRolledBack={() => void handleDataChanged(tab.key)}
              />
            );
          case 'apply-preset':
            return (
              <ApplyPresetModal
                {...base}
                filePath={tab.file.path}
                onDone={() => void handleDataChanged(tab.key)}
              />
            );
          case 'ai-cleanup':
            return (
              <ApplyAIModal
                {...base}
                filePath={tab.file.path}
                onDone={() => void handleDataChanged(tab.key)}
              />
            );
          case 'save-preset':
            return (
              <SaveAsPresetModal
                agentId={tab.agentId}
                filePath={tab.file.path}
                content={tab.content}
                onClose={closeModal}
              />
            );
          default:
            return null;
        }
      })()}

      {/* ---- 命令面板（Ctrl+K） ---- */}
      <CommandPalette
        open={paletteOpen}
        onClose={closePalette}
        items={paletteItems}
        recentIds={recentCommandIds}
        recentFiles={recentFiles}
        onUsed={markCommandUsed}
        onSearchFiles={searchFilesForPalette}
        onOpenFile={(a, p, line) => {
          void openFile(a, p, line);
        }}
      />
    </div>
  );
}
