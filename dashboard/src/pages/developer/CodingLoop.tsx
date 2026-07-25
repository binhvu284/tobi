// Extracted from Developer.tsx (pre-#21 refactor) — verbatim move.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, Archive, BookOpen, CheckCircle2, Circle, Clock3, Code2, Download, ExternalLink,
  ChevronDown, ChevronUp, GitBranch, Github, HardDrive, KeyRound, ListTree, Loader2, MoreHorizontal, Pause, Play, Plus, Radio, RefreshCw,
  RotateCcw, Save, ScrollText, ShieldCheck, Square, Target,
  TerminalSquare, TestTube2, Trash2, Upload, WifiOff, Wrench, XCircle,
} from 'lucide-react'
import {
  approveDeveloperWorkflow, assessDeveloperGoal, commandDeveloperGoal, commandDeveloperWorkflow, createDeveloperGoal,
  getDeveloperHistory, getDeveloperLearning, getDeveloperOverview, getDeveloperQueue, getDeveloperStorage, getDeveloperVersions,
  getDeveloperGoals, getDeveloperWorkerLogin, getDeveloperWorkerModels, getDeveloperWorkers, probeDeveloperWorker, replayDeveloperLearning,
  saveDeveloperWorker, startDeveloperWorkflow, streamDeveloperEvents, switchDeveloperWorker, cleanupDeveloperStorage,
  rejectDeveloperWorkflow, setDeveloperProcessSettings,
  type AvailableModel, type DeveloperAssessment, type DeveloperEvent, type DeveloperOverview, type DeveloperGoal,
  type DeveloperQueueItem, type DeveloperQueueState, type DeveloperRelease, type DeveloperStorage, type DeveloperWorkerLogin,
  type DeveloperWorkerModels, type DeveloperWorkerProfile,
  type DeveloperWorkflow, type LlmProvider,
} from '../../api'
import { DeveloperStreamState, Empty, LiveEventIcon, StateBadge, TERMINAL_STATES, eventKindClasses, eventPresentation, label, relativeAge, stageLabel } from './format'

export function CodingLoop({ workflow, events, workers, busy, streamState, streamIssue, lastSignalAt, onSwitch, onCommand }: {
  workflow: DeveloperWorkflow | null; events: DeveloperEvent[]; workers: DeveloperWorkerProfile[]
  busy: boolean; streamState: DeveloperStreamState; streamIssue: string | null; lastSignalAt: number | null
  onSwitch: (slug: string) => void
  onCommand: (command: 'pause' | 'resume' | 'cancel' | 'retry') => void
}) {
  const [selectedWorker, setSelectedWorker] = useState('')
  const [followLive, setFollowLive] = useState(true)
  const [now, setNow] = useState(() => Date.now())
  const timelineRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!workflow) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [workflow?.id])

  useEffect(() => {
    if (!followLive || !timelineRef.current) return
    timelineRef.current.scrollTo({ top: timelineRef.current.scrollHeight, behavior: 'smooth' })
  }, [events.length, followLive])

  if (!workflow) return <Empty text="No coding workflow has started." />
  const canSwitch = ['paused', 'blocked', 'failed', 'approved'].includes(workflow.state)
  const codingWorkers = workers.filter(item => item.enabled && item.adapter !== 'model_review')
  const currentWorker = workflow.worker_session
  const active = !TERMINAL_STATES.has(workflow.state)
  const latestEvent = events[events.length - 1] ?? null
  const latestPresentation = latestEvent ? eventPresentation(latestEvent) : null
  const parsedEventAt = Date.parse(latestEvent?.created_at ?? workflow.updated_at ?? workflow.created_at)
  const latestEventAt = Number.isFinite(parsedEventAt) ? parsedEventAt : null
  const eventAgeSeconds = latestEventAt
    ? Math.max(0, Math.floor((now - latestEventAt) / 1000))
    : null
  const needsAttention = ['paused', 'blocked', 'failed'].includes(workflow.state)
  const stale = active && !needsAttention && eventAgeSeconds !== null && eventAgeSeconds >= 120
  const quiet = active && !needsAttention && eventAgeSeconds !== null && eventAgeSeconds >= 30
  const statusTitle = needsAttention
    ? 'Owner action needed'
    : workflow.state === 'completed'
      ? 'Run completed'
      : streamState === 'reconnecting'
        ? 'Restoring live updates'
        : streamState === 'connecting'
          ? 'Connecting to the worker'
          : stale
            ? 'Worker may be waiting'
            : 'Worker is active'
  const statusDetail = latestPresentation?.title
    ?? (active ? 'Preparing the workflow and waiting for the first event.' : `Workflow ${label(workflow.state)}.`)
  const streamConnected = streamState === 'live'
  const visibleEvents = events.slice(-120)
  const retryCommand = workflow.error_code ? 'retry' : 'resume'

  return (
    <div className="space-y-6">
      <section className={`rounded-lg border p-4 sm:p-5 ${
        needsAttention ? 'border-warning/40 bg-warning/5' : stale ? 'border-danger/30 bg-danger/5' : 'border-border bg-surface/50'
      }`}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${
              needsAttention || stale
                ? 'border-warning/40 bg-warning/10 text-warning'
                : 'border-accent/35 bg-accent/10 text-accent'
            }`}>
              {needsAttention ? <AlertTriangle size={18} /> : stale ? <WifiOff size={18} /> : <Activity size={18} />}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-semibold text-text">{statusTitle}</h2>
                {active && !needsAttention && (
                  <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium ${
                    streamConnected ? 'text-success' : streamState === 'reconnecting' ? 'text-warning' : 'text-muted'
                  }`}>
                    {streamConnected
                      ? <><span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-50" /><span className="relative inline-flex h-2 w-2 rounded-full bg-success" /></span>Live</>
                      : <><Loader2 size={12} className={streamState === 'connecting' || streamState === 'reconnecting' ? 'animate-spin' : ''} />{label(streamState)}</>}
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm leading-6 text-text">{statusDetail}</p>
              {latestPresentation?.detail && <p className="mt-0.5 text-xs leading-5 text-muted">{latestPresentation.detail}</p>}
            </div>
          </div>
          {needsAttention && (
            <button
              onClick={() => onCommand(retryCommand)}
              disabled={busy}
              className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background disabled:opacity-50"
            >
              <Play size={15} /> {workflow.error_code ? 'Retry failed stage' : 'Resume run'}
            </button>
          )}
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <div className="rounded-md bg-overlay/5 px-3 py-2.5">
            <div className="text-[10px] uppercase text-muted">Current stage</div>
            <div className="mt-1 truncate text-xs font-medium text-text">{stageLabel(workflow.stage)}</div>
          </div>
          <div className="rounded-md bg-overlay/5 px-3 py-2.5">
            <div className="text-[10px] uppercase text-muted">Selected worker</div>
            <div className="mt-1 truncate text-xs font-medium text-text">{currentWorker?.profile_slug ?? workflow.worker_profile_slug ?? 'mc-native'}</div>
          </div>
          <div className="rounded-md bg-overlay/5 px-3 py-2.5">
            <div className="text-[10px] uppercase text-muted">Last activity</div>
            <div className={`mt-1 flex items-center gap-1.5 text-xs font-medium ${stale ? 'text-danger' : quiet ? 'text-warning' : 'text-text'}`}>
              <Clock3 size={12} /> {relativeAge(latestEventAt, now)}
            </div>
          </div>
        </div>

        {(streamIssue || stale || quiet) && active && !needsAttention && (
          <div className={`mt-3 flex items-start gap-2 text-xs leading-5 ${stale ? 'text-danger' : 'text-warning'}`}>
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>
              {streamIssue
                ?? (stale
                  ? 'No worker event has arrived for two minutes. Check the latest technical event, worker availability, and server logs before retrying.'
                  : 'No new worker event for 30 seconds. A model call or command may still be running.')}
            </span>
          </div>
        )}

        {needsAttention && (
          <div className="mt-3 border-l-2 border-warning pl-3">
            <div className="text-xs font-medium text-warning">{workflow.error_code ? label(workflow.error_code) : label(workflow.state)}</div>
            <p className="mt-1 text-xs leading-5 text-muted">{workflow.blocker ?? 'Review the latest event and resume from the saved checkpoint.'}</p>
          </div>
        )}
      </section>

      <section className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-md bg-surface/50 px-3 py-3">
          <div className="text-[10px] uppercase text-muted">Worker runtime</div>
          <div className="mt-1 text-sm font-medium text-text">{currentWorker?.adapter ? label(currentWorker.adapter) : 'Awaiting worker'}</div>
          <div className="mt-1 truncate text-xs text-muted">{currentWorker?.model || 'Model selected by the worker profile'}</div>
        </div>
        <div className="rounded-md bg-surface/50 px-3 py-3">
          <div className="text-[10px] uppercase text-muted">Bounded sprint</div>
          <div className="mt-1 truncate text-sm font-medium text-text">{workflow.sprint?.title ?? 'Queue workflow'}</div>
          <div className="mt-1 text-xs text-muted">{workflow.sprint ? `Sprint ${workflow.sprint.sequence} / ${label(workflow.sprint.status)}` : 'Single approved plan'}</div>
        </div>
        <div className="rounded-md bg-surface/50 px-3 py-3">
          <div className="text-[10px] uppercase text-muted">Worker session</div>
          <div className="mt-1 truncate font-mono text-xs text-text">{currentWorker?.external_session_id ?? `MC-${currentWorker?.id ?? workflow.id}`}</div>
          <div className="mt-1 text-xs text-muted">{currentWorker ? label(currentWorker.status) : 'Not started'}</div>
        </div>
      </section>

      {canSwitch && (
        <section className="flex flex-col gap-2 border-l-2 border-accent pl-3 sm:flex-row sm:items-end">
          <label className="min-w-0 flex-1"><span className="mb-1 block text-xs text-muted">Continue from the latest checkpoint with</span><select value={selectedWorker || workflow.worker_profile_slug || 'mc-native'} onChange={event => setSelectedWorker(event.target.value)} className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent">{codingWorkers.map(worker => <option key={worker.slug} value={worker.slug}>{worker.name} / {worker.health_status}</option>)}</select></label>
          <button disabled={busy || !codingWorkers.length} onClick={() => onSwitch(selectedWorker || workflow.worker_profile_slug || 'mc-native')} className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-accent/40 px-3 text-sm text-accent disabled:opacity-40"><RotateCcw size={14} /> Switch at checkpoint</button>
        </section>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(260px,0.72fr)_minmax(0,1.28fr)]">
        <section>
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-text">Run progress</h2>
            <span className="text-[11px] text-muted">{workflow.progress}% complete</span>
          </div>
          <div className="space-y-1">
            {workflow.stages.map(stage => {
              const running = stage.status === 'running'
              const complete = stage.status === 'completed'
              const failed = ['failed', 'paused'].includes(stage.status)
              const Icon = complete ? CheckCircle2 : failed ? XCircle : running ? Loader2 : Circle
              const stageTitle = stage.node_id === 'code' ? 'Run selected coding worker' : stage.title
              return (
                <div key={stage.node_id} className={`flex min-h-14 items-center gap-3 rounded-md px-3 py-2.5 ${
                  running ? 'bg-accent/10' : failed ? 'bg-danger/5' : 'hover:bg-overlay/5'
                }`}>
                  <Icon size={17} className={`${complete ? 'text-success' : failed ? 'text-danger' : running ? 'animate-spin text-accent' : 'text-muted/60'}`} />
                  <div className="min-w-0 flex-1"><div className="text-sm text-text">{stageTitle}</div><div className="mt-0.5 text-[11px] text-muted">{stage.attempts ? `${stage.attempts} attempt${stage.attempts === 1 ? '' : 's'}` : 'Not started'}</div></div>
                  <StateBadge state={stage.status} />
                </div>
              )
            })}
          </div>
        </section>

        <section className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-text">Live worker activity</h2>
              <p className="mt-0.5 text-[11px] text-muted">
                {streamConnected
                  ? `Connected / last signal ${relativeAge(lastSignalAt, now)}`
                  : streamState === 'reconnecting' ? 'The event stream is reconnecting automatically.' : 'Waiting for the event stream.'}
              </p>
            </div>
            <button
              onClick={() => setFollowLive(value => !value)}
              title={followLive ? 'Pause automatic scrolling' : 'Follow the newest worker event'}
              className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs ${
                followLive ? 'border-accent/35 bg-accent/10 text-accent' : 'border-border text-muted hover:text-text'
              }`}
            >
              <Radio size={13} className={followLive && active ? 'animate-pulse' : ''} />
              {followLive ? 'Following live' : 'Follow live'}
            </button>
          </div>
          <div ref={timelineRef} className="max-h-[620px] overflow-y-auto rounded-lg border border-border bg-background/50 p-2">
            {visibleEvents.length === 0 && (
              <div className="flex min-h-48 flex-col items-center justify-center px-5 text-center">
                {active ? <Loader2 size={20} className="animate-spin text-accent" /> : <ScrollText size={20} className="text-muted" />}
                <div className="mt-3 text-sm font-medium text-text">
                  {active ? 'Waiting for the first worker event' : 'No live events were recorded'}
                </div>
                <p className="mt-1 max-w-sm text-xs leading-5 text-muted">
                  {active
                    ? 'Stage changes, model actions, file operations, checks, and blockers will appear here as they happen.'
                    : 'Start or resume a workflow to see its activity timeline.'}
                </p>
              </div>
            )}
            {visibleEvents.map(event => {
              const presentation = eventPresentation(event)
              const createdAt = Date.parse(event.created_at)
              return (
                <details key={event.id} className="group rounded-md hover:bg-overlay/5">
                  <summary className="flex cursor-pointer list-none items-start gap-3 px-2.5 py-2.5">
                    <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border ${eventKindClasses(presentation.kind)}`}>
                      <LiveEventIcon kind={presentation.kind} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                        <span className="text-xs font-medium text-text">{presentation.title}</span>
                        <span className="text-[10px] text-muted">{event.actor}</span>
                      </span>
                      {presentation.detail && <span className="mt-0.5 block break-words text-[11px] leading-5 text-muted">{presentation.detail}</span>}
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="block text-[10px] text-muted">{Number.isFinite(createdAt) ? new Date(createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : `#${event.sequence}`}</span>
                      <span className="mt-1 block text-[9px] text-muted/70">#{event.sequence}</span>
                    </span>
                  </summary>
                  <div className="mx-2.5 mb-2.5 ml-12 rounded-md bg-overlay/5 px-3 py-2.5">
                    <div className="mb-1.5 text-[10px] font-medium uppercase text-muted">Technical evidence</div>
                    <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all font-mono text-[10px] leading-5 text-muted">{JSON.stringify(event.payload, null, 2)}</pre>
                  </div>
                </details>
              )
            })}
          </div>
        </section>
      </div>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-text">Durable checkpoints</h2>
        {!workflow.checkpoints?.length ? <Empty text="No checkpoint has been recorded yet." /> : <div className="space-y-1">{workflow.checkpoints.map(checkpoint => {
          let handoff: Record<string, unknown> = {}
          try { handoff = JSON.parse(checkpoint.handoff_json) } catch { /* malformed legacy payload */ }
          return <details key={checkpoint.id} className="rounded-md px-3 py-3 hover:bg-overlay/5"><summary className="flex cursor-pointer list-none items-center justify-between gap-3"><div className="flex min-w-0 items-center gap-2"><CheckCircle2 size={15} className="shrink-0 text-accent" /><span className="truncate text-sm text-text">Checkpoint {checkpoint.sequence} / {label(checkpoint.status)}</span></div><span className="font-mono text-[10px] text-muted">{checkpoint.head_sha?.slice(0, 10) ?? 'dirty tree'}</span></summary><div className="mt-3 grid gap-3 pl-6 text-xs text-muted sm:grid-cols-2"><div><span className="text-text">Next action:</span> {String(handoff.next_action ?? 'Resume the recorded stage.')}</div><div><span className="text-text">Changed files:</span> {Array.isArray(handoff.changed_files) ? handoff.changed_files.length : 0}</div></div></details>
        })}</div>}
      </section>
    </div>
  )
}
