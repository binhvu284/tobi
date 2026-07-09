import { useEffect, useState, useRef } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence, useDragControls } from 'framer-motion'
import {
  X, Activity, Zap, Shield, Users, LayoutGrid, Plus, Play, Cpu, Coins, Trash2, Pencil, ListChecks,
  Pause, Square, Send, Radio, CheckCircle2, GripHorizontal, Rocket, ChevronDown, Volume2, VolumeX, Sparkles,
} from 'lucide-react'
import {
  getAgents, getOfficeStats, getMissions, getMission, createMission, runMission, patchMission,
  createAgent, updateAgent, deleteAgent, pauseMission, resumeMission, cancelMission, injectMission,
  type Agent, type OfficeStats, type Mission, type AgentUpsert,
} from '../api'
import { useMissionStream, type WarState } from '../hooks/useMissionStream'
import PageLoader from '../components/PageLoader'
import PhaserGame from '../office/PhaserGame'
import { accentHex } from '../office/theme'
import { useTheme } from '../context/ThemeProvider'
import { sfx } from '../hooks/useSound'

// ── Typography ──────────────────────────────────────────────────────
// Rajdhani is now bundled self-hosted (src/theme/fonts.ts) — no runtime CDN link.

// ── Pixel-art characters (unchanged sprites, selected by agent.sprite) ──
function TobiCharacter({ working }: { working: boolean }) {
  const c = '#58a6ff', e = '#0d1117'
  return (
    <svg width="64" height="80" viewBox="0 0 8 10" className={`pixel-art ${working ? 'char-working' : 'char-idle'}`}>
      <rect x="3" y="0" width="2" height="1" fill={c} /><rect x="3" y="0" width="1" height="1" fill="#f0f6fc" />
      <rect x="1" y="1" width="6" height="4" fill={c} /><rect x="2" y="2" width="1" height="1" fill="white" />
      <rect x="5" y="2" width="1" height="1" fill="white" /><rect x="2" y="2" width="1" height="1" fill={e} style={{ opacity: 0.7 }} />
      <rect x="5" y="2" width="1" height="1" fill={e} style={{ opacity: 0.7 }} /><rect x="3" y="4" width="2" height="1" fill={e} />
      <rect x="2" y="5" width="4" height="3" fill={c} /><rect x="1" y="5" width="1" height="2" fill={c} />
      <rect x="6" y="5" width="1" height="2" fill={c} /><rect x="2" y="8" width="1" height="2" fill={c} /><rect x="5" y="8" width="1" height="2" fill={c} />
    </svg>
  )
}
function ResearchCharacter({ working }: { working: boolean }) {
  return (
    <svg width="64" height="80" viewBox="0 0 8 10" className={`pixel-art ${working ? 'char-working' : 'char-idle'}`}>
      <rect x="1" y="0" width="6" height="2" fill="#d29922" /><rect x="1" y="1" width="6" height="4" fill="#f4a261" />
      <rect x="1" y="2" width="2" height="1" fill="#3fb950" /><rect x="4" y="2" width="2" height="1" fill="#3fb950" />
      <rect x="3" y="2" width="1" height="1" fill="#3fb950" style={{ opacity: 0.5 }} /><rect x="2" y="2" width="1" height="1" fill="#0d1117" />
      <rect x="5" y="2" width="1" height="1" fill="#0d1117" /><rect x="3" y="4" width="2" height="1" fill="#0d1117" />
      <rect x="1" y="5" width="6" height="3" fill="#e5e7eb" /><rect x="3" y="5" width="2" height="3" fill="#3fb950" style={{ opacity: 0.3 }} />
      <rect x="0" y="5" width="1" height="2" fill="#e5e7eb" /><rect x="7" y="5" width="1" height="2" fill="#e5e7eb" />
      <rect x="2" y="8" width="1" height="2" fill="#30363d" /><rect x="5" y="8" width="1" height="2" fill="#30363d" />
    </svg>
  )
}
function CoderCharacter({ working }: { working: boolean }) {
  return (
    <svg width="64" height="80" viewBox="0 0 8 10" className={`pixel-art ${working ? 'char-working' : 'char-idle'}`}>
      <rect x="0" y="0" width="8" height="3" fill="#8b5cf6" /><rect x="2" y="1" width="4" height="3" fill="#f4a261" />
      <rect x="2" y="2" width="1" height="1" fill="#0d1117" /><rect x="5" y="2" width="1" height="1" fill="#0d1117" />
      <rect x="1" y="4" width="6" height="4" fill="#8b5cf6" /><rect x="3" y="6" width="2" height="1" fill="black" style={{ opacity: 0.3 }} />
      <rect x="0" y="4" width="1" height="3" fill="#8b5cf6" /><rect x="7" y="4" width="1" height="3" fill="#8b5cf6" />
      <rect x="2" y="8" width="1" height="2" fill="#30363d" /><rect x="5" y="8" width="1" height="2" fill="#30363d" />
    </svg>
  )
}
function CeoCharacter({ working }: { working: boolean }) {
  return (
    <svg width="64" height="80" viewBox="0 0 8 10" className={`pixel-art ${working ? 'char-working' : 'char-idle'}`}>
      <rect x="2" y="0" width="4" height="1" fill="#30363d" /><rect x="1" y="1" width="6" height="4" fill="#f4a261" />
      <rect x="2" y="2" width="1" height="1" fill="#0d1117" /><rect x="5" y="2" width="1" height="1" fill="#0d1117" />
      <rect x="3" y="4" width="1" height="1" fill="#0d1117" /><rect x="4" y="4" width="1" height="1" fill="#0d1117" />
      <rect x="1" y="5" width="6" height="3" fill="#21262d" /><rect x="3" y="5" width="2" height="3" fill="#d29922" />
      <rect x="3" y="7" width="2" height="1" fill="#d29922" style={{ opacity: 0.7 }} /><rect x="0" y="5" width="1" height="3" fill="#21262d" />
      <rect x="7" y="5" width="1" height="3" fill="#21262d" /><rect x="2" y="8" width="1" height="2" fill="#21262d" /><rect x="5" y="8" width="1" height="2" fill="#21262d" />
    </svg>
  )
}
const SPRITES: Record<string, React.FC<{ working: boolean }>> = {
  tobi: TobiCharacter, research: ResearchCharacter, coder: CoderCharacter, ceo: CeoCharacter,
}
const SPRITE_KEYS = Object.keys(SPRITES)
const spriteOf = (a: Agent) => SPRITES[a.sprite || 'tobi'] || TobiCharacter

// ── Scene FX ────────────────────────────────────────────────────────
const CodeRain = ({ color }: { color?: string }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = canvasRef.current; if (!canvas) return
    const ctx = canvas.getContext('2d'); if (!ctx) return
    const resize = () => { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight }
    resize(); window.addEventListener('resize', resize)
    const letters = '01$#!%&*+-'.split(''); const fontSize = 14
    const columns = Math.floor(canvas.width / fontSize)
    const drops: number[] = new Array(columns).fill(0).map(() => Math.random() * -100)
    const draw = () => {
      ctx.fillStyle = 'rgba(5, 5, 5, 0.15)'; ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = color || '#22c55e'; ctx.font = `600 ${fontSize}px "Rajdhani", monospace`
      for (let i = 0; i < drops.length; i++) {
        ctx.fillText(letters[Math.floor(Math.random() * letters.length)], i * fontSize, drops[i] * fontSize)
        if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0
        drops[i]++
      }
    }
    const interval = setInterval(draw, 40)
    return () => { clearInterval(interval); window.removeEventListener('resize', resize) }
  }, [color])
  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full opacity-[0.2] pointer-events-none" />
}
function Scanlines() { return <div className="absolute inset-0 pointer-events-none z-50 opacity-[0.03] scanlines" /> }

// ── 2D cyberpunk base: Tobi core (hub) + sub-agents on a ring (hub-and-spoke, D68) ──
function StatusDot({ status }: { status: string }) {
  const c = status === 'working' ? 'bg-accent' : status === 'online' ? 'bg-success' : 'bg-gray-500'
  return <span className={`inline-block h-2 w-2 rounded-full ${c} ${status === 'working' ? 'animate-pulse' : ''}`} />
}

function CoreGlow({ color }: { color: string }) {
  return (
    <motion.div className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-44 w-44 -translate-x-1/2 -translate-y-1/2 rounded-full blur-2xl"
      style={{ background: color }} animate={{ opacity: [0.14, 0.28, 0.14], scale: [1, 1.12, 1] }} transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }} />
  )
}

function StationCard({ agent, selected, dimmed, hub, active, onSelect }: { agent: Agent; selected: boolean; dimmed: boolean; hub?: boolean; active?: boolean; onSelect: () => void }) {
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

function HqBase({ agents, selectedId, activeAgentId, onSelect }: { agents: Agent[]; selectedId: string | null; activeAgentId?: string | null; onSelect: (id: string | null) => void }) {
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
function AgentHqPanel({ agent, onClose, onManage, liveText }: { agent: Agent; onClose: () => void; onManage: () => void; liveText?: string }) {
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
function WarRoomPanel({ missionId, war, agents, onClose }: { missionId: number; war: WarState; agents: Agent[]; onClose: () => void }) {
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
function KpiOverlay({ stats, collapsed, onToggle }: { stats: OfficeStats | null; collapsed: boolean; onToggle: () => void }) {
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

// ── Agent config builder modal (D27) ────────────────────────────────
const PROVIDERS = ['openrouter', 'anthropic', 'openai', 'google', 'mock']
const blankAgent: AgentUpsert = { name: '', role: '', provider: 'openrouter', model: '', key_ref: '', autonomy: 'medium', max_tokens: 2000, color: '#58a6ff', sprite: 'tobi', skills: [] }

function AgentModal({ agent, onClose, onSaved }: { agent: Agent | 'new'; onClose: () => void; onSaved: () => void }) {
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
    } catch { /* ignore */ } finally { setBusy(false) }
  }
  const archive = async () => {
    if (!editing) return
    try { await deleteAgent((a as Agent).id); onSaved(); onClose() } catch { /* ignore */ }
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

// ── Mission detail panel ─────────────────────────────────────────────
const PRIO_COLOR: Record<string, string> = { Urgent: 'text-danger', High: 'text-warning', Normal: 'text-accent', Low: 'text-muted' }
const STATUS_COLOR: Record<string, string> = { planned: 'bg-muted/20 text-muted', running: 'bg-accent/20 text-accent', blocked: 'bg-danger/20 text-danger', done: 'bg-success/20 text-success', cancelled: 'bg-muted/20 text-muted' }

function MissionPanel({ mission, agents, onClose, onChanged, onLaunch }: { mission: Mission; agents: Agent[]; onClose: () => void; onChanged: () => void; onLaunch: (id: number, mock: boolean) => void }) {
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

function NewMissionModal({ onClose, onCreated }: { onClose: () => void; onCreated: (m: Mission) => void }) {
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

// ── Main page ───────────────────────────────────────────────────────
type View = 'hq' | 'ops'

export default function Office() {
  const [view, setView] = useState<View>('hq')
  const [agents, setAgents] = useState<Agent[]>([])
  const [stats, setStats] = useState<OfficeStats | null>(null)
  const [missions, setMissions] = useState<Mission[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [booting, setBooting] = useState(true)
  const [agentModal, setAgentModal] = useState<Agent | 'new' | null>(null)
  const [missionModal, setMissionModal] = useState(false)
  const [openMission, setOpenMission] = useState<Mission | null>(null)
  const [warMissionId, setWarMissionId] = useState<number | null>(null)
  const [launcherOpen, setLauncherOpen] = useState(false)
  const [hoverId, setHoverId] = useState<string | null>(null)
  const [kpiCollapsed, setKpiCollapsed] = useState(false)
  const [perf, setPerf] = useState(false)

  // Live theme accent for the Phaser scene (recompute a frame after the theme
  // var is written to <html> by ThemeProvider).
  const { theme, sound, set } = useTheme()
  const [accent, setAccent] = useState<number>(() => accentHex())
  useEffect(() => { const id = requestAnimationFrame(() => setAccent(accentHex())); return () => cancelAnimationFrame(id) }, [theme])
  // prefers-reduced-motion → skip the canvas, fall back to the calm static scene.
  const [reduced] = useState(() => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  // small / touch screens → static fallback too (the canvas is desktop-first).
  const [isMobile, setIsMobile] = useState(() => typeof matchMedia !== 'undefined' && matchMedia('(max-width: 768px)').matches)
  useEffect(() => {
    if (typeof matchMedia === 'undefined') return
    const mq = matchMedia('(max-width: 768px)')
    const on = () => setIsMobile(mq.matches); mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  const staticScene = reduced || isMobile

  // Guard the shape: a stale backend (pre-Phase-2) returns the old /api/agents
  // dict with HTTP 200, so .catch won't fire — degrade to an empty office
  // instead of crashing until the live instance restarts.
  const loadAgents = () => getAgents().then(r => setAgents(Array.isArray(r?.agents) ? r.agents : [])).catch(() => {})
  const loadStats = () => getOfficeStats().then(setStats).catch(() => {})
  const loadMissions = () => getMissions().then(r => setMissions(Array.isArray(r?.items) ? r.items : [])).catch(() => {})

  useEffect(() => {
    loadAgents(); loadStats(); loadMissions()
    const id = setInterval(() => { loadAgents(); loadStats() }, 10000)
    setTimeout(() => setBooting(false), 800)
    return () => clearInterval(id)
  }, [])

  // Live war-room stream (active agent drives the base animation).
  const war = useMissionStream(warMissionId)
  useEffect(() => {
    if (war.done) { loadAgents(); loadStats(); loadMissions() }
  }, [war.done]) // eslint-disable-line react-hooks/exhaustive-deps

  // Event SFX (respects the global sound pref): chime on finish, buzz on failure.
  useEffect(() => {
    if (!warMissionId || !war.done) return
    if (war.status === 'done') sfx.success(); else if (war.status === 'blocked' || war.status === 'failed') sfx.error()
  }, [war.done, war.status, warMissionId])

  // Keyboard: ←/→ (or Tab) cycle agents, Enter opens the focused one, Esc clears.
  useEffect(() => {
    if (view !== 'hq' || staticScene) return
    const onKey = (e: KeyboardEvent) => {
      if (warMissionId) return
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (!['ArrowRight', 'ArrowLeft', 'Tab', 'Enter', 'Escape'].includes(e.key)) return
      if (e.key === 'Escape') { setSelectedAgentId(null); return }
      if (agents.length === 0) return
      e.preventDefault()
      const idx = agents.findIndex(a => a.id === selectedAgentId)
      if (e.key === 'Enter') { if (idx < 0) setSelectedAgentId(agents[0].id); return }
      const dir = e.key === 'ArrowLeft' ? -1 : 1
      const next = idx < 0 ? 0 : (idx + dir + agents.length) % agents.length
      setSelectedAgentId(agents[next].id); sfx.tick()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [view, staticScene, warMissionId, agents, selectedAgentId])

  const launch = async (id: number, mock: boolean) => {
    setOpenMission(null); setSelectedAgentId(null); setView('hq'); setWarMissionId(id)
    try { await runMission(id, mock) } catch { /* already running / shown via stream */ }
  }

  const selected = agents.find(a => a.id === selectedAgentId) || null
  const activeColor = (warMissionId ? agents.find(a => a.id === war.activeAgentId)?.color : selected?.color) || undefined
  // Reserve right-edge space so the iso room shifts left of whatever HUD panel is open.
  const rightInset = warMissionId ? 440 : (!selectedAgentId && !kpiCollapsed) ? 280 : 0

  return (
    <div data-theme="dark" className="h-full flex flex-col bg-[#020202] relative overflow-hidden select-none font-mono">
      <Scanlines />

      {/* Header + view toggle */}
      <div className="absolute top-6 left-6 z-30 flex items-center gap-4">
        <div className="w-10 h-10 bg-accent/10 border border-accent/30 flex items-center justify-center text-accent"><Shield size={20} /></div>
        <div className="font-['Rajdhani']">
          <h1 className="text-white text-xl font-bold tracking-[0.3em] uppercase">Tobi HQ</h1>
          <div className="text-[10px] text-accent tracking-[0.4em] uppercase opacity-70 flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-success rounded-full animate-pulse" /> {agents.length} agents · encrypted
          </div>
        </div>
      </div>
      <div className="absolute top-6 left-1/2 -translate-x-1/2 z-30 flex overflow-hidden rounded-lg border border-white/10 bg-black/50 backdrop-blur-md font-['Rajdhani']">
        {([['hq', 'HQ', LayoutGrid], ['ops', 'Ops', Users]] as const).map(([v, label, Icon]) => (
          <button key={v} onClick={() => setView(v)} className={`flex items-center gap-2 px-5 py-2 text-xs uppercase tracking-widest transition-colors ${view === v ? 'bg-accent/20 text-accent' : 'text-gray-400 hover:text-white'}`}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      <AnimatePresence>
        {booting && (
          <motion.div exit={{ opacity: 0 }} className="absolute inset-0 z-[100]">
            <PageLoader preset="office" />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── HQ scene (2D cyberpunk base — Tobi core + agents on a ring) ── */}
      {view === 'hq' && (
        <>
          {/* KPI overlay hides while an agent panel or the war-room is open (shared top-right) */}
          <AnimatePresence>{!selected && !warMissionId && <KpiOverlay stats={stats} collapsed={kpiCollapsed} onToggle={() => setKpiCollapsed(c => !c)} />}</AnimatePresence>
          <div className="relative m-4 flex-1 overflow-hidden rounded-2xl border border-white/5 shadow-[0_0_100px_rgba(0,0,0,1)]">
            <div className="grid-bg pointer-events-none absolute inset-0 opacity-40" />
            <CodeRain color={activeColor} />
            <div className="pointer-events-none absolute inset-0 z-10 shadow-[inset_0_0_160px_rgba(0,0,0,0.85)]" />
            {/* Living office: Phaser iso scene (or the calm static fallback on reduced-motion / mobile) */}
            {staticScene ? (
              <div className="absolute inset-0 z-20" onClick={() => !warMissionId && setSelectedAgentId(null)}>
                <HqBase agents={agents} selectedId={warMissionId ? null : selectedAgentId} activeAgentId={war.activeAgentId} onSelect={setSelectedAgentId} />
              </div>
            ) : (
              <PhaserGame
                agents={agents} stats={stats} war={war} accent={accent} performance={perf} rightInset={rightInset}
                selectedId={warMissionId ? null : selectedAgentId}
                onAgentClick={(id) => { if (warMissionId) return; setSelectedAgentId(prev => (id && prev === id ? null : id)) }}
                onAgentHover={setHoverId}
              />
            )}
            {hoverId && !selectedAgentId && !warMissionId && (
              <div className="pointer-events-none absolute bottom-24 left-1/2 z-30 -translate-x-1/2 rounded-full border border-white/15 bg-black/70 px-3 py-1 text-[11px] text-gray-200 backdrop-blur font-['Rajdhani']">
                {agents.find(a => a.id === hoverId)?.name}
              </div>
            )}
          </div>
          {/* HQ mission launcher — makes the live War Room reachable from the scene */}
          {!warMissionId && (
            <div className="absolute bottom-20 left-6 z-30 font-['Rajdhani']">
              <AnimatePresence>
                {launcherOpen && (
                  <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
                    className="mb-2 w-72 overflow-hidden rounded-lg border border-white/10 bg-black/85 p-2 backdrop-blur-xl">
                    <div className="px-2 pb-1.5 pt-1 text-[10px] uppercase tracking-widest text-gray-500">Launch a mission live</div>
                    {missions.length === 0 && <div className="px-2 py-3 text-center text-xs text-gray-500">No missions yet</div>}
                    {missions.slice(0, 6).map(m => (
                      <button key={m.id} onClick={() => { setLauncherOpen(false); launch(m.id, true) }}
                        className="flex w-full items-center justify-between gap-2 rounded px-2 py-2 text-left text-xs text-gray-200 hover:bg-white/5">
                        <span className="truncate">{m.title}</span>
                        <span className="flex shrink-0 items-center gap-1 text-accent"><Radio size={11} /> run</span>
                      </button>
                    ))}
                    <button onClick={() => { setLauncherOpen(false); setView('ops'); setMissionModal(true) }}
                      className="mt-1 flex w-full items-center gap-1.5 rounded border border-white/10 px-2 py-2 text-xs text-gray-300 hover:bg-white/5"><Plus size={12} /> New mission</button>
                  </motion.div>
                )}
              </AnimatePresence>
              <button onClick={() => setLauncherOpen(o => !o)}
                className="flex items-center gap-2 rounded-lg border border-accent/50 bg-black/70 px-4 py-2.5 text-sm font-bold uppercase tracking-widest text-accent backdrop-blur transition-colors hover:bg-accent/15">
                <Rocket size={15} /> Launch Mission <ChevronDown size={13} className={`transition-transform ${launcherOpen ? 'rotate-180' : ''}`} />
              </button>
            </div>
          )}

          {/* live war-room takes priority; else the flat agent detail panel */}
          <AnimatePresence>
            {warMissionId ? (
              <WarRoomPanel key={`war-${warMissionId}`} missionId={warMissionId} war={war} agents={agents} onClose={() => setWarMissionId(null)} />
            ) : selected ? (
              <AgentHqPanel key={selected.id} agent={selected}
                onClose={() => setSelectedAgentId(null)}
                onManage={() => { setView('ops'); setAgentModal(selected); setSelectedAgentId(null) }}
                liveText={war.activeAgentId === selected.id && !war.done && war.activeSeq != null ? war.steps[war.activeSeq]?.text : undefined} />
            ) : null}
          </AnimatePresence>
        </>
      )}

      {/* ── Ops view: roster + mission board ── */}
      {view === 'ops' && (
        <div className="flex-1 overflow-hidden pt-20">
          <div className="flex h-full gap-4 px-4 pb-4">
            <div className="flex-1 overflow-y-auto">
              {/* KPI strip */}
              <div className="mb-4 grid grid-cols-4 gap-3 font-['Rajdhani']">
                {[
                  { icon: Users, label: 'Agents', val: `${stats?.stats.agents_active ?? '—'}`, sub: `${stats?.stats.agents_working ?? 0} working`, c: 'text-accent' },
                  { icon: Activity, label: 'Missions', val: `${stats?.stats.missions_total ?? '—'}`, sub: `${stats?.stats.missions_running ?? 0} running`, c: 'text-success' },
                  { icon: ListChecks, label: 'Steps', val: `${stats?.stats.steps_total ?? '—'}`, sub: 'executed', c: 'text-purple' },
                  { icon: Coins, label: 'Tokens', val: `${(stats?.stats.tokens_total ?? 0).toLocaleString()}`, sub: 'all missions', c: 'text-warning' },
                ].map(k => (
                  <div key={k.label} className="rounded-lg border border-border bg-surface p-3">
                    <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted"><k.icon size={12} /> {k.label}</div>
                    <div className={`text-2xl font-bold ${k.c}`}>{k.val}</div>
                    <div className="text-[10px] text-muted">{k.sub}</div>
                  </div>
                ))}
              </div>

              {/* Roster */}
              <div className="mb-3 flex items-center justify-between">
                <div className="text-xs font-bold uppercase tracking-widest text-accent">Roster</div>
                <button onClick={() => setAgentModal('new')} className="flex items-center gap-1 rounded border border-border px-2 py-1 text-xs text-muted hover:text-text"><Plus size={12} /> New agent</button>
              </div>
              <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {agents.map(a => {
                  const Character = spriteOf(a)
                  return (
                    <div key={a.id} className="group rounded-lg border border-border bg-surface p-3" style={{ borderLeftColor: a.color || '#30363d', borderLeftWidth: 3 }}>
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div className="flex h-12 w-10 items-end justify-center"><div className="scale-[0.6] origin-bottom"><Character working={a.live.status === 'working'} /></div></div>
                          <div>
                            <div className="flex items-center gap-2"><span className="font-semibold text-heading">{a.name}</span>{a.is_head && <span className="whitespace-nowrap rounded bg-accent/20 px-1.5 py-0.5 text-[10px] text-accent">HEAD</span>}</div>
                            <div className="text-[11px] text-muted">{a.role}</div>
                            <div className="mt-0.5 font-mono text-[10px] text-muted">{a.provider} · {a.model || '—'}</div>
                          </div>
                        </div>
                        <button onClick={() => setAgentModal(a)} className="text-muted opacity-0 transition-opacity hover:text-text group-hover:opacity-100"><Pencil size={13} /></button>
                      </div>
                      <div className="mt-2 flex items-center gap-2 text-[10px]">
                        <span className={`whitespace-nowrap rounded px-1.5 py-0.5 ${a.live.status === 'working' ? 'bg-accent/20 text-accent' : a.live.status === 'online' ? 'bg-success/20 text-success' : 'bg-muted/20 text-muted'}`}>{a.live.status}</span>
                        <span className="whitespace-nowrap text-muted">autonomy: {a.autonomy}</span>
                        {a.scorecard && <span className="whitespace-nowrap text-muted">· {a.scorecard.steps ?? 0} steps</span>}
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Mission board */}
              <div className="mb-3 flex items-center justify-between">
                <div className="text-xs font-bold uppercase tracking-widest text-success">Mission board</div>
                <button onClick={() => setMissionModal(true)} className="flex items-center gap-1 rounded border border-border px-2 py-1 text-xs text-muted hover:text-text"><Plus size={12} /> New mission</button>
              </div>
              <div className="space-y-2">
                {missions.length === 0 && <div className="rounded-lg border border-dashed border-border p-6 text-center text-xs text-muted">No missions yet. Create one to run the Sunday → Alphabet → Friday workflow.</div>}
                {missions.map(m => (
                  <button key={m.id} onClick={() => getMission(m.id).then(setOpenMission)} className={`flex w-full items-center justify-between rounded-lg border bg-surface p-3 text-left transition-colors ${openMission?.id === m.id ? 'border-accent' : 'border-border hover:border-white/20'}`}>
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-heading">{m.title}</div>
                      <div className="mt-0.5 flex items-center gap-2 text-[11px]">
                        <span className={`rounded px-1.5 py-0.5 ${STATUS_COLOR[m.status]}`}>{m.status}</span>
                        <span className={`font-bold ${PRIO_COLOR[m.priority]}`}>{m.priority}</span>
                      </div>
                    </div>
                    <span className="flex shrink-0 items-center gap-1 text-[11px] text-muted"><Coins size={11} />{m.cost_tokens.toLocaleString()}</span>
                  </button>
                ))}
              </div>
            </div>

            <AnimatePresence mode="wait">
              {openMission && <MissionPanel mission={openMission} agents={agents} onClose={() => setOpenMission(null)} onChanged={() => { loadMissions(); loadStats() }} onLaunch={launch} />}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="h-10 px-8 flex items-center justify-between border-t border-white/5 bg-black/50 backdrop-blur-md z-20 font-['Rajdhani']">
        <div className="flex gap-6">
          <div className="text-[10px] text-gray-500 uppercase tracking-widest flex items-center gap-2"><Cpu size={10} className="text-accent" /> Engine: {stats?.stats.missions_running ? 'Running' : 'Idle'}</div>
          <div className="text-[10px] text-gray-500 uppercase tracking-widest flex items-center gap-2"><Zap size={10} className="text-warning" /> Tokens: {(stats?.stats.tokens_total ?? 0).toLocaleString()}</div>
        </div>
        <div className="flex items-center gap-3">
          {view === 'hq' && !staticScene && (
            <>
              <button onClick={() => setPerf(p => !p)} title="Performance mode (strip FX)"
                className={`flex items-center gap-1.5 text-[10px] uppercase tracking-widest transition-colors ${perf ? 'text-accent' : 'text-gray-500 hover:text-gray-300'}`}>
                <Sparkles size={11} /> {perf ? 'Perf' : 'FX'}
              </button>
              <button onClick={() => set({ sound: !sound })} title="Sound effects"
                className={`flex items-center gap-1.5 text-[10px] uppercase tracking-widest transition-colors ${sound ? 'text-accent' : 'text-gray-500 hover:text-gray-300'}`}>
                {sound ? <Volume2 size={11} /> : <VolumeX size={11} />} {sound ? 'On' : 'Off'}
              </button>
            </>
          )}
          <div className="text-[10px] text-gray-500 uppercase tracking-widest">Local: {new Date().toLocaleTimeString()} (GMT+7)</div>
        </div>
      </div>

      <AnimatePresence>
        {agentModal && <AgentModal agent={agentModal} onClose={() => setAgentModal(null)} onSaved={() => { loadAgents(); loadStats() }} />}
        {missionModal && <NewMissionModal onClose={() => setMissionModal(false)} onCreated={(m) => { loadMissions(); setOpenMission(m); setView('ops') }} />}
      </AnimatePresence>
    </div>
  )
}
