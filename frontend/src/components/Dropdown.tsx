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

  // 打开后先定位再绘制，避免首帧闪烁
  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (rootRef.current?.contains(t) || menuRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
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
      <div onClick={() => setOpen((v) => !v)}>{trigger}</div>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            className="dropdown-menu"
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
                  setOpen(false);
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
