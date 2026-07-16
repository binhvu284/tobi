import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, BookOpen, Bot, CheckCircle2, Circle, Code2, ExternalLink, GitBranch,
  KeyRound, Loader2, Pause, Play, Plus, RefreshCw, RotateCcw, Save, ShieldCheck,
  Square, Target, TerminalSquare, TestTube2, XCircle,
} from 'lucide-react'
import AmbientField from '../components/motion/AmbientField'
import VaultUnlockPanel from '../components/VaultUnlockPanel'
import { useToast } from '../context/ToastProvider'
import { useVaultSession } from '../hooks/useVaultSession'
import {
  approveDeveloperWorkflow, assessDeveloperGoal, commandDeveloperGoal, commandDeveloperWorkflow, createDeveloperGoal,
  getDeveloperLearning, getDeveloperOverview, getDeveloperQueue, getDeveloperStorage, getDeveloperVersions,
  getDeveloperGoals, getDeveloperWorkerLogin, getDeveloperWorkers, probeDeveloperWorker, replayDeveloperLearning,
  saveDeveloperWorker, startDeveloperWorkflow, streamDeveloperEvents, switchDeveloperWorker, cleanupDeveloperStorage,
  type DeveloperAssessment, type DeveloperEvent, type DeveloperOverview, type DeveloperGoal,
  type DeveloperQueueItem, type DeveloperRelease, type DeveloperStorage, type DeveloperWorkerProfile,
  type DeveloperWorkflow,
} from '../api'

type Tab = 'overview' | 'goals' | 'loop' | 'workers' | 'learning' | 'queue' | 'versions' | 'storage'
type DeveloperLoadError = { message: string; status?: number; code?: string }

const LOAD_TIMEOUT_MS = 15_000
const TERMINAL_STATES = new Set(['completed', 'canceled', 'failed', 'rolled_back'])
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
  return (
    <section className="border-y border-border bg-surface/40 px-4 py-5 sm:px-6">
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
      <div className="mt-5 h-1.5 overflow-hidden rounded bg-overlay/10">
        <div className="h-full rounded bg-accent transition-[width] duration-500" style={{ width: `${Math.max(2, workflow.progress)}%` }} />
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-muted"><span>{workflow.progress}%</span><span>{label(workflow.stage)}</span></div>
      {workflow.blocker && (
        <div className="mt-4 flex items-start gap-2 border-l-2 border-warning pl-3 text-sm text-warning">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" /><span>{workflow.blocker}</span>
        </div>
      )}
      <ApprovalGate workflow={workflow} busy={busy} onApprove={onApprove} />
    </section>
  )
}

function CodingLoop({ workflow, events, workers, busy, onSwitch }: {
  workflow: DeveloperWorkflow | null; events: DeveloperEvent[]; workers: DeveloperWorkerProfile[]
  busy: boolean; onSwitch: (slug: string) => void
}) {
  const [selectedWorker, setSelectedWorker] = useState('')
  if (!workflow) return <Empty text="No coding workflow has started." />
  const canSwitch = ['paused', 'blocked', 'failed', 'approved'].includes(workflow.state)
  const codingWorkers = workers.filter(item => item.enabled && item.adapter !== 'model_review')
  const currentWorker = workflow.worker_session
  return (
    <div className="space-y-7">
      <section className="grid gap-4 border-y border-border py-4 md:grid-cols-3">
        <div><div className="text-[11px] uppercase text-muted">Worker</div><div className="mt-1 text-sm font-medium text-text">{currentWorker?.profile_slug ?? workflow.worker_profile_slug ?? 'mc-native'}</div><div className="mt-1 text-xs text-muted">{currentWorker?.adapter ?? 'Awaiting worker'}{currentWorker?.model ? ` · ${currentWorker.model}` : ''}</div></div>
        <div><div className="text-[11px] uppercase text-muted">Bounded sprint</div><div className="mt-1 text-sm font-medium text-text">{workflow.sprint?.title ?? 'Queue workflow'}</div><div className="mt-1 text-xs text-muted">{workflow.sprint ? `Sprint ${workflow.sprint.sequence} · ${label(workflow.sprint.status)}` : 'Single approved plan'}</div></div>
        <div><div className="text-[11px] uppercase text-muted">Worker session</div><div className="mt-1 font-mono text-xs text-text">{currentWorker?.external_session_id ?? `MC-${currentWorker?.id ?? workflow.id}`}</div><div className="mt-1 text-xs text-muted">{currentWorker ? label(currentWorker.status) : 'Not started'}</div></div>
      </section>
      {canSwitch && (
        <section className="flex flex-col gap-2 border-l-2 border-accent pl-3 sm:flex-row sm:items-end">
          <label className="min-w-0 flex-1"><span className="mb-1 block text-xs text-muted">Continue from the latest checkpoint with</span><select value={selectedWorker || workflow.worker_profile_slug || 'mc-native'} onChange={event => setSelectedWorker(event.target.value)} className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent">{codingWorkers.map(worker => <option key={worker.slug} value={worker.slug}>{worker.name} · {worker.health_status}</option>)}</select></label>
          <button disabled={busy || !codingWorkers.length} onClick={() => onSwitch(selectedWorker || workflow.worker_profile_slug || 'mc-native')} className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-accent/40 px-3 text-sm text-accent disabled:opacity-40"><RotateCcw size={14} /> Switch at checkpoint</button>
        </section>
      )}
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.55fr)]">
      <section>
        <h2 className="mb-3 text-sm font-semibold text-text">Stage checklist</h2>
        <div className="border-t border-border">
          {workflow.stages.map(stage => {
            const running = stage.status === 'running'
            const complete = stage.status === 'completed'
            const failed = ['failed', 'paused'].includes(stage.status)
            const Icon = complete ? CheckCircle2 : failed ? XCircle : running ? Loader2 : Circle
            return (
              <div key={stage.node_id} className="flex min-h-14 items-center gap-3 border-b border-border/70 px-1 py-3">
                <Icon size={17} className={`${complete ? 'text-success' : failed ? 'text-danger' : running ? 'animate-spin text-accent' : 'text-muted/60'}`} />
                <div className="min-w-0 flex-1"><div className="text-sm text-text">{stage.title}</div><div className="mt-0.5 text-[11px] text-muted">{stage.attempts ? `${stage.attempts} attempt${stage.attempts === 1 ? '' : 's'}` : 'Not started'}</div></div>
                <StateBadge state={stage.status} />
              </div>
            )
          })}
        </div>
      </section>
      <section>
        <h2 className="mb-3 text-sm font-semibold text-text">Live evidence</h2>
        <div className="max-h-[560px] overflow-y-auto border-y border-border bg-background/50">
          {events.length === 0 && <div className="px-3 py-8 text-center text-xs text-muted">Waiting for workflow events.</div>}
          {events.slice(-100).map(event => (
            <div key={event.id} className="border-b border-border/60 px-3 py-2.5 last:border-0">
              <div className="flex items-center justify-between gap-3"><span className="text-xs font-medium text-text">{label(event.event_type)}</span><span className="text-[10px] text-muted">#{event.sequence}</span></div>
              <div className="mt-1 truncate font-mono text-[10px] text-muted">{JSON.stringify(event.payload)}</div>
            </div>
          ))}
        </div>
      </section>
      </div>
      <section>
        <h2 className="mb-3 text-sm font-semibold text-text">Durable checkpoints</h2>
        {!workflow.checkpoints?.length ? <Empty text="No checkpoint has been recorded yet." /> : <div className="border-t border-border">{workflow.checkpoints.map(checkpoint => {
          let handoff: Record<string, unknown> = {}
          try { handoff = JSON.parse(checkpoint.handoff_json) } catch { /* malformed legacy payload */ }
          return <details key={checkpoint.id} className="border-b border-border/70 py-3"><summary className="flex cursor-pointer list-none items-center justify-between gap-3"><div className="flex min-w-0 items-center gap-2"><CheckCircle2 size={15} className="shrink-0 text-accent" /><span className="truncate text-sm text-text">Checkpoint {checkpoint.sequence} · {label(checkpoint.status)}</span></div><span className="font-mono text-[10px] text-muted">{checkpoint.head_sha?.slice(0, 10) ?? 'dirty tree'}</span></summary><div className="mt-3 grid gap-3 pl-6 text-xs text-muted sm:grid-cols-2"><div><span className="text-text">Next action:</span> {String(handoff.next_action ?? 'Resume the recorded stage.')}</div><div><span className="text-text">Changed files:</span> {Array.isArray(handoff.changed_files) ? handoff.changed_files.length : 0}</div></div></details>
        })}</div>}
      </section>
    </div>
  )
}

function GoalsView({ goals, workers, busy, onCreate, onCommand }: {
  goals: DeveloperGoal[]; workers: DeveloperWorkerProfile[]; busy: boolean
  onCreate: (input: { title: string; objective: string; acceptance_criteria: string[]; autonomy: 'sandbox' | 'pr' | 'merge_deploy'; preferred_models: string[]; worker_profile_slug: string; reviewer_profile_slug: string }) => void
  onCommand: (id: number, command: 'pause' | 'resume' | 'cancel' | 'approve_scope') => void
}) {
  const [title, setTitle] = useState('')
  const [objective, setObjective] = useState('')
  const [criteria, setCriteria] = useState('')
  const [assessment, setAssessment] = useState<DeveloperAssessment | null>(null)
  const [assessing, setAssessing] = useState(false)
  const codingWorkers = workers.filter(item => item.enabled && item.adapter !== 'model_review')
  const reviewers = workers.filter(item => item.enabled && item.adapter === 'model_review')
  const [worker, setWorker] = useState('mc-native')
  const [reviewer, setReviewer] = useState('reviewer-default')
  const [autonomy, setAutonomy] = useState<'sandbox' | 'pr' | 'merge_deploy'>('sandbox')
  const input = () => {
    const acceptance = criteria.split('\n').map(item => item.trim()).filter(Boolean)
    return { title: title.trim(), objective: objective.trim(), acceptance_criteria: acceptance }
  }
  const assess = async () => {
    const value = input()
    if (!value.title || value.objective.length < 10 || !value.acceptance_criteria.length) return
    setAssessing(true)
    try { setAssessment(await assessDeveloperGoal(value)) } finally { setAssessing(false) }
  }
  const submit = () => {
    const value = input()
    if (!assessment || !value.title || value.objective.length < 10 || !value.acceptance_criteria.length) return
    onCreate({ ...value, autonomy, preferred_models: [], worker_profile_slug: worker, reviewer_profile_slug: reviewer })
    setTitle(''); setObjective(''); setCriteria(''); setAssessment(null)
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
      <div className="mt-4 flex flex-wrap gap-2">{!assessment ? <button onClick={assess} disabled={busy || assessing || !title.trim() || objective.trim().length < 10 || !criteria.trim()} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background disabled:opacity-40">{assessing ? <Loader2 size={15} className="animate-spin" /> : <TestTube2 size={15} />} Assess scope</button> : <><button onClick={submit} disabled={busy} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background disabled:opacity-40"><Plus size={15} /> Queue bounded sprints</button><button onClick={() => setAssessment(null)} className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm text-text"><RotateCcw size={14} /> Reassess</button></>}</div>
    </section>
    <section><h2 className="mb-3 text-sm font-semibold text-text">Development goals</h2>{!goals.length ? <Empty text="No continuous development goals have been created." /> : <div className="border-t border-border">{goals.map(goal => {
      const resumable = ['paused', 'blocked', 'awaiting_config'].includes(goal.status)
      const awaitingScope = goal.status === 'awaiting_scope_approval'
      const active = !['completed', 'qualified_local', 'canceled'].includes(goal.status)
      return <div key={goal.id} className="grid gap-3 border-b border-border/70 py-4 lg:grid-cols-[minmax(0,1fr)_180px_240px] lg:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="font-medium text-text">{goal.title}</span><StateBadge state={goal.status} /></div><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{goal.objective}</p>{goal.last_error && <div className="mt-1 text-xs text-warning">{label(goal.last_error)}</div>}</div><div className="text-xs text-muted">Iteration {goal.iteration_count}/{goal.max_iterations}<br />{goal.worker_profile_slug ?? 'mc-native'} · {label(goal.autonomy)}</div><div className="flex flex-wrap justify-start gap-2 lg:justify-end">{awaitingScope && <button disabled={busy} onClick={() => onCommand(goal.id, 'approve_scope')} className="inline-flex h-8 items-center gap-1 rounded-md bg-warning px-2 text-xs font-medium text-background"><ShieldCheck size={13} /> Approve scope</button>}{resumable && <button disabled={busy} onClick={() => onCommand(goal.id, 'resume')} className="inline-flex h-8 items-center gap-1 rounded-md bg-accent px-2 text-xs text-background"><Play size={13} /> Resume</button>}{active && !resumable && !awaitingScope && <button disabled={busy} onClick={() => onCommand(goal.id, 'pause')} className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-2 text-xs text-text"><Pause size={13} /> Pause</button>}{active && <button disabled={busy} onClick={() => onCommand(goal.id, 'cancel')} className="inline-flex h-8 items-center gap-1 rounded-md border border-danger/40 px-2 text-xs text-danger"><Square size={12} /> Cancel</button>}</div></div>
    })}</div>}</section>
  </div>
}

function WorkersView({ workers, busy, onSave, onProbe, onLogin }: {
  workers: DeveloperWorkerProfile[]; busy: boolean
  onSave: (slug: string, profile: DeveloperWorkerProfile) => void
  onProbe: (slug: string) => void
  onLogin: (slug: string) => void
}) {
  const [slug, setSlug] = useState(workers[0]?.slug ?? 'mc-native')
  const selected = workers.find(item => item.slug === slug) ?? workers[0]
  const [draft, setDraft] = useState<DeveloperWorkerProfile | null>(selected ?? null)
  useEffect(() => { if (selected) setDraft(selected) }, [selected])
  if (!draft) return <Empty text="No coding worker profiles are configured." />
  const update = <K extends keyof DeveloperWorkerProfile>(key: K, value: DeveloperWorkerProfile[K]) =>
    setDraft(current => current ? { ...current, [key]: value } : current)
  return <div className="space-y-7">
    <section className="grid gap-4 border-y border-border py-5 lg:grid-cols-[240px_minmax(0,1fr)]">
      <div><label><span className="mb-1 block text-xs text-muted">Worker profile</span><select value={slug} onChange={event => setSlug(event.target.value)} className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text">{workers.map(worker => <option key={worker.slug} value={worker.slug}>{worker.name}</option>)}</select></label><div className="mt-3 flex items-center gap-2"><StateBadge state={draft.health_status} /><span className="text-xs text-muted">{draft.health_detail ?? 'Not probed yet.'}</span></div>{draft.runner_mode && <div className="mt-2 text-[11px] text-muted">Execution boundary: {draft.runner_mode === 'service' ? 'supervised runner service' : 'local isolated process'}</div>}</div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label><span className="mb-1 block text-xs text-muted">Name</span><input value={draft.name} onChange={event => update('name', event.target.value)} className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text" /></label>
        <label><span className="mb-1 block text-xs text-muted">Adapter</span><select value={draft.adapter} onChange={event => update('adapter', event.target.value as DeveloperWorkerProfile['adapter'])} className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text"><option value="native">MC Native</option><option value="codex">Codex CLI</option><option value="opencode">OpenCode CLI</option><option value="hermes">Hermes CLI</option><option value="model_review">Model reviewer</option></select></label>
        <label><span className="mb-1 block text-xs text-muted">Model ID</span><input value={draft.model} onChange={event => update('model', event.target.value)} placeholder="Blank uses Models routing" className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text" /></label>
        <label><span className="mb-1 block text-xs text-muted">Authentication</span><select value={draft.auth_mode} onChange={event => { const auth = event.target.value as DeveloperWorkerProfile['auth_mode']; setDraft(current => current ? { ...current, auth_mode: auth, credential_env: auth === 'vault_env' ? current.credential_env : '' } : current) }} className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text"><option value="inherited">Models / inherited</option><option value="native_login">Native agent login</option><option value="vault_env">Vault environment secret</option></select></label>
        <label><span className="mb-1 block text-xs text-muted">Vault environment name</span><input disabled={draft.auth_mode !== 'vault_env'} value={draft.auth_mode === 'vault_env' ? draft.credential_env : ''} onChange={event => update('credential_env', event.target.value.toUpperCase())} placeholder={draft.auth_mode === 'vault_env' ? 'ZAI_API_KEY' : 'Only used for Vault authentication'} className="h-10 w-full rounded-md border border-border bg-background px-3 font-mono text-sm text-text disabled:cursor-not-allowed disabled:opacity-50" /></label>
        <label className="flex h-10 items-center gap-2 self-end border-y border-border px-2"><input type="checkbox" checked={draft.enabled} onChange={event => update('enabled', event.target.checked)} /><span className="text-sm text-text">Enabled for new sprints</span></label>
      </div>
    </section>
    <div className="flex flex-wrap gap-2"><button disabled={busy} onClick={() => onSave(draft.slug, draft)} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background disabled:opacity-40"><Save size={14} /> Save profile</button><button disabled={busy} onClick={() => onProbe(draft.slug)} className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm text-text disabled:opacity-40"><TestTube2 size={14} /> Test worker</button>{draft.auth_mode === 'native_login' && <button disabled={busy} onClick={() => onLogin(draft.slug)} className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm text-text disabled:opacity-40"><KeyRound size={14} /> Login instructions</button>}</div>
    <section><h2 className="mb-3 text-sm font-semibold text-text">Worker availability</h2><div className="border-t border-border">{workers.map(worker => <div key={worker.slug} className="grid gap-2 border-b border-border/70 py-3 sm:grid-cols-[minmax(0,1fr)_190px_140px] sm:items-center"><div><div className="flex items-center gap-2"><Bot size={14} className="text-accent" /><span className="text-sm text-text">{worker.name}</span></div><div className="mt-1 text-xs text-muted">{worker.slug} · {worker.model || 'Models route'}</div></div><div className="text-xs text-muted">{label(worker.adapter)} · {label(worker.auth_mode)}{worker.runner_mode ? ` · ${label(worker.runner_mode)}` : ''}</div><div className="sm:text-right"><StateBadge state={worker.health_status} /></div></div>)}</div></section>
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

function QueueView({ items, busy, onStart }: { items: DeveloperQueueItem[]; busy: boolean; onStart: (id: number) => void }) {
  return (
    <div className="overflow-x-auto border-y border-border">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="bg-overlay/5 text-[11px] uppercase text-muted"><tr><th className="px-3 py-3">Item</th><th className="px-3 py-3">State</th><th className="px-3 py-3">Risk</th><th className="px-3 py-3">Time</th><th className="w-28 px-3 py-3 text-right">Action</th></tr></thead>
        <tbody>
          {items.map(item => {
            let deps: number[] = []
            try { deps = JSON.parse(item.dependencies_json) } catch { /* ignore */ }
            const canStart = item.status === 'planned'
            return (
              <tr key={item.id} className="border-t border-border/70 align-top">
                <td className="px-3 py-4"><div className="font-medium text-text">#{item.queue_id} {item.title}</div><div className="mt-1 text-xs text-muted">{deps.length ? `After ${deps.map(id => `#${id}`).join(', ')}` : item.plan_path}</div></td>
                <td className="px-3 py-4"><StateBadge state={item.status} /></td>
                <td className="px-3 py-4 text-xs text-muted">{label(item.risk)}</td>
                <td className="px-3 py-4 text-xs text-muted">{item.queue_effort ?? '—'}</td>
                <td className="px-3 py-4 text-right">
                  {canStart ? <button disabled={busy} onClick={() => onStart(item.queue_id)} title={`Start queue item ${item.queue_id}`}
                    className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-2.5 text-xs font-medium text-background disabled:opacity-40"><Play size={13} /> Start</button>
                    : <span className="text-xs text-muted">{label(item.status)}</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function VersionsView({ releases }: { releases: DeveloperRelease[] }) {
  if (!releases.length) return <Empty text="No version has been reserved." />
  return <div className="border-t border-border">{releases.map(release => (
    <div key={release.id} className="grid gap-2 border-b border-border/70 py-4 sm:grid-cols-[120px_1fr_150px] sm:items-center">
      <div className="font-mono text-sm font-semibold text-text">v{release.version}</div>
      <div><div className="text-sm text-text">Queue #{release.queue_item ?? '—'}</div><div className="mt-1 text-xs text-muted">{release.commit_sha?.slice(0, 12) ?? 'Commit pending'} · {release.source}</div></div>
      <div className="sm:text-right"><StateBadge state={release.status} /></div>
    </div>
  ))}</div>
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

export default function Developer() {
  const { toast } = useToast()
  const vaultSession = useVaultSession()
  const [tab, setTab] = useState<Tab>('overview')
  const [overview, setOverview] = useState<DeveloperOverview | null>(null)
  const [queue, setQueue] = useState<DeveloperQueueItem[]>([])
  const [releases, setReleases] = useState<DeveloperRelease[]>([])
  const [storage, setStorage] = useState<DeveloperStorage | null>(null)
  const [goals, setGoals] = useState<DeveloperGoal[]>([])
  const [workers, setWorkers] = useState<DeveloperWorkerProfile[]>([])
  const [learning, setLearning] = useState<{ records: Array<Record<string, unknown>>; playbooks: Array<Record<string, unknown>> }>({ records: [], playbooks: [] })
  const [events, setEvents] = useState<DeveloperEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<DeveloperLoadError | null>(null)
  const lastSequence = useRef(0)
  const loadController = useRef<AbortController | null>(null)

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
      setOverview(o); setQueue(q.items); setReleases(v.releases); setStorage(s); setGoals(g.goals)
      setWorkers(w.workers); setLearning(learn); setError(null)
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
  useEffect(() => { if (vaultSession) load(true) }, [vaultSession, load])

  const active = overview?.active_workflow ?? overview?.workflows[0] ?? null
  useEffect(() => {
    if (!active?.id) return
    lastSequence.current = 0
    setEvents([])
    const controller = new AbortController()
    streamDeveloperEvents(active.id, lastSequence.current, event => {
      lastSequence.current = Math.max(lastSequence.current, event.sequence)
      setEvents(current => [...current.filter(item => item.id !== event.id), event].slice(-200))
      load(true)
    }, controller.signal).catch(err => { if (err?.name !== 'AbortError') load(true) })
    return () => controller.abort()
  }, [active?.id, load])

  const act = async (fn: () => Promise<unknown>, success: string) => {
    setBusy(true)
    try { await fn(); toast({ kind: 'success', title: success }); await load(true) }
    catch (err) { toast({ kind: 'error', title: 'Developer action stopped', detail: err instanceof Error ? err.message : String(err) }) }
    finally { setBusy(false) }
  }
  const workerAction = async (fn: () => Promise<DeveloperWorkerProfile>, success: string) => {
    setBusy(true)
    try {
      const updated = await fn()
      setWorkers(current => current.map(item => item.slug === updated.slug ? { ...item, ...updated } : item))
      toast({ kind: 'success', title: success })
    } catch (err) {
      toast({ kind: 'error', title: 'Worker action stopped', detail: err instanceof Error ? err.message : String(err) })
    } finally { setBusy(false) }
  }
  const command = (cmd: 'pause' | 'resume' | 'cancel' | 'retry') => active && act(() => commandDeveloperWorkflow(active.id, cmd), `Workflow ${cmd} accepted`)
  const approve = (purpose: 'special_paths' | 'merge_deploy', master: string) => active && act(() => approveDeveloperWorkflow(active.id, purpose, master), 'Approval accepted')
  const createGoal = (input: Parameters<typeof createDeveloperGoal>[0]) => act(() => createDeveloperGoal(input), 'Development goal queued')
  const goalCommand = (id: number, cmd: 'pause' | 'resume' | 'cancel' | 'approve_scope') => act(() => commandDeveloperGoal(id, cmd), `Goal ${label(cmd)} accepted`)
  const switchWorker = (slug: string) => active && act(() => switchDeveloperWorker(active.id, slug), `Worker switched to ${slug}`)
  const saveWorker = (slug: string, profile: DeveloperWorkerProfile) => workerAction(() => saveDeveloperWorker(slug, {
    name: profile.name, adapter: profile.adapter, model: profile.model, auth_mode: profile.auth_mode,
    credential_env: profile.auth_mode === 'vault_env' ? profile.credential_env : '',
    reviewer_profile: profile.reviewer_profile,
    enabled: profile.enabled, config: profile.config,
  }), 'Worker profile saved')
  const probeWorker = (slug: string) => workerAction(() => probeDeveloperWorker(slug), `Worker ${slug} tested`)
  const loginWorker = async (slug: string) => {
    setBusy(true)
    try {
      const result = await getDeveloperWorkerLogin(slug)
      toast({ kind: 'info', title: result.interactive_required ? 'Runner login required' : 'Worker authentication', detail: result.command ? `${result.command.join(' ')} · ${result.detail}` : result.detail })
    } catch (err) { toast({ kind: 'error', title: 'Login instructions unavailable', detail: err instanceof Error ? err.message : String(err) }) }
    finally { setBusy(false) }
  }
  const replayLearning = () => act(() => replayDeveloperLearning(), 'Learning replay completed')

  const capabilities = useMemo(() => Object.entries(overview?.policy.capabilities ?? {}), [overview])
  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' }, { id: 'goals', label: 'Goals' }, { id: 'loop', label: 'Coding Loop' },
    { id: 'workers', label: 'Workers' }, { id: 'learning', label: 'Learning' }, { id: 'queue', label: 'Queue' },
    { id: 'versions', label: 'Versions' }, { id: 'storage', label: 'Storage' },
  ]

  return (
    <div className="relative min-h-full"><AmbientField tone="rgb(var(--accent))" variant="grid" />
      <header className="border-b border-border px-4 py-5 sm:px-6">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-md border border-accent/30 bg-accent/10 text-accent"><Code2 size={19} /></div><div><h1 className="text-xl font-semibold text-text">Developer</h1><p className="mt-0.5 text-xs text-muted">Controlled self-development</p></div></div>
          <button onClick={() => load()} disabled={loading} title="Refresh Developer state" className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm text-text hover:bg-overlay/5 disabled:opacity-50"><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh</button>
        </div>
      </header>

      <div className="border-b border-border px-4 sm:px-6"><div className="flex overflow-x-auto">{tabs.map(item => <button key={item.id} onClick={() => setTab(item.id)} className={`h-11 shrink-0 border-b-2 px-3 text-sm transition-colors ${tab === item.id ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-text'}`}>{item.label}</button>)}</div></div>

      {loading && !overview ? <div className="flex min-h-72 items-center justify-center text-muted"><Loader2 className="animate-spin" size={22} /></div>
        : error?.status === 401 ? <div className="mx-4 mt-6 sm:mx-6"><VaultUnlockPanel mode="inline" title="Unlock Developer"
          detail="Authorize protected coding workflows here. The same session immediately unlocks Integrations, Models, and MCP." /></div>
        : error ? <div className="mx-4 mt-6 border-l-2 border-danger bg-danger/5 px-4 py-4 sm:mx-6"><div className="flex items-start gap-3"><AlertTriangle size={17} className="mt-0.5 shrink-0 text-danger" /><div className="min-w-0 flex-1"><div className="text-sm font-semibold text-heading">{error.code === 'backend_mismatch' ? 'Mission Control backend update required' : 'Developer data unavailable'}</div><p className="mt-1 text-xs leading-5 text-muted">{error.message}</p><button onClick={() => load()} className="mt-3 inline-flex h-8 items-center gap-2 rounded-md border border-border px-2.5 text-xs text-text hover:bg-overlay/5"><RefreshCw size={13} /> Retry</button></div></div></div>
        : <>
          {active && (tab === 'overview' || tab === 'loop') && <WorkflowHeader workflow={active} busy={busy} onCommand={command} onApprove={approve} />}
          <main className="px-4 py-6 sm:px-6">
            {tab === 'overview' && <div className="space-y-8">
              {!active && <Empty text="Select an eligible queue item to begin a controlled workflow." />}
              <section><h2 className="mb-3 text-sm font-semibold text-text">Runtime gates</h2><div className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 lg:grid-cols-5">{capabilities.map(([name, enabled]) => <div key={name} className="flex items-center justify-between bg-surface px-3 py-3"><span className="text-xs text-muted">{label(name)}</span>{enabled ? <CheckCircle2 size={15} className="text-success" /> : <Circle size={15} className="text-muted/50" />}</div>)}</div></section>
              <section><h2 className="mb-3 text-sm font-semibold text-text">Control-plane status</h2><div className="grid gap-4 sm:grid-cols-3"><div className="border-l-2 border-accent pl-3"><div className="text-xs text-muted">Policy</div><div className="mt-1 font-mono text-sm text-text">v{overview?.policy.version} · {overview?.policy.hash.slice(0, 10)}</div></div><div className="border-l-2 border-border pl-3"><div className="text-xs text-muted">GitHub App</div><div className="mt-1 text-sm text-text">{overview?.policy.github_configured ? 'Configured' : 'Not configured'}</div></div><div className="border-l-2 border-border pl-3"><div className="text-xs text-muted">Deployment</div><div className="mt-1 text-sm text-text">{overview?.policy.deployment_configured ? 'Configured' : 'Not configured'}</div></div></div></section>
            </div>}
            {tab === 'loop' && <CodingLoop workflow={active} events={events} workers={workers} busy={busy} onSwitch={switchWorker} />}
            {tab === 'goals' && <GoalsView goals={goals} workers={workers} busy={busy} onCreate={createGoal} onCommand={goalCommand} />}
            {tab === 'workers' && <WorkersView workers={workers} busy={busy} onSave={saveWorker} onProbe={probeWorker} onLogin={loginWorker} />}
            {tab === 'learning' && <LearningView state={learning} busy={busy} onReplay={replayLearning} />}
            {tab === 'queue' && <QueueView items={queue} busy={busy} onStart={id => act(() => startDeveloperWorkflow(id), `Queue #${id} started`)} />}
            {tab === 'versions' && <VersionsView releases={releases} />}
            {tab === 'storage' && <StorageView storage={storage} busy={busy} onCleanup={master => act(() => cleanupDeveloperStorage(master), 'Developer cleanup completed')} />}
          </main>
        </>}
    </div>
  )
}
