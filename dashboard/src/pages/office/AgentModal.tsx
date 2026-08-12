// Extracted from Office.tsx (pre-#21 refactor) — verbatim move.

import { useEffect, useState, useRef } from 'react'
import { softFail } from '../../lib/report'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence, useDragControls } from 'framer-motion'
import {
  X, Activity, Zap, Shield, Users, LayoutGrid, Plus, Play, Cpu, Coins, Trash2, Pencil, ListChecks,
  Pause, Square, Send, Radio, CheckCircle2, GripHorizontal, Rocket, ChevronDown, Volume2, VolumeX, Sparkles,
} from 'lucide-react'
import { getAgents, getOfficeStats, getMissions, getMission, createMission, runMission, patchMission, createAgent, updateAgent, deleteAgent, pauseMission, resumeMission, cancelMission, injectMission, type Agent, type OfficeStats, type Mission, type AgentUpsert } from '../../api.office'
import { SPRITE_KEYS } from './sprites'


// ── Agent config builder modal (D27) ────────────────────────────────
export const PROVIDERS = ['openrouter', 'anthropic', 'openai', 'google', 'mock']
export const blankAgent: AgentUpsert = { name: '', role: '', provider: 'openrouter', model: '', key_ref: '', autonomy: 'medium', max_tokens: 2000, color: '#58a6ff', sprite: 'tobi', skills: [] }

export function AgentModal({ agent, onClose, onSaved }: { agent: Agent | 'new'; onClose: () => void; onSaved: () => void }) {
  const editing = agent !== 'new'
  const a = editing ? agent : null
  const [form, setForm] = useState<AgentUpsert>(
    a ? { id: a.id, name: a.name, role: a.role || '', persona: a.persona || '', provider: a.provider, model: a.model || '', key_ref: a.key_ref || '', temperature: a.temperature, max_tokens: a.max_tokens, autonomy: a.autonomy, can_spawn: a.can_spawn, daily_budget_tokens: a.daily_budget_tokens, color: a.color || '#58a6ff', sprite: a.sprite || 'tobi', skills: a.skills } : { ...blankAgent },
  )
  const [busy, setBusy] = useState(false)
  const dragControls = useDragControls()
  const constraintsRef = useRef<HTMLDivElement>(null)
  const set = (k: keyof AgentUpsert, v: unknown) => setForm(f => ({ ...f, [k]: v }))

  const save = async () => {
    if (!form.name.trim()) return
    setBusy(true)
    try {
      if (editing) await updateAgent((a as Agent).id, form); else await createAgent(form)
      onSaved(); onClose()
    } catch (error) { softFail('this agent')(error) } finally { setBusy(false) }
  }
  const archive = async () => {
    if (!editing) return
    try { await deleteAgent((a as Agent).id); onSaved(); onClose() } catch (error) { softFail('this agent')(error) }
  }
  const F = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <label className="block"><span className="mb-1 block text-[11px] uppercase tracking-wider text-muted">{label}</span>{children}</label>
  )
  const input = 'w-full rounded border border-border bg-bg px-2 py-1.5 text-xs text-text outline-none focus:border-accent/60'

  return createPortal(
    <div data-theme="dark" className="font-['Rajdhani']">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[60] bg-black/70 backdrop-blur-sm" onClick={onClose} />
      {/* full-screen centering layer (pointer-events-none so backdrop clicks still close) */}
      <div ref={constraintsRef} className="pointer-events-none fixed inset-0 z-[61] flex items-center justify-center p-4">
        <motion.div
          drag dragControls={dragControls} dragListener={false} dragMomentum={false} dragElastic={0.06} dragConstraints={constraintsRef}
          initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}
          className="pointer-events-auto flex max-h-[88vh] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-border bg-surface text-text shadow-2xl">
          {/* drag handle = header (so inputs/scroll inside aren't hijacked) */}
          <div onPointerDown={(e) => dragControls.start(e)}
            className="flex cursor-grab items-center justify-between border-b border-border px-5 py-3 active:cursor-grabbing">
            <div className="flex items-center gap-2 font-bold text-heading"><GripHorizontal size={14} className="text-muted" /> {editing ? `Edit ${(a as Agent).name}` : 'New agent'}</div>
            <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
          </div>
          <div className="overflow-y-auto p-5">
            <div className="grid grid-cols-2 gap-3">
              <F label="Name"><input className={input} value={form.name} onChange={e => set('name', e.target.value)} /></F>
              <F label="Role"><input className={input} value={form.role} onChange={e => set('role', e.target.value)} /></F>
              <F label="Provider"><select className={input} value={form.provider} onChange={e => set('provider', e.target.value)}>{PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}</select></F>
              <F label="Model"><input className={input} value={form.model} onChange={e => set('model', e.target.value)} placeholder="e.g. claude-opus-4" /></F>
              <F label="API key (env var NAME)"><input className={input} value={form.key_ref} onChange={e => set('key_ref', e.target.value)} placeholder="ANTHROPIC_API_KEY" /></F>
              <F label="Autonomy"><select className={input} value={form.autonomy} onChange={e => set('autonomy', e.target.value)}>{['low', 'medium', 'high'].map(x => <option key={x}>{x}</option>)}</select></F>
              <F label="Max tokens"><input type="number" className={input} value={form.max_tokens} onChange={e => set('max_tokens', Number(e.target.value))} /></F>
              <F label="Sprite"><select className={input} value={form.sprite} onChange={e => set('sprite', e.target.value)}>{SPRITE_KEYS.map(s => <option key={s}>{s}</option>)}</select></F>
              <F label="Color"><input type="color" className="h-8 w-full rounded border border-border bg-bg" value={form.color} onChange={e => set('color', e.target.value)} /></F>
              <F label="Skills (comma-sep)"><input className={input} value={(form.skills || []).join(',')} onChange={e => set('skills', e.target.value.split(',').map(s => s.trim()).filter(Boolean))} /></F>
            </div>
            <F label="Persona"><textarea className={`${input} mt-3 h-20 resize-none`} value={form.persona} onChange={e => set('persona', e.target.value)} /></F>
            <div className="mt-2 text-[10px] leading-relaxed text-muted">API keys are referenced by env-var <b>name</b> only — secrets are never stored or sent here (D37).</div>
            <div className="mt-4 flex items-center justify-between">
              {editing && !(a as Agent).is_head
                ? <button onClick={archive} className="flex items-center gap-1 text-xs text-danger hover:underline"><Trash2 size={12} /> Archive</button>
                : <span />}
              <button onClick={save} disabled={busy || !form.name.trim()} className="rounded bg-accent/20 px-4 py-1.5 text-xs font-medium text-accent hover:bg-accent/30 disabled:opacity-40">{busy ? 'Saving…' : 'Save agent'}</button>
            </div>
          </div>
        </motion.div>
      </div>
    </div>,
    document.body,
  )
}
