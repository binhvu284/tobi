import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Bot, Maximize2, Radio, ScanLine } from 'lucide-react'
import type { Agent, OfficeStats } from '../../api.office'
import type { WarState } from '../../hooks/useMissionStream'
import PhaserGame from '../../office/PhaserGame'
import { accentHex } from '../../office/theme'
import { useTheme } from '../../context/ThemeProvider'
import { useReducedMotionPref } from '../../context/MotionProvider'

function StaticFloor({ agents, selectedId, activeAgentId, onSelect }:
  { agents: Agent[]; selectedId?: string; activeAgentId?: string | null; onSelect: (agent: Agent) => void }) {
  return (
    <div className="absolute inset-0 overflow-hidden bg-[#0b1110]">
      <div className="absolute inset-0 opacity-40 [background-image:linear-gradient(rgb(255_255_255/0.045)_1px,transparent_1px),linear-gradient(90deg,rgb(255_255_255/0.045)_1px,transparent_1px)] [background-size:32px_32px]" />
      <div className="absolute inset-x-[8%] bottom-[12%] top-[10%] border border-white/10 bg-[#101817] shadow-[inset_0_0_90px_rgb(0_0_0/0.65)]">
        <div className="grid h-full grid-cols-2 gap-4 p-5 sm:grid-cols-3 lg:grid-cols-4">
          {agents.map((agent, index) => {
            const working = activeAgentId === agent.id || agent.live.status === 'working'
            return (
              <button key={agent.id} onClick={() => onSelect(agent)}
                className={`relative flex min-h-[120px] flex-col items-center justify-center border p-3 transition-colors ${selectedId === agent.id ? 'border-accent bg-accent/10' : 'border-white/10 bg-black/25 hover:border-white/25'}`}>
                <div className="absolute inset-x-4 top-3 h-7 border border-white/10 bg-black/40">
                  <i className={`absolute inset-1 ${working ? 'bg-success/40' : 'bg-white/5'}`} />
                </div>
                <div className="mt-6 grid h-11 w-9 grid-cols-3 grid-rows-4 gap-px" style={{ color: agent.color || '#58a6ff' }}>
                  {[0,1,2,3,4,5,6,7,8,9,10,11].map(cell => <i key={cell} className={`${[0,2,9,11].includes(cell) ? 'bg-transparent' : 'bg-current'}`} />)}
                </div>
                <span className="mt-2 text-[11px] font-semibold uppercase text-white">{agent.name}</span>
                <span className="text-[9px] uppercase text-white/45">Desk {String(index + 1).padStart(2, '0')}</span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default function OfficeFloor({ agents, stats, war, selectedId, onSelect }:
  { agents: Agent[]; stats: OfficeStats | null; war: WarState; selectedId?: string; onSelect: (agent: Agent) => void }) {
  const { theme } = useTheme()
  const motionLevel = useReducedMotionPref()
  const [accent, setAccent] = useState(() => accentHex())
  const [compact, setCompact] = useState(() => typeof matchMedia !== 'undefined' && matchMedia('(max-width: 820px)').matches)
  useEffect(() => { const id = requestAnimationFrame(() => setAccent(accentHex())); return () => cancelAnimationFrame(id) }, [theme])
  useEffect(() => {
    if (typeof matchMedia === 'undefined') return
    const mq = matchMedia('(max-width: 820px)')
    const change = () => setCompact(mq.matches)
    mq.addEventListener('change', change)
    return () => mq.removeEventListener('change', change)
  }, [])
  const fallback = compact || motionLevel !== 'full'

  return (
    <div className="relative min-h-[360px] flex-1 overflow-hidden bg-[#080d0c]">
      {fallback ? (
        <StaticFloor agents={agents} selectedId={selectedId} activeAgentId={war.activeAgentId} onSelect={onSelect} />
      ) : (
        <PhaserGame agents={agents} stats={stats} war={war} accent={accent} performance={false} rightInset={0}
          selectedId={selectedId || null} onAgentClick={id => { const agent = agents.find(a => a.id === id); if (agent) onSelect(agent) }}
          onAgentHover={() => {}} />
      )}
      <div className="pointer-events-none absolute inset-0 shadow-[inset_0_0_100px_rgb(0_0_0/0.55)]" />
      <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 border border-white/10 bg-black/55 px-2.5 py-1.5 text-[10px] uppercase text-white/65 backdrop-blur">
        <ScanLine size={12} className="text-success" /> Live floor <span className="h-1.5 w-1.5 animate-pulse bg-success" />
      </div>
      <div className="pointer-events-none absolute right-4 top-4 flex items-center gap-3 border border-white/10 bg-black/55 px-2.5 py-1.5 text-[10px] text-white/55 backdrop-blur">
        <span>{stats?.stats.agents_working ?? 0} working</span><span>{stats?.stats.missions_running ?? 0} missions</span><Maximize2 size={11} />
      </div>
      {war.activeAgentId && !war.done && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
          className="absolute bottom-4 left-4 right-4 flex items-center gap-3 border border-warning/35 bg-black/75 px-3 py-2 backdrop-blur">
          <span className="flex h-8 w-8 items-center justify-center bg-warning/15 text-warning"><Bot size={15} /></span>
          <span className="min-w-0 flex-1">
            <span className="block text-[10px] uppercase text-warning">Mission live</span>
            <span className="block truncate text-[12px] text-white/80">{war.activeSeq != null ? war.steps[war.activeSeq]?.action || 'Executing step' : 'Coordinating agents'}</span>
          </span>
          <Radio size={14} className="animate-pulse text-warning" />
        </motion.div>
      )}
    </div>
  )
}
