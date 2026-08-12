import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { FileRole } from '../types';

export type ThemeMode = 'auto' | 'light' | 'dark';

export interface Settings {
  theme: ThemeMode;
  showSkills: boolean;
  showMeta: boolean;
  showMemory: boolean;
  showOther: boolean;
  /** P5：自动保存（防抖 2s，编辑后自动写入） */
  autoSave: boolean;
}

const DEFAULT_SETTINGS: Settings = {
  theme: 'auto',
  showSkills: false,
  showMeta: false,
  showMemory: false,
  showOther: false,
  autoSave: false,
};

/** 文件角色在当前显示设置下是否可见（CORE 始终可见） */
export function isRoleVisible(
  role: FileRole,
  settings: Pick<Settings, 'showSkills' | 'showMeta' | 'showMemory' | 'showOther'>,
): boolean {
  switch (role) {
    case 'SKILL':
      return settings.showSkills;
    case 'META':
      return settings.showMeta;
    case 'MEMORY':
      return settings.showMemory;
    case 'OTHER':
      return settings.showOther;
    default:
      return true;
  }
}
const STORAGE_KEY = 'soulforge.settings';

interface SettingsContextValue {
  settings: Settings;
  set: (patch: Partial<Settings>) => void;
  resolvedTheme: 'light' | 'dark';
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<Settings>) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [systemDark, setSystemDark] = useState<boolean>(() =>
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
      : false,
  );

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const resolvedTheme: 'light' | 'dark' =
    settings.theme === 'auto' ? (systemDark ? 'dark' : 'light') : settings.theme;

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedTheme);
  }, [resolvedTheme]);

  const set = useCallback((patch: Partial<Settings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // localStorage 不可用时静默降级
      }
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({ settings, set, resolvedTheme }),
    [settings, set, resolvedTheme],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings 必须在 SettingsProvider 内使用');
  return ctx;
}
