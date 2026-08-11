import type { ReactNode } from 'react';
import { Modal } from './Modal';

interface ConfirmDialogProps {
  title: string;
  message: ReactNode;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  busy?: boolean;
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
