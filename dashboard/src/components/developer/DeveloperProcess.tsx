import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import {
  AlertTriangle, Check, CheckCircle2, ChevronDown, Circle, Clock3, GripVertical,
  Pause, Play, Radio, ShieldAlert, Square, TerminalSquare, Trash2, XCircle,
} from 'lucide-react'
import LlmLogo from '../LlmLogo'
import DeveloperToolLogo, { type DeveloperTool } from './DeveloperToolLogo'
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
const COOKING = new Set(['approved', 'preparing', 'coding', 'validating', 'reviewing', 'pushed', 'merging', 'deploying'])

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
  const rawAdapter = workflow.worker_session?.adapter || worker?.adapter || 'native'
  const adapter: DeveloperTool = rawAdapter === 'codex' || rawAdapter === 'opencode' || rawAdapter === 'model_review'
    ? rawAdapter : 'native'
  const model = workflow.worker_session?.model || worker?.model || ''
  const initials = (worker?.name || 'TOBI Agent').split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase()
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <div className="relative flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-background text-[11px] font-semibold text-text">
        {typeof worker?.config?.avatar === 'string' && worker.config.avatar
          ? <img src={worker.config.avatar} alt="" className="h-full w-full object-cover" />
          : initials}
        <span className={`absolute bottom-0.5 right-0.5 h-2 w-2 rounded-full border border-background ${worker?.health_status === 'ready' ? 'bg-success' : 'bg-muted'}`} />
      </div>
      <div className="min-w-0">
        <div className="truncate text-xs font-semibold text-text">{worker?.name || workflow.worker_profile_slug || 'TOBI Agent'}</div>
        <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[10px] text-muted">
          <DeveloperToolLogo tool={adapter} size={11} />
          <LlmLogo model={model} size={10} />
          <span className="truncate">{model || titleCase(adapter)}</span>
        </div>
      </div>
    </div>
  )
}

function ProcessActions({ workflow, busy, onCommand }: {
  workflow: DeveloperWorkflow; busy: boolean; onCommand: (command: WorkflowCommand) => void
}) {
  const tone = processTone(workflow)
  const active = !TERMINAL.has(workflow.state)
  const resumable = ['paused', 'blocked', 'failed'].includes(workflow.state)
  return (
    <div className="flex flex-wrap justify-end gap-2">
      {resumable && <button disabled={busy} onClick={() => onCommand(workflow.error_code ? 'retry' : 'resume')} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-xs font-semibold text-background disabled:opacity-45"><Play size={14} />{workflow.error_code ? 'Retry' : 'Resume'}</button>}
      {active && !resumable && workflow.state !== 'awaiting_merge_deploy_approval' && <button disabled={busy} onClick={() => onCommand('pause')} className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-background/50 px-3 text-xs font-medium text-text hover:bg-overlay/5 disabled:opacity-45"><Pause size={14} /> Pause</button>}
      {active && <button disabled={busy} onClick={() => onCommand('cancel')} className="inline-flex h-9 items-center gap-2 rounded-md border border-danger/35 px-3 text-xs font-medium text-danger hover:bg-danger/5 disabled:opacity-45"><Square size={13} /> Cancel</button>}
      {(tone === 'canceled' || tone === 'completed') && <button disabled={busy} onClick={() => onCommand('remove')} className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-xs font-medium text-muted hover:border-danger/35 hover:text-danger disabled:opacity-45"><Trash2 size={14} /> Remove</button>}
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
          <label className="flex cursor-pointer items-center gap-3 rounded-md border border-border bg-background/50 px-3 py-2.5"><span><span className="block text-xs font-semibold text-text">Auto</span><span className="block text-[10px] text-muted">Continue through Queue</span></span><input type="checkbox" checked={autoQueue} onChange={event => onAutoQueue(event.target.checked)} className="h-4 w-4 accent-[rgb(var(--accent))]" /></label>
        </div>
      </section>
      {autoQueue && nextItem && <NextItem item={nextItem} />}
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
  const stageIndex = Math.max(0, workflow.stages.findIndex(stage => stage.node_id === workflow.stage || stage.status === 'running'))
  const stageProgress = workflow.stages.length > 1 ? Math.min(100, (stageIndex / (workflow.stages.length - 1)) * 100) : 0

  return (
    <div className="space-y-5">
      <section className={`relative overflow-hidden rounded-md border bg-surface/55 p-4 shadow-[0_22px_65px_rgb(0_0_0/0.16)] sm:p-5 ${visual.border}`}>
        <div className="developer-process-grid pointer-events-none absolute inset-0 opacity-35" />
        <div className="relative">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2 text-[10px] font-semibold uppercase text-muted">
                <span>Item #{workflow.queue_id}</span><span className="text-border">/</span><span className={visual.text}>{visual.label}</span>
                {currentTone === 'cooking' && <span className="developer-process-skeleton" aria-label="Active process"><i /><i /><i /></span>}
              </div>
              <h2 className="mt-2 truncate text-lg font-semibold text-text">{workflow.title}</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(240px,0.55fr)]">
                <div>
                  <div className="flex items-center justify-between gap-3 text-[10px] text-muted"><span>{workflow.progress}% complete</span><span>{titleCase(workflow.stage)}</span></div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-background/80"><div className={`h-full rounded-full transition-[width] duration-700 ${visual.bar} ${currentTone === 'cooking' ? 'developer-process-bar' : ''}`} style={{ width: `${Math.max(2, workflow.progress)}%` }} /></div>
                  <div className="mt-3 flex min-w-0 items-center gap-2 rounded-md border border-border/70 bg-background/55 px-3 py-2 font-mono text-[10px] text-muted"><TerminalSquare size={13} className={`shrink-0 ${visual.text}`} /><span className="truncate">{activity}</span><span className="developer-terminal-caret" /></div>
                </div>
                <AgentIdentity workflow={workflow} workers={workers} />
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-stretch gap-3 sm:flex-row sm:items-center xl:flex-col xl:items-end">
              <label className="flex cursor-pointer items-center gap-3 rounded-md border border-border bg-background/55 px-3 py-2"><span><span className="block text-xs font-semibold text-text">Auto</span><span className="block text-[9px] text-muted">Run next queue item</span></span><input type="checkbox" checked={autoQueue} onChange={event => onAutoQueue(event.target.checked)} className="h-4 w-4 accent-[rgb(var(--accent))]" /></label>
              <ProcessActions workflow={workflow} busy={busy} onCommand={onCommand} />
            </div>
          </div>
          {currentTone === 'crashed' && <div className="mt-4 flex items-start gap-2 border-l-2 border-danger pl-3 text-xs leading-5 text-danger"><AlertTriangle size={14} className="mt-0.5 shrink-0" /><div><div className="font-semibold">{titleCase(workflow.error_code || 'workflow_failed')}</div><div className="mt-0.5 text-muted">{workflow.blocker || streamIssue || 'Open Live activities for the latest failure evidence.'}</div></div></div>}
        </div>
      </section>

      <ApprovalCard workflow={workflow} busy={busy} onApprove={onApprove} onReject={onReject} onCommand={onCommand} />

      <section className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
        <article className="rounded-md border border-border bg-surface/35 p-4 sm:p-5">
          <div className="text-[10px] font-semibold uppercase text-accent">Implementation plan</div>
          <h3 className="mt-2 text-sm font-semibold text-text">{workflow.sprint?.title || workflow.title}</h3>
          <p className="mt-2 text-xs leading-6 text-muted">{workflow.sprint?.objective || `Execute the approved plan at ${workflow.plan_path} within the reviewed policy and current sprint budget.`}</p>
          {planCriteria.length > 0 && <div className="mt-4 grid gap-2 sm:grid-cols-2">{planCriteria.slice(0, 6).map(item => <div key={item} className="flex items-start gap-2 text-[11px] leading-5 text-text"><Check size={13} className="mt-0.5 shrink-0 text-accent" /><span>{item}</span></div>)}</div>}
        </article>
        <article className="developer-checkpoint-card rounded-md border border-accent/35 bg-accent/5 p-4">
          <div className="flex items-center justify-between gap-2"><div className="text-[10px] font-semibold uppercase text-accent">Durable checkpoint</div><Clock3 size={14} className="text-accent" /></div>
          {checkpoint ? <><div className="mt-4 text-2xl font-semibold text-text">#{checkpoint.sequence}</div><div className="mt-1 text-xs text-muted">{titleCase(checkpoint.status)}</div><div className="mt-4 rounded-md bg-background/55 p-3 text-[10px] leading-5 text-muted"><span className="text-text">Next:</span> {String(handoff.next_action || 'Resume from the recorded stage.')}</div><div className="mt-3 truncate font-mono text-[10px] text-accent">{checkpoint.head_sha?.slice(0, 12) || 'Uncommitted worktree'}</div></> : <div className="mt-6 text-xs leading-5 text-muted">The first checkpoint appears after the worktree is prepared.</div>}
        </article>
      </section>

      <section ref={splitRef} className="developer-process-split grid min-h-[520px] gap-0 overflow-hidden rounded-md border border-border bg-surface/25 lg:grid-cols-[var(--process-left)_8px_minmax(0,1fr)]" style={{ '--process-left': `${split}%` } as CSSProperties}>
        <article className="min-w-0 p-4 sm:p-5">
          <header className="flex items-center justify-between gap-3"><div><div className="flex items-center gap-2"><TerminalSquare size={15} className="text-accent" /><h3 className="text-sm font-semibold text-text">Live activities</h3></div><p className="mt-1 text-[10px] text-muted">Exact runtime evidence from the selected developer tool.</p></div><span className={`inline-flex items-center gap-1.5 text-[10px] ${streamState === 'live' ? 'text-success' : 'text-warning'}`}><Radio size={12} className={streamState === 'live' && !TERMINAL.has(workflow.state) ? 'animate-pulse' : ''} />{streamState === 'live' ? 'Live' : titleCase(streamState)}</span></header>
          <div ref={activityRef} className="mt-4 h-[420px] overflow-y-auto rounded-md border border-border/70 bg-[rgb(7_10_14/0.72)] p-3 font-mono text-[10px] leading-5">
            {events.length === 0 ? <div className="flex h-full items-center justify-center text-muted">Waiting for worker output...</div> : events.slice(-160).map(event => <div key={event.id} className="grid grid-cols-[64px_minmax(0,1fr)] gap-2 border-b border-white/5 py-1.5 last:border-0"><span className="text-muted/70">{timeLabel(event.created_at)}</span><span className={`${event.event_type.includes('failed') || event.event_type.includes('blocked') ? 'text-danger' : event.event_type.includes('completed') ? 'text-success' : 'text-[#cbd5e1]'}`}><span className="mr-2 text-accent/80">{event.actor}&gt;</span>{eventLine(event)}</span></div>)}
          </div>
        </article>
        <button type="button" onPointerDown={event => { event.preventDefault(); setDragging(true) }} title="Drag to resize Process panels" className="hidden cursor-col-resize items-center justify-center border-x border-border bg-background/60 text-muted hover:bg-accent/10 hover:text-accent lg:flex"><GripVertical size={14} /></button>
        <article className="min-w-0 border-t border-border p-4 sm:p-5 lg:border-l-0 lg:border-t-0">
          <header><div className="flex items-center gap-2"><CheckCircle2 size={15} className="text-accent" /><h3 className="text-sm font-semibold text-text">Sprint</h3></div><p className="mt-1 text-[10px] text-muted">Fixed execution gates. The active gate advances only with durable evidence.</p></header>
          <div className="relative mt-5 pl-1">
            <div className="absolute bottom-5 left-[15px] top-5 w-px bg-border" />
            <div className="developer-sprint-line absolute left-[15px] top-5 w-px bg-accent transition-[height] duration-700" style={{ height: `calc(${stageProgress}% - 20px)` }} />
            <div className="space-y-1">{workflow.stages.map(stage => {
              const current = stage.node_id === workflow.stage || stage.status === 'running'
              const done = stage.status === 'completed'
              const failed = stage.status === 'failed' || stage.status === 'paused'
              return <div key={stage.node_id} className={`relative flex min-h-14 items-center gap-3 rounded-md px-2 py-2 ${current ? 'developer-sprint-current bg-accent/10' : ''}`}><span className={`relative z-[1] flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${done ? 'border-success bg-success text-background' : failed ? 'border-danger bg-danger/10 text-danger' : current ? 'border-accent bg-background text-accent' : 'border-border bg-background text-muted'}`}>{done ? <Check size={13} /> : failed ? <XCircle size={13} /> : current ? <span className="h-2 w-2 rounded-full bg-accent" /> : <Circle size={12} />}</span><div className="min-w-0 flex-1"><div className={`truncate text-xs font-medium ${current ? 'text-accent' : 'text-text'}`}>{stage.node_id === 'code' ? 'Run selected developer agent' : stage.title}</div><div className="mt-0.5 text-[9px] uppercase text-muted">{current ? 'In progress' : done ? 'Evidence saved' : titleCase(stage.status)}</div></div></div>
            })}</div>
          </div>
        </article>
      </section>

      {autoQueue && nextItem && <NextItem item={nextItem} />}
    </div>
  )
}

function NextItem({ item }: { item: DeveloperQueueItem }) {
  const criteria = safeJsonList(item.acceptance_criteria_json)
  return <details className="group rounded-md border border-border bg-surface/35">
    <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3.5"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent/10 text-xs font-semibold text-accent">#{item.queue_id}</span><span className="min-w-0 flex-1"><span className="block text-[10px] font-semibold uppercase text-muted">Next in queue</span><span className="mt-0.5 block truncate text-sm font-medium text-text">{item.title}</span></span><ChevronDown size={15} className="text-muted transition-transform group-open:rotate-180" /></summary>
    <div className="border-t border-border px-4 py-4 text-xs leading-5 text-muted"><div className="grid gap-3 sm:grid-cols-3"><div><span className="text-text">Status:</span> {item.queue_status || titleCase(item.status)}</div><div><span className="text-text">Effort:</span> {item.queue_effort || 'Not estimated'}</div><div><span className="text-text">Plan:</span> {item.plan_path}</div></div>{criteria.length > 0 && <ul className="mt-4 space-y-1">{criteria.slice(0, 5).map(value => <li key={value}>- {value}</li>)}</ul>}</div>
  </details>
}
