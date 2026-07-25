import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, Bot, Building2, FileOutput, ListChecks, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react'
import type { PendingAction } from '../../api.brain'
import { getAgent, getMission, type Agent, type Mission } from '../../api.office'
import { getOfficeArtifact, getOfficeV3Snapshot, proposeOfficeAction, type OfficeArtifact, type OfficeV3Snapshot } from '../../api.officev3'
import { useMissionStream } from '../../hooks/useMissionStream'
import { useToast } from '../../context/ToastProvider'
import OfficeFloor from './OfficeFloor'
import AgentDock from './AgentDock'
import AgentDetailPanel from './AgentDetailPanel'
import MissionCommandPanel from './MissionCommandPanel'
import OfficeArtifactPanel from './OfficeArtifactPanel'
import OfficeActivityFeed from './OfficeActivityFeed'
import OfficeTobiPanel from './OfficeTobiPanel'
import type { OfficeRailTab, OfficeSelection } from './types'

const emptySnapshot: OfficeV3Snapshot = { enabled: true, agents: [], missions: [], stats: {
  agents_active: 0, agents_working: 0, missions_total: 0, missions_running: 0, missions_done: 0,
  missions_by_status: {}, tokens_total: 0, steps_total: 0,
}, integrations: {}, artifacts: [], activity: [], timestamp: '' }

export default function OfficeV3Shell() {
  const { toast } = useToast()
  const [snapshot, setSnapshot] = useState<OfficeV3Snapshot>(emptySnapshot)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selection, setSelection] = useState<OfficeSelection>(null)
  const [tab, setTab] = useState<OfficeRailTab>('command')
  const [liveMissionId, setLiveMissionId] = useState<number | null>(null)
  const [pending, setPending] = useState<PendingAction | null>(null)
  const war = useMissionStream(liveMissionId)

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try { setSnapshot(await getOfficeV3Snapshot()); setError('') }
    catch (e) { setError((e as Error).message) }
    finally { if (!quiet) setLoading(false) }
  }, [])
  useEffect(() => { refresh(); const id = setInterval(() => refresh(true), 12000); return () => clearInterval(id) }, [refresh])
  useEffect(() => {
    if (liveMissionId == null) {
      const running = snapshot.missions.find(mission => mission.status === 'running')
      if (running) setLiveMissionId(running.id)
    }
  }, [snapshot.missions, liveMissionId])
  useEffect(() => { if (war.done) { refresh(true); setTimeout(() => refresh(true), 500) } }, [war.done, refresh])

  const selectedAgent = selection?.type === 'agent' ? selection.item : null
  const selectedMission = selection?.type === 'mission' ? selection.item : null
  const selectedArtifact = selection?.type === 'artifact' ? selection.item : null
  const officeStats = useMemo(() => ({ stats: snapshot.stats, integrations: snapshot.integrations, timestamp: snapshot.timestamp }), [snapshot])

  const selectAgent = async (agent: Agent) => {
    try { setSelection({ type: 'agent', item: await getAgent(agent.id) }) } catch { setSelection({ type: 'agent', item: agent }) }
    setTab('command')
  }
  const selectMission = async (mission: Mission) => {
    try { setSelection({ type: 'mission', item: await getMission(mission.id) }) } catch { setSelection({ type: 'mission', item: mission }) }
  }
  const selectArtifact = async (artifact: OfficeArtifact) => {
    try { setSelection({ type: 'artifact', item: await getOfficeArtifact(artifact.id) }) } catch { setSelection({ type: 'artifact', item: artifact }) }
  }
  const propose = async (action: string, args: Record<string, unknown>) => {
    try {
      const result = await proposeOfficeAction(action as Parameters<typeof proposeOfficeAction>[0], args)
      setPending(result.pending_action); setTab('tobi')
    } catch (e) { toast({ kind: 'error', title: 'Could not prepare Office action', detail: (e as Error).message }) }
  }
  const resolved = (result?: unknown) => {
    const payload = result as { mission_id?: number; streaming?: boolean } | undefined
    if (payload?.mission_id && payload.streaming) setLiveMissionId(payload.mission_id)
    refresh(true)
  }

  const tabs: Array<{ id: OfficeRailTab; label: string; icon: typeof ListChecks }> = [
    { id: 'command', label: 'Command', icon: ListChecks },
    { id: 'tobi', label: 'TOBI', icon: Sparkles },
    { id: 'artifacts', label: 'Artifacts', icon: FileOutput },
    { id: 'activity', label: 'Activity', icon: Activity },
  ]

  if (loading) return <div className="flex h-full min-h-[620px] items-center justify-center bg-bg"><div className="text-center"><Building2 size={28} className="mx-auto animate-pulse text-accent" /><div className="mt-3 text-xs uppercase text-muted">Opening Office command floor</div></div></div>
  if (error) return <div className="flex h-full min-h-[620px] items-center justify-center bg-bg"><div className="max-w-sm text-center"><div className="text-sm font-semibold text-danger">Office unavailable</div><p className="mt-2 text-xs text-muted">{error}</p><button onClick={() => refresh()} className="mt-4 inline-flex h-9 items-center gap-2 border border-border px-3 text-xs text-text"><RefreshCw size={13} /> Retry</button></div></div>

  return (
    <div className="flex h-full min-h-[640px] flex-col overflow-hidden bg-bg text-text">
      <header className="flex h-14 shrink-0 items-center border-b border-border bg-bg px-4">
        <div className="flex items-center gap-2.5"><span className="flex h-8 w-8 items-center justify-center bg-accent text-bg"><Building2 size={16} /></span><div><h1 className="text-sm font-semibold text-heading">TOBI Office</h1><p className="text-[9px] uppercase text-muted">Agent command floor</p></div></div>
        <div className="ml-auto hidden items-center divide-x divide-border border border-border md:flex">
          <div className="px-3 py-1.5"><span className="block text-[8px] uppercase text-muted">Agents</span><span className="text-xs font-semibold">{snapshot.stats.agents_working}/{snapshot.stats.agents_active}</span></div>
          <div className="px-3 py-1.5"><span className="block text-[8px] uppercase text-muted">Running</span><span className="text-xs font-semibold text-warning">{snapshot.stats.missions_running}</span></div>
          <div className="px-3 py-1.5"><span className="block text-[8px] uppercase text-muted">Artifacts</span><span className="text-xs font-semibold">{snapshot.artifacts.length}</span></div>
        </div>
        <div className="ml-3 flex items-center gap-1.5 text-[9px] uppercase text-success"><ShieldCheck size={12} /> local secure</div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px]">
        <main className="flex min-h-[430px] min-w-0 flex-col border-b border-border lg:border-b-0 lg:border-r">
          <OfficeFloor agents={snapshot.agents} stats={officeStats} war={war} selectedId={selectedAgent?.id} onSelect={selectAgent} />
          <AgentDock agents={snapshot.agents} selectedId={selectedAgent?.id} activeAgentId={war.activeAgentId} onSelect={selectAgent} />
        </main>

        <aside className="flex min-h-[520px] min-w-0 flex-col bg-surface/35">
          <nav className="grid h-11 shrink-0 grid-cols-4 border-b border-border">
            {tabs.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => setTab(id)} className={`flex items-center justify-center gap-1.5 text-[10px] transition-colors ${tab === id ? 'border-b-2 border-accent text-accent' : 'text-muted hover:text-text'}`}><Icon size={12} /> {label}</button>)}
          </nav>
          <div className="min-h-0 flex-1">
            {tab === 'command' && (selectedAgent
              ? <AgentDetailPanel agent={selectedAgent} />
              : <MissionCommandPanel missions={snapshot.missions} selectedId={selectedMission?.id} liveMissionId={liveMissionId} war={war} onSelect={selectMission} onPropose={propose} />)}
            {tab === 'tobi' && <OfficeTobiPanel selection={selection} pending={pending} onPending={setPending} onResolved={resolved} />}
            {tab === 'artifacts' && <OfficeArtifactPanel artifacts={snapshot.artifacts} selected={selectedArtifact} onSelect={selectArtifact} onPropose={propose} />}
            {tab === 'activity' && <OfficeActivityFeed activity={snapshot.activity} />}
          </div>
          {tab === 'command' && selectedAgent && <button onClick={() => { setSelection(null); setTab('command') }} className="h-9 shrink-0 border-t border-border text-[10px] uppercase text-muted hover:text-text">Back to mission queue</button>}
        </aside>
      </div>
    </div>
  )
}
