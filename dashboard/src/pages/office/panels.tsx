// Extracted from Office.tsx (pre-#21 refactor) — verbatim move.

import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence, useDragControls } from 'framer-motion'
import {
  X, Activity, Zap, Shield, Users, LayoutGrid, Plus, Play, Cpu, Coins, Trash2, Pencil, ListChecks,
  Pause, Square, Send, Radio, CheckCircle2, GripHorizontal, Rocket, ChevronDown, Volume2, VolumeX, Sparkles,
} from 'lucide-react'
import { getAgents, getOfficeStats, getMissions, getMission, createMission, runMission, patchMission, createAgent, updateAgent, deleteAgent, pauseMission, resumeMission, cancelMission, injectMission, type Agent, type OfficeStats, type Mission, type AgentUpsert } from '../../api.office'
import { useMissionStream, type WarState } from '../../hooks/useMissionStream'
import { CoreGlow, StatusDot, spriteOf } from './sprites'


export function StationCard({ agent, selected, dimmed, hub, active, onSelect }: { agent: Agent; selected: boolean; dimmed: boolean; hub?: boolean; active?: boolean; onSelect: () => void }) {
  const color = agent.color || '#58a6ff'
  const Character = spriteOf(agent)
  const working = agent.live.status === 'working' || active === true
  return (
    <motion.button
      onClick={(e) => { e.stopPropagation(); onSelect() }}
      animate={{ opacity: dimmed ? 0.4 : 1, scale: selected ? 1.04 : active ? 1.06 : 1 }}
      whileHover={{ scale: selected ? 1.05 : 1.04 }} whileTap={{ scale: 0.97 }}
      transition={{ type: 'spring', stiffness: 320, damping: 24 }}
      className={`relative flex ${hub ? 'w-44' : 'w-40'} flex-col items-center gap-1 rounded-xl border bg-black/70 px-4 py-3 text-center backdrop-blur-sm`}
      style={{ borderColor: active || selected ? color : `${color}66`, boxShadow: `0 0 ${active ? 38 : selected ? 28 : working ? 20 : 12}px ${color}${active ? '99' : selected ? '66' : '33'}` }}
    >
      {active && (
        <motion.span className="pointer-events-none absolute -inset-1 rounded-xl border-2" style={{ borderColor: color }}
          animate={{ opacity: [0.7, 0.1, 0.7], scale: [1, 1.06, 1] }} transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut' }} />
      )}
      {hub && <div className="absolute -top-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-accent/20 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-accent">Core</div>}
      <div className="flex h-14 w-12 items-end justify-center"><div className="origin-bottom scale-[0.7]"><Character working={working} /></div></div>
      <div className="text-sm font-bold uppercase tracking-wide" style={{ color }}>{agent.name}</div>
      <div className="text-[10px] text-gray-400">{agent.role}</div>
      <div className="mt-0.5 flex items-center gap-1.5 whitespace-nowrap text-[10px] uppercase tracking-wider text-gray-300">
        <StatusDot status={active ? 'working' : agent.live.status} /> {active ? 'working' : agent.live.status}
      </div>
    </motion.button>
  )
}

export function HqBase({ agents, selectedId, activeAgentId, onSelect }: { agents: Agent[]; selectedId: string | null; activeAgentId?: string | null; onSelect: (id: string | null) => void }) {
  const head = agents.find(a => a.is_head) || agents[0] || null
  const others = agents.filter(a => a !== head)
  const R = 35
  const pos = others.map((_, i) => {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(1, others.length)
    return { x: 50 + Math.cos(ang) * R, y: 50 + Math.sin(ang) * (R * 0.9) }
  })
  const toggle = (id: string) => onSelect(selectedId === id ? null : id)
  return (
    <>
      {/* DESKTOP — hub + ring with neon connector lines + live handoff packet */}
      <div className="relative hidden h-full w-full md:block">
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
          {others.map((a, i) => {
            const isActive = a.id === activeAgentId
            const live = a.live.status === 'working' || selectedId === a.id || isActive
            return (
              <g key={a.id}>
                <line x1="50" y1="50" x2={pos[i].x} y2={pos[i].y}
                  stroke={a.color || '#58a6ff'} strokeWidth={isActive ? 0.6 : live ? 0.45 : 0.28} strokeDasharray="2 2"
                  className={live ? 'svg-flow-line' : ''} opacity={live ? 0.95 : 0.3} />
                {isActive && (
                  <motion.circle r={1.3} fill={a.color || '#58a6ff'}
                    initial={{ cx: pos[i].x, cy: pos[i].y }}
                    animate={{ cx: [pos[i].x, 50], cy: [pos[i].y, 50] }}
                    transition={{ duration: 1.1, repeat: Infinity, ease: 'linear' }} />
                )}
              </g>
            )
          })}
        </svg>
        {head && (
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
            <CoreGlow color={head.color || '#58a6ff'} />
            <StationCard agent={head} hub active={head.id === activeAgentId} selected={selectedId === head.id} dimmed={!!selectedId && selectedId !== head.id} onSelect={() => toggle(head.id)} />
          </div>
        )}
        {others.map((a, i) => (
          <div key={a.id} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ left: `${pos[i].x}%`, top: `${pos[i].y}%` }}>
            <StationCard agent={a} active={a.id === activeAgentId} selected={selectedId === a.id} dimmed={!!selectedId && selectedId !== a.id} onSelect={() => toggle(a.id)} />
          </div>
        ))}
      </div>
      {/* MOBILE — stacked column (core first) */}
      <div className="flex h-full w-full flex-col items-center gap-3 overflow-y-auto px-4 py-6 md:hidden">
        {head && <StationCard agent={head} hub active={head.id === activeAgentId} selected={selectedId === head.id} dimmed={false} onSelect={() => toggle(head.id)} />}
        {others.map(a => <StationCard key={a.id} agent={a} active={a.id === activeAgentId} selected={selectedId === a.id} dimmed={false} onSelect={() => toggle(a.id)} />)}
      </div>
    </>
  )
}
/** Flat, screen-space agent detail panel for the HQ scene. Rendered OUTSIDE the
 * 3D-transformed plane so its text never skews. Glance-and-read only — full
 * config/missions live in Ops (the "Manage in Ops" affordance jumps there). */
export function AgentHqPanel({ agent, onClose, onManage, liveText }: { agent: Agent; onClose: () => void; onManage: () => void; liveText?: string }) {
  const color = agent.color || '#58a6ff'
  const Character = spriteOf(agent)
  const Row = ({ k, v }: { k: string; v: string }) => (
    <div className="flex justify-between gap-3"><span className="text-gray-500">{k}</span><span className="truncate text-gray-200">{v}</span></div>
  )
  return (
    <motion.div
      drag dragMomentum={false} dragElastic={0.12}
      initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      onClick={(e) => e.stopPropagation()}
      className="absolute inset-0 z-40 m-auto h-fit w-72 cursor-grab rounded-lg border bg-black/90 p-5 backdrop-blur-xl font-['Rajdhani'] active:cursor-grabbing"
      style={{ borderColor: color, boxShadow: `0 14px 50px ${color}55` }}
    >
      <div className="-mt-2 mb-1 flex justify-center text-gray-600" title="Drag to reposition"><GripHorizontal size={14} /></div>
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-10 items-end justify-center"><div className="origin-bottom scale-[0.55]"><Character working={agent.live.status === 'working'} /></div></div>
          <div>
            <div className="text-base font-bold uppercase tracking-wide" style={{ color }}>{agent.name}</div>
            <div className="text-[11px] text-gray-400">{agent.role}{agent.is_head ? ' · HEAD' : ''}</div>
          </div>
        </div>
        <button onClick={onClose} className="text-gray-500 transition-colors hover:text-white"><X size={16} /></button>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2">
        <div className="border border-white/10 bg-white/[0.04] p-2">
          <div className="text-[10px] uppercase tracking-widest text-gray-500">Status</div>
          <div className="text-sm font-bold uppercase" style={{ color }}>{agent.live.status}</div>
        </div>
        <div className="border border-white/10 bg-white/[0.04] p-2">
          <div className="text-[10px] uppercase tracking-widest text-gray-500">Autonomy</div>
          <div className="text-sm font-bold uppercase text-gray-200">{agent.autonomy}</div>
        </div>
      </div>
      <div className="mb-3 space-y-1.5 border-t border-white/10 pt-3 text-[11px]">
        <Row k="Provider" v={agent.provider} />
        <Row k="Model" v={agent.model || '—'} />
        <Row k="Last active" v={agent.live.last_active || '—'} />
      </div>
      {liveText && (
        <div className="mb-3 rounded border border-accent/30 bg-accent/5 p-2">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-accent"><Radio size={10} className="animate-pulse" /> Live step</div>
          <div className="font-mono text-[11px] leading-relaxed text-gray-300">{liveText.slice(-220)}<span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-accent align-middle" /></div>
        </div>
      )}
      {agent.live.detail && <div className="mb-3 text-[11px] italic leading-relaxed text-gray-400">{agent.live.detail}</div>}
      <button onClick={onManage} className="w-full rounded bg-accent/20 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/30">Manage in Ops →</button>
    </motion.div>
  )
}

// ── Live War-Room panel (screen-space; driven by the mission event stream) ──
export function WarRoomPanel({ missionId, war, agents, onClose }: { missionId: number; war: WarState; agents: Agent[]; onClose: () => void }) {
  const [inject, setInject] = useState('')
  const nameOf = (id?: string) => agents.find(a => a.id === id)?.name || id || '—'
  const colorOf = (id?: string) => agents.find(a => a.id === id)?.color || '#58a6ff'
  const steps = war.order.map(s => war.steps[s])
  const total = war.total || steps.length
  const done = steps.filter(s => s.status === 'done').length
  const running = !war.done
  const doInject = async () => { if (!inject.trim()) return; try { await injectMission(missionId, inject.trim()) } catch { /* ignore */ } setInject('') }

  return (
    <motion.div initial={{ opacity: 0, x: 28 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 28 }} transition={{ duration: 0.24 }}
      onClick={(e) => e.stopPropagation()}
      className="absolute top-20 right-6 bottom-16 z-40 flex w-[26rem] max-w-[calc(100vw-3rem)] flex-col rounded-lg border border-accent/40 bg-black/90 backdrop-blur-xl font-['Rajdhani'] shadow-[0_0_60px_rgba(88,166,255,0.2)]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <Radio size={15} className={running ? 'animate-pulse text-accent' : 'text-success'} />
          <span className="text-sm font-bold uppercase tracking-widest text-white">War Room</span>
          <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${war.done ? (war.status === 'done' ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger') : 'bg-accent/20 text-accent'}`}>{war.status}</span>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={16} /></button>
      </div>

      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2 text-[11px] text-gray-400">
        <span>Step {Math.min(done + (running ? 1 : 0), total) || 0} / {total}</span>
        <span className="flex items-center gap-1 text-warning"><Coins size={11} /> <motion.span key={war.totalTokens}>{war.totalTokens.toLocaleString()}</motion.span> tok</span>
      </div>
      <div className="h-1 w-full bg-white/5"><motion.div className="h-full bg-accent" animate={{ width: `${total ? (done / total) * 100 : 0}%` }} transition={{ ease: 'easeOut' }} /></div>

      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {steps.length === 0 && <div className="py-8 text-center text-xs text-gray-500">Awaiting first step…</div>}
        {steps.map(s => (
          <div key={s.seq} className="rounded-lg border p-2.5" style={{ borderColor: s.status === 'running' ? colorOf(s.agent_id) : 'rgba(255,255,255,0.08)' }}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-bold" style={{ color: colorOf(s.agent_id) }}>{s.seq}. {nameOf(s.agent_id)} <span className="text-gray-500">· {s.action}</span></span>
              <span className={`rounded px-1.5 py-0.5 text-[9px] uppercase ${s.status === 'done' ? 'bg-success/20 text-success' : s.status === 'failed' ? 'bg-danger/20 text-danger' : 'bg-accent/20 text-accent'}`}>{s.status}</span>
            </div>
            {s.text && <div className="font-mono text-[11px] leading-relaxed text-gray-300">{s.text}{s.status === 'running' && <span className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-accent align-middle" />}</div>}
            {s.tokens > 0 && <div className="mt-1 text-[10px] text-gray-500">{s.tokens} tok</div>}
          </div>
        ))}

        {war.blackboard && (
          <details className="rounded-lg border border-white/10 p-2.5">
            <summary className="cursor-pointer text-[10px] uppercase tracking-widest text-gray-500">Blackboard (shared context)</summary>
            <pre className="mt-2 whitespace-pre-wrap font-mono text-[10px] leading-relaxed text-gray-400">{war.blackboard}</pre>
          </details>
        )}

        {war.done && war.summary && (
          <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
            className="rounded-lg border border-success/40 bg-success/10 p-3">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-bold text-success"><CheckCircle2 size={13} /> Mission {war.status}</div>
            <pre className="whitespace-pre-wrap font-sans text-[11px] leading-relaxed text-gray-200">{war.summary}</pre>
          </motion.div>
        )}
      </div>

      {/* Steering (D58/D32) — effective between steps */}
      {running && (
        <div className="border-t border-white/10 p-3">
          <div className="mb-2 flex gap-2">
            <button onClick={() => (war.status === 'running' ? pauseMission(missionId) : resumeMission(missionId))}
              className="flex flex-1 items-center justify-center gap-1 rounded bg-white/5 py-1.5 text-xs text-gray-200 hover:bg-white/10">
              {war.status === 'running' ? <><Pause size={12} /> Pause</> : <><Play size={12} /> Resume</>}
            </button>
            <button onClick={() => cancelMission(missionId)} className="flex flex-1 items-center justify-center gap-1 rounded bg-danger/15 py-1.5 text-xs text-danger hover:bg-danger/25">
              <Square size={11} /> Cancel
            </button>
          </div>
          <div className="flex gap-2">
            <input value={inject} onChange={e => setInject(e.target.value)} onKeyDown={e => e.key === 'Enter' && doInject()}
              placeholder="Inject guidance for the next step…" className="flex-1 rounded border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-white outline-none placeholder:text-gray-600" />
            <button onClick={doInject} className="rounded bg-accent/20 px-2.5 text-accent hover:bg-accent/30"><Send size={13} /></button>
          </div>
          <div className="mt-1 text-[9px] text-gray-600">Steering applies between steps (a cancel lands after the current step).</div>
        </div>
      )}
    </motion.div>
  )
}

// ── Real org KPIs (replaces the old fake CPU/MEM/NET overlay — D43) ──
export function KpiOverlay({ stats, collapsed, onToggle }: { stats: OfficeStats | null; collapsed: boolean; onToggle: () => void }) {
  const s = stats?.stats
  const integrations = stats?.integrations || {}
  const intlist = Object.entries(integrations)
  if (collapsed) {
    return (
      <div className="absolute top-6 right-6 z-30 hidden sm:block font-['Rajdhani']">
        <button onClick={onToggle} title="Expand status"
          className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/60 px-3 py-2 text-[11px] text-gray-300 backdrop-blur-md transition-colors hover:bg-black/80">
          <Activity size={12} className="text-accent" />
          <span className="font-bold text-accent">{s?.agents_active ?? '—'}</span> agents
          <span className="text-gray-600">·</span>
          <span className="font-bold text-warning">{(s?.tokens_total ?? 0).toLocaleString()}</span> tok
          <ChevronDown size={13} className="rotate-90 text-gray-500" />
        </button>
      </div>
    )
  }
  return (
    <div className="absolute top-6 right-6 z-30 hidden sm:flex flex-col gap-3 font-['Rajdhani'] w-60">
      <div className="bg-black/60 border border-white/10 px-4 py-3 backdrop-blur-md">
        <div className="mb-2 flex items-center justify-between gap-2 text-[11px] text-gray-400 uppercase tracking-widest">
          <span className="flex items-center gap-2"><Activity size={12} className="text-accent" /> Org Status</span>
          <button onClick={onToggle} title="Collapse" className="text-gray-500 transition-colors hover:text-white"><ChevronDown size={13} className="-rotate-90" /></button>
        </div>
        <div className="grid grid-cols-2 gap-y-1.5 text-[11px]">
          <span className="text-gray-400">Agents</span><span className="text-right font-bold text-accent">{s?.agents_active ?? '—'} ({s?.agents_working ?? 0} working)</span>
          <span className="text-gray-400">Missions</span><span className="text-right font-bold text-success">{s?.missions_running ?? 0} running / {s?.missions_done ?? 0} done</span>
          <span className="text-gray-400">Steps</span><span className="text-right font-bold text-gray-300">{s?.steps_total ?? 0}</span>
          <span className="text-gray-400">Tokens</span><span className="text-right font-bold text-warning">{(s?.tokens_total ?? 0).toLocaleString()}</span>
        </div>
      </div>
      <div className="bg-black/60 border border-white/10 px-4 py-3 backdrop-blur-md">
        <div className="mb-2 flex items-center gap-2 text-[11px] text-gray-400 uppercase tracking-widest"><Shield size={12} className="text-success" /> Integrations</div>
        <div className="flex flex-wrap gap-1.5">
          {intlist.length === 0 ? <span className="text-[11px] text-gray-500">—</span> : intlist.map(([k, ok]) => (
            <span key={k} className={`flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ${ok ? 'bg-success/15 text-success' : 'bg-white/5 text-gray-500'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-success' : 'bg-gray-600'}`} />{k}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
