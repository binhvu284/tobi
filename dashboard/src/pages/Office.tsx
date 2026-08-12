import { useEffect, useState, useRef } from 'react'
import { softFail } from '../lib/report'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence, useDragControls } from 'framer-motion'
import {
  X, Activity, Zap, Shield, Users, LayoutGrid, Plus, Play, Cpu, Coins, Trash2, Pencil, ListChecks,
  Pause, Square, Send, Radio, CheckCircle2, GripHorizontal, Rocket, ChevronDown, Volume2, VolumeX, Sparkles,
} from 'lucide-react'
import { getAgents, getOfficeStats, getMissions, getMission, createMission, runMission, patchMission, createAgent, updateAgent, deleteAgent, pauseMission, resumeMission, cancelMission, injectMission, type Agent, type OfficeStats, type Mission, type AgentUpsert } from '../api.office'
import { useMissionStream, type WarState } from '../hooks/useMissionStream'
import PageLoader from '../components/PageLoader'
import PhaserGame from '../office/PhaserGame'
import { accentHex } from '../office/theme'
import { useTheme } from '../context/ThemeProvider'
import { sfx } from '../hooks/useSound'
import { AgentModal } from './office/AgentModal'
import { MissionPanel, NewMissionModal, PRIO_COLOR, STATUS_COLOR } from './office/MissionPanel'
import { AgentHqPanel, HqBase, KpiOverlay, WarRoomPanel } from './office/panels'
import { CodeRain, Scanlines, spriteOf } from './office/sprites'
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
  const loadAgents = () => getAgents().then(r => setAgents(Array.isArray(r?.agents) ? r.agents : [])).catch(softFail('the office'))
  const loadStats = () => getOfficeStats().then(setStats).catch(softFail('the office'))
  const loadMissions = () => getMissions().then(r => setMissions(Array.isArray(r?.items) ? r.items : [])).catch(softFail('the office'))

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
    try { await runMission(id, mock) } catch (error) { softFail('the office')(error) }
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
