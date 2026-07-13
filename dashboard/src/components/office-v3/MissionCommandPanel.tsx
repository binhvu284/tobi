import { useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, Circle, Pause, Play, Plus, RotateCcw, Square, Timer, Zap } from 'lucide-react'
import type { Mission } from '../../api'
import type { WarState } from '../../hooks/useMissionStream'

const statusIcon = (status: string) => status === 'done' ? CheckCircle2 : status === 'blocked' ? AlertCircle : status === 'running' ? Zap : Circle

export default function MissionCommandPanel({ missions, selectedId, liveMissionId, war, onSelect, onPropose }:
  { missions: Mission[]; selectedId?: number; liveMissionId: number | null; war: WarState; onSelect: (mission: Mission) => void; onPropose: (action: string, args: Record<string, unknown>) => void }) {
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [goal, setGoal] = useState('')
  const [priority, setPriority] = useState('Normal')
  const selected = useMemo(() => missions.find(m => m.id === selectedId) || null, [missions, selectedId])
  const running = liveMissionId && selected?.id === liveMissionId

  const proposeCreate = () => {
    if (!title.trim()) return
    onPropose('office_create_mission', { title: title.trim(), goal: goal.trim(), priority })
    setCreating(false); setTitle(''); setGoal('')
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div><div className="text-[10px] font-semibold uppercase text-muted">Mission command</div><div className="text-sm font-semibold text-heading">Queue and live control</div></div>
        <button onClick={() => setCreating(v => !v)} title="Create mission" className="flex h-8 w-8 items-center justify-center border border-border text-muted hover:border-accent hover:text-accent"><Plus size={15} /></button>
      </div>

      {creating && (
        <div className="space-y-2 border-b border-border bg-overlay/5 p-3">
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Mission title" className="w-full border border-border bg-bg px-2.5 py-2 text-xs text-text outline-none focus:border-accent" />
          <textarea value={goal} onChange={e => setGoal(e.target.value)} placeholder="Outcome and constraints" rows={3} className="w-full resize-none border border-border bg-bg px-2.5 py-2 text-xs text-text outline-none focus:border-accent" />
          <div className="flex items-center gap-2">
            <select value={priority} onChange={e => setPriority(e.target.value)} className="h-8 flex-1 border border-border bg-bg px-2 text-xs text-text outline-none">
              {['Low','Normal','High','Urgent'].map(p => <option key={p}>{p}</option>)}
            </select>
            <button onClick={proposeCreate} disabled={!title.trim()} className="h-8 bg-accent px-3 text-xs font-semibold text-bg disabled:opacity-40">Review</button>
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {missions.length === 0 && <div className="p-6 text-center text-xs text-muted">No missions yet. Create a mission to bring the floor online.</div>}
        {missions.map(mission => {
          const Icon = statusIcon(mission.status)
          const active = selectedId === mission.id
          return (
            <button key={mission.id} onClick={() => onSelect(mission)}
              className={`flex w-full items-start gap-3 border-b border-border px-4 py-3 text-left transition-colors ${active ? 'bg-accent/8' : 'hover:bg-overlay/5'}`}>
              <span className={`mt-0.5 ${mission.status === 'running' ? 'text-warning' : mission.status === 'done' ? 'text-success' : 'text-muted'}`}><Icon size={14} /></span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] font-semibold text-heading">{mission.title}</span>
                <span className="mt-1 flex gap-2 text-[9px] uppercase text-muted"><span>{mission.status}</span><span>{mission.priority}</span><span>{mission.cost_tokens.toLocaleString()} tok</span></span>
              </span>
            </button>
          )
        })}
      </div>

      {selected && (
        <div className="border-t border-border bg-surface/60 p-4">
          <div className="mb-2 text-[10px] uppercase text-muted">Selected mission</div>
          <div className="text-sm font-semibold text-heading">{selected.title}</div>
          <p className="mt-1 line-clamp-3 text-[11px] leading-relaxed text-muted">{selected.goal || selected.summary || 'No goal recorded.'}</p>
          {running && (
            <div className="mt-3 border-l-2 border-warning pl-3">
              <div className="flex items-center gap-1.5 text-[10px] uppercase text-warning"><Timer size={11} /> live execution</div>
              <div className="mt-1 truncate text-[11px] text-text">{war.activeSeq != null ? war.steps[war.activeSeq]?.action || 'Working' : war.status}</div>
            </div>
          )}
          <div className="mt-3 grid grid-cols-3 gap-1.5">
            {!running ? (
              <button onClick={() => onPropose('office_run_mission', { mission_id: selected.id, mock: false })} className="col-span-3 flex h-8 items-center justify-center gap-1.5 bg-accent text-xs font-semibold text-bg"><Play size={12} /> Review run</button>
            ) : (
              <>
                <button onClick={() => onPropose('office_control_mission', { mission_id: selected.id, action: 'pause' })} className="flex h-8 items-center justify-center gap-1 border border-border text-[10px] text-muted hover:text-text"><Pause size={11} /> Pause</button>
                <button onClick={() => onPropose('office_control_mission', { mission_id: selected.id, action: 'resume' })} className="flex h-8 items-center justify-center gap-1 border border-border text-[10px] text-muted hover:text-text"><RotateCcw size={11} /> Resume</button>
                <button onClick={() => onPropose('office_control_mission', { mission_id: selected.id, action: 'cancel' })} className="flex h-8 items-center justify-center gap-1 border border-danger/40 text-[10px] text-danger"><Square size={11} /> Cancel</button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
