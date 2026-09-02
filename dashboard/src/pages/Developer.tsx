import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, Archive, BookOpen, CheckCircle2, Circle, Clock3, Code2, Download, ExternalLink,
  ChevronDown, ChevronUp, GitBranch, Github, HardDrive, KeyRound, ListTree, Loader2, MoreHorizontal, Pause, Play, Plus, Radio, RefreshCw,
  RotateCcw, Save, ScrollText, ShieldCheck, Square, Target,
  TerminalSquare, TestTube2, Trash2, Upload, WifiOff, Wrench, XCircle,
} from 'lucide-react'
import AmbientField from '../components/motion/AmbientField'
import { ActivityBar, SectionSkeleton } from '../components/async-ui'
import LlmLogo, { BRAND_META, brandForModel, brandForProvider } from '../components/LlmLogo'
import ModelMenu from '../components/chat/ModelMenu'
import DeveloperAgents from '../components/developer/DeveloperAgents'
import DeveloperProcess from '../components/developer/DeveloperProcess'
import DeveloperQueue from '../components/developer/DeveloperQueue'
import DeveloperRuntimeLoop from '../components/developer/DeveloperRuntimeLoop'
import DeveloperEvidence from '../components/developer/DeveloperEvidence'
import DevelopmentGoals, { type GoalCommand } from '../components/developer/DevelopmentGoals'
import VaultUnlockPanel from '../components/VaultUnlockPanel'
import { useToast } from '../context/ToastProvider'
import { useVaultSession } from '../hooks/useVaultSession'
import type { AvailableModel, LlmProvider } from '../api.chat'
import { approveDeveloperWorkflow, assessDeveloperGoal, commandDeveloperGoal, commandDeveloperWorkflow, createDeveloperGoal, getDeveloperHistory, getDeveloperLearning, getDeveloperOverview, getDeveloperQueue, getDeveloperStorage, getDeveloperVersions, getDeveloperGoals, getDeveloperWorkflow, getDeveloperWorkerLogin, getDeveloperWorkerModels, getDeveloperWorkers, prepareDeveloperWorkflow, probeDeveloperWorker, replayDeveloperLearning, saveDeveloperWorker, startDeveloperWorkflow, streamDeveloperEvents, switchDeveloperWorker, cleanupDeveloperStorage, rejectDeveloperWorkflow, setDeveloperProcessSettings, type DeveloperAssessment, type DeveloperEvent, type DeveloperOverview, type DeveloperGoal, type DeveloperQueueItem, type DeveloperQueueState, type DeveloperRelease, type DeveloperStorage, type DeveloperWorkerLogin, type DeveloperWorkerModels, type DeveloperWorkerProfile, type DeveloperWorkflow } from '../api.developer'

import { HistoryView, SystemView } from './developer/SystemView'
import { DeveloperSkeleton, WorkflowHeader } from './developer/WorkflowHeader'
import { DeveloperLoadError, DeveloperStreamState, LOAD_TIMEOUT_MS, STREAM_REFRESH_EVENTS, TERMINAL_STATES, Tab, label, tone } from '../components/developer/format'
export default function Developer() {
  const { toast } = useToast()
  const vaultSession = useVaultSession()
  const [tab, setTab] = useState<Tab>('overview')
  const [queueGoalDraft, setQueueGoalDraft] = useState<{ goalId: number; requestId: number } | null>(null)
  const [overview, setOverview] = useState<DeveloperOverview | null>(null)
  const [queue, setQueue] = useState<DeveloperQueueState>({ items: [], order: [], next_queue_id: null, auto_queue: false, queue_hash: '' })
  const [releases, setReleases] = useState<DeveloperRelease[]>([])
  const [storage, setStorage] = useState<DeveloperStorage | null>(null)
  const [goals, setGoals] = useState<DeveloperGoal[]>([])
  const [workers, setWorkers] = useState<DeveloperWorkerProfile[]>([])
  const [workerModels, setWorkerModels] = useState<AvailableModel[]>([])
  const [workerProviders, setWorkerProviders] = useState<LlmProvider[]>([])
  const [modelRouting, setModelRouting] = useState({ default_model: '', coding: '', coding_review: '' })
  const [learning, setLearning] = useState<{ records: Array<Record<string, unknown>>; playbooks: Array<Record<string, unknown>> }>({ records: [], playbooks: [] })
  const [events, setEvents] = useState<DeveloperEvent[]>([])
  const [history, setHistory] = useState<DeveloperWorkflow[]>([])
  const [linkedWorkflow, setLinkedWorkflow] = useState<DeveloperWorkflow | null>(null)
  const [streamState, setStreamState] = useState<DeveloperStreamState>('idle')
  const [streamIssue, setStreamIssue] = useState<string | null>(null)
  const [lastSignalAt, setLastSignalAt] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [autoQueuePending, setAutoQueuePending] = useState<boolean | null>(null)
  const [error, setError] = useState<DeveloperLoadError | null>(null)
  const [headerCollapsed, setHeaderCollapsed] = useState(() => localStorage.getItem('tobi.developer.header.collapsed') === 'true')
  const lastSequence = useRef(0)
  const loadController = useRef<AbortController | null>(null)
  const previousVaultSession = useRef(vaultSession)

  const load = useCallback(async (quiet = false) => {
    if (quiet && loadController.current) return
    if (!quiet) loadController.current?.abort()
    const controller = new AbortController()
    loadController.current = controller
    if (!quiet) setLoading(true)
    let timedOut = false
    const timeout = window.setTimeout(() => {
      timedOut = true
      controller.abort()
    }, LOAD_TIMEOUT_MS)
    try {
      const requestedWorkflowId = Number(new URLSearchParams(window.location.search).get('workflow'))
      const linkedRequest = Number.isFinite(requestedWorkflowId) && requestedWorkflowId > 0
        ? getDeveloperWorkflow(requestedWorkflowId, controller.signal).catch(() => null)
        : Promise.resolve(null)
      const [o, q, v, s, g, w, learn, historyResult, linked] = await Promise.all([
        getDeveloperOverview(controller.signal), getDeveloperQueue(controller.signal),
        getDeveloperVersions(controller.signal), getDeveloperStorage(controller.signal),
        getDeveloperGoals(controller.signal), getDeveloperWorkers(false, controller.signal),
        getDeveloperLearning(controller.signal), getDeveloperHistory(controller.signal), linkedRequest,
      ])
      if (controller.signal.aborted) return
      setOverview(o); setQueue(q); setReleases(v.releases); setStorage(s); setGoals(g.goals)
      setWorkers(w.workers); setWorkerModels(w.models ?? []); setWorkerProviders(w.providers ?? [])
      setModelRouting(w.routing ?? { default_model: '', coding: '', coding_review: '' })
      setLearning(learn); setHistory(historyResult.workflows); setLinkedWorkflow(linked); setError(null)
    } catch (err) {
      if (controller.signal.aborted && !timedOut) return
      const apiError = err as { message?: string; status?: number; code?: string }
      setError({
        message: timedOut
          ? 'Developer refresh timed out after 15 seconds. The request was canceled; retry without reloading the browser tab.'
          : apiError?.message || 'Developer data is unavailable.',
        status: apiError?.status,
        code: apiError?.code,
      })
    } finally {
      window.clearTimeout(timeout)
      if (loadController.current === controller) {
        loadController.current = null
        if (!quiet) setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    load()
    const timer = window.setInterval(() => load(true), 5000)
    return () => {
      window.clearInterval(timer)
      loadController.current?.abort()
    }
  }, [load])
  useEffect(() => {
    const wasUnlocked = previousVaultSession.current
    previousVaultSession.current = vaultSession
    if (vaultSession && !wasUnlocked) void load()
  }, [vaultSession, load])

  const setDeveloperHeaderCollapsed = (collapsed: boolean) => {
    setHeaderCollapsed(collapsed)
    localStorage.setItem('tobi.developer.header.collapsed', String(collapsed))
  }

  const active = linkedWorkflow ?? overview?.active_workflow ?? null
  const activeIsTerminal = active ? TERMINAL_STATES.has(active.state) : false
  useEffect(() => {
    if (!active?.id) {
      setEvents([])
      setStreamState('idle')
      setStreamIssue(null)
      setLastSignalAt(null)
      return
    }
    let stopped = false
    let reconnectTimer: number | null = null
    let controller: AbortController | null = null
    let attempt = 0
    let lastOverviewRefresh = 0
    lastSequence.current = 0
    setEvents([])
    setStreamState('connecting')
    setStreamIssue(null)
    setLastSignalAt(null)

    const waitForReconnect = (delay: number) => new Promise<void>(resolve => {
      reconnectTimer = window.setTimeout(resolve, delay)
    })
    const refreshOverview = () => {
      const current = Date.now()
      if (current - lastOverviewRefresh < 750) return
      lastOverviewRefresh = current
      void load(true)
    }
    const connect = async () => {
      while (!stopped) {
        controller = new AbortController()
        setStreamState(attempt === 0 ? 'connecting' : 'reconnecting')
        try {
          await streamDeveloperEvents(
            active.id,
            lastSequence.current,
            event => {
              if (stopped) return
              lastSequence.current = Math.max(lastSequence.current, event.sequence)
              setEvents(current => [...current.filter(item => item.id !== event.id), event].slice(-200))
              setStreamState('live')
              setStreamIssue(null)
              setLastSignalAt(Date.now())
              if (event.event_type.startsWith('stage_') || STREAM_REFRESH_EVENTS.has(event.event_type)) {
                refreshOverview()
              }
            },
            controller.signal,
            status => {
              if (stopped) return
              setStreamState('live')
              setStreamIssue(null)
              setLastSignalAt(Date.now())
              if (status === 'connected') attempt = 0
            },
          )
          if (stopped) return
          refreshOverview()
          if (activeIsTerminal) {
            setStreamState('closed')
            return
          }
          setStreamIssue('Live updates disconnected. Mission Control is reconnecting automatically.')
        } catch (err) {
          if (stopped || (err instanceof DOMException && err.name === 'AbortError')) return
          setStreamIssue(err instanceof Error
            ? `Live updates stopped: ${err.message}. Reconnecting automatically.`
            : 'Live updates stopped. Reconnecting automatically.')
        }
        attempt += 1
        setStreamState('reconnecting')
        await waitForReconnect(Math.min(5000, 750 * (2 ** Math.min(attempt, 3))))
      }
    }

    void connect()
    return () => {
      stopped = true
      controller?.abort()
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
    }
  }, [active?.id, activeIsTerminal, load])

  const act = async (fn: () => Promise<unknown>, success: string): Promise<boolean> => {
    setBusy(true)
    try {
      await fn()
      toast({ kind: 'success', title: success })
      await load(true)
      return true
    } catch (err) {
      toast({ kind: 'error', title: 'Developer action stopped', detail: err instanceof Error ? err.message : String(err) })
      return false
    }
    finally { setBusy(false) }
  }
  const workerAction = async (fn: () => Promise<DeveloperWorkerProfile>, success: string): Promise<DeveloperWorkerProfile | null> => {
    setBusy(true)
    try {
      const updated = await fn()
      setWorkers(current => current.map(item => item.slug === updated.slug ? { ...item, ...updated } : item))
      toast({ kind: 'success', title: success })
      return updated
    } catch (err) {
      toast({ kind: 'error', title: 'Agent action stopped', detail: err instanceof Error ? err.message : String(err) })
      return null
    } finally { setBusy(false) }
  }
  const command = async (cmd: 'pause' | 'resume' | 'cancel' | 'retry' | 'remove' | 'sync_delivery' | 'reconcile_base') => {
    if (!active) return
    if (cmd !== 'sync_delivery') {
      await act(() => commandDeveloperWorkflow(active.id, cmd), `Workflow ${label(cmd)} accepted`)
      return
    }
    setBusy(true)
    try {
      const result = await commandDeveloperWorkflow(active.id, cmd)
      const waiting = result.state === 'awaiting_owner_merge'
      const draft = Boolean(result.delivery?.draft)
      toast({
        kind: 'success',
        title: waiting ? 'GitHub status checked' : 'Delivery synchronized',
        detail: waiting
          ? draft
            ? 'The pull request is still a draft. Open it on GitHub, mark it ready, and merge it.'
            : 'The pull request is still open. Merge it on GitHub, then synchronize again.'
          : 'The GitHub merge was detected and Mission Control continued the workflow.',
      })
      await load(true)
    } catch (err) {
      toast({ kind: 'error', title: 'Delivery synchronization stopped', detail: err instanceof Error ? err.message : String(err) })
    } finally {
      setBusy(false)
    }
  }
  const approve = (purpose: 'special_paths' | 'merge_deploy', master: string) => active && act(() => approveDeveloperWorkflow(active.id, purpose, master), 'Approval accepted')
  const rejectApproval = (purpose: 'special_paths' | 'merge_deploy') => active && act(() => rejectDeveloperWorkflow(active.id, purpose), 'Approval rejected; agent revision started')
  const setAutoQueue = async (enabled: boolean) => {
    if (autoQueuePending !== null) return
    setAutoQueuePending(enabled)
    try {
      const result = await setDeveloperProcessSettings(enabled)
      setOverview(current => current ? {
        ...current,
        process: { ...(current.process ?? {}), auto_queue: result.auto_queue },
      } : current)
      toast({ kind: 'success', title: result.auto_queue ? 'Auto queue enabled' : 'Auto queue disabled' })
      if (result.next_workflow) await load(true)
    } catch (err) {
      toast({ kind: 'error', title: 'Auto queue was not changed', detail: err instanceof Error ? err.message : String(err) })
    } finally {
      setAutoQueuePending(null)
    }
  }
  const createGoal = (input: Parameters<typeof createDeveloperGoal>[0]) => act(() => createDeveloperGoal(input), 'Development goal queued')
  const goalCommand = (id: number, cmd: GoalCommand) => act(() => commandDeveloperGoal(id, cmd), `Goal ${label(cmd)} accepted`)
  const switchWorker = (slug: string) => active && act(() => switchDeveloperWorker(active.id, slug), `Worker switched to ${slug}`)
  const saveWorker = (slug: string, profile: DeveloperWorkerProfile, success = 'Agent profile saved') => {
    const modelsManaged = profile.adapter === 'deepseek' || profile.adapter === 'native' || profile.adapter === 'model_review'
    return workerAction(() => saveDeveloperWorker(slug, {
      name: profile.name, adapter: profile.adapter, model: profile.model,
      auth_mode: modelsManaged ? 'inherited' : profile.auth_mode,
      credential_env: !modelsManaged && profile.auth_mode === 'vault_env' ? profile.credential_env : '',
      reviewer_profile: profile.reviewer_profile,
      enabled: profile.enabled, config: profile.config,
    }), success)
  }
  const probeWorker = (slug: string) => workerAction(() => probeDeveloperWorker(slug), `Agent ${slug} tested`)
  const loginWorker = async (slug: string): Promise<DeveloperWorkerLogin | null> => {
    setBusy(true)
    try {
      const result = await getDeveloperWorkerLogin(slug)
      return result
    } catch (err) {
      toast({ kind: 'error', title: 'Login instructions unavailable', detail: err instanceof Error ? err.message : String(err) })
      return null
    }
    finally { setBusy(false) }
  }
  const loadWorkerModels = async (slug: string, refresh = false): Promise<DeveloperWorkerModels | null> => {
    try { return await getDeveloperWorkerModels(slug, refresh) }
    catch (err) {
      toast({ kind: 'error', title: 'Agent models unavailable', detail: err instanceof Error ? err.message : String(err) })
      return null
    }
  }
  const replayLearning = () => act(() => replayDeveloperLearning(), 'Learning replay completed')

  useEffect(() => {
    if (active?.state !== 'awaiting_owner_merge') return
    let stopped = false
    const synchronize = async () => {
      try {
        await commandDeveloperWorkflow(active.id, 'sync_delivery')
        if (!stopped) await load(true)
      } catch {
        // Explicit Sync status remains available in Process. Background polling is quiet.
      }
    }
    const timer = window.setInterval(() => { void synchronize() }, 15_000)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [active?.id, active?.state, load])

  const capabilities = useMemo(() => Object.entries(overview?.policy.capabilities ?? {}), [overview])
  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' }, { id: 'work', label: 'Work' }, { id: 'loop', label: 'Process' },
    { id: 'workers', label: 'Agents' }, { id: 'history', label: 'History' }, { id: 'system', label: 'System' },
  ]

  return (
    <div className="relative min-h-full"><AmbientField tone="rgb(var(--accent))" variant="grid" />
      {/* Page-scoped work: every owner action refetches the whole Developer state, and until
          now nothing said so. Sections kept showing correct-but-stale data with no motion
          anywhere, which reads as a frozen screen. A bar rather than a skeleton because the
          content is still valid -- replacing it would cost the reader their place. */}
      <ActivityBar pending={busy || (loading && !!overview)} label={busy ? 'Applying…' : 'Refreshing…'} />
      {headerCollapsed ? <div className="sticky top-0 z-30 flex justify-end border-b border-border/60 bg-background/85 px-4 py-2 backdrop-blur sm:px-6"><button onClick={() => setDeveloperHeaderCollapsed(false)} title="Expand Developer header" className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-surface px-3 text-xs font-medium text-text shadow-lg"><Code2 size={15} className="text-accent" /> Developer <ChevronDown size={14} className="text-muted" /></button></div> : <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur-xl">
        <div className="flex items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-accent/30 bg-accent/10 text-accent"><Code2 size={19} /></div><div className="min-w-0"><h1 className="truncate text-lg font-semibold text-text">Developer</h1><p className="mt-0.5 truncate text-[11px] text-muted">Controlled self-development</p></div></div>
          <div className="flex shrink-0 items-center gap-1"><button onClick={() => load()} disabled={loading} title="Refresh Developer state" className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border text-text hover:bg-overlay/5 disabled:opacity-50"><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /></button><button onClick={() => setDeveloperHeaderCollapsed(true)} title="Collapse Developer header" className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted hover:bg-overlay/5 hover:text-text"><ChevronUp size={16} /></button></div>
        </div>
        <nav aria-label="Developer sections" className="flex overflow-x-auto px-2 sm:px-4">{tabs.map(item => <button key={item.id} onClick={() => setTab(item.id)} className={`h-10 shrink-0 border-b-2 px-3 text-xs font-medium transition-colors ${tab === item.id ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-text'}`}>{item.label}</button>)}</nav>
      </header>}

      {loading && !overview ? <DeveloperSkeleton />
        : error?.status === 401 ? <div className="mx-4 mt-6 sm:mx-6"><VaultUnlockPanel mode="inline" title="Unlock Developer"
          detail="Authorize protected coding workflows here. The same session immediately unlocks Integrations, Models, and MCP." /></div>
        : error ? <div className="mx-4 mt-6 border-l-2 border-danger bg-danger/5 px-4 py-4 sm:mx-6"><div className="flex items-start gap-3"><AlertTriangle size={17} className="mt-0.5 shrink-0 text-danger" /><div className="min-w-0 flex-1"><div className="text-sm font-semibold text-heading">{error.code === 'backend_mismatch' ? 'Mission Control backend update required' : 'Developer data unavailable'}</div><p className="mt-1 text-xs leading-5 text-muted">{error.message}</p><button onClick={() => load()} className="mt-3 inline-flex h-8 items-center gap-2 rounded-md border border-border px-2.5 text-xs text-text hover:bg-overlay/5"><RefreshCw size={13} /> Retry</button></div></div></div>
        : <>
          {active && tab === 'overview' && <WorkflowHeader workflow={active} busy={busy} onCommand={command} onApprove={approve} />}
          <main className="px-4 py-6 sm:px-6">
            {tab === 'overview' && <div className="space-y-8">
              {linkedWorkflow && <DeveloperEvidence workflow={linkedWorkflow} />}
              {!active && <div className="grid w-full gap-3 xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,0.8fr)]"><section className="relative overflow-hidden rounded-lg border border-accent/25 bg-surface/70 px-5 py-6 shadow-[0_20px_60px_rgb(0_0_0/0.12)] sm:px-6"><div className="absolute inset-y-0 left-0 w-1 bg-accent" /><div className="flex items-start justify-between gap-5"><div><div className="text-[10px] font-semibold uppercase text-accent">Development runtime</div><h2 className="mt-2 text-lg font-semibold text-text">Choose verified work to begin</h2><p className="mt-1 max-w-2xl text-xs leading-5 text-muted">Create an outcome Goal, link a Queue item, review readiness, then start one durable run.</p></div><button onClick={() => setTab('work')} className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md bg-accent px-3 text-xs font-medium text-background"><Target size={14} /> Open work</button></div><div className="mt-6 h-2 overflow-hidden rounded-full bg-background/70" /><div className="mt-2 text-[11px] text-muted">Idle · no active run</div></section><section className="rounded-lg border border-border bg-surface/60 px-5 py-5"><div className="flex items-start gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-md bg-success/10 text-success"><CheckCircle2 size={18} /></div><div><div className="text-[10px] font-semibold uppercase text-muted">Owner action</div><p className="mt-1.5 text-sm leading-6 text-text">Select a Ready Queue item. Start remains locked until strict preflight passes.</p></div></div></section></div>}
              <div className="grid gap-4 lg:grid-cols-2">
                <section className="overflow-hidden rounded-md border border-border bg-surface/35">
                  <header className="flex h-11 items-center gap-2 border-b border-border px-4"><ListTree size={14} className="text-accent" /><h2 className="text-xs font-semibold text-text">Runtime gate checklist</h2></header>
                  <div className="grid sm:grid-cols-2">{capabilities.map(([name, enabled]) => <div key={name} className="flex min-h-14 items-center gap-3 border-b border-border/60 px-4 py-3 sm:border-r"><span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${enabled ? 'bg-success/10 text-success' : 'bg-overlay/5 text-muted'}`}>{enabled ? <CheckCircle2 size={15} /> : <Circle size={15} />}</span><div className="min-w-0"><div className="text-xs font-medium text-text">{label(name)}</div><div className="mt-0.5 text-[10px] text-muted">{enabled ? 'Available to development runs' : 'Not configured'}</div></div></div>)}</div>
                </section>
                <section className="overflow-hidden rounded-md border border-border bg-surface/35">
                  <header className="flex h-11 items-center gap-2 border-b border-border px-4"><ShieldCheck size={14} className="text-accent" /><h2 className="text-xs font-semibold text-text">Control-plane status</h2></header>
                  <div className="divide-y divide-border/60"><div className="flex min-h-14 items-center justify-between gap-4 px-4 py-3"><div><div className="text-xs font-medium text-text">Policy</div><div className="mt-0.5 text-[10px] text-muted">Active reviewed development policy</div></div><div className="font-mono text-xs text-accent">v{overview?.policy.version} · {overview?.policy.hash.slice(0, 10)}</div></div><div className="flex min-h-14 items-center justify-between gap-4 px-4 py-3"><div><div className="text-xs font-medium text-text">GitHub App</div><div className="mt-0.5 text-[10px] text-muted">Pull request and repository actions</div></div><div className={`text-xs font-medium ${overview?.policy.github_configured ? 'text-success' : 'text-warning'}`}>{overview?.policy.github_configured ? 'Configured' : 'Not configured'}</div></div><div className="flex min-h-14 items-center justify-between gap-4 px-4 py-3"><div><div className="text-xs font-medium text-text">Deployment</div><div className="mt-0.5 text-[10px] text-muted">Owner-gated release target</div></div><div className={`text-xs font-medium ${overview?.policy.deployment_configured ? 'text-success' : 'text-warning'}`}>{overview?.policy.deployment_configured ? 'Configured' : 'Not configured'}</div></div></div>
                </section>
              </div>
            </div>}
            {tab === "loop" && <div className="space-y-4">
              <DeveloperRuntimeLoop />
              <DeveloperProcess workflow={active} events={events} workers={workers} queue={queue.items} capabilities={overview?.policy.capabilities} busy={busy}
                autoQueue={autoQueuePending ?? overview?.process?.auto_queue ?? false} autoQueueBusy={autoQueuePending !== null} streamState={streamState} streamIssue={streamIssue}
                onAutoQueue={setAutoQueue} onCommand={command} onApprove={approve} onReject={rejectApproval} />
            </div>}
            {tab === 'work' && <div className="space-y-8"><DevelopmentGoals goals={goals} busy={busy} onCreate={createGoal} onCommand={goalCommand} onCreateItem={goalId => setQueueGoalDraft({ goalId, requestId: Date.now() })} /><DeveloperQueue state={queue} active={active} busy={busy} goals={goals} createForGoalId={queueGoalDraft?.goalId} createRequestId={queueGoalDraft?.requestId}
              autoQueue={autoQueuePending ?? overview?.process?.auto_queue ?? queue.auto_queue} autoQueueBusy={autoQueuePending !== null} acceptanceMode={Boolean(overview?.acceptance_mode)} onAutoQueue={setAutoQueue}
              onPrepare={(id, readinessId) => { void act(() => prepareDeveloperWorkflow(id, readinessId), `Queue #${id} prepared for acceptance testing`) }}
              onStart={(id, readinessId) => { void act(() => startDeveloperWorkflow(id, readinessId), `Queue #${id} started`) }} onOpenProcess={() => setTab('loop')} onConfigureReviewer={() => setTab('workers')} onState={setQueue} /></div>}
            {tab === 'workers' && <DeveloperAgents workers={workers} models={workerModels} providers={workerProviders} routing={modelRouting} busy={busy} onSave={saveWorker} onProbe={probeWorker} onLogin={loginWorker} onModels={loadWorkerModels} />}
            {/* History and System hold no data until the first load resolves. Rendering their
                empty state during a refresh reads as "nothing here" rather than "not yet". */}
            {tab === 'history' && (loading && !history.length ? <SectionSkeleton rows={6} /> : <HistoryView workflows={history} />)}
            {tab === 'system' && (loading && !storage ? <SectionSkeleton rows={5} /> : <SystemView storage={storage} learning={learning} releases={releases} workflowId={active?.id ?? null} acceptanceMode={Boolean(overview?.acceptance_mode)} busy={busy} onReplay={replayLearning} onCleanup={master => act(() => cleanupDeveloperStorage(master), 'Developer cleanup completed')} />)}
          </main>
        </>}
    </div>
  )
}
