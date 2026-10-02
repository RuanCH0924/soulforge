import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../api';
import { ApiError } from '../api/client';
import type { LintAgentResult } from '../types';

/**
 * 全量 lint 扫描的共享状态（进度 + 取消）。
 *
 * 为什么要前端编排：`GET /api/lint/all` 一次同步跑完全部 Agent（大库 1~2 分钟），
 * 期间既无进度也无法中止。这里改为逐 Agent 串行调用 `GET /api/lint/{agent_id}`
 * ——与 `lint_all` 内部的循环等价、口径完全一致，但前端因此能拿到「已完成 N / 共 M」
 * 并支持在 Agent 之间中止。全应用共享同一份状态，避免多处同时触发重复扫描。
 */
export type LintScanStatus = 'idle' | 'running' | 'done' | 'cancelled' | 'error';

interface LintScanState {
  status: LintScanStatus;
  /** 已完成的 Agent 数 */
  done: number;
  /** 本轮总 Agent 数（start 之后才有值） */
  total: number;
  /** 当前正在检查的 Agent id */
  currentAgent: string | null;
  results: LintAgentResult[];
  error: string | null;
}

interface LintScanContextValue extends LintScanState {
  /** 全量 lint 警告总数（含 error 级；口径与「检查报告」一致）；未取到为 null，不谎报「无警告」 */
  warningsTotal: number | null;
  /** 本轮已检查的文件数 */
  checkedFiles: number;
  /** 启动一次全量扫描；已在运行时直接复用，不重复启动 */
  start: () => Promise<void>;
  /** 请求取消：当前 Agent 检查完成后停止（不影响已完成的 Agent 结果） */
  cancel: () => void;
}

const INITIAL: LintScanState = {
  status: 'idle',
  done: 0,
  total: 0,
  currentAgent: null,
  results: [],
  error: null,
};

const LintScanContext = createContext<LintScanContextValue | null>(null);

export function LintScanProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LintScanState>(INITIAL);
  // 单飞：同一时刻只允许一轮全量扫描
  const runningRef = useRef(false);
  const cancelRef = useRef(false);

  const start = useCallback(async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    cancelRef.current = false;
    setState({ status: 'running', done: 0, total: 0, currentAgent: null, results: [], error: null });
    try {
      const agents = await api.listAgents();
      setState((s) => ({ ...s, total: agents.length }));
      const results: LintAgentResult[] = [];
      for (let i = 0; i < agents.length; i += 1) {
        if (cancelRef.current) break;
        const agentId = agents[i].id;
        setState((s) => ({ ...s, currentAgent: agentId }));
        try {
          results.push(await api.lintAgent(agentId));
        } catch (e) {
          // 后端断连：整轮扫描已失去意义，立即中止并如实标失败，
          // 不能把「只检查了一部分」的残缺结果当成扫描成功。
          if (e instanceof ApiError && e.code === 'NETWORK_ERROR') {
            setState((s) => ({
              ...s,
              status: 'error',
              currentAgent: null,
              error: '与后端的连接已断开',
              results: [...results],
            }));
            return;
          }
          // 单个 Agent 业务失败：跳过它，其余 Agent 照常汇总
        }
        setState((s) => ({ ...s, done: i + 1, results: [...results] }));
      }
      setState((s) => ({
        ...s,
        status: cancelRef.current ? 'cancelled' : 'done',
        currentAgent: null,
        results: [...results],
      }));
    } catch (e) {
      setState((s) => ({ ...s, status: 'error', currentAgent: null, error: (e as Error).message }));
    } finally {
      runningRef.current = false;
    }
  }, []);

  const cancel = useCallback(() => {
    if (runningRef.current) cancelRef.current = true;
  }, []);

  const value = useMemo<LintScanContextValue>(() => {
    const known = state.status === 'done' || state.status === 'cancelled';
    return {
      ...state,
      warningsTotal: known ? state.results.reduce((n, r) => n + r.warnings.length, 0) : null,
      checkedFiles: state.results.reduce((n, r) => n + r.stats.files_checked, 0),
      start,
      cancel,
    };
  }, [state, start, cancel]);

  return <LintScanContext.Provider value={value}>{children}</LintScanContext.Provider>;
}

export function useLintScan(): LintScanContextValue {
  const ctx = useContext(LintScanContext);
  if (!ctx) throw new Error('useLintScan 必须在 <LintScanProvider> 内使用');
  return ctx;
}
