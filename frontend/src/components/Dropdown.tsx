import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export interface DropdownItem {
  label: string;
  hint?: string;
  danger?: boolean;
  onSelect: () => void;
}

interface DropdownProps {
  trigger: React.ReactNode;
  items: DropdownItem[];
  title?: string;
  align?: 'left' | 'right';
}

/** 退场时长（ms）：与 global.css 里 .dropdown-menu.is-closing 的过渡一致，退场快于入场（150ms） */
const EXIT_MS = 120;

/**
 * 通用下拉菜单：点击外部 / Esc 关闭。
 *
 * 菜单经 createPortal 挂到 body 并采用 fixed 定位 —— 若就地绝对定位，
 * 会被带 overflow 的祖先容器（如收起的侧栏、滚动面板）裁剪。
 */
export function Dropdown({ trigger, items, title, align = 'right' }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  /** 退场进行中：菜单保持挂载，等过渡播完再卸载 */
  const [closing, setClosing] = useState(false);
  const closingRef = useRef(false);
  const exitTimer = useRef<number | null>(null);

  /** 依据触发器位置计算菜单坐标（贴合视口左右边界） */
  const place = useCallback(() => {
    const root = rootRef.current;
    if (!root) return;
    const rect = root.getBoundingClientRect();
    const width = menuRef.current?.offsetWidth ?? 200;
    const left =
      align === 'right'
        ? Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))
        : Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    setPos({ top: rect.bottom + 4, left });
  }, [align]);

  /**
   * 关闭菜单：先挂 .is-closing 播退场，EXIT_MS 后才真正卸载。
   * 退场期间菜单仍挂载，所以「点外部 / Esc / 选中项」都有退场动画；
   * closingRef 守卫保证重复触发只播一次。
   */
  const close = useCallback(() => {
    if (closingRef.current) return;
    closingRef.current = true;
    setClosing(true);
    exitTimer.current = window.setTimeout(() => {
      setOpen(false);
      setClosing(false);
      closingRef.current = false;
      exitTimer.current = null;
    }, EXIT_MS);
  }, []);

  // 卸载时清掉退场定时器，避免对已卸载组件 setState
  useEffect(
    () => () => {
      if (exitTimer.current !== null) window.clearTimeout(exitTimer.current);
    },
    [],
  );

  // 打开后先定位再绘制，避免首帧闪烁
  useLayoutEffect(() => {
    if (open) place();
  }, [open, place, close]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (rootRef.current?.contains(t) || menuRef.current?.contains(t)) return;
      close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open, place]);

  return (
    <div className="dropdown" ref={rootRef}>
      <div onClick={() => (open ? close() : setOpen(true))}>{trigger}</div>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            className={`dropdown-menu${closing ? ' is-closing' : ''}`}
            style={{
              position: 'fixed',
              top: pos?.top ?? -9999,
              left: pos?.left ?? -9999,
              right: 'auto',
            }}
          >
            {title && <div className="dropdown-title">{title}</div>}
            {items.map((it, i) => (
              <button
                key={i}
                className={`dropdown-item${it.danger ? ' danger' : ''}`}
                onClick={() => {
                  close();
                  it.onSelect();
                }}
              >
                <span>{it.label}</span>
                {it.hint && <span className="dropdown-hint">{it.hint}</span>}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}
