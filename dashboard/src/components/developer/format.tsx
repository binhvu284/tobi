// Extracted from Developer.tsx (pre-#21 refactor). Lives beside the components that use it
// so both frontend trees share one module instead of each keeping a private copy — the
// duplication that let a terminal state render as "still running".

import {
  Activity, AlertTriangle, Archive, BookOpen, CheckCircle2, Circle, Clock3, Code2, Download, ExternalLink,
  ChevronDown, ChevronUp, GitBranch, Github, HardDrive, KeyRound, ListTree, Loader2, MoreHorizontal, Pause, Play, Plus, Radio, RefreshCw,
  RotateCcw, Save, ScrollText, ShieldCheck, Square, Target,
  TerminalSquare, TestTube2, Trash2, Upload, WifiOff, Wrench, XCircle,
} from 'lucide-react'
import type { AvailableModel, LlmProvider } from '../../api.chat'
// Generated from core/coding_states.py by scripts/generate_developer_states.py.
import { STATE_KIND, TERMINAL_STATES, stateKind, type StateKind } from '../../developer.states'

export { TERMINAL_STATES }
import { approveDeveloperWorkflow, assessDeveloperGoal, commandDeveloperGoal, commandDeveloperWorkflow, createDeveloperGoal, getDeveloperHistory, getDeveloperLearning, getDeveloperOverview, getDeveloperQueue, getDeveloperStorage, getDeveloperVersions, getDeveloperGoals, getDeveloperWorkerLogin, getDeveloperWorkerModels, getDeveloperWorkers, probeDeveloperWorker, replayDeveloperLearning, saveDeveloperWorker, startDeveloperWorkflow, streamDeveloperEvents, switchDeveloperWorker, cleanupDeveloperStorage, rejectDeveloperWorkflow, setDeveloperProcessSettings, type DeveloperAssessment, type DeveloperEvent, type DeveloperOverview, type DeveloperGoal, type DeveloperQueueItem, type DeveloperQueueState, type DeveloperRelease, type DeveloperStorage, type DeveloperWorkerLogin, type DeveloperWorkerModels, type DeveloperWorkerProfile, type DeveloperWorkflow } from '../../api.developer'

export type Tab = 'overview' | 'work' | 'loop' | 'workers' | 'history' | 'system'
export type DeveloperLoadError = { message: string; status?: number; code?: string }
export type DeveloperStreamState = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'closed'
export type LiveEventKind = 'stage' | 'tool' | 'worker' | 'checkpoint' | 'success' | 'problem' | 'system'
export type LiveEventPresentation = { title: string; detail?: string; kind: LiveEventKind }

export const LOAD_TIMEOUT_MS = 15_000
export const STREAM_REFRESH_EVENTS = new Set([
  'checkpoint_created', 'quality_gate_completed', 'worker_switched',
  'delivery_synchronized', 'workflow_blocked', 'workflow_completed', 'workflow_merged',
  'workflow_locally_complete', 'workflow_paused',
])

const MUTED = 'text-muted border-border bg-overlay/5'

// Appearance is keyed on the state's kind, not its name. The previous per-name map had no
// entry for approved, pushed, merging, deploying or rolled_back, so those rendered muted as
// if nothing were happening — the same silent-gap failure that hid a finished run.
const KIND_TONE: Record<StateKind, string> = {
  active: 'text-accent border-accent/30 bg-accent/10',
  success: 'text-success border-success/30 bg-success/10',
  fault: 'text-danger border-danger/30 bg-danger/10',
  waiting: 'text-warning border-warning/30 bg-warning/10',
  idle: MUTED,
}

// `tone` is also given release, deployment and playbook statuses, which are a separate
// vocabulary from the workflow states and are not generated from coding_states.py.
const OTHER_TONE: Record<string, string> = {
  released: KIND_TONE.success,
  healthy: KIND_TONE.success,
  deploying: KIND_TONE.active,
  candidate: KIND_TONE.waiting,
  repair: KIND_TONE.waiting,
}

export function tone(state: string) {
  if (state in STATE_KIND) return KIND_TONE[stateKind(state)]
  return OTHER_TONE[state] ?? MUTED
}

export function label(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char: string) => char.toUpperCase())
}

export function stageLabel(value: unknown) {
  const stage = typeof value === 'string' ? value : ''
  return stage === 'code' ? 'Run selected coding worker' : label(stage || 'workflow')
}

export function textValue(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

export function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

export function compactText(value: unknown, max = 180): string | null {
  const text = textValue(value)?.replace(/\s+/g, ' ')
  if (!text) return null
  return text.length > max ? `${text.slice(0, max - 1)}...` : text
}

export function readablePayloadText(payload: Record<string, unknown>): string | null {
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

export function eventPresentation(event: DeveloperEvent): LiveEventPresentation {
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

export function eventKindClasses(kind: LiveEventKind) {
  if (kind === 'problem') return 'border-danger/30 bg-danger/10 text-danger'
  if (kind === 'success') return 'border-success/30 bg-success/10 text-success'
  if (kind === 'tool') return 'border-accent/30 bg-accent/10 text-accent'
  if (kind === 'checkpoint') return 'border-warning/30 bg-warning/10 text-warning'
  return 'border-border bg-overlay/5 text-muted'
}

export function LiveEventIcon({ kind, size = 15 }: { kind: LiveEventKind; size?: number }) {
  if (kind === 'problem') return <AlertTriangle size={size} />
  if (kind === 'success') return <CheckCircle2 size={size} />
  if (kind === 'tool') return <Wrench size={size} />
  if (kind === 'checkpoint') return <ScrollText size={size} />
  if (kind === 'stage') return <ListTree size={size} />
  if (kind === 'worker') return <TerminalSquare size={size} />
  return <Activity size={size} />
}

export function relativeAge(timestamp: number | null, now: number) {
  if (!timestamp) return 'No update yet'
  const seconds = Math.max(0, Math.floor((now - timestamp) / 1000))
  if (seconds < 2) return 'Just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  return `${Math.floor(minutes / 60)}h ago`
}

export function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}

export function StateBadge({ state }: { state: string }) {
  return <span className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-medium ${tone(state)}`}>{label(state)}</span>
}

export function Empty({ text }: { text: string }) {
  return <div className="border-y border-border/60 py-12 text-center text-sm text-muted">{text}</div>
}
