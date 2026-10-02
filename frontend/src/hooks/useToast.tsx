import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
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

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);
  // 每条通知一个计时器引用：悬停 / 聚焦可暂停，手动关闭或卸载时清理
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t !== undefined) {
      window.clearTimeout(t);
      timers.current.delete(id);
    }
    setToasts((prev) => prev.filter((x) => x.id !== id));
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
    },
    [],
  );

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-container" role="region" aria-label="通知">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast ${t.type}`}
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
