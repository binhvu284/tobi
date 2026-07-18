import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import {
  AlertTriangle, Check, CheckCircle2, ChevronDown, Circle, Clock3, GripVertical,
  Pause, Play, Radio, ShieldAlert, Square, TerminalSquare, Trash2, XCircle,
} from 'lucide-react'
import LlmLogo from '../LlmLogo'
import type {
  DeveloperEvent, DeveloperQueueItem, DeveloperWorkerProfile, DeveloperWorkflow,
} from '../../api'

type WorkflowCommand = 'pause' | 'resume' | 'cancel' | 'retry' | 'remove'
type ApprovalPurpose = 'special_paths' | 'merge_deploy'
type ProcessTone = 'cooking' | 'paused' | 'completed' | 'canceled' | 'crashed' | 'waiting'

type Props = {
  workflow: DeveloperWorkflow | null
  events: DeveloperEvent[]
  workers: DeveloperWorkerProfile[]
  queue: DeveloperQueueItem[]
  busy: boolean
  autoQueue: boolean
  streamState: 'idle' | 'connecting' | 'live' | 'reconnecting' | 'closed'
  streamIssue: string | null
  onAutoQueue: (enabled: boolean) => void
  onCommand: (command: WorkflowCommand) => void
  onApprove: (purpose: ApprovalPurpose, master: string) => void
  onReject: (purpose: ApprovalPurpose) => void
}

const TERMINAL = new Set(['completed', 'canceled', 'failed', 'rolled_back'])

function titleCase(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function processTone(workflow: DeveloperWorkflow): ProcessTone {
  if (workflow.state === 'completed') return 'completed'
  if (workflow.state === 'canceled') return 'canceled'
  if (workflow.state === 'failed' || workflow.state === 'rolled_back') return 'crashed'
  if (workflow.state === 'awaiting_merge_deploy_approval' || workflow.error_code === 'special_approval_required') return 'waiting'
  if (workflow.state === 'paused' || workflow.state === 'blocked') return workflow.error_code && workflow.error_code !== 'owner_paused' ? 'crashed' : 'paused'
  return 'cooking'
}

const TONE = {
  cooking: {
    label: 'Cooking', bar: 'bg-warning', text: 'text-warning', border: 'developer-process-cooking border-warning/45',
  },
  paused: {
    label: 'Paused', bar: 'bg-danger', text: 'text-danger', border: 'border-danger/35',
  },
  completed: {
    label: 'Completed', bar: 'bg-success', text: 'text-success', border: 'developer-process-completed border-success/40',
  },
  canceled: {
    label: 'Canceled', bar: 'bg-muted', text: 'text-muted', border: 'border-border',
  },
  crashed: {
    label: 'Crashed', bar: 'bg-danger', text: 'text-danger', border: 'border-danger/55',
  },
  waiting: {
    label: 'Waiting', bar: 'bg-warning', text: 'text-warning', border: 'border-warning/45',
  },
} as const

function eventLine(event: DeveloperEvent): string {
  const payload = event.payload ?? {}
  const values: unknown[] = [
    payload.output, payload.stdout, payload.stderr, payload.line, payload.message,
    payload.summary, payload.text, payload.detail, payload.action,
  ]
  const nested = payload.item && typeof payload.item === 'object' && !Array.isArray(payload.item)
    ? payload.item as Record<string, unknown> : null
  if (nested) values.push(nested.output, nested.text, nested.message, nested.command, nested.path)
  const value = values.find(item => typeof item === 'string' && item.trim())
  if (typeof value === 'string') return value.trim().replace(/\s+/g, ' ')
  const stage = typeof payload.stage === 'string' ? ` ${titleCase(payload.stage)}` : ''
  return `${titleCase(event.event_type)}${stage}`
}

function timeLabel(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? '--:--:--' : date.toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function safeJsonList(value?: string | null): string[] {
  try {
    const parsed = JSON.parse(value || '[]')
    return Array.isArray(parsed) ? parsed.map(item => String(item)) : []
  } catch {
    return []
  }
}

function latestCheckpoint(workflow: DeveloperWorkflow) {
  return [...(workflow.checkpoints ?? [])].sort((a, b) => b.sequence - a.sequence)[0] ?? null
}

function nextEligibleItem(queue: DeveloperQueueItem[], currentQueueId?: number) {
  const completed = new Set(queue.filter(item => item.status === 'completed').map(item => item.queue_id))
  return queue.find(item => {
    if (item.status !== 'planned' || item.queue_id === currentQueueId) return false
    return safeJsonList(item.dependencies_json).every(value => completed.has(Number(value)))
  }) ?? null
}

function approvalPurpose(workflow: DeveloperWorkflow): ApprovalPurpose | null {
  if (workflow.error_code === 'special_approval_required') return 'special_paths'
  if (workflow.state === 'awaiting_merge_deploy_approval') return 'merge_deploy'
  return null
}

function AgentIdentity({ workflow, workers }: { workflow: DeveloperWorkflow; workers: DeveloperWorkerProfile[] }) {
  const worker = workers.find(item => item.slug === (workflow.worker_session?.profile_slug || workflow.worker_profile_slug))
  const adapter = workflow.worker_session?.adapter || worker?.adapter || 'native'
  const model = workflow.worker_session?.model || worker?.model || ''
  const initials = (worker?.name || 'TOBI Agent').split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase()
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <div className="relative flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-background text-[10px] font-semibold text-text">
        {typeof worker?.config?.avatar === 'string' && worker.config.avatar
          ? <img src={worker.config.avatar} alt="" className="h-full w-full object-cover" />
          : initials}
        <span className={`absolute bottom-0.5 right-0.5 h-2 w-2 rounded-full border border-background ${worker?.health_status === 'ready' ? 'bg-success' : 'bg-muted'}`} />
      </div>
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-text">{worker?.name || workflow.worker_profile_slug || 'TOBI Agent'}</div>
        <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[9px] text-muted">
          <LlmLogo model={model} size={9} />
          <span className="truncate">{titleCase(adapter)}{model ? ` / ${model}` : ''}</span>
        </div>
      </div>
    </div>
  )
}

function AutoToggle({ enabled, onChange }: { enabled: boolean; onChange: (enabled: boolean) => void }) {
  return <button type="button" role="switch" aria-checked={enabled} onClick={() => onChange(!enabled)} className="inline-flex h-8 items-center gap-2 text-left">
    <span className={`relative h-5 w-9 rounded-full border transition-colors ${enabled ? 'border-accent/60 bg-accent/25' : 'border-border bg-background'}`}><span className={`absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all ${enabled ? 'left-[17px] bg-accent' : 'left-0.5 bg-muted'}`} /></span>
    <span><span className="block text-[10px] font-medium text-text">Auto</span><span className="block text-[8px] text-muted">Next queue item</span></span>
  </button>
}

function ProcessActions({ workflow, busy, onCommand }: {
  workflow: DeveloperWorkflow; busy: boolean; onCommand: (command: WorkflowCommand) => void
}) {
  const tone = processTone(workflow)
  const active = !TERMINAL.has(workflow.state)
  const resumable = ['paused', 'blocked', 'failed'].includes(workflow.state)
  return (
    <div className="flex flex-wrap justify-end gap-1.5">
      {resumable && <button disabled={busy} onClick={() => onCommand(workflow.error_code ? 'retry' : 'resume')} className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-2.5 text-[10px] font-semibold text-background disabled:opacity-45"><Play size={13} />{workflow.error_code ? 'Retry' : 'Resume'}</button>}
      {active && !resumable && workflow.state !== 'awaiting_merge_deploy_approval' && <button disabled={busy} onClick={() => onCommand('pause')} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-[10px] font-medium text-text hover:bg-overlay/5 disabled:opacity-45"><Pause size={13} /> Pause</button>}
      {active && <button disabled={busy} onClick={() => onCommand('cancel')} title="Cancel process" className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-danger/30 text-danger hover:bg-danger/5 disabled:opacity-45"><Square size={12} /></button>}
      {(tone === 'canceled' || tone === 'completed') && <button disabled={busy} onClick={() => onCommand('remove')} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-[10px] font-medium text-muted hover:border-danger/35 hover:text-danger disabled:opacity-45"><Trash2 size={13} /> Remove</button>}
    </div>
  )
}

function ApprovalCard({ workflow, busy, onApprove, onReject, onCommand }: {
  workflow: DeveloperWorkflow; busy: boolean
  onApprove: (purpose: ApprovalPurpose, master: string) => void
  onReject: (purpose: ApprovalPurpose) => void
  onCommand: (command: WorkflowCommand) => void
}) {
  const purpose = approvalPurpose(workflow)
  const external = workflow.state === 'blocked' && workflow.error_code === 'external_reconciliation_required'
  const [master, setMaster] = useState('')
  if (!purpose && !external) return null
  const description = workflow.blocker || (purpose === 'merge_deploy'
    ? 'The implementation passed its gates and needs permission to merge and deploy.'
    : purpose === 'special_paths'
      ? 'The agent needs to modify a protected path. Review the request before allowing it.'
      : 'Finish the required action outside Mission Control, then continue from the durable checkpoint.')
  return (
    <section className="relative overflow-hidden rounded-md border border-warning/45 bg-warning/5 p-4 sm:p-5">
      <div className="absolute inset-y-0 left-0 w-1 bg-warning" />
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-warning/10 text-warning"><ShieldAlert size={18} /></span>
          <div><div className="text-[10px] font-semibold uppercase text-warning">Requires your approval</div><p className="mt-1 max-w-3xl text-sm leading-6 text-text">{description}</p></div>
        </div>
        {purpose ? <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
          <input type="password" value={master} onChange={event => setMaster(event.target.value)} placeholder="Vault master password" className="h-9 min-w-52 rounded-md border border-border bg-background px-3 text-xs text-text outline-none focus:border-warning" />
          <button disabled={busy} onClick={() => onReject(purpose)} className="h-9 rounded-md border border-border px-3 text-xs font-medium text-text hover:bg-overlay/5 disabled:opacity-45">Reject</button>
          <button disabled={busy || master.length < 6} onClick={() => onApprove(purpose, master)} className="h-9 rounded-md bg-warning px-3 text-xs font-semibold text-background disabled:opacity-45">Approve</button>
        </div> : <div className="flex gap-2">
          <button disabled={busy} onClick={() => onCommand('cancel')} className="h-9 rounded-md border border-danger/35 px-3 text-xs text-danger disabled:opacity-45">Cancel</button>
          <button disabled={busy} onClick={() => onCommand('resume')} className="h-9 rounded-md bg-accent px-3 text-xs font-semibold text-background disabled:opacity-45">Continue</button>
        </div>}
      </div>
    </section>
  )
}

export default function DeveloperProcess({
  workflow, events, workers, queue, busy, autoQueue, streamState, streamIssue,
  onAutoQueue, onCommand, onApprove, onReject,
}: Props) {
  const [split, setSplit] = useState(58)
  const [dragging, setDragging] = useState(false)
  const splitRef = useRef<HTMLDivElement | null>(null)
  const activityRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!dragging) return
    const move = (event: PointerEvent) => {
      const box = splitRef.current?.getBoundingClientRect()
      if (!box) return
      setSplit(Math.max(34, Math.min(72, ((event.clientX - box.left) / box.width) * 100)))
    }
    const stop = () => setDragging(false)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop, { once: true })
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop) }
  }, [dragging])

  useEffect(() => {
    const panel = activityRef.current
    if (panel) panel.scrollTop = panel.scrollHeight
  }, [events.length, workflow?.id])

  const nextItem = useMemo(() => nextEligibleItem(queue, workflow?.queue_id), [queue, workflow?.queue_id])

  if (!workflow) return (
    <div className="space-y-5">
      <section className="rounded-md border border-border bg-surface/45 px-5 py-8">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div><div className="text-[10px] font-semibold uppercase text-accent">Process runtime</div><h2 className="mt-2 text-lg font-semibold text-text">No development process is active</h2><p className="mt-1 max-w-2xl text-xs leading-5 text-muted">Start an item from Queue, or enable Auto to take the next eligible planned item.</p></div>
          <AutoToggle enabled={autoQueue} onChange={onAutoQueue} />
        </div>
      </section>
      <NextQueueSection item={nextItem} autoQueue={autoQueue} onAutoQueue={onAutoQueue} />
    </div>
  )

  const currentTone = processTone(workflow)
  const visual = TONE[currentTone]
  const latest = events[events.length - 1]
  const activity = latest ? eventLine(latest) : 'Waiting for the first runtime event.'
  const checkpoint = latestCheckpoint(workflow)
  const queueItem = queue.find(item => item.queue_id === workflow.queue_id)
  const criteria = safeJsonList(queueItem?.acceptance_criteria_json)
  const sprintCriteria = safeJsonList(workflow.sprint?.acceptance_criteria_json)
  const planCriteria = sprintCriteria.length ? sprintCriteria : criteria
  let handoff: Record<string, unknown> = {}
  try { handoff = checkpoint ? JSON.parse(checkpoint.handoff_json) : {} } catch { /* legacy checkpoint */ }
  const activeStageIndex = Math.max(0, workflow.stages.findIndex(stage => stage.node_id === workflow.stage || stage.status === 'running'))
  const lastCompletedIndex = workflow.stages.reduce((last, stage, index) => stage.status === 'completed' ? index : last, 0)
  const progressStageIndex = TERMINAL.has(workflow.state) ? lastCompletedIndex : activeStageIndex
  const stageProgress = workflow.stages.length > 1 ? Math.min(100, (progressStageIndex / (workflow.stages.length - 1)) * 100) : 0

  return (
    <div className="space-y-5">
      <section className={`overflow-hidden rounded-md border bg-surface/45 ${visual.border}`}>
        <div className="flex flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:justify-between sm:px-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-[9px] font-medium uppercase text-muted">
              <span>Item #{workflow.queue_id}</span><span className="text-border">/</span>
              <span className={`inline-flex items-center gap-1.5 ${visual.text}`}><span className={`h-1.5 w-1.5 rounded-full ${visual.bar}`} />{visual.label}{currentTone === 'cooking' && <span className="developer-process-skeleton" aria-label="Active process"><i /><i /><i /></span>}</span>
            </div>
            <h2 className="mt-1.5 truncate text-base font-semibold text-text">{workflow.title}</h2>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3 lg:justify-end">
            <AgentIdentity workflow={workflow} workers={workers} />
            <span className="hidden h-8 w-px bg-border lg:block" />
            <AutoToggle enabled={autoQueue} onChange={onAutoQueue} />
            <ProcessActions workflow={workflow} busy={busy} onCommand={onCommand} />
          </div>
        </div>
        <div className="grid border-t border-border/70 md:grid-cols-[minmax(220px,0.65fr)_minmax(220px,0.55fr)_minmax(0,1fr)]">
          <div className="px-4 py-3 sm:px-5">
            <div className="flex items-center justify-between gap-3 text-[9px] text-muted"><span>Progress</span><span className="font-medium text-text">{workflow.progress}%</span></div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-background"><div className={`h-full rounded-full transition-[width] duration-700 ${visual.bar} ${currentTone === 'cooking' ? 'developer-process-bar' : ''}`} style={{ width: `${Math.max(2, workflow.progress)}%` }} /></div>
          </div>
          <div className="border-t border-border/70 px-4 py-3 md:border-l md:border-t-0 sm:px-5">
            <div className="text-[9px] text-muted">Current sprint</div>
            <div className="mt-1 truncate text-[11px] font-medium text-text">{TERMINAL.has(workflow.state) ? `Stopped at ${titleCase(workflow.stage)}` : workflow.sprint?.title || titleCase(workflow.stage)}</div>
          </div>
          <div className="flex min-w-0 items-center gap-2 border-t border-border/70 px-4 py-3 font-mono text-[9px] text-muted md:border-l md:border-t-0 sm:px-5"><TerminalSquare size={12} className={`shrink-0 ${visual.text}`} /><span className="truncate">{activity}</span>{!TERMINAL.has(workflow.state) && <span className="developer-terminal-caret" />}</div>
        </div>
        {currentTone === 'crashed' && <div className="flex items-start gap-2 border-t border-danger/25 bg-danger/5 px-4 py-3 text-[10px] leading-5 text-danger sm:px-5"><AlertTriangle size={13} className="mt-0.5 shrink-0" /><div><span className="font-semibold">{titleCase(workflow.error_code || 'workflow_failed')}:</span> <span className="text-muted">{workflow.blocker || streamIssue || 'Open Live activities for the latest failure evidence.'}</span></div></div>}
      </section>

      <ApprovalCard workflow={workflow} busy={busy} onApprove={onApprove} onReject={onReject} onCommand={onCommand} />

      <section className="overflow-hidden rounded-md border border-border bg-surface/30">
        <header className="flex items-center justify-between gap-4 border-b border-border/70 px-4 py-3 sm:px-5"><div><div className="text-[9px] font-semibold uppercase text-accent">Run brief</div><h3 className="mt-0.5 text-xs font-semibold text-text">{workflow.sprint?.title || workflow.title}</h3></div><span className="max-w-[45%] truncate font-mono text-[9px] text-muted">{workflow.plan_path}</span></header>
        <div className="grid lg:grid-cols-[minmax(0,1fr)_300px]">
          <article className="px-4 py-4 sm:px-5">
            <p className="max-w-4xl text-[11px] leading-5 text-muted">{workflow.sprint?.objective || `Execute the approved plan within the reviewed policy and current sprint budget.`}</p>
            {planCriteria.length > 0 && <div className="mt-3 grid gap-x-6 gap-y-1.5 sm:grid-cols-2">{planCriteria.slice(0, 6).map(item => <div key={item} className="flex items-start gap-2 text-[10px] leading-5 text-text"><Check size={12} className="mt-1 shrink-0 text-success" /><span>{item}</span></div>)}</div>}
          </article>
          <aside className="border-t border-border/70 px-4 py-4 lg:border-l lg:border-t-0 sm:px-5">
            <div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2"><Clock3 size={13} className="text-accent" /><span className="text-[9px] font-semibold uppercase text-muted">Durable checkpoint</span></div>{checkpoint && <span className="font-mono text-[9px] text-accent">{checkpoint.head_sha?.slice(0, 10) || 'working tree'}</span>}</div>
            {checkpoint ? <div className="mt-3 flex items-start gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent/10 text-xs font-semibold text-accent">#{checkpoint.sequence}</span><div className="min-w-0"><div className="text-[10px] font-medium text-text">{titleCase(checkpoint.status)}</div><p className="mt-1 line-clamp-2 text-[9px] leading-4 text-muted">{String(handoff.next_action || 'Resume from the recorded stage.')}</p></div></div> : <p className="mt-3 text-[10px] leading-5 text-muted">Checkpoint appears after the worktree is prepared.</p>}
          </aside>
        </div>
      </section>

      <section ref={splitRef} className="developer-process-split grid overflow-hidden rounded-md border border-border bg-surface/25 lg:grid-cols-[var(--process-left)_6px_minmax(0,1fr)]" style={{ '--process-left': `${split}%` } as CSSProperties}>
        <article className="min-w-0">
          <header className="flex h-12 items-center justify-between gap-3 border-b border-border/70 px-4"><div className="flex items-center gap-2"><TerminalSquare size={14} className="text-accent" /><h3 className="text-xs font-semibold text-text">Live activities</h3></div><span className={`inline-flex items-center gap-1.5 text-[9px] ${streamState === 'live' ? 'text-success' : TERMINAL.has(workflow.state) ? 'text-muted' : 'text-warning'}`}><Radio size={11} className={streamState === 'live' && !TERMINAL.has(workflow.state) ? 'animate-pulse' : ''} />{TERMINAL.has(workflow.state) ? 'Closed' : streamState === 'live' ? 'Live' : titleCase(streamState)}</span></header>
          <div ref={activityRef} className="h-[380px] overflow-y-auto bg-[rgb(7_10_14/0.68)] px-4 py-3 font-mono text-[9px] leading-5">
            {events.length === 0 ? <div className="flex h-full items-center justify-center text-muted">Waiting for worker output...</div> : events.slice(-160).map(event => <div key={event.id} className="grid grid-cols-[58px_minmax(0,1fr)] gap-2 border-b border-white/5 py-1 last:border-0"><span className="text-muted/60">{timeLabel(event.created_at)}</span><span className={`${event.event_type.includes('failed') || event.event_type.includes('blocked') ? 'text-danger' : event.event_type.includes('completed') ? 'text-success' : 'text-[#cbd5e1]'}`}><span className="mr-2 text-accent/75">{event.actor}&gt;</span>{eventLine(event)}</span></div>)}
          </div>
        </article>
        <button type="button" onPointerDown={event => { event.preventDefault(); setDragging(true) }} title="Drag to resize Process panels" className="hidden cursor-col-resize items-center justify-center border-x border-border/70 bg-background/50 text-muted/50 hover:bg-accent/10 hover:text-accent lg:flex"><GripVertical size={12} /></button>
        <article className="min-w-0 border-t border-border lg:border-t-0">
          <header className="flex h-12 items-center justify-between gap-3 border-b border-border/70 px-4"><div className="flex items-center gap-2"><CheckCircle2 size={14} className="text-accent" /><h3 className="text-xs font-semibold text-text">Sprint</h3></div><span className="text-[9px] text-muted">{workflow.stages.filter(stage => stage.status === 'completed').length}/{workflow.stages.length} gates</span></header>
          <div className="relative h-[380px] overflow-y-auto px-4 py-3">
            <div className="absolute bottom-5 left-[34px] top-5 w-px bg-border" />
            <div className="developer-sprint-line absolute left-[34px] top-5 w-px bg-accent transition-[height] duration-700" style={{ height: stageProgress > 0 ? `calc(${stageProgress}% - 8px)` : 0 }} />
            <div className="space-y-1">{workflow.stages.map(stage => {
              const current = !TERMINAL.has(workflow.state) && (stage.node_id === workflow.stage || stage.status === 'running')
              const done = stage.status === 'completed'
              const failed = stage.status === 'failed' || stage.status === 'paused'
              return <div key={stage.node_id} className={`relative flex min-h-10 items-center gap-3 rounded-md px-1.5 py-1.5 ${current ? 'developer-sprint-current bg-accent/10' : ''}`}><span className={`relative z-[1] flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${done ? 'border-success bg-success text-background' : failed ? 'border-danger bg-danger/10 text-danger' : current ? 'border-accent bg-background text-accent' : 'border-border bg-background text-muted'}`}>{done ? <Check size={11} /> : failed ? <XCircle size={11} /> : current ? <span className="h-1.5 w-1.5 rounded-full bg-accent" /> : <Circle size={10} />}</span><div className="min-w-0 flex-1"><div className={`truncate text-[10px] font-medium ${current ? 'text-accent' : done ? 'text-text' : 'text-muted'}`}>{stage.node_id === 'code' ? 'Run selected developer agent' : stage.title}</div><div className="mt-0.5 text-[8px] uppercase text-muted/70">{current ? 'In progress' : done ? 'Saved' : failed ? titleCase(stage.status) : 'Pending'}</div></div></div>
            })}</div>
          </div>
        </article>
      </section>

      <NextQueueSection item={nextItem} autoQueue={autoQueue} onAutoQueue={onAutoQueue} />
    </div>
  )
}

function NextQueueSection({ item, autoQueue, onAutoQueue }: {
  item: DeveloperQueueItem | null
  autoQueue: boolean
  onAutoQueue: (enabled: boolean) => void
}) {
  const criteria = safeJsonList(item?.acceptance_criteria_json)
  return <section className="overflow-hidden rounded-md border border-border bg-surface/25">
    <div className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div className="flex min-w-0 items-center gap-3">
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-xs font-semibold ${item ? 'bg-accent/10 text-accent' : 'bg-overlay/5 text-muted'}`}>{item ? `#${item.queue_id}` : <Circle size={14} />}</span>
        <div className="min-w-0">
          <div className="text-[9px] font-semibold uppercase text-muted">Up next</div>
          <div className={`mt-0.5 truncate text-xs font-medium ${item ? 'text-text' : 'text-muted'}`}>{item?.title || 'No eligible planned item'}</div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className={`inline-flex h-6 items-center rounded-md border px-2 text-[9px] font-medium ${autoQueue ? 'border-success/30 bg-success/5 text-success' : 'border-border text-muted'}`}>{autoQueue ? 'Auto ready' : 'Preview only'}</span>
        {!autoQueue && <button type="button" onClick={() => onAutoQueue(true)} className="inline-flex h-7 items-center gap-1.5 rounded-md border border-accent/35 px-2.5 text-[9px] font-semibold text-accent hover:bg-accent/5"><Play size={11} /> Enable Auto</button>}
      </div>
    </div>
    {item ? <details className="group border-t border-border/70">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-2.5 text-[10px] text-muted hover:bg-overlay/5 sm:px-5"><span>{autoQueue ? 'This item starts after the current process finishes.' : 'Enable Auto to start this item after the current process.'}</span><span className="inline-flex shrink-0 items-center gap-1.5 text-accent">View scope <ChevronDown size={13} className="transition-transform group-open:rotate-180" /></span></summary>
      <div className="border-t border-border/70 px-4 py-3 text-[10px] leading-5 text-muted sm:px-5"><div className="grid gap-2 sm:grid-cols-3"><div><span className="text-text">Status:</span> {item.queue_status || titleCase(item.status)}</div><div><span className="text-text">Effort:</span> {item.queue_effort || 'Not estimated'}</div><div className="truncate"><span className="text-text">Plan:</span> {item.plan_path}</div></div>{criteria.length > 0 && <ul className="mt-3 grid gap-x-5 gap-y-1 sm:grid-cols-2">{criteria.slice(0, 6).map(value => <li key={value} className="flex items-start gap-1.5"><Check size={10} className="mt-1 shrink-0 text-success" /><span>{value}</span></li>)}</ul>}</div>
    </details> : <div className="border-t border-border/70 px-4 py-3 text-[10px] leading-5 text-muted sm:px-5">The queue is empty, or its planned items are waiting for dependencies. Review the Queue tab to choose the next runnable item.</div>}
  </section>
}
