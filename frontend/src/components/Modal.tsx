import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
  /** 页面内嵌模式：不渲染遮罩/固定定位，直接作为页面区块展示（P2 页面化） */
  embedded?: boolean;
  /**
   * 隐藏内嵌模式的标题栏（M-02）：页面级内嵌面板已有 page-tabs 作为唯一标题层级，
   * 返回能力由 SideNav 承担，避免出现双标题与冗余返回按钮。
   */
  headerless?: boolean;
}

/** 可聚焦元素选择器（用于打开时聚焦与 Tab 焦点陷阱） */
const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * 当前打开的弹窗栈（仅顶层弹窗响应 Esc / Tab）。
 * 应用里存在「弹窗内再开确认框」的嵌套场景，必须让最上层对话框独占键盘交互，
 * 否则 Esc 会同时关掉两层、Tab 陷阱也会互相抢占。
 */
const openDialogs: HTMLElement[] = [];

/** 通用弹窗：Esc / 点击遮罩关闭；embedded 模式下作为页面内嵌面板 */
export function Modal({ title, onClose, children, footer, width = 640, embedded, headerless }: ModalProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  // 用 ref 持有最新的 onClose：调用方常传内联箭头函数，若让 effect 依赖它，
  // 每次父组件重渲染都会重建 effect → 焦点被反复重置。这里让 effect 只在挂载时初始化一次。
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (embedded) return;
    const panel = panelRef.current;
    if (panel) openDialogs.push(panel);
    // 记住打开前的焦点，关闭后归还，避免焦点丢回 <body>
    const opener = document.activeElement as HTMLElement | null;
    if (panel) {
      const first = panel.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? panel).focus();
    }

    const handler = (e: KeyboardEvent) => {
      // 只有最顶层弹窗处理键盘事件
      if (openDialogs[openDialogs.length - 1] !== panel) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key !== 'Tab' || !panel) return;
      const nodes = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (nodes.length === 0) {
        e.preventDefault();
        panel.focus();
        return;
      }
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const current = document.activeElement;
      if (e.shiftKey && (current === first || current === panel)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && current === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => {
      window.removeEventListener('keydown', handler);
      const i = openDialogs.indexOf(panel as HTMLElement);
      if (i >= 0) openDialogs.splice(i, 1);
      if (opener && document.contains(opener)) opener.focus();
    };
  }, [embedded]);

  if (embedded) {
    return (
      <div className="modal modal-embedded" style={{ width: '100%' }}>
        {!headerless && (
          <div className="modal-header">
            <h3>{title}</h3>
            <button className="btn btn-ghost btn-sm" onClick={onClose} title="返回主工作台">
              返回
            </button>
          </div>
        )}
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
      <div
        className="modal"
        style={{ width }}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="modal-header">
          <h3 id={titleId}>{title}</h3>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="关闭对话框">
            关闭
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
