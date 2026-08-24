// Announcements and confirmations.
//
// Morpheus does not reuse TOBI's ToastProvider, for one concrete reason: TOBI's toasts render in
// a portal at the document root, outside the element that carries Morpheus's theme variables, so
// they would come out wearing TOBI's colours on top of Morpheus's UI. Keeping the layer inside
// the themed subtree guarantees they always match.
//
// Two things live here:
//   announce()  a transient statement that something happened, and what it means
//   confirm()   a promise-returning dialog for anything the owner cannot casually undo
import {
  createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode,
} from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, AlertTriangle, Info, ShieldAlert, X } from 'lucide-react'
import { Btn } from './ui'

type Tone = 'ok' | 'warn' | 'danger' | 'info'
type Note = { id: number; tone: Tone; title: string; detail?: string }

type ConfirmSpec = {
  title: string
  body: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'danger' | 'accent'
  /** Typed confirmation for anything irreversible. The owner must type this word exactly. */
  typeToConfirm?: string
}

type Ctx = {
  announce: (n: Omit<Note, 'id'>) => void
  confirm: (spec: ConfirmSpec) => Promise<boolean>
}

const FeedbackContext = createContext<Ctx | null>(null)

const TONE_ICON: Record<Tone, ReactNode> = {
  ok: <Check size={14} className="text-success" />,
  warn: <AlertTriangle size={14} className="text-warning" />,
  danger: <ShieldAlert size={14} className="text-danger" />,
  info: <Info size={14} className="text-accent" />,
}

const TONE_EDGE: Record<Tone, string> = {
  ok: 'border-l-success',
  warn: 'border-l-warning',
  danger: 'border-l-danger',
  info: 'border-l-accent',
}

export function MorpheusFeedbackProvider({ children }: { children: ReactNode }) {
  const [notes, setNotes] = useState<Note[]>([])
  const [dialog, setDialog] = useState<ConfirmSpec | null>(null)
  const [typed, setTyped] = useState('')
  const resolver = useRef<((v: boolean) => void) | null>(null)
  const seq = useRef(0)

  const announce = useCallback((n: Omit<Note, 'id'>) => {
    const id = ++seq.current
    setNotes(p => [...p, { ...n, id }])
    setTimeout(() => setNotes(p => p.filter(x => x.id !== id)), 4200)
  }, [])

  const confirm = useCallback((spec: ConfirmSpec) => {
    setDialog(spec)
    setTyped('')
    return new Promise<boolean>(resolve => { resolver.current = resolve })
  }, [])

  const settle = useCallback((ok: boolean) => {
    resolver.current?.(ok)
    resolver.current = null
    setDialog(null)
    setTyped('')
  }, [])

  const value = useMemo<Ctx>(() => ({ announce, confirm }), [announce, confirm])
  const blocked = !!dialog?.typeToConfirm && typed.trim() !== dialog.typeToConfirm

  return (
    <FeedbackContext.Provider value={value}>
      {children}

      {/* Announcements: bottom-right, stacked, out of the way of the sidebar and the composer. */}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[70] flex w-[334px] flex-col gap-2"
        role="status" aria-live="polite">
        <AnimatePresence initial={false}>
          {notes.map(n => (
            <motion.div key={n.id} layout
              initial={{ opacity: 0, x: 24, scale: 0.97 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 24, scale: 0.97 }}
              transition={{ duration: 0.26, ease: [0.16, 1, 0.3, 1] }}
              className={`pointer-events-auto flex items-start gap-2.5 rounded-card border border-border
                border-l-2 bg-panel px-3.5 py-3 shadow-popover ${TONE_EDGE[n.tone]}`}>
              <span className="mt-0.5 shrink-0">{TONE_ICON[n.tone]}</span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium leading-snug text-heading">{n.title}</p>
                {n.detail && <p className="mt-0.5 text-[12px] leading-relaxed text-muted">{n.detail}</p>}
              </div>
              <button onClick={() => setNotes(p => p.filter(x => x.id !== n.id))}
                aria-label="Dismiss" className="shrink-0 rounded p-0.5 text-muted transition-colors hover:text-text">
                <X size={13} />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Confirmation */}
      <AnimatePresence>
        {dialog && (
          <motion.div className="fixed inset-0 z-[80] grid place-items-center px-6"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}>
            <button aria-label="Cancel" onClick={() => settle(false)}
              className="absolute inset-0 cursor-default bg-bg/80 backdrop-blur-sm" />
            <motion.div role="dialog" aria-modal="true" aria-labelledby="mdlg-title"
              initial={{ opacity: 0, y: 12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
              className="relative w-full max-w-[420px] rounded-card border border-border bg-panel p-5 shadow-popover">
              <h2 id="mdlg-title" className="text-[16px] font-semibold text-heading">{dialog.title}</h2>
              <p className="mt-2 text-[13.5px] leading-relaxed text-text/85">{dialog.body}</p>

              {dialog.typeToConfirm && (
                <div className="mt-4">
                  <label htmlFor="mdlg-type" className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted">
                    Type {dialog.typeToConfirm} to continue
                  </label>
                  <input id="mdlg-type" autoFocus value={typed} onChange={e => setTyped(e.target.value)}
                    className="mt-1.5 w-full rounded-input border border-border bg-bg px-3 py-2 text-[13.5px]
                      text-heading outline-none transition-colors focus:border-danger/60 focus:ring-2 focus:ring-danger/15" />
                </div>
              )}

              <div className="mt-5 flex justify-end gap-2">
                <Btn variant="ghost" onClick={() => settle(false)}>{dialog.cancelLabel ?? 'Cancel'}</Btn>
                <Btn variant={dialog.tone === 'danger' ? 'danger' : 'primary'}
                  disabled={blocked} onClick={() => settle(true)}>
                  {dialog.confirmLabel ?? 'Confirm'}
                </Btn>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </FeedbackContext.Provider>
  )
}

export function useFeedback() {
  const ctx = useContext(FeedbackContext)
  if (!ctx) throw new Error('useFeedback must be used within MorpheusFeedbackProvider')
  return ctx
}
