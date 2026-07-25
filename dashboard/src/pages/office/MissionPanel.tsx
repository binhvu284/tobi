// Extracted from Office.tsx (pre-#21 refactor) — verbatim move.

import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence, useDragControls } from 'framer-motion'
import {
  X, Activity, Zap, Shield, Users, LayoutGrid, Plus, Play, Cpu, Coins, Trash2, Pencil, ListChecks,
  Pause, Square, Send, Radio, CheckCircle2, GripHorizontal, Rocket, ChevronDown, Volume2, VolumeX, Sparkles,
} from 'lucide-react'
import {
  getAgents, getOfficeStats, getMissions, getMission, createMission, runMission, patchMission,
  createAgent, updateAgent, deleteAgent, pauseMission, resumeMission, cancelMission, injectMission,
  type Agent, type OfficeStats, type Mission, type AgentUpsert,
} from '../../api'

// ── Mission detail panel ─────────────────────────────────────────────
export const PRIO_COLOR: Record<string, string> = { Urgent: 'text-danger', High: 'text-warning', Normal: 'text-accent', Low: 'text-muted' }
export const STATUS_COLOR: Record<string, string> = { planned: 'bg-muted/20 text-muted', running: 'bg-accent/20 text-accent', blocked: 'bg-danger/20 text-danger', done: 'bg-success/20 text-success', cancelled: 'bg-muted/20 text-muted' }

export function MissionPanel({ mission, agents, onClose, onChanged, onLaunch }: { mission: Mission; agents: Agent[]; onClose: () => void; onChanged: () => void; onLaunch: (id: number, mock: boolean) => void }) {
  const [m, setM] = useState<Mission>(mission)
  const [mock, setMock] = useState(true)
  useEffect(() => { setM(mission) }, [mission])
  const nameOf = (id: string) => agents.find(a => a.id === id)?.name || id

  const run = () => onLaunch(m.id, mock)  // hand off to the live war-room (HQ)
  return (
    <motion.div key={m.id} initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 40 }}
      className="sticky top-0 h-fit max-h-[calc(100vh-2rem)] w-96 flex-shrink-0 overflow-y-auto rounded-lg border border-border bg-surface p-5">
      <div className="mb-3 flex items-start justify-between">
        <div>
          <div className="font-bold text-heading">{m.title}</div>
          <div className="mt-1 flex items-center gap-2 text-[11px]">
            <span className={`rounded px-1.5 py-0.5 font-medium ${STATUS_COLOR[m.status]}`}>{m.status}</span>
            <span className={`font-bold ${PRIO_COLOR[m.priority]}`}>{m.priority}</span>
            <span className="flex items-center gap-1 text-muted"><Coins size={11} />{m.cost_tokens.toLocaleString()}</span>
          </div>
        </div>
        <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
      </div>
      {m.goal && <p className="mb-3 text-xs leading-relaxed text-text">{m.goal}</p>}

      <div className="mb-3 flex items-center gap-2">
        <button onClick={run} className="flex items-center gap-1.5 rounded bg-success/20 px-3 py-1.5 text-xs font-medium text-success hover:bg-success/30">
          <Radio size={12} /> {m.status === 'done' ? 'Re-run in War Room' : 'Launch in War Room'}
        </button>
        <label className="flex items-center gap-1 text-[11px] text-muted"><input type="checkbox" checked={mock} onChange={e => setMock(e.target.checked)} /> mock</label>
      </div>

      <div className="mb-3">
        <div className="mb-1.5 flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted"><ListChecks size={12} /> Steps (Tobi-mediated)</div>
        <div className="space-y-1.5">
          {(m.steps || []).length === 0 && <div className="text-[11px] text-muted">No steps yet — run the mission.</div>}
          {(m.steps || []).map(s => (
            <div key={s.id} className="rounded border border-border bg-bg p-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-heading">{s.seq}. {nameOf(s.agent_id)} <span className="text-muted">· {s.action}</span></span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] ${STATUS_COLOR[s.status] || 'bg-muted/20 text-muted'}`}>{s.status}</span>
              </div>
              {s.output && <div className="mt-1 line-clamp-3 text-[11px] leading-relaxed text-text">{s.output}</div>}
              {s.tokens > 0 && <div className="mt-1 text-[10px] text-muted">{s.tokens} tokens</div>}
            </div>
          ))}
        </div>
      </div>

      {(m.usage || []).length > 0 && (
        <div className="mb-3">
          <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">Cost by agent (D34)</div>
          <div className="space-y-1">
            {m.usage!.map(u => (
              <div key={u.agent_id} className="flex items-center justify-between text-[11px]">
                <span className="text-text">{nameOf(u.agent_id)} <span className="text-muted">· {u.provider}</span></span>
                <span className="font-mono text-warning">{u.total_tokens.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {m.summary && (
        <div className="rounded border border-accent/30 bg-accent/10 p-3">
          <div className="mb-1 text-[11px] uppercase tracking-wider text-accent">Tobi close-out (D69)</div>
          <pre className="whitespace-pre-wrap font-sans text-[11px] leading-relaxed text-text">{m.summary}</pre>
        </div>
      )}
    </motion.div>
  )
}

export function NewMissionModal({ onClose, onCreated }: { onClose: () => void; onCreated: (m: Mission) => void }) {
  const [title, setTitle] = useState(''); const [goal, setGoal] = useState(''); const [priority, setPriority] = useState('Normal'); const [busy, setBusy] = useState(false)
  const create = async () => {
    if (!title.trim()) return
    setBusy(true)
    try { const m = await createMission({ title: title.trim(), goal: goal.trim(), priority }); onCreated(m); onClose() } catch { /* ignore */ } finally { setBusy(false) }
  }
  const input = 'w-full rounded border border-border bg-bg px-2 py-1.5 text-xs text-text outline-none focus:border-accent/60'
  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[60] bg-black/70" onClick={onClose} />
      <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}
        className="fixed left-1/2 top-1/2 z-[61] w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-5 shadow-2xl">
        <div className="mb-4 flex items-center justify-between"><div className="font-bold text-heading">New mission</div><button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button></div>
        <div className="space-y-3">
          <input className={input} placeholder="Mission title" value={title} onChange={e => setTitle(e.target.value)} />
          <textarea className={`${input} h-20 resize-none`} placeholder="Goal / what done looks like" value={goal} onChange={e => setGoal(e.target.value)} />
          <select className={input} value={priority} onChange={e => setPriority(e.target.value)}>{['Low', 'Normal', 'High', 'Urgent'].map(p => <option key={p}>{p}</option>)}</select>
          <div className="text-[10px] text-muted">Runs the active <b>standard_delivery</b> workflow: Sunday → Alphabet → Friday.</div>
        </div>
        <button onClick={create} disabled={busy || !title.trim()} className="mt-4 w-full rounded bg-accent/20 py-1.5 text-xs font-medium text-accent hover:bg-accent/30 disabled:opacity-40">{busy ? 'Creating…' : 'Create mission'}</button>
      </motion.div>
    </>
  )
}
