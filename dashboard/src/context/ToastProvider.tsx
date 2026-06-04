import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react'
import { sfx } from '../hooks/useSound'

type Kind = 'success' | 'error' | 'info'
export type Note = { id: number; kind: Kind; title: string; detail?: string; ts: number }
type Ctx = { toast: (t: { kind?: Kind; title: string; detail?: string }) => void; notes: Note[]; clear: () => void }
const C = createContext<Ctx>(null as unknown as Ctx)
export function useToast() { return useContext(C) }

const ICON = { success: CheckCircle2, error: AlertTriangle, info: Info }
const TONE: Record<Kind, string> = {
  success: 'border-success/50 text-success', error: 'border-danger/50 text-danger', info: 'border-accent/50 text-accent',
}
let _id = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Note[]>([])
  const [notes, setNotes] = useState<Note[]>(() => { try { return JSON.parse(localStorage.getItem('tobi.notes') || '[]') } catch { return [] } })

  const toast = useCallback((t: { kind?: Kind; title: string; detail?: string }) => {
    const n: Note = { id: _id++, kind: t.kind || 'info', title: t.title, detail: t.detail, ts: Date.now() }
    setToasts(s => [...s, n])
    setNotes(s => { const u = [n, ...s].slice(0, 50); try { localStorage.setItem('tobi.notes', JSON.stringify(u)) } catch { /* ignore */ } return u })
    if (n.kind === 'success') sfx.success(); else if (n.kind === 'error') sfx.error(); else sfx.tick()
    setTimeout(() => setToasts(s => s.filter(x => x.id !== n.id)), 4200)
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
                initial={{ opacity: 0, y: 24, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, x: 40 }}
                transition={{ type: 'spring', stiffness: 380, damping: 26 }}
                className={`pointer-events-auto flex items-start gap-2 rounded-lg border bg-surface/95 p-3 shadow-2xl backdrop-blur ${TONE[t.kind]}`}>
                <Icon size={16} className="mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-heading">{t.title}</div>
                  {t.detail && <div className="mt-0.5 text-xs text-muted">{t.detail}</div>}
                </div>
                <button onClick={() => setToasts(s => s.filter(x => x.id !== t.id))} className="text-muted hover:text-text"><X size={13} /></button>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </C.Provider>
  )
}
