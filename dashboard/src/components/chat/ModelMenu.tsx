import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, Check, Eye, Brain, Zap, Cpu } from 'lucide-react'
import type { AvailableModel } from '../../api'
import LlmLogo, { BRAND_META, brandForProvider } from '../LlmLogo'

/**
 * Premium model picker (Premium Chat v2 · checkpoint B).
 * A grouped dropdown: official brand logos (LobeHub icon set), models grouped by
 * provider with each model wearing its own brand mark, and per-model badges —
 * context size, 👁 vision, reasoning, and a price/speed tier dot.
 * `direction="up"` opens above the trigger (for the composer bar).
 */

const meta = (p: string) => BRAND_META[brandForProvider(p)]

export function ProviderLogo({ provider, size = 15 }: { provider: string; size?: number }) {
  return <LlmLogo provider={provider} size={size} />
}

const fmtCtx = (n?: number) => !n ? '' : n >= 1_000_000 ? `${(n / 1_000_000).toFixed(n % 1_000_000 ? 1 : 0)}M` : `${Math.round(n / 1000)}K`

type Caps = { vision: boolean; reasoning: boolean; speed: 'fast' | 'balanced' | 'premium' }
function caps(id: string): Caps {
  const s = id.toLowerCase()
  return {
    vision: /4o|gemini|claude|grok-4|\bo3\b|\bo4\b|vision|-vl|pixtral|llava/.test(s),
    reasoning: /\bo1\b|\bo3\b|\bo4\b|-r1|qwq|reason|think|gemini-2\.5|grok-4|glm-4\.6|deepseek-r/.test(s),
    speed: /mini|flash|air|:free|nano|haiku|-8b|-7b|small/.test(s) ? 'fast'
      : /opus|gemini-2\.5-pro|grok-4|glm-4\.6|gpt-4o|\bo3\b|405b|large/.test(s) ? 'premium' : 'balanced',
  }
}
const SPEED: Record<Caps['speed'], { color: string; label: string }> = {
  fast: { color: '#3FB950', label: 'Fast / low cost' },
  balanced: { color: '#D29922', label: 'Balanced' },
  premium: { color: '#F0883E', label: 'Premium / higher cost' },
}

function Badges({ id, context }: { id: string; context?: number }) {
  const c = caps(id)
  return (
    <span className="ml-auto flex shrink-0 items-center gap-1.5 pl-2">
      {context ? <span className="font-mono text-[10px] tabular-nums text-muted">{fmtCtx(context)}</span> : null}
      {c.vision && <Eye size={12} className="text-accent" />}
      {c.reasoning && <Brain size={12} className="text-purple" />}
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: SPEED[c.speed].color }} title={SPEED[c.speed].label} />
    </span>
  )
}

export default function ModelMenu({ models, value, onChange, open: openProp, onOpenChange, direction = 'down' }: {
  models: AvailableModel[]; value: string | null; onChange: (id: string) => void
  open?: boolean; onOpenChange?: (o: boolean) => void; direction?: 'down' | 'up'
}) {
  const [openState, setOpenState] = useState(false)
  const open = openProp ?? openState
  const setOpen = (o: boolean) => { setOpenState(o); onOpenChange?.(o) }
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc); document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  const current = models.find(m => m.id === value)
  // group by provider, preserving catalog order
  const groups: { provider: string; items: AvailableModel[] }[] = []
  for (const m of models) {
    let g = groups.find(x => x.provider === m.provider)
    if (!g) { g = { provider: m.provider, items: [] }; groups.push(g) }
    g.items.push(m)
  }

  const pick = (id: string) => { onChange(id); setOpen(false) }

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(!open)}
        className={`flex max-w-[44vw] items-center gap-1.5 rounded-lg border bg-surface py-1.5 pl-1.5 pr-2 text-xs text-text outline-none transition-colors sm:max-w-[240px] ${open ? 'border-accent/50' : 'border-border hover:border-accent/40'}`}>
        {current ? <LlmLogo model={current.id} size={14} /> : <span className="flex h-[23px] w-[23px] items-center justify-center rounded-md bg-accent/15 text-accent"><Cpu size={13} /></span>}
        <span className="truncate">{current ? current.model : 'Auto · default'}</span>
        <ChevronDown size={13} className={`shrink-0 text-muted transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: direction === 'up' ? 4 : -4, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: direction === 'up' ? 4 : -4, scale: 0.98 }}
            transition={{ duration: 0.13 }}
            className={`absolute right-0 z-30 max-h-[60vh] w-80 max-w-[88vw] overflow-y-auto rounded-xl border border-border bg-surface p-1.5 shadow-2xl ${
              direction === 'up' ? 'bottom-full mb-1.5' : 'mt-1.5'}`}>
            <button onClick={() => pick('')}
              className={`flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-bg/60 ${!value ? 'text-accent' : 'text-text'}`}>
              <span className="flex h-[23px] w-[23px] items-center justify-center rounded-md bg-accent/15 text-accent"><Zap size={13} /></span>
              <span className="flex-1">Auto · default</span>
              {!value && <Check size={14} className="text-accent" />}
            </button>
            {groups.length === 0 && (
              <div className="px-2 py-3 text-center text-[11px] text-muted">No models yet — add a provider key in Models.</div>
            )}
            {groups.map(g => (
              <div key={g.provider} className="mt-1">
                <div className="flex items-center gap-1.5 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted">
                  <ProviderLogo provider={g.provider} size={12} /> {meta(g.provider).name}
                </div>
                {g.items.map(m => (
                  <button key={m.id} onClick={() => pick(m.id)}
                    className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-bg/60 ${value === m.id ? 'bg-accent/10 text-text' : 'text-text'}`}>
                    <LlmLogo model={m.id} size={13} />
                    <span className="truncate">{m.model}</span>
                    <Badges id={m.id} context={m.context} />
                    {value === m.id && <Check size={13} className="shrink-0 text-accent" />}
                  </button>
                ))}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
