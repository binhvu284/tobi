import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import {
  AlertTriangle, ArrowDown, BadgeCheck, Check, CheckCheck, CheckCircle2, ChevronDown, Circle, Clock3, Copy,
  GitBranch, Github, GripVertical, LoaderCircle, Package, Pause, Play, Radio, ShieldAlert, Square, TerminalSquare, Trash2, XCircle,
} from 'lucide-react'
import LlmLogo from '../LlmLogo'
import AutoQueueToggle from './AutoQueueToggle'
import { getDeveloperChanges, type DeveloperChanges, type DeveloperEvent, type DeveloperQueueItem, type DeveloperWorkerProfile, type DeveloperWorkflow } from '../../api.developer'

import { effectiveStages, TERMINAL_STATES, permittedStages, stateKind } from '../../developer.states'

type WorkflowCommand = 'pause' | 'resume' | 'cancel' | 'retry' | 'remove' | 'sync_delivery' | 'reconcile_base'
type ApprovalPurpose = 'special_paths' | 'merge_deploy'
type ProcessTone = 'cooking' | 'paused' | 'completed' | 'merged' | 'canceled' | 'crashed' | 'waiting' | 'local'

type Props = {
  workflow: DeveloperWorkflow | null
  events: DeveloperEvent[]
  workers: DeveloperWorkerProfile[]
  queue: DeveloperQueueItem[]
  /** Reviewed policy capabilities. Decides which gates this run was ever allowed to reach,
   *  so the rail can separate "not done" from "not permitted". */
  capabilities?: Record<string, boolean>
  busy: boolean
  autoQueue: boolean
  autoQueueBusy?: boolean
  streamState: 'idle' | 'connecting' | 'live' | 'reconnecting' | 'closed'
  streamIssue: string | null
  onAutoQueue: (enabled: boolean) => void
  onCommand: (command: WorkflowCommand) => void
  onApprove: (purpose: ApprovalPurpose, master: string) => void
  onReject: (purpose: ApprovalPurpose) => void
}

// Generated from core/coding_states.py. This used to be a hand-written copy, and a state
// missing from it did not degrade gracefully: the run read as active forever, so the card
// animated, the stop control stayed armed, and the gate it stopped at showed "In progress".
const TERMINAL = TERMINAL_STATES

function titleCase(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

// The two states this card distinguishes by name rather than by kind: both are successes,
// but one shipped and one stopped at a gate the policy forbids, and the owner needs to see
// the difference. Everything else is classified by the shared kind, so a state added to
// core/coding_states.py can never again fall through to "still running".
const TONE_BY_STATE: Partial<Record<string, ProcessTone>> = {
  completed: 'completed',
  merged: 'merged',
  locally_complete: 'local',
  canceled: 'canceled',
}
const TONE_BY_KIND: Record<string, ProcessTone> = {
  active: 'cooking', success: 'completed', fault: 'crashed', waiting: 'paused', idle: 'canceled',
}

function processTone(workflow: DeveloperWorkflow): ProcessTone {
  const named = TONE_BY_STATE[workflow.state]
  if (named) return named
  if (workflow.state === 'awaiting_merge_deploy_approval' || workflow.state === 'awaiting_owner_merge' || workflow.error_code === 'special_approval_required') return 'waiting'
  // A pause carrying an error code is a fault the owner must act on; a bare pause is theirs.
  if (workflow.state === 'paused' || workflow.state === 'blocked') return workflow.error_code && workflow.error_code !== 'owner_paused' ? 'crashed' : 'paused'
  return TONE_BY_KIND[stateKind(workflow.state)] ?? 'cooking'
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
  merged: {
    label: 'Merged', bar: 'bg-success', text: 'text-success', border: 'developer-process-completed border-success/40',
  },
  local: {
    label: 'Locally Complete', bar: 'bg-success', text: 'text-success', border: 'developer-process-completed border-success/40',
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

function elapsedLabel(totalSeconds: number) {
  const value = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  const seconds = value % 60
  return [hours, minutes, seconds].map(part => String(part).padStart(2, '0')).join(':')
}

function ActiveTime({ workflow }: { workflow: DeveloperWorkflow }) {
  const timerStart = workflow.active_timer_started_at
  const running = stateKind(workflow.state) === 'active' && Boolean(timerStart)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    setNow(Date.now())
    if (!running) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [running, timerStart, workflow.id])

  const started = timerStart ? new Date(timerStart).valueOf() : Number.NaN
  const liveSeconds = running && Number.isFinite(started)
    ? Math.max(0, Math.floor((now - started) / 1000))
    : 0
  const elapsed = Number(workflow.active_seconds || 0) + liveSeconds

  return (
    <div
      className="flex items-center gap-2"
      title="Active implementation time. Paused and waiting time is excluded."
    >
      <span className={`flex h-8 w-8 items-center justify-center rounded-md border ${running ? 'border-warning/35 bg-warning/10 text-warning' : 'border-border bg-background/55 text-muted'}`}>
        <Clock3 size={13} className={running ? 'animate-pulse' : ''} />
      </span>
      <div>
        <div className="text-[9px] text-muted">Active time</div>
        <div className="mt-0.5 font-mono text-[11px] font-medium tabular-nums text-text">
          {elapsedLabel(elapsed)}
        </div>
      </div>
    </div>
  )
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

function changedPath(entry: DeveloperChanges['files'][number]) {
  return typeof entry === 'string' ? entry : String(entry.path ?? '')
}

/** Where a finished run's work actually is, and how to get at it.
 *
 *  Until this existed a locally-complete run left its branch inside .tobi/developer/worktrees
 *  with nothing in Mission Control pointing at it, so "complete" was not something the owner
 *  could act on. Progress is gated on the same signal that fills this panel: a run is only
 *  100% once there is a result here to open. */
function DeliverySection({ workflow, busy, onCommand }: {
  workflow: DeveloperWorkflow
  busy: boolean
  onCommand: (command: WorkflowCommand) => void
}) {
  const delivery = workflow.delivery
  const [changes, setChanges] = useState<DeveloperChanges | null>(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!delivery?.reachable) return
    const controller = new AbortController()
    setLoading(true); setFailed(false)
    getDeveloperChanges(workflow.id, controller.signal)
      .then(result => { if (!controller.signal.aborted) setChanges(result) })
      .catch(() => { if (!controller.signal.aborted) setFailed(true) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [workflow.id, delivery?.reachable])

  if (!delivery?.reachable) return null
  const checkout = `git checkout ${delivery.branch ?? ''}`
  const files = changes?.files ?? []
  const copyCheckout = () => {
    void navigator.clipboard.writeText(checkout).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <section className="overflow-hidden rounded-md border border-success/35 bg-success/[0.03]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-success/20 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2">
          <Package size={14} className="text-success" />
          <h3 className="text-xs font-semibold text-text">Delivery</h3>
          <span className="text-[10px] text-muted">
            {delivery.kind === 'pull_request'
              ? delivery.merged
                ? 'Merged on GitHub'
                : delivery.draft
                  ? 'Draft waiting on GitHub'
                  : 'Pull request waiting on GitHub'
              : 'Committed on this machine'}
          </span>
        </div>
        {delivery.kind === 'pull_request' && delivery.url
          ? <div className="flex items-center gap-2">
              {delivery.allowed_actions?.includes('sync_delivery') && <button type="button" disabled={busy} onClick={() => onCommand('sync_delivery')} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-[10px] font-medium text-text hover:border-accent/40 disabled:opacity-45"><Radio size={12} /> Sync status</button>}
              <a href={delivery.url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-md border border-success/35 px-2.5 text-[10px] font-medium text-success hover:bg-success/10"><Github size={13} /> Open pull request</a>
            </div>
          : <button type="button" onClick={copyCheckout} className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-[10px] font-medium transition-colors ${copied ? 'border-success/45 bg-success/10 text-success' : 'border-border text-muted hover:border-success/35 hover:text-text'}`}>{copied ? <CheckCheck size={12} /> : <Copy size={12} />}{copied ? 'Copied' : 'Copy checkout'}</button>}
      </header>
      <div className="grid gap-4 px-4 py-4 sm:px-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="min-w-0 space-y-3">
          <div><div className="text-[9px] uppercase text-muted">Branch</div><div className="mt-1 break-all font-mono text-[10px] text-text">{delivery.branch || 'unknown'}</div></div>
          <div><div className="text-[9px] uppercase text-muted">Commit</div><div className="mt-1 font-mono text-[10px] text-accent">{delivery.head_sha?.slice(0, 12) || 'unknown'}</div></div>
          {delivery.kind === 'pull_request' && <div className="flex flex-wrap gap-1.5">
            <span className="rounded border border-border px-1.5 py-0.5 text-[9px] text-muted">{titleCase(delivery.state || 'open')}</span>
            <span className="rounded border border-border px-1.5 py-0.5 text-[9px] text-muted">CI {titleCase(delivery.ci_state || 'unknown')}</span>
            <span className="rounded border border-border px-1.5 py-0.5 text-[9px] text-muted">{titleCase(delivery.conflict_state || 'unknown')}</span>
          </div>}
          {changes?.stat && <div><div className="text-[9px] uppercase text-muted">Diff</div><div className="mt-1 font-mono text-[10px] text-muted">{changes.stat.trim().split('\n').slice(-1)[0]}</div></div>}
        </div>
        <div className="min-w-0">
          <div className="text-[9px] uppercase text-muted">Changed files{files.length ? ` (${files.length})` : ''}</div>
          {loading ? <div className="mt-2 flex items-center gap-2 text-[10px] text-muted"><LoaderCircle size={12} className="animate-spin" /> Reading the worktree...</div>
            : failed ? <p className="mt-2 text-[10px] leading-5 text-muted">The diff is unavailable -- the worktree may have been reclaimed. The commit itself is still on the branch above.</p>
            : !files.length ? <p className="mt-2 text-[10px] text-muted">No file-level detail was recorded for this run.</p>
            : <ul className="mt-2 max-h-32 space-y-0.5 overflow-y-auto pr-1">{files.slice(0, 40).map((entry, index) => <li key={`${changedPath(entry)}-${index}`} className="truncate font-mono text-[10px] text-text">{changedPath(entry)}</li>)}</ul>}
        </div>
      </div>
    </section>
  )
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

function ProcessActions({ workflow, busy, onCommand }: {
  workflow: DeveloperWorkflow; busy: boolean; onCommand: (command: WorkflowCommand) => void
}) {
  const tone = processTone(workflow)
  const active = !TERMINAL.has(workflow.state)
  const retryBlocked = ['repeated_failure', 'validation_infrastructure_failed'].includes(workflow.error_code || '')
  const resumable = ['paused', 'blocked', 'failed'].includes(workflow.state) && !retryBlocked
  const awaitingOwnerMerge = workflow.state === 'awaiting_owner_merge'
  const drifted = workflow.error_code === 'main_drift'
  return (
    <div className="flex flex-wrap justify-end gap-1.5">
      {awaitingOwnerMerge && <button disabled={busy} onClick={() => onCommand('sync_delivery')} className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-2.5 text-[10px] font-semibold text-background disabled:opacity-45"><Radio size={13} /> Sync status</button>}
      {drifted && <button disabled={busy} onClick={() => onCommand('reconcile_base')} className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-2.5 text-[10px] font-semibold text-background disabled:opacity-45"><GitBranch size={13} /> Reconcile base</button>}
      {resumable && !drifted && <button disabled={busy} onClick={() => onCommand(workflow.error_code ? 'retry' : 'resume')} className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-2.5 text-[10px] font-semibold text-background disabled:opacity-45"><Play size={13} />{workflow.error_code ? 'Retry' : 'Resume'}</button>}
      {active && !resumable && !awaitingOwnerMerge && workflow.state !== 'awaiting_merge_deploy_approval' && <button disabled={busy} onClick={() => onCommand('pause')} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-[10px] font-medium text-text hover:bg-overlay/5 disabled:opacity-45"><Pause size={13} /> Pause</button>}
      {active && <button disabled={busy} onClick={() => onCommand('cancel')} title="Cancel process" className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-danger/30 text-danger hover:bg-danger/5 disabled:opacity-45"><Square size={12} /></button>}
      {(tone === 'canceled' || tone === 'completed' || tone === 'merged' || tone === 'local') && <button disabled={busy} onClick={() => onCommand('remove')} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-[10px] font-medium text-muted hover:border-danger/35 hover:text-danger disabled:opacity-45"><Trash2 size={13} /> Remove</button>}
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
  workflow, events, workers, queue, capabilities, busy, autoQueue, autoQueueBusy, streamState, streamIssue,
  onAutoQueue, onCommand, onApprove, onReject,
}: Props) {
  const [split, setSplit] = useState(58)
  const [dragging, setDragging] = useState(false)
  const [logCopied, setLogCopied] = useState(false)
  const [followActivity, setFollowActivity] = useState(true)
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

  const scrollActivityToLatest = (behavior: ScrollBehavior = 'smooth') => {
    const panel = activityRef.current
    if (!panel) return
    panel.scrollTo({ top: panel.scrollHeight, behavior })
    setFollowActivity(true)
  }

  useEffect(() => {
    setFollowActivity(true)
    const frame = window.requestAnimationFrame(() => scrollActivityToLatest('auto'))
    return () => window.cancelAnimationFrame(frame)
  }, [workflow?.id])

  useEffect(() => {
    if (!followActivity) return
    const frame = window.requestAnimationFrame(() => scrollActivityToLatest('auto'))
    return () => window.cancelAnimationFrame(frame)
  }, [events.length, followActivity])

  useEffect(() => {
    if (!logCopied) return
    const timer = window.setTimeout(() => setLogCopied(false), 1800)
    return () => window.clearTimeout(timer)
  }, [logCopied])

  const copyProcessLog = async () => {
    if (!events.length) return
    const log = events.map(event => `[${timeLabel(event.created_at)}] ${event.actor}> ${eventLine(event)}`).join('\n')
    try {
      await navigator.clipboard.writeText(log)
      setLogCopied(true)
    } catch {
      const field = document.createElement('textarea')
      field.value = log
      field.style.position = 'fixed'
      field.style.opacity = '0'
      document.body.appendChild(field)
      field.select()
      const copied = document.execCommand('copy')
      field.remove()
      if (copied) setLogCopied(true)
    }
  }

  const nextItem = useMemo(() => nextEligibleItem(queue, workflow?.queue_id), [queue, workflow?.queue_id])

  if (!workflow) return (
    <div className="space-y-5">
      <section className="rounded-md border border-border bg-surface/45 px-5 py-8">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div><div className="text-[10px] font-semibold uppercase text-accent">Process runtime</div><h2 className="mt-2 text-lg font-semibold text-text">No development process is active</h2><p className="mt-1 max-w-2xl text-xs leading-5 text-muted">Start an item from Queue, or enable Auto to take the next eligible planned item.</p></div>
          <AutoQueueToggle enabled={autoQueue} busy={autoQueueBusy} onChange={onAutoQueue} />
        </div>
      </section>
      {autoQueue && <NextQueueSection item={nextItem} />}
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
  // Gates this policy allows. A gate outside this set was never attempted, so it is neither
  // pending nor failed -- reporting it either way misdescribes a clean run.
  const permittedGates = useMemo(() => new Set(permittedStages(capabilities)), [capabilities])
  const stageStatuses = useMemo(
    () => Object.fromEntries(workflow.stages.map(stage => [stage.node_id, stage.status])),
    [workflow.stages],
  )
  const effectiveGates = useMemo(
    () => new Set(effectiveStages(stageStatuses, capabilities)),
    [stageStatuses, capabilities],
  )
  const activeStageIndex = Math.max(0, workflow.stages.findIndex(stage => stage.node_id === workflow.stage || stage.status === 'running'))
  const lastCompletedIndex = workflow.stages.reduce((last, stage, index) => stage.status === 'completed' ? index : last, 0)
  const progressStageIndex = TERMINAL.has(workflow.state) ? lastCompletedIndex : activeStageIndex
  const stageProgress = workflow.stages.length > 1 ? Math.min(100, (progressStageIndex / (workflow.stages.length - 1)) * 100) : 0

  return (
    <div className="space-y-5">
      <section className={`overflow-hidden rounded-md border bg-surface/45 ${visual.border}`}>
        <div className="flex flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:justify-between sm:px-5">
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-2 text-[9px] font-medium uppercase text-muted">
              <span>Item #{workflow.queue_id}</span><span className="text-border">/</span>
              <span className={`inline-flex items-center gap-1.5 ${visual.text}`}><span className={`h-1.5 w-1.5 rounded-full ${visual.bar}`} />{visual.label}{currentTone === 'cooking' && <span className="developer-process-skeleton" aria-label="Active process"><i /><i /><i /></span>}</span>
              {currentTone === 'cooking' && <><span className="text-border">/</span><span className="flex min-w-0 max-w-[min(44vw,620px)] items-center gap-1.5 normal-case text-muted"><TerminalSquare size={10} className="shrink-0 text-warning" /><span className="truncate font-mono">{activity}</span><span className="developer-terminal-caret h-[9px]" /></span></>}
            </div>
            <h2 className="mt-1.5 truncate text-base font-semibold text-text">{workflow.title}</h2>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3 lg:justify-end">
            <ActiveTime workflow={workflow} />
            <span className="hidden h-8 w-px bg-border lg:block" />
            <AgentIdentity workflow={workflow} workers={workers} />
            <span className="hidden h-8 w-px bg-border lg:block" />
            <AutoQueueToggle enabled={autoQueue} busy={autoQueueBusy} onChange={onAutoQueue} />
            <ProcessActions workflow={workflow} busy={busy} onCommand={onCommand} />
          </div>
        </div>
        <div className="grid border-t border-border/70 md:grid-cols-[minmax(0,1fr)_280px]">
          <div className="px-4 py-3 sm:px-5">
            <div className="flex items-center justify-between gap-3 text-[9px] text-muted"><span>Progress</span><span className="font-medium text-text">{workflow.progress}%</span></div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-background"><div className={`h-full rounded-full transition-[width] duration-700 ${visual.bar} ${currentTone === 'cooking' ? 'developer-process-bar' : ''}`} style={{ width: `${Math.max(2, workflow.progress)}%` }} /></div>
          </div>
          <div className="border-t border-border/70 px-4 py-3 md:border-l md:border-t-0 sm:px-5">
            <div className="text-[9px] text-muted">Current sprint</div>
            <div className="mt-1 truncate text-[11px] font-medium text-text">{TERMINAL.has(workflow.state) ? `Stopped at ${titleCase(workflow.stage)}` : workflow.sprint?.title || titleCase(workflow.stage)}</div>
          </div>
        </div>
        {currentTone === 'crashed' && <div className="flex items-start gap-2 border-t border-danger/25 bg-danger/5 px-4 py-3 text-[10px] leading-5 text-danger sm:px-5"><AlertTriangle size={13} className="mt-0.5 shrink-0" /><div><span className="font-semibold">{titleCase(workflow.error_code || 'workflow_failed')}:</span> <span className="text-muted">{workflow.blocker || streamIssue || 'Open Live activities for the latest failure evidence.'}</span></div></div>}
        {currentTone === 'local' && <div className="flex items-start gap-2 border-t border-success/25 bg-success/5 px-4 py-3 text-[10px] leading-5 text-success sm:px-5"><BadgeCheck size={13} className="mt-0.5 shrink-0" /><div><span className="font-semibold">Finished locally:</span> <span className="text-muted">{workflow.blocker || 'Every stage the reviewed policy permits has passed. The branch is committed but nothing has left this machine.'}</span></div></div>}
        {currentTone === 'merged' && <div className="flex items-start gap-2 border-t border-success/25 bg-success/5 px-4 py-3 text-[10px] leading-5 text-success sm:px-5"><BadgeCheck size={13} className="mt-0.5 shrink-0" /><div><span className="font-semibold">Merged:</span> <span className="text-muted">{workflow.blocker || 'Deployment was skipped by reviewed policy.'}</span></div></div>}
        {!TERMINAL.has(workflow.state) && !workflow.delivery?.reachable && <div className="border-t border-border/70 px-4 py-2 text-[9px] leading-4 text-muted sm:px-5">Progress counts the {effectiveGates.size} gates this run can satisfy. It reaches 100% once there is a result you can open.</div>}
      </section>

      <ApprovalCard workflow={workflow} busy={busy} onApprove={onApprove} onReject={onReject} onCommand={onCommand} />

      <DeliverySection workflow={workflow} busy={busy} onCommand={onCommand} />

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
          <header className="flex h-12 items-center justify-between gap-3 border-b border-border/70 px-4"><div className="flex items-center gap-2"><TerminalSquare size={14} className="text-accent" /><h3 className="text-xs font-semibold text-text">Live activities</h3></div><div className="flex items-center gap-2"><span className={`inline-flex items-center gap-1.5 text-[9px] ${streamState === 'live' ? 'text-success' : TERMINAL.has(workflow.state) ? 'text-muted' : 'text-warning'}`}><Radio size={11} className={streamState === 'live' && !TERMINAL.has(workflow.state) ? 'animate-pulse' : ''} />{TERMINAL.has(workflow.state) ? 'Closed' : streamState === 'live' ? 'Live' : titleCase(streamState)}</span><button type="button" disabled={!events.length} onClick={copyProcessLog} title="Copy the complete process log" className={`inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-[9px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${logCopied ? 'border-success/35 bg-success/5 text-success' : 'border-border text-muted hover:border-accent/35 hover:text-text'}`}>{logCopied ? <CheckCheck size={11} /> : <Copy size={11} />}{logCopied ? 'Copied' : 'Copy log'}</button></div></header>
          <div className="relative">
            <div
              ref={activityRef}
              onScroll={event => {
                const panel = event.currentTarget
                setFollowActivity(panel.scrollHeight - panel.scrollTop - panel.clientHeight < 48)
              }}
              className="h-[380px] overflow-y-auto bg-[rgb(7_10_14/0.68)] px-4 py-3 font-mono text-[9px] leading-5"
            >
              {events.length === 0 ? <div className="flex h-full items-center justify-center text-muted">Waiting for worker output...</div> : events.slice(-160).map(event => <div key={event.id} className="grid grid-cols-[58px_minmax(0,1fr)] gap-2 border-b border-white/5 py-1 last:border-0"><span className="text-muted/60">{timeLabel(event.created_at)}</span><span className={`${event.event_type.includes('failed') || event.event_type.includes('blocked') ? 'text-danger' : event.event_type.includes('completed') ? 'text-success' : 'text-[#cbd5e1]'}`}><span className="mr-2 text-accent/75">{event.actor}&gt;</span>{eventLine(event)}</span></div>)}
            </div>
            {!followActivity && events.length > 0 && (
              <button
                type="button"
                onClick={() => scrollActivityToLatest()}
                className="absolute bottom-3 right-3 inline-flex h-8 items-center gap-1.5 rounded-md border border-accent/35 bg-background/95 px-2.5 text-[9px] font-semibold text-accent shadow-lg shadow-black/30 backdrop-blur hover:border-accent hover:bg-accent/10"
                title="Move to the newest activity"
              >
                <ArrowDown size={12} /> Latest
              </button>
            )}
          </div>
        </article>
        <button type="button" onPointerDown={event => { event.preventDefault(); setDragging(true) }} title="Drag to resize Process panels" className="hidden cursor-col-resize items-center justify-center border-x border-border/70 bg-background/50 text-muted/50 hover:bg-accent/10 hover:text-accent lg:flex"><GripVertical size={12} /></button>
        <article className="min-w-0 border-t border-border lg:border-t-0">
          <header className="flex h-12 items-center justify-between gap-3 border-b border-border/70 px-4"><div className="flex items-center gap-2"><CheckCircle2 size={14} className="text-accent" /><h3 className="text-xs font-semibold text-text">Sprint</h3></div><span className="text-[9px] text-muted">{workflow.stages.filter(stage => stage.status === 'completed' && effectiveGates.has(stage.node_id)).length}/{effectiveGates.size} gates{workflow.stages.length > effectiveGates.size && <span className="text-muted/60"> · {workflow.stages.length - effectiveGates.size} not permitted</span>}</span></header>
          <div className="relative h-[380px] overflow-y-auto px-4 py-3">
            <div className="absolute bottom-5 left-[34px] top-5 w-px bg-border" />
            <div className="developer-sprint-line absolute left-[34px] top-5 w-px bg-accent transition-[height] duration-700" style={{ height: stageProgress > 0 ? `calc(${stageProgress}% - 8px)` : 0 }} />
            <div className="space-y-1">{workflow.stages.map(stage => {
              const running = stateKind(workflow.state) === 'active'
              const current = running && (stage.node_id === workflow.stage || stage.status === 'running')
              const waiting = stateKind(workflow.state) === 'waiting' && stage.node_id === workflow.stage
              const done = stage.status === 'completed'
              // A locally-complete run stopped at a gate the reviewed policy does not permit.
              // Those gates were never attempted, so they are not failures.
              const unreachable = !done && !permittedGates.has(stage.node_id)
              const failed = !unreachable && (stage.status === 'failed' || stage.status === 'paused')
              return <div key={stage.node_id} className={`relative flex min-h-10 items-center gap-3 overflow-hidden rounded-md px-1.5 py-1.5 ${current ? 'developer-sprint-current' : waiting ? 'bg-warning/[0.04]' : ''}`}><span className={`relative z-[2] flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${done ? 'developer-sprint-complete-marker border-success/45 bg-success/10 text-success' : failed ? 'border-danger bg-danger/10 text-danger' : current ? 'developer-sprint-active-marker border-accent bg-background text-accent' : waiting ? 'border-warning/50 bg-background text-warning' : 'border-border bg-background text-muted'}`}>{done ? <BadgeCheck size={15} strokeWidth={2.25} /> : failed ? <XCircle size={11} /> : current ? <LoaderCircle size={13} className="animate-spin" /> : waiting ? <Clock3 size={11} /> : <Circle size={10} />}</span><div className="relative z-[1] min-w-0 flex-1"><div className={`truncate text-[10px] font-medium ${current ? 'text-accent' : waiting ? 'text-warning' : done ? 'text-text' : 'text-muted'}`}>{stage.node_id === 'code' ? 'Run selected developer agent' : stage.title}</div><div className="mt-0.5 text-[8px] uppercase text-muted/70">{current ? 'In progress' : waiting ? 'Waiting for owner' : done ? 'Evidence saved' : unreachable ? 'Not permitted by policy' : failed ? titleCase(stage.status) : 'Pending'}</div></div></div>
            })}</div>
          </div>
        </article>
      </section>

      {autoQueue && <NextQueueSection item={nextItem} />}
    </div>
  )
}

function NextQueueSection({ item }: { item: DeveloperQueueItem | null }) {
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
        <span className="inline-flex h-6 items-center rounded-md border border-success/30 bg-success/5 px-2 text-[9px] font-medium text-success">Auto ready</span>
      </div>
    </div>
    {item ? <details className="group border-t border-border/70">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-2.5 text-[10px] text-muted hover:bg-overlay/5 sm:px-5"><span>This item starts after the current process finishes.</span><span className="inline-flex shrink-0 items-center gap-1.5 text-accent">View scope <ChevronDown size={13} className="transition-transform group-open:rotate-180" /></span></summary>
      <div className="border-t border-border/70 px-4 py-3 text-[10px] leading-5 text-muted sm:px-5"><div className="grid gap-2 sm:grid-cols-3"><div><span className="text-text">Status:</span> {item.queue_status || titleCase(item.status)}</div><div><span className="text-text">Effort:</span> {item.queue_effort || 'Not estimated'}</div><div className="truncate"><span className="text-text">Plan:</span> {item.plan_path}</div></div>{criteria.length > 0 && <ul className="mt-3 grid gap-x-5 gap-y-1 sm:grid-cols-2">{criteria.slice(0, 6).map(value => <li key={value} className="flex items-start gap-1.5"><Check size={10} className="mt-1 shrink-0 text-success" /><span>{value}</span></li>)}</ul>}</div>
    </details> : <div className="border-t border-border/70 px-4 py-3 text-[10px] leading-5 text-muted sm:px-5">The queue is empty, or its planned items are waiting for dependencies. Review the Queue tab to choose the next runnable item.</div>}
  </section>
}
