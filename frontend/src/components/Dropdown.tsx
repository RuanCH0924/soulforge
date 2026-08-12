import { useEffect, useRef, useState } from 'react';

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

/** 通用下拉菜单：点击外部 / Esc 关闭 */
export function Dropdown({ trigger, items, title, align = 'right' }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="dropdown" ref={ref}>
      <div onClick={() => setOpen((v) => !v)}>{trigger}</div>
      {open && (
        <div className={`dropdown-menu ${align === 'right' ? 'align-right' : ''}`}>
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
        </div>
      )}
    </div>
  );
}
