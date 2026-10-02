import type { ReactNode } from 'react';
import { Modal } from './Modal';

interface ConfirmDialogProps {
  title: string;
  message: ReactNode;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  busy?: boolean;
  /** 可选的第三个按钮（位于「取消」与主按钮之间），用于需要「两条出路」的确认场景 */
  secondaryText?: string;
  secondaryDanger?: boolean;
  onSecondary?: () => void;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 危险操作二次确认对话框 */
export function ConfirmDialog({
  title,
  message,
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
  busy = false,
  secondaryText,
  secondaryDanger = false,
  onSecondary,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      width={480}
      footer={
        <>
          <button className="btn" onClick={onCancel} disabled={busy}>
            {cancelText}
          </button>
          {secondaryText && onSecondary && (
            <button
              className={secondaryDanger ? 'btn btn-danger' : 'btn'}
              onClick={onSecondary}
              disabled={busy}
            >
              {secondaryText}
            </button>
          )}
          <button
            className={danger ? 'btn btn-danger' : 'btn btn-primary'}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy && <span className="spinner" />}
            {confirmText}
          </button>
        </>
      }
    >
      <div style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-primary)' }}>{message}</div>
    </Modal>
  );
}
