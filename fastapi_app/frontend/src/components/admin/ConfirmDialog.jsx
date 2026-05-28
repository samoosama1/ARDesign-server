import { useEffect } from 'react'

/**
 * Controlled confirmation dialog reusing the app's .modal-overlay / .modal
 * styling. Replaces window.confirm so destructive actions get a real,
 * on-brand prompt. Render it unconditionally and toggle `open`.
 *
 *   <ConfirmDialog
 *     open={!!pending}
 *     title="Delete user?"
 *     confirmLabel="Delete"
 *     danger
 *     busy={busy}
 *     onConfirm={...}
 *     onCancel={() => setPending(null)}
 *   >
 *     optional rich body (e.g. a diff summary)
 *   </ConfirmDialog>
 */
export default function ConfirmDialog({
  open,
  title,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
  children,
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => {
      if (e.key === 'Escape' && !busy) onCancel?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, onCancel])

  if (!open) return null

  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel?.()
      }}
    >
      <div className="modal confirm-dialog" role="dialog" aria-modal="true" aria-label={title}>
        <h3 className="confirm-title">{title}</h3>
        {children && <div className="confirm-body">{children}</div>}
        <div className="confirm-actions">
          <button className="btn-secondary" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            className={danger ? 'btn-delete' : 'btn-primary'}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
