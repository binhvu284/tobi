import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, Archive, BookOpen, CheckCircle2, Circle, Clock3, Code2, Download, ExternalLink,
  ChevronDown, ChevronUp, GitBranch, Github, HardDrive, KeyRound, ListTree, Loader2, MoreHorizontal, Pause, Play, Plus, Radio, RefreshCw,
  RotateCcw, Save, ScrollText, ShieldCheck, Square, Target,
  TerminalSquare, TestTube2, Trash2, Upload, WifiOff, Wrench, XCircle,
} from 'lucide-react'
import AmbientField from '../components/motion/AmbientField'
import LlmLogo, { BRAND_META, brandForModel, brandForProvider } from '../components/LlmLogo'
import ModelMenu from '../components/chat/ModelMenu'
import DeveloperAgents from '../components/developer/DeveloperAgents'
import DeveloperProcess from '../components/developer/DeveloperProcess'
import DeveloperQueue from '../components/developer/DeveloperQueue'
import DevelopmentGoals, { type GoalCommand } from '../components/developer/DevelopmentGoals'
import VaultUnlockPanel from '../components/VaultUnlockPanel'
import { useToast } from '../context/ToastProvider'
import { useVaultSession } from '../hooks/useVaultSession'
import {
  approveDeveloperWorkflow, assessDeveloperGoal, commandDeveloperGoal, commandDeveloperWorkflow, createDeveloperGoal,
  getDeveloperLearning, getDeveloperOverview, getDeveloperQueue, getDeveloperStorage, getDeveloperVersions,
  getDeveloperGoals, getDeveloperWorkerLogin, getDeveloperWorkerModels, getDeveloperWorkers, probeDeveloperWorker, replayDeveloperLearning,
  saveDeveloperWorker, startDeveloperWorkflow, streamDeveloperEvents, switchDeveloperWorker, cleanupDeveloperStorage,
  rejectDeveloperWorkflow, setDeveloperProcessSettings,
  type AvailableModel, type DeveloperAssessment, type DeveloperEvent, type DeveloperOverview, type DeveloperGoal,
  type DeveloperQueueItem, type DeveloperQueueState, type DeveloperRelease, type DeveloperStorage, type DeveloperWorkerLogin,
  type DeveloperWorkerModels, type DeveloperWorkerProfile,
  type DeveloperWorkflow, type LlmProvider,
} from '../api'

type Tab = 'overview' | 'goals' | 'loop' | 'workers' | 'data' | 'queue' | 'versions'
type DeveloperLoadError = { message: string; status?: number; code?: string }
type DeveloperStreamState = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'closed'
type LiveEventKind = 'stage' | 'tool' | 'worker' | 'checkpoint' | 'success' | 'problem' | 'system'
type LiveEventPresentation = { title: string; detail?: string; kind: LiveEventKind }

const LOAD_TIMEOUT_MS = 15_000
const TERMINAL_STATES = new Set(['completed', 'canceled', 'failed', 'rolled_back'])
const STREAM_REFRESH_EVENTS = new Set([
  'checkpoint_created', 'quality_gate_completed', 'worker_switched',
  'workflow_blocked', 'workflow_completed', 'workflow_paused',
])
const STATE_TONE: Record<string, string> = {
  completed: 'text-success border-success/30 bg-success/10',
  released: 'text-success border-success/30 bg-success/10',
  coding: 'text-accent border-accent/30 bg-accent/10',
  validating: 'text-accent border-accent/30 bg-accent/10',
  reviewing: 'text-accent border-accent/30 bg-accent/10',
  preparing: 'text-accent border-accent/30 bg-accent/10',
  awaiting_merge_deploy_approval: 'text-warning border-warning/30 bg-warning/10',
  paused: 'text-warning border-warning/30 bg-warning/10',
  blocked: 'text-warning border-warning/30 bg-warning/10',
  failed: 'text-danger border-danger/30 bg-danger/10',
  canceled: 'text-muted border-border bg-overlay/5',
}

function tone(state: string) {
  return STATE_TONE[state] ?? 'text-muted border-border bg-overlay/5'
}

function label(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char: string) => char.toUpperCase())
}

function stageLabel(value: unknown) {
  const stage = typeof value === 'string' ? value : ''
  return stage === 'code' ? 'Run selected coding worker' : label(stage || 'workflow')
}

function textValue(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function compactText(value: unknown, max = 180): string | null {
  const text = textValue(value)?.replace(/\s+/g, ' ')
  if (!text) return null
  return text.length > max ? `${text.slice(0, max - 1)}...` : text
}

function readablePayloadText(payload: Record<string, unknown>): string | null {
  for (const key of ['message', 'summary', 'text', 'detail', 'action_needed', 'action']) {
    const text = compactText(payload[key])
    if (text) return text
  }
  for (const key of ['item', 'content', 'result', 'error']) {
    const nested = objectValue(payload[key])
    if (!nested) continue
    for (const nestedKey of ['message', 'summary', 'text', 'detail', 'command', 'output']) {
      const value = nested[nestedKey]
      const text = Array.isArray(value) ? compactText(value.join(' ')) : compactText(value)
      if (text) return text
    }
  }
  return null
}

function eventPresentation(event: DeveloperEvent): LiveEventPresentation {
  const payload = event.payload ?? {}
  const stage = stageLabel(payload.stage)
  const path = compactText(payload.path, 120)
  const count = textValue(payload.count)
  const eventType = textValue(payload.type)
  const item = objectValue(payload.item)
  const itemType = textValue(item?.type)
  const itemText = item ? readablePayloadText(item) : null

  switch (event.event_type) {
    case 'stage_started':
      return { title: `Started ${stage}`, detail: `Attempt ${textValue(payload.attempt) ?? '1'}`, kind: 'stage' }
    case 'stage_completed':
      return { title: `Completed ${stage}`, detail: readablePayloadText(payload) ?? undefined, kind: 'success' }
    case 'stage_failed':
      return { title: `${stage} failed`, detail: readablePayloadText(payload) ?? 'Review the failed check evidence.', kind: 'problem' }
    case 'worker_model_action': {
      const action = textValue(payload.action) ?? 'next action'
      const actions: Record<string, string> = {
        complete: 'Worker is finishing the sprint',
        blocker: 'Worker reported a blocker',
        list_files: 'Inspecting repository files',
        read_file: 'Reading a source file',
        replace_text: 'Applying a targeted edit',
        run_check: 'Preparing a validation check',
        search: 'Searching the codebase',
        write_file: 'Writing a source file',
      }
      return {
        title: actions[action] ?? `Worker selected ${label(action)}`,
        detail: `Model step ${textValue(payload.step) ?? '?'}`,
        kind: action === 'blocker' ? 'problem' : 'worker',
      }
    }
    case 'worker_tool_read':
      return { title: path ? `Read ${path}` : 'Read a source file', detail: payload.bytes ? `${payload.bytes} bytes` : undefined, kind: 'tool' }
    case 'worker_tool_list':
      return { title: 'Inspected repository files', detail: `${count ?? '0'} files${payload.prefix ? ` under ${payload.prefix}` : ''}`, kind: 'tool' }
    case 'worker_tool_search':
      return { title: `Searched for "${compactText(payload.query, 80) ?? 'code'}"`, detail: `${count ?? '0'} matches`, kind: 'tool' }
    case 'worker_tool_write':
      return { title: path ? `Updated ${path}` : 'Updated a source file', detail: payload.bytes ? `${payload.bytes} bytes written` : undefined, kind: 'tool' }
    case 'worker_tool_check': {
      const argv = Array.isArray(payload.argv) ? payload.argv.join(' ') : compactText(payload.argv)
      const passed = payload.ok === true
      return {
        title: passed ? 'Validation check passed' : 'Validation check failed',
        detail: compactText(argv, 160) ?? `Exit code ${textValue(payload.exit_code) ?? '?'}`,
        kind: passed ? 'success' : 'problem',
      }
    }
    case 'worker_adapter_started':
      return {
        title: `${label(textValue(payload.adapter) ?? 'coding')} worker started`,
        detail: payload.resuming ? 'Continuing the saved worker session.' : 'A new worker session was created.',
        kind: 'worker',
      }
    case 'worker_adapter_event': {
      const command = compactText(item?.command, 160)
      const adapterProblem = [eventType, itemType, textValue(item?.status)]
        .some(value => Boolean(value && /error|fail|blocked|denied/i.test(value)))
      if (itemType === 'command_execution') {
        return {
          title: adapterProblem ? 'Worker command failed' : command ? `Running ${command}` : 'Running a command',
          detail: itemText ?? command ?? undefined,
          kind: adapterProblem ? 'problem' : 'tool',
        }
      }
      if (itemType === 'file_change') {
        return { title: itemText ?? 'Applying file changes', detail: eventType ? label(eventType) : undefined, kind: 'tool' }
      }
      if (itemType === 'agent_message') {
        return { title: itemText ?? 'Worker reported progress', detail: eventType ? label(eventType) : undefined, kind: 'worker' }
      }
      return {
        title: adapterProblem ? 'Worker reported an error' : eventType ? label(eventType) : 'Worker reported progress',
        detail: itemText ?? readablePayloadText(payload) ?? undefined,
        kind: adapterProblem ? 'problem' : 'worker',
      }
    }
    case 'worker_complete':
      return { title: 'Coding worker completed the sprint', detail: readablePayloadText(payload) ?? undefined, kind: 'success' }
    case 'checkpoint_created':
      return {
        title: `Checkpoint ${textValue(payload.sequence) ?? ''} saved`.replace('  ', ' '),
        detail: compactText(payload.next_action) ?? 'The workflow can resume safely from this point.',
        kind: 'checkpoint',
      }
    case 'quality_gate_completed':
      return {
        title: payload.qualified === true ? 'Quality gates passed' : 'Quality gates need attention',
        detail: Array.isArray(payload.failures) ? compactText(payload.failures.join(' ')) ?? undefined : undefined,
        kind: payload.qualified === true ? 'success' : 'problem',
      }
    case 'workflow_paused':
      return { title: 'Workflow paused', detail: readablePayloadText(payload) ?? 'Resume when the required action is complete.', kind: 'problem' }
    case 'workflow_blocked':
      return { title: 'Workflow is blocked', detail: readablePayloadText(payload) ?? 'Owner action is required.', kind: 'problem' }
    case 'workflow_completed':
      return { title: 'Workflow completed', detail: payload.version ? `Version ${payload.version}` : undefined, kind: 'success' }
    case 'worker_switched':
      return { title: `Worker switched to ${textValue(payload.to) ?? 'the selected profile'}`, detail: 'The latest durable checkpoint will be used.', kind: 'system' }
    default:
      return {
        title: label(event.event_type),
        detail: readablePayloadText(payload) ?? undefined,
        kind: event.event_type.includes('fail') || event.event_type.includes('error') ? 'problem' : 'system',
      }
  }
}

function eventKindClasses(kind: LiveEventKind) {
  if (kind === 'problem') return 'border-danger/30 bg-danger/10 text-danger'
  if (kind === 'success') return 'border-success/30 bg-success/10 text-success'
  if (kind === 'tool') return 'border-accent/30 bg-accent/10 text-accent'
  if (kind === 'checkpoint') return 'border-warning/30 bg-warning/10 text-warning'
  return 'border-border bg-overlay/5 text-muted'
}

function LiveEventIcon({ kind, size = 15 }: { kind: LiveEventKind; size?: number }) {
  if (kind === 'problem') return <AlertTriangle size={size} />
  if (kind === 'success') return <CheckCircle2 size={size} />
  if (kind === 'tool') return <Wrench size={size} />
  if (kind === 'checkpoint') return <ScrollText size={size} />
  if (kind === 'stage') return <ListTree size={size} />
  if (kind === 'worker') return <TerminalSquare size={size} />
  return <Activity size={size} />
}

function relativeAge(timestamp: number | null, now: number) {
  if (!timestamp) return 'No update yet'
  const seconds = Math.max(0, Math.floor((now - timestamp) / 1000))
  if (seconds < 2) return 'Just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  return `${Math.floor(minutes / 60)}h ago`
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}

function StateBadge({ state }: { state: string }) {
  return <span className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-medium ${tone(state)}`}>{label(state)}</span>
}

function Empty({ text }: { text: string }) {
  return <div className="border-y border-border/60 py-12 text-center text-sm text-muted">{text}</div>
}

function DeveloperSkeleton() {
  return (
    <main aria-hidden className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6">
      <div className="flex items-end justify-between gap-4">
        <div className="space-y-2">
          <div className="tobi-skel h-5 w-32" />
          <div className="tobi-skel h-3 w-72 max-w-full" />
        </div>
        <div className="tobi-skel h-7 w-20" />
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="flex min-h-20 items-center gap-3 rounded-md bg-surface/60 px-3 py-3">
            <div className="tobi-skel h-9 w-9 shrink-0" />
            <div className="min-w-0 flex-1 space-y-2">
              <div className="tobi-skel h-3 w-3/4" />
              <div className="tobi-skel h-2.5 w-1/2" />
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-lg bg-surface/70 p-5 shadow-[0_18px_60px_rgb(0_0_0/0.12)] sm:p-6">
        <div className="flex items-center gap-3">
          <div className="tobi-skel h-11 w-11 shrink-0" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="tobi-skel h-4 w-40" />
            <div className="tobi-skel h-2.5 w-64 max-w-full" />
          </div>
          <div className="tobi-skel h-8 w-24" />
        </div>
        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <div key={index} className="space-y-2">
              <div className="tobi-skel h-3 w-24" />
              <div className="tobi-skel h-10 w-full" />
            </div>
          ))}
        </div>
        <div className="mt-8 flex justify-end gap-2">
          <div className="tobi-skel h-10 w-28" />
          <div className="tobi-skel h-10 w-36" />
        </div>
      </div>
    </main>
  )
}

function WorkflowActions({ workflow, busy, onCommand }: {
  workflow: DeveloperWorkflow; busy: boolean
  onCommand: (command: 'pause' | 'resume' | 'cancel' | 'retry') => void
}) {
  const active = !TERMINAL_STATES.has(workflow.state)
  const resumable = ['paused', 'blocked', 'failed', 'approved'].includes(workflow.state)
  return (
    <div className="flex flex-wrap gap-2">
      {active && !resumable && (
        <button onClick={() => onCommand('pause')} disabled={busy} title="Pause workflow"
          className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm text-text hover:bg-overlay/5 disabled:opacity-50">
          <Pause size={15} /> Pause
        </button>
      )}
      {resumable && (
        <button onClick={() => onCommand(workflow.error_code ? 'retry' : 'resume')} disabled={busy} title="Resume workflow"
          className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background hover:brightness-110 disabled:opacity-50">
          <Play size={15} /> {workflow.error_code ? 'Retry' : 'Resume'}
        </button>
      )}
      {active && (
        <button onClick={() => onCommand('cancel')} disabled={busy} title="Cancel and retain recovery data"
          className="inline-flex h-9 items-center gap-2 rounded-md border border-danger/40 px-3 text-sm text-danger hover:bg-danger/10 disabled:opacity-50">
          <Square size={14} /> Cancel
        </button>
      )}
      {workflow.pull_request?.url && (
        <a href={workflow.pull_request.url} target="_blank" rel="noreferrer"
          className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm text-text hover:bg-overlay/5">
          <ExternalLink size={15} /> Pull request
        </a>
      )}
    </div>
  )
}

function ApprovalGate({ workflow, busy, onApprove }: {
  workflow: DeveloperWorkflow; busy: boolean
  onApprove: (purpose: 'special_paths' | 'merge_deploy', master: string) => void
}) {
  const required = workflow.state === 'awaiting_merge_deploy_approval'
    ? 'merge_deploy'
    : workflow.error_code === 'special_approval_required' ? 'special_paths' : null
  const [master, setMaster] = useState('')
  if (!required) return null
  return (
    <section className="mt-5 border-l-2 border-warning bg-warning/5 px-4 py-4">
      <div className="flex items-start gap-3">
        <KeyRound size={18} className="mt-0.5 shrink-0 text-warning" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-text">
            {required === 'merge_deploy' ? 'Merge and deployment approval' : 'Protected-path approval'}
          </h3>
          <p className="mt-1 text-xs leading-5 text-muted">
            {required === 'merge_deploy'
              ? `Approve squash merge of ${workflow.branch ?? 'the feature branch'} and immediate deployment with rollback.`
              : 'This workflow touches protected self-development files. Review the scope before allowing it to continue.'}
          </p>
          <div className="mt-3 flex max-w-xl flex-col gap-2 sm:flex-row">
            <input type="password" value={master} onChange={event => setMaster(event.target.value)}
              placeholder="Vault master password" autoComplete="current-password"
              className="h-9 min-w-0 flex-1 rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent" />
            <button disabled={busy || master.length < 6} onClick={() => { onApprove(required, master); setMaster('') }}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-warning px-3 text-sm font-semibold text-background disabled:opacity-40">
              <ShieldCheck size={15} /> Approve
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}

function WorkflowHeader({ workflow, busy, onCommand, onApprove }: {
  workflow: DeveloperWorkflow; busy: boolean
  onCommand: (command: 'pause' | 'resume' | 'cancel' | 'retry') => void
  onApprove: (purpose: 'special_paths' | 'merge_deploy', master: string) => void
}) {
  const stopped = TERMINAL_STATES.has(workflow.state) || ['paused', 'blocked', 'failed', 'awaiting_merge_deploy_approval'].includes(workflow.state)
  const ownerAction = workflow.state === 'awaiting_merge_deploy_approval'
    ? 'Review and approve the merge and deployment gate.'
    : workflow.error_code === 'special_approval_required'
      ? 'Review protected-path access before this run continues.'
      : workflow.blocker
        ? workflow.blocker
        : ['paused', 'blocked', 'failed'].includes(workflow.state)
          ? 'Resume or retry after reviewing the latest evidence.'
          : TERMINAL_STATES.has(workflow.state)
            ? 'No action required. This run has stopped.'
            : 'No action needed. The development agent is working.'
  return (
    <section className="px-4 pt-5 sm:px-6">
      <div className="grid w-full gap-3 xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,0.8fr)]">
        <article className="relative overflow-hidden rounded-lg border border-accent/25 bg-[linear-gradient(125deg,color-mix(in_srgb,rgb(var(--accent))_12%,rgb(var(--surface)))_0%,rgb(var(--surface))_48%,color-mix(in_srgb,rgb(var(--success))_7%,rgb(var(--surface)))_100%)] px-5 py-5 shadow-[0_20px_60px_rgb(0_0_0/0.14)] sm:px-6">
          <div className="absolute inset-y-0 left-0 w-1 bg-accent" />
          <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <StateBadge state={workflow.state} />
                <span className="text-xs text-muted">Queue #{workflow.queue_id}</span>
                {workflow.target_version && <span className="text-xs text-muted">v{workflow.target_version}</span>}
              </div>
              <h2 className="mt-3 text-lg font-semibold text-text sm:text-xl">{workflow.title}</h2>
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
                <span className="inline-flex items-center gap-1.5"><GitBranch size={13} />{workflow.branch ?? 'Branch pending'}</span>
                <span className="inline-flex items-center gap-1.5"><TerminalSquare size={13} />{label(workflow.stage)}</span>
              </div>
            </div>
            <WorkflowActions workflow={workflow} busy={busy} onCommand={onCommand} />
          </div>
          <div className="mt-6 h-2 overflow-hidden rounded-full bg-background/60 shadow-inner">
            <div className={`h-full rounded-full bg-accent transition-[width] duration-500 ${stopped ? '' : 'developer-progress-live'}`} style={{ width: `${Math.max(2, workflow.progress)}%` }} />
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-muted"><span>{workflow.progress}% complete</span><span>{label(workflow.stage)}</span></div>
        </article>

        <article className={`rounded-lg border px-5 py-5 ${stopped && !TERMINAL_STATES.has(workflow.state) ? 'border-warning/35 bg-warning/5' : 'border-border bg-surface/60'}`}>
          <div className="flex items-start gap-3">
            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${stopped && !TERMINAL_STATES.has(workflow.state) ? 'bg-warning/10 text-warning' : 'bg-success/10 text-success'}`}>
              {stopped && !TERMINAL_STATES.has(workflow.state) ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
            </div>
            <div className="min-w-0"><div className="text-[10px] font-semibold uppercase text-muted">Owner action</div><p className="mt-1.5 text-sm leading-6 text-text">{ownerAction}</p></div>
          </div>
          {workflow.blocker && !workflow.error_code?.includes('approval') && <div className="mt-4 border-l-2 border-warning pl-3 text-xs leading-5 text-warning">{workflow.blocker}</div>}
          <ApprovalGate workflow={workflow} busy={busy} onApprove={onApprove} />
        </article>
      </div>
    </section>
  )
}

function CodingLoop({ workflow, events, workers, busy, streamState, streamIssue, lastSignalAt, onSwitch, onCommand }: {
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

function GoalsView({ goals, workers, busy, onCreate, onCommand }: {
  goals: DeveloperGoal[]; workers: DeveloperWorkerProfile[]; busy: boolean
  onCreate: (input: { title: string; objective: string; acceptance_criteria: string[]; autonomy: 'sandbox' | 'pr' | 'merge_deploy'; preferred_models: string[]; worker_profile_slug: string; reviewer_profile_slug: string }) => Promise<boolean>
  onCommand: (id: number, command: 'pause' | 'resume' | 'cancel' | 'approve_scope') => void
}) {
  const [title, setTitle] = useState('')
  const [objective, setObjective] = useState('')
  const [criteria, setCriteria] = useState('')
  const [assessment, setAssessment] = useState<DeveloperAssessment | null>(null)
  const [assessing, setAssessing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const codingWorkers = workers.filter(item => item.enabled && item.adapter !== 'model_review')
  const reviewers = workers.filter(item => item.enabled && item.adapter === 'model_review')
  const [worker, setWorker] = useState('mc-native')
  const [reviewer, setReviewer] = useState('reviewer-default')
  const [autonomy, setAutonomy] = useState<'sandbox' | 'pr' | 'merge_deploy'>('sandbox')
  useEffect(() => {
    if (!codingWorkers.some(item => item.slug === worker)) setWorker(codingWorkers[0]?.slug ?? '')
  }, [workers, worker])
  useEffect(() => {
    if (!reviewers.some(item => item.slug === reviewer)) setReviewer(reviewers[0]?.slug ?? '')
  }, [workers, reviewer])
  const input = () => {
    const acceptance = criteria.split('\n').map(item => item.trim()).filter(Boolean)
    return { title: title.trim(), objective: objective.trim(), acceptance_criteria: acceptance }
  }
  const assess = async () => {
    const value = input()
    if (value.title.length < 3 || value.objective.length < 10 || !value.acceptance_criteria.length) return
    setAssessing(true)
    setFormError(null)
    try {
      setAssessment(await assessDeveloperGoal(value))
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err))
    } finally {
      setAssessing(false)
    }
  }
  const submit = async () => {
    const value = input()
    if (!assessment || value.title.length < 3 || value.objective.length < 10 || !value.acceptance_criteria.length || !worker || !reviewer) return
    setSubmitting(true)
    setFormError(null)
    try {
      const saved = await onCreate({
        ...value,
        autonomy,
        preferred_models: [],
        worker_profile_slug: worker,
        reviewer_profile_slug: reviewer,
      })
      if (saved) {
        setTitle('')
        setObjective('')
        setCriteria('')
        setAssessment(null)
      } else {
        setFormError('The goal was not saved. Your input has been kept so you can retry.')
      }
    } finally {
      setSubmitting(false)
    }
  }
  return <div className="space-y-8">
    <section className="border-y border-border py-5">
      <div className="flex items-center gap-2"><Target size={17} className="text-accent" /><h2 className="text-sm font-semibold text-text">New continuous development goal</h2></div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <label className="lg:col-span-2"><span className="mb-1 block text-xs text-muted">Goal title</span><input value={title} onChange={event => setTitle(event.target.value)} placeholder="Improve Agent runtime reliability" className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent" /></label>
        <label className="lg:col-span-2"><span className="mb-1 block text-xs text-muted">Objective</span><textarea value={objective} onChange={event => setObjective(event.target.value)} rows={3} placeholder="Describe the infrastructure outcome and boundaries." className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm text-text outline-none focus:border-accent" /></label>
        <label><span className="mb-1 block text-xs text-muted">Acceptance criteria, one per line</span><textarea value={criteria} onChange={event => setCriteria(event.target.value)} rows={5} placeholder={'All focused tests pass\nNo regression in Chat mode\nRuntime recovers after restart'} className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm text-text outline-none focus:border-accent" /></label>
        <div className="space-y-3"><label><span className="mb-1 block text-xs text-muted">Autonomy boundary</span><select value={autonomy} onChange={event => setAutonomy(event.target.value as typeof autonomy)} className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent"><option value="sandbox">Local sandbox only</option><option value="pr">Create draft pull request</option><option value="merge_deploy">Draft PR, owner merge and deploy gate</option></select></label><label><span className="mb-1 block text-xs text-muted">Coding worker</span><select value={worker} onChange={event => setWorker(event.target.value)} className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent">{codingWorkers.map(item => <option key={item.slug} value={item.slug}>{item.name} · {item.health_status}</option>)}</select></label><label><span className="mb-1 block text-xs text-muted">Independent reviewer</span><select value={reviewer} onChange={event => setReviewer(event.target.value)} className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent">{reviewers.map(item => <option key={item.slug} value={item.slug}>{item.name}</option>)}</select></label></div>
      </div>
      {assessment && <div className="mt-4 border-y border-border py-4"><div className="flex flex-wrap items-center gap-2"><StateBadge state={assessment.route} /><StateBadge state={assessment.risk} /><span className="text-xs text-muted">Capability score {assessment.score}/100 · {assessment.sprints.length} bounded sprint{assessment.sprints.length === 1 ? '' : 's'}</span></div><div className="mt-3 grid gap-2 sm:grid-cols-2">{assessment.sprints.map(sprint => <div key={sprint.sequence} className="border-l-2 border-border pl-3"><div className="text-sm text-text">{sprint.title}</div><div className="mt-1 text-[11px] text-muted">{sprint.budget.max_files} files · {sprint.budget.max_changed_lines} lines · {sprint.budget.max_minutes} min</div></div>)}</div><ul className="mt-3 space-y-1 text-xs text-muted">{assessment.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></div>}
      {formError && <div className="mt-4 border-l-2 border-danger pl-3 text-xs text-danger">{formError}</div>}
      {(!codingWorkers.length || !reviewers.length) && <div className="mt-4 border-l-2 border-warning pl-3 text-xs text-warning">Enable at least one coding worker and one independent reviewer before saving a goal.</div>}
      <div className="mt-4 flex flex-wrap gap-2">{!assessment ? <button onClick={assess} disabled={busy || assessing || title.trim().length < 3 || objective.trim().length < 10 || !criteria.trim()} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background disabled:opacity-40">{assessing ? <Loader2 size={15} className="animate-spin" /> : <TestTube2 size={15} />} Assess scope</button> : <><button onClick={submit} disabled={busy || submitting || !worker || !reviewer} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background disabled:opacity-40">{submitting ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} Save goal and queue sprints</button><button onClick={() => setAssessment(null)} disabled={submitting} className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm text-text disabled:opacity-40"><RotateCcw size={14} /> Reassess</button></>}</div>
    </section>
    <section><h2 className="mb-3 text-sm font-semibold text-text">Development goals</h2>{!goals.length ? <Empty text="No continuous development goals have been created." /> : <div className="border-t border-border">{goals.map(goal => {
      const resumable = ['paused', 'blocked', 'awaiting_config'].includes(goal.status)
      const awaitingScope = goal.status === 'awaiting_scope_approval'
      const active = !['completed', 'qualified_local', 'canceled'].includes(goal.status)
      return <div key={goal.id} className="grid gap-3 border-b border-border/70 py-4 lg:grid-cols-[minmax(0,1fr)_180px_240px] lg:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="font-medium text-text">{goal.title}</span><StateBadge state={goal.status} /></div><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{goal.objective}</p>{goal.last_error && <div className="mt-1 text-xs text-warning">{label(goal.last_error)}</div>}</div><div className="text-xs text-muted">Iteration {goal.iteration_count}/{goal.max_iterations}<br />{goal.worker_profile_slug ?? 'mc-native'} · {label(goal.autonomy)}</div><div className="flex flex-wrap justify-start gap-2 lg:justify-end">{awaitingScope && <button disabled={busy} onClick={() => onCommand(goal.id, 'approve_scope')} className="inline-flex h-8 items-center gap-1 rounded-md bg-warning px-2 text-xs font-medium text-background"><ShieldCheck size={13} /> Approve scope</button>}{resumable && <button disabled={busy} onClick={() => onCommand(goal.id, 'resume')} className="inline-flex h-8 items-center gap-1 rounded-md bg-accent px-2 text-xs text-background"><Play size={13} /> Resume</button>}{active && !resumable && !awaitingScope && <button disabled={busy} onClick={() => onCommand(goal.id, 'pause')} className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-2 text-xs text-text"><Pause size={13} /> Pause</button>}{active && <button disabled={busy} onClick={() => onCommand(goal.id, 'cancel')} className="inline-flex h-8 items-center gap-1 rounded-md border border-danger/40 px-2 text-xs text-danger"><Square size={12} /> Cancel</button>}</div></div>
    })}</div>}</section>
  </div>
}

function WorkersView({ workers, models, providers, routing, busy, onSave, onProbe, onLogin }: {
  workers: DeveloperWorkerProfile[]; busy: boolean
  models: AvailableModel[]; providers: LlmProvider[]
  routing: { default_model: string; coding: string; coding_review: string }
  onSave: (slug: string, profile: DeveloperWorkerProfile) => void
  onProbe: (slug: string) => void
  onLogin: (slug: string) => void
}) {
  const defaultWorker = workers.find(item => item.slug === 'mc-native') ?? workers[0]
  const [slug, setSlug] = useState(defaultWorker?.slug ?? 'mc-native')
  const selected = workers.find(item => item.slug === slug) ?? workers[0]
  const [draft, setDraft] = useState<DeveloperWorkerProfile | null>(selected ?? null)
  useEffect(() => { if (selected) setDraft(selected) }, [selected?.slug])
  useEffect(() => {
    if (!selected) return
    setDraft(current => current?.slug === selected.slug ? {
      ...current,
      health_status: selected.health_status,
      health_detail: selected.health_detail,
      last_probed_at: selected.last_probed_at,
      runner: selected.runner,
      runner_mode: selected.runner_mode,
    } : current)
  }, [
    selected?.health_status, selected?.health_detail, selected?.last_probed_at,
    selected?.runner, selected?.runner_mode, selected?.slug,
  ])
  if (!draft) return <Empty text="No coding worker profiles are configured." />
  const update = <K extends keyof DeveloperWorkerProfile>(key: K, value: DeveloperWorkerProfile[K]) =>
    setDraft(current => current ? { ...current, [key]: value } : current)
  const modelsManaged = draft.adapter === 'native' || draft.adapter === 'model_review'
  const routeTask = draft.adapter === 'model_review' ? 'coding_review' : 'coding'
  const routeModel = routing[routeTask] || routing.default_model
  const selectedModelUnavailable = Boolean(
    modelsManaged && draft.model && !models.some(model => model.id === draft.model),
  )
  const effectiveModel = modelsManaged ? (draft.model || routeModel) : draft.model
  const effectiveModelConfig = models.find(model => model.id === effectiveModel)
  const effectiveProvider = providers.find(provider => provider.id === effectiveModelConfig?.provider)
  const effectiveProviderNeedsAuth = Boolean(
    effectiveProvider?.enabled && effectiveProvider.needs_key && !effectiveProvider.key_present,
  )
  const effectiveModelLabel = effectiveModelConfig?.label
    || effectiveModel
    || (modelsManaged ? 'Legacy environment route' : 'CLI default')
  const dirty = Boolean(selected && (
    draft.name !== selected.name
    || draft.adapter !== selected.adapter
    || draft.model !== selected.model
    || draft.auth_mode !== selected.auth_mode
    || draft.credential_env !== selected.credential_env
    || draft.enabled !== selected.enabled
  ))
  const adapterName = (adapter: DeveloperWorkerProfile['adapter']) => ({
    native: 'Mission Control',
    codex: 'Codex CLI',
    opencode: 'OpenCode CLI',
    hermes: 'Hermes CLI',
    model_review: 'Model review',
  }[adapter])
  const workerModelId = (worker: DeveloperWorkerProfile) => {
    if (worker.adapter === 'native' || worker.adapter === 'model_review') {
      const task = worker.adapter === 'model_review' ? 'coding_review' : 'coding'
      return worker.model || routing[task] || routing.default_model
    }
    return worker.model
  }
  const workerModel = (worker: DeveloperWorkerProfile) => {
    const id = workerModelId(worker)
    return models.find(model => model.id === id)?.label || id || 'CLI default'
  }
  const workerProvider = (worker: DeveloperWorkerProfile) => {
    if (worker.adapter === 'codex') return 'codex'
    return null
  }
  const workerLogo = (worker: DeveloperWorkerProfile, size = 15) =>
    <LlmLogo model={workerModelId(worker)} provider={workerProvider(worker)} size={size} />
  const draftProvider = draft.adapter === 'codex' ? 'codex' : null
  const draftLogo = (size = 15) =>
    <LlmLogo model={modelsManaged ? effectiveModel : draft.model} provider={draftProvider} size={size} />
  const draftBrand = effectiveModel ? brandForModel(effectiveModel) : brandForProvider(draftProvider)
  const providerName = BRAND_META[draftBrand].name
  const iconDescription = modelsManaged || draft.model
    ? `${providerName} model provider`
    : `${adapterName(draft.adapter)} default`
  const modelLabelWithProvider = (
    <div className="flex min-w-0 items-center gap-2">
      {draftLogo(14)}
      <span className="min-w-0 break-words">{effectiveModelLabel}</span>
    </div>
  )
  const providerLogoTitle = (worker: DeveloperWorkerProfile) => {
    const id = workerModelId(worker)
    return models.find(model => model.id === id)?.label || workerModel(worker)
  }
  const healthDot = (status: string) => {
    if (status === 'ready') return 'bg-success'
    if (['failed', 'unavailable'].includes(status)) return 'bg-danger'
    if (['needs_auth', 'disabled', 'blocked'].includes(status)) return 'bg-warning'
    return 'bg-muted/50'
  }
  const workerOrder: Record<DeveloperWorkerProfile['adapter'], number> = {
    native: 0,
    codex: 1,
    opencode: 2,
    model_review: 3,
    hermes: 4,
  }
  const orderedWorkers = workers.filter(worker => worker.adapter !== 'hermes').sort((a, b) =>
    workerOrder[a.adapter] - workerOrder[b.adapter] || a.name.localeCompare(b.name),
  )
  const workerKind = (worker: DeveloperWorkerProfile) =>
    worker.adapter === 'model_review' ? 'Reviewer' : worker.adapter === 'native' ? 'Built-in' : 'Coding CLI'
  const selectWorker = (nextSlug: string) => {
    if (nextSlug === draft.slug) return
    if (dirty && !window.confirm('Discard unsaved worker changes?')) return
    setSlug(nextSlug)
  }
  const readyWorkers = orderedWorkers.filter(worker => worker.health_status === 'ready').length
  const routeName = (id: string) => models.find(model => model.id === id)?.label || id || 'Legacy environment'
  const lastTested = draft.last_probed_at
    ? new Date(draft.last_probed_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
    : 'Not tested'
  const modelSourceLabel = modelsManaged
    ? draft.model ? 'Pinned to this worker' : 'Following shared routing'
    : draft.model ? 'CLI model override' : 'Using CLI default'
  const changeAdapter = (adapter: DeveloperWorkerProfile['adapter']) => {
    setDraft(current => {
      if (!current) return current
      return {
        ...current,
        adapter,
        model: '',
        auth_mode: adapter === 'codex' ? 'native_login' : 'inherited',
        credential_env: '',
      }
    })
  }
  return <div className="mx-auto max-w-5xl space-y-6 pb-6">
    <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h2 className="text-base font-semibold text-text">Coding workers</h2>
        <p className="mt-1 text-xs leading-5 text-muted">Choose the coding engine Mission Control uses for development goals.</p>
      </div>
      <div className="inline-flex w-fit items-center gap-2 rounded-full bg-surface/70 px-3 py-1.5 text-xs text-muted">
        <span className="h-2 w-2 rounded-full bg-success" />
        {readyWorkers} of {orderedWorkers.length} ready
      </div>
    </header>

    <div role="tablist" aria-label="Coding workers" className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      {orderedWorkers.map(worker => {
        const active = worker.slug === draft.slug
        return <button
          key={worker.slug}
          type="button"
          role="tab"
          aria-selected={active}
          onClick={() => selectWorker(worker.slug)}
          className={`group flex min-h-20 min-w-0 items-center gap-3 rounded-md px-3 py-3 text-left transition-all ${
            active
              ? 'bg-accent/10 shadow-[0_8px_30px_rgb(var(--accent)/0.08)] ring-1 ring-accent/40'
              : 'bg-surface/50 hover:bg-surface/90'
          }`}
        >
          <span title={providerLogoTitle(worker)} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-background/70">
            {workerLogo(worker, 18)}
          </span>
          <span className="min-w-0 flex-1">
            <span className={`flex items-center gap-2 truncate text-sm font-medium ${active ? 'text-text' : 'text-muted group-hover:text-text'}`}>
              <span className="truncate">{worker.name}</span>
              <span title={label(worker.health_status)} className={`ml-auto h-2 w-2 shrink-0 rounded-full ${healthDot(worker.health_status)}`} />
            </span>
            <span className="mt-1 block truncate text-[10px] text-muted">{workerKind(worker)}</span>
          </span>
        </button>
      })}
    </div>

    <section className="rounded-lg bg-surface/75 p-5 shadow-[0_18px_60px_rgb(0_0_0/0.14)] ring-1 ring-border/30 sm:p-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <span title={iconDescription} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-background/70">
          {draftLogo(22)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold text-text">{draft.name}</h3>
            <StateBadge state={draft.health_status} />
            {dirty && <span className="text-[10px] font-medium uppercase text-warning">Unsaved</span>}
          </div>
          <div className="mt-1 text-xs text-muted">{adapterName(draft.adapter)} · {providerName}</div>
        </div>
        <label className="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted">
          <span>Use in new goals</span>
          <input type="checkbox" checked={draft.enabled} onChange={event => update('enabled', event.target.checked)} className="peer sr-only" />
          <span className="relative h-5 w-9 rounded-full bg-overlay/15 transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-muted after:transition-transform peer-checked:bg-accent peer-checked:after:translate-x-4 peer-checked:after:bg-background" />
        </label>
      </header>

      <div className="mt-5 flex flex-col gap-3 rounded-md bg-background/40 px-4 py-3 sm:flex-row sm:items-center">
        {draft.health_status === 'ready'
          ? <CheckCircle2 size={16} className="shrink-0 text-success" />
          : <Circle size={16} className="shrink-0 text-muted" />}
        <div className="min-w-0 flex-1">
          <div className="text-xs font-medium text-text">{draft.health_detail || 'This worker has not been tested yet.'}</div>
        </div>
        <div className="shrink-0 text-[10px] text-muted">Last test: {lastTested}</div>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <label>
          <span className="mb-2 block text-xs font-medium text-text">Run with</span>
          <select value={draft.adapter} onChange={event => changeAdapter(event.target.value as DeveloperWorkerProfile['adapter'])} className="h-11 w-full rounded-md border border-border/70 bg-background px-3 text-sm text-text outline-none transition-colors focus:border-accent">
            <option value="native">Mission Control runtime</option>
            <option value="codex">Codex CLI</option>
            <option value="opencode">OpenCode CLI</option>
            <option value="model_review">Independent model review</option>
          </select>
        </label>

        {modelsManaged ? <div>
          <div className="mb-2 flex items-center justify-between gap-3 text-xs font-medium text-text">
            <span>AI model</span>
            <a href="/models" className="inline-flex items-center gap-1 text-[10px] font-normal text-accent hover:underline">Manage models <ExternalLink size={10} /></a>
          </div>
          <ModelMenu
            models={models}
            value={draft.model || null}
            onChange={model => update('model', model)}
            autoLabel={`Shared ${routeTask === 'coding_review' ? 'review' : 'coding'} · ${routeName(routeModel)}`}
            wide
            align="left"
          />
          <p className="mt-2 text-[10px] leading-4 text-muted">Same providers and models as Chat. Enable or configure them on the Models page.</p>
        </div> : <div>
          <span className="mb-2 block text-xs font-medium text-text">AI model</span>
          <div className="flex h-11 items-center gap-2 rounded-md bg-background/60 px-3">
            {draftLogo(14)}
            <span className="min-w-0 flex-1 truncate text-sm text-text">
              {draft.adapter === 'codex' ? 'Managed by Codex CLI' : draft.adapter === 'opencode' ? 'Managed by OpenCode CLI' : 'Managed by external CLI'}
            </span>
          </div>
          <p className="mt-2 text-[10px] leading-4 text-muted">External coding agents use their own model and login configuration.</p>
        </div>}
      </div>

      {!modelsManaged && <div className="mt-5 grid gap-6 lg:grid-cols-2">
        <label>
          <span className="mb-2 block text-xs font-medium text-text">Authentication</span>
          <select value={draft.auth_mode} onChange={event => {
            const auth = event.target.value as DeveloperWorkerProfile['auth_mode']
            setDraft(current => current ? { ...current, auth_mode: auth, credential_env: auth === 'vault_env' ? current.credential_env : '' } : current)
          }} className="h-11 w-full rounded-md border border-border/70 bg-background px-3 text-sm text-text outline-none transition-colors focus:border-accent">
            <option value="inherited">Use CLI authentication</option>
            <option value="native_login">Native agent login</option>
            <option value="vault_env">Vault environment secret</option>
          </select>
        </label>
        {draft.auth_mode === 'vault_env' && <label>
          <span className="mb-2 block text-xs font-medium text-text">Vault environment name</span>
          <input value={draft.credential_env} onChange={event => update('credential_env', event.target.value.toUpperCase())} placeholder="ZAI_API_KEY" className="h-11 w-full rounded-md border border-border/70 bg-background px-3 font-mono text-sm text-text outline-none transition-colors focus:border-accent" />
        </label>}
      </div>}

      {effectiveProviderNeedsAuth && <div className="mt-5 flex items-start gap-2 rounded-md bg-warning/[0.08] px-3 py-2.5 text-[11px] text-warning">
        <AlertTriangle size={14} className="mt-0.5 shrink-0" />
        <span>{effectiveProvider?.label} needs credentials before this worker can run.</span>
      </div>}
      {selectedModelUnavailable && <div className="mt-5 flex items-start gap-2 rounded-md bg-warning/[0.08] px-3 py-2.5 text-[11px] text-warning">
        <AlertTriangle size={14} className="mt-0.5 shrink-0" />
        <span>The saved model is no longer available on the Models page. Choose another model or use the shared route.</span>
      </div>}

      <details className="group mt-6">
        <summary className="inline-flex cursor-pointer list-none items-center gap-2 text-xs text-muted hover:text-text">
          <Plus size={13} className="transition-transform group-open:rotate-45" />
          Advanced settings
        </summary>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <label>
            <span className="mb-2 block text-xs font-medium text-text">Worker name</span>
            <input value={draft.name} onChange={event => update('name', event.target.value)} className="h-10 w-full rounded-md border border-border/70 bg-background px-3 text-sm text-text outline-none transition-colors focus:border-accent" />
          </label>
          {!modelsManaged && <label>
            <span className="mb-2 block text-xs font-medium text-text">CLI model ID <span className="font-normal text-muted">optional</span></span>
            <input value={draft.model} onChange={event => update('model', event.target.value)} placeholder="Use CLI default" className="h-10 w-full rounded-md border border-border/70 bg-background px-3 font-mono text-sm text-text outline-none transition-colors focus:border-accent" />
          </label>}
        </div>
      </details>

      <footer className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2 text-xs text-muted">
          {modelLabelWithProvider}
          <span className="hidden sm:inline">·</span>
          <span className="hidden truncate sm:inline">{modelSourceLabel}</span>
        </div>
        <div className="flex flex-wrap gap-2 sm:justify-end">
          {dirty && <button type="button" disabled={busy} onClick={() => setDraft(selected)} title="Discard unsaved changes" className="flex h-10 w-10 items-center justify-center rounded-md text-muted hover:bg-overlay/5 hover:text-text disabled:opacity-40"><RotateCcw size={14} /></button>}
          {draft.auth_mode === 'native_login' && <button disabled={busy || dirty} onClick={() => onLogin(draft.slug)} className="inline-flex h-10 items-center justify-center gap-2 rounded-md px-3 text-sm text-muted hover:bg-overlay/5 hover:text-text disabled:opacity-40"><KeyRound size={14} /> Login</button>}
          <button disabled={busy || dirty} onClick={() => onProbe(draft.slug)} title={dirty ? 'Save changes before testing' : 'Test worker'} className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-background/70 px-3 text-sm text-text hover:bg-overlay/10 disabled:cursor-not-allowed disabled:opacity-40"><TestTube2 size={14} /> Test</button>
          <button disabled={busy || !dirty} onClick={() => onSave(draft.slug, draft)} className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-medium text-background disabled:cursor-not-allowed disabled:opacity-40">{busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save changes</button>
        </div>
      </footer>
    </section>
  </div>
}

function LearningView({ state, busy, onReplay }: {
  state: { records: Array<Record<string, unknown>>; playbooks: Array<Record<string, unknown>> }
  busy: boolean; onReplay: () => void
}) {
  return <div className="space-y-8">
    <section className="flex flex-col justify-between gap-3 border-y border-border py-5 sm:flex-row sm:items-center"><div><div className="flex items-center gap-2"><BookOpen size={16} className="text-accent" /><h2 className="text-sm font-semibold text-text">Evidence-backed improvement</h2></div><p className="mt-1 text-xs text-muted">{state.records.length} outcomes · {state.playbooks.length} reusable playbooks</p></div><button disabled={busy || !state.playbooks.length} onClick={onReplay} className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-accent/40 px-3 text-sm text-accent disabled:opacity-40"><TestTube2 size={14} /> Replay evaluations</button></section>
    <section><h2 className="mb-3 text-sm font-semibold text-text">Playbooks</h2>{!state.playbooks.length ? <Empty text="Playbooks appear after repeated evidence-backed outcomes." /> : <div className="border-t border-border">{state.playbooks.map((item, index) => <div key={String(item.slug ?? index)} className="grid gap-2 border-b border-border/70 py-3 sm:grid-cols-[minmax(0,1fr)_120px_120px] sm:items-center"><div><div className="text-sm text-text">{String(item.title ?? item.slug)}</div><div className="mt-1 text-xs text-muted">v{String(item.version ?? 1)} · {String(item.evidence_count ?? 0)} evidence records</div></div><StateBadge state={String(item.kind ?? 'repair')} /><div className="sm:text-right"><StateBadge state={String(item.status ?? 'candidate')} /></div></div>)}</div>}</section>
    <section><h2 className="mb-3 text-sm font-semibold text-text">Recent outcomes</h2>{!state.records.length ? <Empty text="No coding outcomes have been recorded." /> : <div className="border-t border-border">{state.records.slice(0, 50).map((item, index) => <div key={String(item.id ?? index)} className="grid gap-2 border-b border-border/70 py-3 sm:grid-cols-[minmax(0,1fr)_160px_140px] sm:items-center"><div><div className="text-sm text-text">{label(String(item.outcome ?? 'unknown'))}</div><div className="mt-1 font-mono text-[10px] text-muted">{String(item.signature ?? '')}</div></div><div className="text-xs text-muted">{String(item.worker_profile ?? 'unassigned')} · {label(String(item.stage ?? 'unknown'))}</div><div className="text-xs text-muted sm:text-right">{String(item.error_code ?? '') || 'Qualified evidence'}</div></div>)}</div>}</section>
  </div>
}

const TOBI_REPOSITORY_URL = 'https://github.com/binhvu284/tobi'

function releaseDate(value?: string | null) {
  if (!value) return 'Date pending'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
}

function releaseDescription(release: DeveloperRelease) {
  if (release.notes?.trim()) return release.notes.trim()
  if (release.queue_item) return `Mission Control release for queue item #${release.queue_item}.`
  return `TOBI ${release.tier ? `${label(release.tier)} tier ` : ''}release tracked by Mission Control.`
}

function VersionActions({ version }: { version: string }) {
  const actions = [
    { label: 'Download this version', icon: Download },
    { label: 'Change to this version', icon: RotateCcw },
    { label: 'Remove version', icon: Trash2 },
  ]
  return <details className="relative shrink-0">
    <summary title={`Actions for version ${version}`} aria-label={`Actions for version ${version}`} className="flex h-8 w-8 cursor-pointer list-none items-center justify-center rounded-md text-muted transition-colors hover:bg-overlay/10 hover:text-text [&::-webkit-details-marker]:hidden">
      <MoreHorizontal size={16} />
    </summary>
    <div className="absolute right-0 top-9 z-20 w-60 rounded-md border border-border bg-surface p-1 shadow-2xl">
      {actions.map(action => {
        const Icon = action.icon
        return <button key={action.label} type="button" disabled className="flex h-9 w-full cursor-not-allowed items-center gap-2 rounded px-2 text-left text-xs text-muted opacity-70">
          <Icon size={13} /><span className="min-w-0 flex-1 truncate">{action.label}</span><span className="rounded border border-border px-1.5 py-0.5 text-[9px] uppercase text-muted">Soon</span>
        </button>
      })}
    </div>
  </details>
}

function VersionsView({ releases }: { releases: DeveloperRelease[] }) {
  const current = releases.find(release => release.status === 'released') ?? releases[0] ?? null
  const currentIndex = current ? releases.findIndex(release => release.id === current.id) : -1
  const previous = currentIndex >= 0 ? releases.slice(currentIndex + 1)[0] ?? null : null
  const currentDescription = current ? releaseDescription(current) : 'No TOBI release has been recorded in Mission Control yet.'
  const changedSummary = current
    ? previous
      ? `Advanced from v${previous.version}${current.queue_item ? ` through queue item #${current.queue_item}` : ''}.`
      : current.queue_item
        ? `Established by queue item #${current.queue_item}; no earlier release is recorded.`
        : 'This is the earliest release currently recorded in Mission Control.'
    : 'Version comparison will appear after the first release is recorded.'

  return <div className="space-y-6">
    <section className="overflow-hidden rounded-md border border-border bg-surface/45">
      <div className="flex flex-col gap-5 border-l-2 border-accent px-5 py-5 sm:px-6">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[10px] font-semibold uppercase text-accent"><GitBranch size={13} /> Current version</div>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h2 className="font-mono text-2xl font-semibold text-heading">{current ? `v${current.version}` : 'Not recorded'}</h2>
              {current && <StateBadge state={current.status} />}
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">{currentDescription}</p>
          </div>
          {current && <div className="shrink-0 text-left text-[11px] text-muted sm:text-right"><div>{releaseDate(current.released_at ?? current.created_at)}</div><div className="mt-1 font-mono">{current.commit_sha?.slice(0, 12) ?? 'Commit pending'}</div></div>}
        </div>
        <div className="grid gap-4 border-t border-border/70 pt-4 lg:grid-cols-2">
          <div><div className="text-[10px] font-semibold uppercase text-muted">Changed from previous</div><p className="mt-1.5 text-xs leading-5 text-text">{changedSummary}</p></div>
          <div><div className="text-[10px] font-semibold uppercase text-muted">Update recap</div><p className="mt-1.5 text-xs leading-5 text-text">{current ? `${label(current.status)} from ${label(current.source)}${current.tier ? ` for the ${label(current.tier)} tier` : ''}.` : 'Release status, source, and deployment recap will appear here.'}</p></div>
        </div>
      </div>
    </section>

    <div className="grid gap-4 lg:grid-cols-2">
      <section className="rounded-md border border-border bg-surface/30 p-5">
        <div className="flex items-start gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-overlay/5 text-text"><Github size={18} /></span><div className="min-w-0"><h2 className="text-sm font-semibold text-text">Source</h2><p className="mt-1 text-xs leading-5 text-muted">Mission Control and the repository should document the same active version.</p></div></div>
        <a href={TOBI_REPOSITORY_URL} target="_blank" rel="noreferrer" className="mt-5 flex items-center justify-between gap-3 rounded-md border border-border bg-background/55 px-3 py-2.5 text-xs text-text transition-colors hover:border-accent/45 hover:text-accent">
          <span className="truncate font-mono">github.com/binhvu284/tobi</span><ExternalLink size={13} className="shrink-0" />
        </a>
      </section>

      <section className="rounded-md border border-border bg-surface/30 p-5">
        <div className="flex items-start gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent/10 text-accent"><Archive size={18} /></span><div className="min-w-0"><h2 className="text-sm font-semibold text-text">Backup data</h2><p className="mt-1 text-xs leading-5 text-muted">Import or export chats, files, projects, and related TOBI data.</p></div></div>
        <div className="mt-5 grid grid-cols-2 gap-2">
          <button type="button" disabled title="Backup import is coming soon" className="inline-flex h-10 cursor-not-allowed items-center justify-center gap-2 rounded-md border border-border text-xs text-muted opacity-70"><Upload size={14} /> Import <span className="text-[9px] uppercase">Soon</span></button>
          <button type="button" disabled title="Backup export is coming soon" className="inline-flex h-10 cursor-not-allowed items-center justify-center gap-2 rounded-md border border-border text-xs text-muted opacity-70"><Download size={14} /> Export <span className="text-[9px] uppercase">Soon</span></button>
        </div>
      </section>
    </div>

    <section>
      <div className="flex items-end justify-between gap-4"><div><h2 className="text-sm font-semibold text-text">Version history</h2><p className="mt-1 text-xs text-muted">Recorded TOBI releases, newest first.</p></div><span className="text-[11px] tabular-nums text-muted">{releases.length} {releases.length === 1 ? 'version' : 'versions'}</span></div>
      {!releases.length ? <div className="mt-3"><Empty text="No version has been reserved." /></div> : <div className="mt-3 space-y-2">{releases.map(release => (
        <div key={release.id} className="flex min-h-14 items-center gap-3 rounded-md border border-border bg-surface/25 px-3 py-2.5 transition-colors hover:bg-surface/45 sm:px-4">
          <div className="w-24 shrink-0"><div className="font-mono text-sm font-semibold text-text">v{release.version}</div>{current?.id === release.id && <div className="mt-0.5 text-[9px] font-semibold uppercase text-accent">Current</div>}</div>
          <p className="min-w-0 flex-1 truncate text-xs text-muted">{releaseDescription(release)}</p>
          <div className="hidden shrink-0 items-center gap-3 md:flex"><StateBadge state={release.status} /><span className="w-24 text-right text-[10px] text-muted">{releaseDate(release.released_at ?? release.created_at)}</span></div>
          <VersionActions version={release.version} />
        </div>
      ))}</div>}
    </section>
  </div>
}

function StorageView({ storage, busy, onCleanup }: { storage: DeveloperStorage | null; busy: boolean; onCleanup: (master: string) => void }) {
  const [master, setMaster] = useState('')
  if (!storage) return <Empty text="Storage data is unavailable." />
  const pct = Math.min(100, storage.warning_bytes ? storage.total_developer_bytes / storage.warning_bytes * 100 : 0)
  const eligible = storage.cleanup_eligible_artifacts + storage.cleanup_eligible_worktrees
  return (
    <section className="border-y border-border py-5">
      <div className="grid gap-6 sm:grid-cols-3">
        <div><div className="text-xs text-muted">Worktrees</div><div className="mt-1 text-2xl font-semibold text-text">{storage.worktree_count}</div></div>
        <div><div className="text-xs text-muted">Developer storage</div><div className="mt-1 text-2xl font-semibold text-text">{formatBytes(storage.total_developer_bytes)}</div><div className="mt-1 text-[11px] text-muted">{storage.artifact_count} evidence files</div></div>
        <div><div className="text-xs text-muted">Retention</div><div className="mt-1 text-2xl font-semibold text-text">{storage.retention_days} days</div></div>
      </div>
      <div className="mt-6"><div className="mb-2 flex justify-between text-xs text-muted"><span>Worktree pressure</span><span>{pct.toFixed(1)}%</span></div><div className="h-2 rounded bg-overlay/10"><div className={`h-full rounded ${storage.blocked_new_workflows ? 'bg-danger' : 'bg-accent'}`} style={{ width: `${Math.max(pct, 1)}%` }} /></div></div>
      <div className="mt-4 break-all font-mono text-[11px] text-muted">{storage.worktree_root}</div>
      <div className="mt-6 flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:items-end">
        <label className="min-w-0 flex-1"><span className="mb-1 block text-xs text-muted">Cleanup approval · {eligible} eligible</span><input type="password" value={master} onChange={event => setMaster(event.target.value)} placeholder="Vault master password" className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent" /></label>
        <button disabled={busy || eligible === 0 || master.length < 6} onClick={() => { onCleanup(master); setMaster('') }} className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm text-text hover:bg-overlay/5 disabled:opacity-40"><RotateCcw size={14} /> Clean eligible</button>
      </div>
    </section>
  )
}

function DataLearningView({ storage, learning, busy, onCleanup, onReplay }: {
  storage: DeveloperStorage | null
  learning: { records: Array<Record<string, unknown>>; playbooks: Array<Record<string, unknown>> }
  busy: boolean; onCleanup: (master: string) => void; onReplay: () => void
}) {
  return <div className="space-y-10">
    <div>
      <div className="mb-4 flex items-start gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent/10 text-accent"><HardDrive size={16} /></span><div><h2 className="text-sm font-semibold text-text">Storage</h2><p className="mt-1 text-xs text-muted">Developer worktrees, evidence, and retention controls.</p></div></div>
      <StorageView storage={storage} busy={busy} onCleanup={onCleanup} />
    </div>
    <div>
      <div className="mb-4 flex items-start gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-success/10 text-success"><BookOpen size={16} /></span><div><h2 className="text-sm font-semibold text-text">Learning</h2><p className="mt-1 text-xs text-muted">Evidence-backed outcomes and reusable development playbooks.</p></div></div>
      <LearningView state={learning} busy={busy} onReplay={onReplay} />
    </div>
  </div>
}

export default function Developer() {
  const { toast } = useToast()
  const vaultSession = useVaultSession()
  const [tab, setTab] = useState<Tab>('overview')
  const [overview, setOverview] = useState<DeveloperOverview | null>(null)
  const [queue, setQueue] = useState<DeveloperQueueState>({ items: [], order: [], next_queue_id: null, auto_queue: false })
  const [releases, setReleases] = useState<DeveloperRelease[]>([])
  const [storage, setStorage] = useState<DeveloperStorage | null>(null)
  const [goals, setGoals] = useState<DeveloperGoal[]>([])
  const [workers, setWorkers] = useState<DeveloperWorkerProfile[]>([])
  const [workerModels, setWorkerModels] = useState<AvailableModel[]>([])
  const [workerProviders, setWorkerProviders] = useState<LlmProvider[]>([])
  const [modelRouting, setModelRouting] = useState({ default_model: '', coding: '', coding_review: '' })
  const [learning, setLearning] = useState<{ records: Array<Record<string, unknown>>; playbooks: Array<Record<string, unknown>> }>({ records: [], playbooks: [] })
  const [events, setEvents] = useState<DeveloperEvent[]>([])
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
      const [o, q, v, s, g, w, learn] = await Promise.all([
        getDeveloperOverview(controller.signal), getDeveloperQueue(controller.signal),
        getDeveloperVersions(controller.signal), getDeveloperStorage(controller.signal),
        getDeveloperGoals(controller.signal), getDeveloperWorkers(false, controller.signal),
        getDeveloperLearning(controller.signal),
      ])
      if (controller.signal.aborted) return
      setOverview(o); setQueue(q); setReleases(v.releases); setStorage(s); setGoals(g.goals)
      setWorkers(w.workers); setWorkerModels(w.models ?? []); setWorkerProviders(w.providers ?? [])
      setModelRouting(w.routing ?? { default_model: '', coding: '', coding_review: '' })
      setLearning(learn); setError(null)
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

  const active = overview?.active_workflow ?? overview?.workflows[0] ?? null
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
  const command = (cmd: 'pause' | 'resume' | 'cancel' | 'retry' | 'remove') => active && act(() => commandDeveloperWorkflow(active.id, cmd), `Workflow ${cmd} accepted`)
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
    const modelsManaged = profile.adapter === 'native' || profile.adapter === 'model_review'
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

  const capabilities = useMemo(() => Object.entries(overview?.policy.capabilities ?? {}), [overview])
  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' }, { id: 'goals', label: 'Goals' }, { id: 'loop', label: 'Process' },
    { id: 'workers', label: 'Agents' }, { id: 'data', label: 'Storage & Learning' }, { id: 'queue', label: 'Queue' },
    { id: 'versions', label: 'Version' },
  ]

  return (
    <div className="relative min-h-full"><AmbientField tone="rgb(var(--accent))" variant="grid" />
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
              {!active && <div className="grid w-full gap-3 xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,0.8fr)]"><section className="relative overflow-hidden rounded-lg border border-accent/25 bg-surface/70 px-5 py-6 shadow-[0_20px_60px_rgb(0_0_0/0.12)] sm:px-6"><div className="absolute inset-y-0 left-0 w-1 bg-accent" /><div className="flex items-start justify-between gap-5"><div><div className="text-[10px] font-semibold uppercase text-accent">Development runtime</div><h2 className="mt-2 text-lg font-semibold text-text">Ready for a controlled run</h2><p className="mt-1 max-w-2xl text-xs leading-5 text-muted">Select a queue item or create a goal. Mission Control will isolate the work, preserve checkpoints, and keep owner gates visible.</p></div><button onClick={() => setTab('goals')} className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md bg-accent px-3 text-xs font-medium text-background"><Plus size={14} /> New goal</button></div><div className="mt-6 h-2 overflow-hidden rounded-full bg-background/70"><div className="h-full w-0 rounded-full bg-accent" /></div><div className="mt-2 text-[11px] text-muted">Idle - waiting for a goal</div></section><section className="rounded-lg border border-border bg-surface/60 px-5 py-5"><div className="flex items-start gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-md bg-success/10 text-success"><CheckCircle2 size={18} /></div><div><div className="text-[10px] font-semibold uppercase text-muted">Owner action</div><p className="mt-1.5 text-sm leading-6 text-text">No action is required. Start when the next goal is ready.</p></div></div></section></div>}
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
            {tab === 'loop' && <DeveloperProcess workflow={active} events={events} workers={workers} queue={queue.items} busy={busy}
              autoQueue={autoQueuePending ?? overview?.process?.auto_queue ?? false} autoQueueBusy={autoQueuePending !== null} streamState={streamState} streamIssue={streamIssue}
              onAutoQueue={setAutoQueue} onCommand={command} onApprove={approve} onReject={rejectApproval} />}
            {tab === 'goals' && <DevelopmentGoals goals={goals} workers={workers} busy={busy} onCreate={createGoal} onCommand={goalCommand} />}
            {tab === 'workers' && <DeveloperAgents workers={workers} models={workerModels} providers={workerProviders} routing={modelRouting} busy={busy} onSave={saveWorker} onProbe={probeWorker} onLogin={loginWorker} onModels={loadWorkerModels} />}
            {tab === 'data' && <DataLearningView storage={storage} learning={learning} busy={busy} onReplay={replayLearning} onCleanup={master => act(() => cleanupDeveloperStorage(master), 'Developer cleanup completed')} />}
            {tab === 'queue' && <DeveloperQueue state={queue} active={active} busy={busy} goals={goals}
              autoQueue={autoQueuePending ?? overview?.process?.auto_queue ?? queue.auto_queue}
              autoQueueBusy={autoQueuePending !== null}
              onAutoQueue={setAutoQueue}
              onStart={id => act(() => startDeveloperWorkflow(id), `Queue #${id} started`)}
              onOpenProcess={() => setTab('loop')}
              onState={setQueue} />}
            {tab === 'versions' && <VersionsView releases={releases} />}
          </main>
        </>}
    </div>
  )
}
