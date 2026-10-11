import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
  /** 退场中：CSS 过渡到不可见，过渡播完才从列表移除 */
  leaving?: boolean;
}

interface ToastContextValue {
  push: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({ push: () => undefined });

/** 自动消失时长（ms）：错误停留更久，便于阅读并可手动关闭（悬停 / 聚焦时暂停计时） */
const DURATION: Record<ToastType, number> = {
  success: 3200,
  info: 3200,
  warning: 5000,
  error: 8000,
};

/** 退场时长（ms）：与 global.css 里 .toast.is-closing 的过渡一致，退场快于入场（200ms） */
const EXIT_MS = 150;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);
  // 每条通知一个计时器引用：悬停 / 聚焦可暂停，手动关闭或卸载时清理
  const timers = useRef(new Map<number, number>());
  // 退场定时器单独放：悬停暂停 / 恢复计时不得影响已经在退场的通知
  const exitTimers = useRef(new Set<number>());

  // FLIP：列表增删后，让存活的通知从旧位置滑到新位置，而不是瞬间跳位
  const listRef = useRef<HTMLDivElement | null>(null);
  const prevRects = useRef(new Map<number, DOMRect>());

  useLayoutEffect(() => {
    const host = listRef.current;
    if (!host) return;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const next = new Map<number, DOMRect>();
    Array.from(host.querySelectorAll<HTMLElement>('[data-toast-id]')).forEach((el) => {
      const id = Number(el.dataset.toastId);
      const rect = el.getBoundingClientRect();
      const dy = reduceMotion ? 0 : (prevRects.current.get(id)?.top ?? rect.top) - rect.top;
      if (dy) {
        // WAAPI：硬件加速、可中断，且不占用元素自身的 CSS transition（入场过渡仍在）
        el.animate([{ transform: `translateY(${dy}px)` }, { transform: 'translateY(0)' }], {
          duration: 240,
          easing: 'cubic-bezier(0.23, 1, 0.32, 1)',
        });
      }
      next.set(id, rect);
    });
    prevRects.current = next;
  }, [toasts]);

  const dismiss = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t !== undefined) {
      window.clearTimeout(t);
      timers.current.delete(id);
    }
    // 先标记退场（CSS 过渡到不可见），过渡播完再真正移除：直接移除会「啪」地消失
    setToasts((prev) => prev.map((x) => (x.id === id ? { ...x, leaving: true } : x)));
    const exit = window.setTimeout(() => {
      exitTimers.current.delete(exit);
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, EXIT_MS);
    exitTimers.current.add(exit);
  }, []);

  const schedule = useCallback(
    (id: number, type: ToastType) => {
      timers.current.set(id, window.setTimeout(() => dismiss(id), DURATION[type]));
    },
    [dismiss],
  );

  const push = useCallback(
    (message: string, type: ToastType = 'info') => {
      const id = ++idRef.current;
      setToasts((prev) => [...prev, { id, type, message }]);
      schedule(id, type);
    },
    [schedule],
  );

  const pause = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t !== undefined) {
      window.clearTimeout(t);
      timers.current.delete(id);
    }
  }, []);

  // 卸载时清空所有计时器，避免对已卸载组件 setState
  useEffect(
    () => () => {
      timers.current.forEach((t) => window.clearTimeout(t));
      timers.current.clear();
      exitTimers.current.forEach((t) => window.clearTimeout(t));
      exitTimers.current.clear();
    },
    [],
  );

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-container" role="region" aria-label="通知" ref={listRef}>
        {toasts.map((t) => (
          <div
            key={t.id}
            data-toast-id={t.id}
            className={`toast ${t.type}${t.leaving ? ' is-closing' : ''}`}
            onMouseEnter={() => pause(t.id)}
            onMouseLeave={() => schedule(t.id, t.type)}
            onFocus={() => pause(t.id)}
            onBlur={() => schedule(t.id, t.type)}
          >
            <span className="toast-message" role={t.type === 'error' ? 'alert' : 'status'}>
              {t.message}
            </span>
            <button
              type="button"
              className="toast-close"
              aria-label="关闭通知"
              onClick={() => dismiss(t.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  return useContext(ToastContext);
}
