import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react'
import { sfx } from '../hooks/useSound'
import { useReducedMotionPref } from './MotionProvider'

type Kind = 'success' | 'error' | 'info'
export type Note = { id: number; kind: Kind; title: string; detail?: string; ts: number }
type Ctx = { toast: (t: { kind?: Kind; title: string; detail?: string }) => void; notes: Note[]; clear: () => void }
const C = createContext<Ctx>(null as unknown as Ctx)
export function useToast() { return useContext(C) }

const ICON = { success: CheckCircle2, error: AlertTriangle, info: Info }
const TONE: Record<Kind, string> = {
  success: 'border-success/50 text-success', error: 'border-danger/50 text-danger', info: 'border-accent/50 text-accent',
}
const EDGE: Record<Kind, string> = { success: 'bg-success', error: 'bg-danger', info: 'bg-accent' }
const TOAST_MS = 4200
let _id = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Note[]>([])
  const [notes, setNotes] = useState<Note[]>(() => { try { return JSON.parse(localStorage.getItem('tobi.notes') || '[]') } catch { return [] } })
  const level = useReducedMotionPref()

  const toast = useCallback((t: { kind?: Kind; title: string; detail?: string }) => {
    const n: Note = { id: _id++, kind: t.kind || 'info', title: t.title, detail: t.detail, ts: Date.now() }
    setToasts(s => [...s, n])
    setNotes(s => { const u = [n, ...s].slice(0, 50); try { localStorage.setItem('tobi.notes', JSON.stringify(u)) } catch { /* ignore */ } return u })
    if (n.kind === 'success') sfx.success(); else if (n.kind === 'error') sfx.error(); else sfx.tick()
    setTimeout(() => setToasts(s => s.filter(x => x.id !== n.id)), TOAST_MS)
  }, [])
  const clear = () => { setNotes([]); try { localStorage.removeItem('tobi.notes') } catch { /* ignore */ } }

  return (
    <C.Provider value={{ toast, notes, clear }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[200] flex w-80 flex-col gap-2">
        <AnimatePresence>
          {toasts.map(t => {
            const Icon = ICON[t.kind]
            return (
              <motion.div key={t.id}
                initial={{ opacity: 0, x: level === 'off' ? 0 : 40, y: level === 'full' ? 8 : 0, scale: level === 'full' ? 0.95 : 1 }}
                animate={{ opacity: 1, x: 0, y: 0, scale: 1 }} exit={{ opacity: 0, x: level === 'off' ? 0 : 40 }}
                transition={level === 'full' ? { type: 'spring', stiffness: 380, damping: 26 } : { duration: 0.18 }}
                className={`pointer-events-auto relative flex items-start gap-2 overflow-hidden rounded-lg border bg-surface/95 p-3 pl-3.5 shadow-2xl backdrop-blur ${TONE[t.kind]}`}>
                <span className={`absolute inset-y-0 left-0 w-1 ${EDGE[t.kind]}`} />
                <Icon size={16} className="mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-heading">{t.title}</div>
                  {t.detail && <div className="mt-0.5 text-xs text-muted">{t.detail}</div>}
                </div>
                <button onClick={() => setToasts(s => s.filter(x => x.id !== t.id))} className="text-muted hover:text-text"><X size={13} /></button>
                {level !== 'off' && (
                  <motion.span aria-hidden className={`absolute bottom-0 left-0 h-0.5 w-full origin-left ${EDGE[t.kind]} opacity-60`}
                    initial={{ scaleX: 1 }} animate={{ scaleX: 0 }} transition={{ duration: TOAST_MS / 1000, ease: 'linear' }} />
                )}
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </C.Provider>
  )
}
