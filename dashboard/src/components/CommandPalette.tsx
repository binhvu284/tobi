import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, ArrowRight, Play, Palette, LayoutDashboard, Network, Zap, Building2, Kanban, HeartPulse, Terminal, Settings, type LucideIcon } from 'lucide-react'
import { useTheme, THEMES, THEME_META, type Theme } from '../context/ThemeProvider'
import { useToast } from '../context/ToastProvider'
import { runEngine, type EngineName } from '../api'

type Action = { id: string; label: string; group: string; icon: LucideIcon; run: () => void | Promise<void> }

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const nav = useNavigate()
  const { set } = useTheme()
  const { toast } = useToast()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setOpen(o => !o) }
      else if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  useEffect(() => { if (open) { setQ(''); setI(0); setTimeout(() => inputRef.current?.focus(), 30) } }, [open])

  const runEng = async (name: EngineName, label: string) => {
    toast({ kind: 'info', title: `${label}…`, detail: 'Triggered' })
    try {
      const r = await runEngine(name)
      toast({ kind: r.ok ? 'success' : 'error', title: label, detail: r.message || r.detail || (r.ok ? 'Done' : 'Failed') })
    } catch (e) { toast({ kind: 'error', title: label, detail: (e as Error).message }) }
  }

  const actions: Action[] = useMemo(() => [
    { id: 'nav-dash', label: 'Go to Dashboard', group: 'Navigate', icon: LayoutDashboard, run: () => nav('/dashboard') },
    { id: 'nav-arch', label: 'Go to Architecture', group: 'Navigate', icon: Network, run: () => nav('/architecture') },
    { id: 'nav-abil', label: 'Go to Ability', group: 'Navigate', icon: Zap, run: () => nav('/ability') },
    { id: 'nav-office', label: 'Go to Office', group: 'Navigate', icon: Building2, run: () => nav('/office') },
    { id: 'nav-task', label: 'Go to Task', group: 'Navigate', icon: Kanban, run: () => nav('/task') },
    { id: 'nav-health', label: 'Go to Health', group: 'Navigate', icon: HeartPulse, run: () => nav('/health') },
    { id: 'nav-control', label: 'Go to Control Room', group: 'Navigate', icon: Terminal, run: () => nav('/control') },
    { id: 'nav-settings', label: 'Go to Settings', group: 'Navigate', icon: Settings, run: () => nav('/settings') },
    { id: 'run-research', label: 'Run research', group: 'Run', icon: Play, run: () => runEng('research', 'Run research') },
    { id: 'run-report', label: 'Generate daily report', group: 'Run', icon: Play, run: () => runEng('report', 'Generate report') },
    { id: 'run-ceo', label: 'Run CEO strategy review', group: 'Run', icon: Play, run: () => runEng('ceo', 'CEO review') },
    { id: 'run-execute', label: 'Run execution cycle', group: 'Run', icon: Play, run: () => runEng('execute', 'Execution cycle') },
    ...THEMES.map((t: Theme) => ({ id: `theme-${t}`, label: `Theme: ${THEME_META[t].label}`, group: 'Theme', icon: Palette, run: () => set({ theme: t }) })),
  ], [nav, set]) // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    return s ? actions.filter(a => a.label.toLowerCase().includes(s) || a.group.toLowerCase().includes(s)) : actions
  }, [q, actions])

  const exec = (a?: Action) => { if (!a) return; setOpen(false); a.run() }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[150] bg-black/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
          <motion.div initial={{ opacity: 0, y: -16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -16, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 380, damping: 28 }}
            className="fixed left-1/2 top-24 z-[151] w-[92vw] max-w-lg -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-surface shadow-2xl"
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setI(v => Math.min(v + 1, filtered.length - 1)) }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setI(v => Math.max(v - 1, 0)) }
              else if (e.key === 'Enter') { e.preventDefault(); exec(filtered[i]) }
            }}>
            <div className="flex items-center gap-2 border-b border-border px-3">
              <Search size={16} className="text-muted" />
              <input ref={inputRef} value={q} onChange={e => { setQ(e.target.value); setI(0) }}
                placeholder="Search pages, run a feature, switch theme…"
                className="w-full bg-transparent py-3 text-sm text-text outline-none placeholder:text-muted" />
              <kbd className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted">ESC</kbd>
            </div>
            <div className="max-h-80 overflow-y-auto py-1">
              {filtered.length === 0 && <div className="px-4 py-6 text-center text-sm text-muted">No matches</div>}
              {filtered.map((a, idx) => {
                const Icon = a.icon
                return (
                  <button key={a.id} onMouseEnter={() => setI(idx)} onClick={() => exec(a)}
                    className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm ${idx === i ? 'bg-accent/15 text-text' : 'text-muted'}`}>
                    <Icon size={15} />
                    <span className="flex-1 text-text">{a.label}</span>
                    <span className="text-[10px] uppercase tracking-wider text-muted">{a.group}</span>
                    {idx === i && <ArrowRight size={13} className="text-accent" />}
                  </button>
                )
              })}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
