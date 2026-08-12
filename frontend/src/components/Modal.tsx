import { useEffect } from 'react';
import type { ReactNode } from 'react';

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
  /** 页面内嵌模式：不渲染遮罩/固定定位，直接作为页面区块展示（P2 页面化） */
  embedded?: boolean;
}

/** 通用弹窗：Esc / 点击遮罩关闭；embedded 模式下作为页面内嵌面板 */
export function Modal({ title, onClose, children, footer, width = 640, embedded }: ModalProps) {
  useEffect(() => {
    if (embedded) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose, embedded]);

  if (embedded) {
    return (
      <div className="modal modal-embedded" style={{ width: '100%' }}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="btn btn-ghost btn-sm" onClick={onClose} title="返回主工作台">
            返回
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    );
  }

  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" style={{ width }}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
