import { motion, AnimatePresence } from 'framer-motion'

type Props = {
  open: boolean
  title: string
  detail: string
  onCancel: () => void
  onConfirm: () => void
}

export default function ConfirmTransitionModal({ open, title, detail, onCancel, onConfirm }: Props) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/60"
            onClick={onCancel}
          />
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.96 }}
            className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-surface p-5"
          >
            <h3 className="text-sm font-semibold text-heading">{title}</h3>
            <p className="mt-1 text-xs text-muted">{detail}</p>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={onCancel} className="rounded border border-border px-3 py-1.5 text-xs text-muted hover:text-text">
                Cancel
              </button>
              <button onClick={onConfirm} className="rounded border border-danger/40 bg-danger/10 px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/20">
                Confirm
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
