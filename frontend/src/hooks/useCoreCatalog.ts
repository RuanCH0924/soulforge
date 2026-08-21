import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import type { AgentInfo, FileInfo } from '../types';
import { buildCoreCatalog, type CoreEntry } from '../components/CoreBrowser';

export interface CoreCatalog {
  loading: boolean;
  coreTypes: string[];
  agentsByCore: Map<string, CoreEntry[]>;
  activeCore: string | null;
  setActiveCore: (t: string) => void;
}

/**
 * CORE 分类目录（App 层共享状态）：
 * - 懒加载全部 Agent 文件清单并缓存（激活后只请求一次）
 * - 一级分类 activeCore 提升到此处，左栏/中栏共享，切换模式不丢失
 */
export function useCoreCatalog(agents: AgentInfo[]): CoreCatalog {
  const [cache, setCache] = useState<Record<string, FileInfo[]>>({});
  const [loading, setLoading] = useState(true);
  const [activeCore, setActiveCore] = useState<string | null>(null);
  const loadedRef = useRef<string[]>([]);

  useEffect(() => {
    const ids = agents.map((a) => a.id);
    if (ids.length === 0) {
      setLoading(false);
      return;
    }
    const fresh = ids.filter((id) => !loadedRef.current.includes(id));
    if (fresh.length === 0) {
      setLoading(false);
      return;
    }
    setLoading(true);
    let cancelled = false;
    Promise.all(fresh.map((id) => api.listFiles(id).catch(() => [] as FileInfo[])))
      .then((lists) => {
        if (cancelled) return;
        setCache((prev) => {
          const next = { ...prev };
          fresh.forEach((id, i) => {
            next[id] = lists[i];
          });
          return next;
        });
        loadedRef.current = [...loadedRef.current, ...fresh];
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agents]);

  const { coreTypes, agentsByCore } = useMemo(() => buildCoreCatalog(cache), [cache]);

  // 默认选中第一个 CORE 分类
  useEffect(() => {
    if (activeCore === null && coreTypes.length > 0) {
      setActiveCore(coreTypes[0]);
    }
  }, [coreTypes, activeCore]);

  return { loading, coreTypes, agentsByCore, activeCore, setActiveCore };
}
