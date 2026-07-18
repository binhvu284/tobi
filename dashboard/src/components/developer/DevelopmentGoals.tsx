import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  MoreHorizontal, Pause, Play, Plus, RotateCcw, ShieldCheck, Square,
  Target, TestTube2, Trash2, X, Loader2,
} from 'lucide-react'
import { assessDeveloperGoal, type DeveloperAssessment, type DeveloperGoal, type DeveloperWorkerProfile } from '../../api'

export type GoalCommand = 'pause' | 'resume' | 'reattempt' | 'cancel' | 'delete' | 'approve_scope'

const FINAL_STATES = new Set(['completed', 'qualified_local', 'canceled'])
const ACTIVE_STATES = new Set(['queued', 'running', 'retrying', 'awaiting_approval'])

function label(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function GoalStatus({ status }: { status: string }) {
  const color = status === 'running' || status === 'retrying'
    ? 'border-accent/30 bg-accent/10 text-accent'
    : status === 'completed' || status === 'qualified_local'
      ? 'border-success/30 bg-success/10 text-success'
      : status === 'blocked' || status === 'paused' || status.startsWith('awaiting_')
        ? 'border-warning/30 bg-warning/10 text-warning'
        : status === 'canceled'
          ? 'border-border bg-overlay/5 text-muted'
          : 'border-border bg-overlay/5 text-text'
  return <span className={`inline-flex rounded border px-2 py-0.5 text-[10px] font-medium ${color}`}>{label(status)}</span>
}

function GoalMenu({ goal, busy, onCommand }: {
  goal: DeveloperGoal; busy: boolean
  onCommand: (id: number, command: GoalCommand) => Promise<boolean>
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const resumable = ['paused', 'blocked', 'awaiting_config'].includes(goal.status)
  const reattemptable = ['paused', 'blocked', 'awaiting_config', 'canceled', 'completed', 'qualified_local'].includes(goal.status)
  const cancellable = !FINAL_STATES.has(goal.status) && goal.status !== 'canceled'
  const deletable = !ACTIVE_STATES.has(goal.status) && goal.status !== 'awaiting_scope_approval'
  const action = async (command: GoalCommand) => {
    if (command === 'delete' && !window.confirm(`Delete "${goal.title}" from Development goals? Its audit history remains stored.`)) return
    setOpen(false)
    await onCommand(goal.id, command)
  }
  const items: Array<{ command: GoalCommand; label: string; icon: typeof Play; danger?: boolean }> = []
  if (goal.status === 'awaiting_scope_approval') items.push({ command: 'approve_scope', label: 'Approve scope', icon: ShieldCheck })
  if (resumable) items.push({ command: 'resume', label: 'Resume', icon: Play })
  if (reattemptable) items.push({ command: 'reattempt', label: 'Re-attempt as new goal', icon: RotateCcw })
  if (ACTIVE_STATES.has(goal.status)) items.push({ command: 'pause', label: 'Pause', icon: Pause })
  if (cancellable) items.push({ command: 'cancel', label: 'Cancel', icon: Square, danger: true })
  if (deletable) items.push({ command: 'delete', label: 'Delete', icon: Trash2, danger: true })

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        title="Goal actions"
        aria-label={`Actions for ${goal.title}`}
        onClick={() => setOpen(value => !value)}
        disabled={busy}
        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text disabled:opacity-40"
      >
        <MoreHorizontal size={17} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 z-30 mt-1 w-52 rounded-md border border-border bg-surface p-1 shadow-2xl"
          >
            {items.map(item => {
              const Icon = item.icon
              return (
                <button
                  key={item.command}
                  type="button"
                  onClick={() => void action(item.command)}
                  className={`flex h-9 w-full items-center gap-2 rounded px-2 text-left text-xs hover:bg-overlay/10 ${item.danger ? 'text-danger' : 'text-text'}`}
                >
                  <Icon size={14} /> {item.label}
                </button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function GoalDialog({ workers, busy, open, onClose, onCreate }: {
  workers: DeveloperWorkerProfile[]; busy: boolean; open: boolean; onClose: () => void
  onCreate: (input: {
    title: string; objective: string; acceptance_criteria: string[]
    autonomy: 'sandbox' | 'pr' | 'merge_deploy'; preferred_models: string[]
    worker_profile_slug: string; reviewer_profile_slug: string
  }) => Promise<boolean>
}) {
  const [title, setTitle] = useState('')
  const [objective, setObjective] = useState('')
  const [criteria, setCriteria] = useState('')
  const [assessment, setAssessment] = useState<DeveloperAssessment | null>(null)
  const [assessing, setAssessing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const codingAgents = workers.filter(item => item.enabled && item.adapter !== 'model_review' && item.adapter !== 'hermes')
  const reviewers = workers.filter(item => item.enabled && item.adapter === 'model_review')
  const [agent, setAgent] = useState('mc-native')
  const [reviewer, setReviewer] = useState('reviewer-default')
  const [autonomy, setAutonomy] = useState<'sandbox' | 'pr' | 'merge_deploy'>('sandbox')

  useEffect(() => {
    if (!codingAgents.some(item => item.slug === agent)) setAgent(codingAgents[0]?.slug ?? '')
    if (!reviewers.some(item => item.slug === reviewer)) setReviewer(reviewers[0]?.slug ?? '')
  }, [workers, agent, reviewer])
  useEffect(() => {
    if (!open) return
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !submitting) onClose() }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [open, submitting, onClose])

  const values = () => ({
    title: title.trim(),
    objective: objective.trim(),
    acceptance_criteria: criteria.split('\n').map(item => item.trim()).filter(Boolean),
  })
  const assess = async () => {
    setAssessing(true); setError(null)
    try { setAssessment(await assessDeveloperGoal(values())) }
    catch (err) { setError(err instanceof Error ? err.message : String(err)) }
    finally { setAssessing(false) }
  }
  const submit = async () => {
    if (!assessment || !agent || !reviewer) return
    setSubmitting(true); setError(null)
    try {
      const saved = await onCreate({ ...values(), autonomy, preferred_models: [], worker_profile_slug: agent, reviewer_profile_slug: reviewer })
      if (saved) {
        setTitle(''); setObjective(''); setCriteria(''); setAssessment(null); onClose()
      } else setError('The goal was not saved. Your draft remains available.')
    } finally { setSubmitting(false) }
  }
  const valid = title.trim().length >= 3 && objective.trim().length >= 10 && criteria.trim().length > 0

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-3 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.section
            role="dialog" aria-modal="true" aria-labelledby="new-goal-title"
            initial={{ opacity: 0, y: 12, scale: 0.985 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.985 }}
            transition={{ duration: 0.16 }}
            className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-lg border border-border bg-surface shadow-2xl"
          >
            <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-surface/95 px-5 py-4 backdrop-blur">
              <div><h2 id="new-goal-title" className="font-semibold text-text">New development goal</h2><p className="mt-0.5 text-xs text-muted">Scope it first, then queue bounded implementation sprints.</p></div>
              <button onClick={onClose} disabled={submitting} title="Close" className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text"><X size={17} /></button>
            </header>
            <div className="space-y-5 px-5 py-5">
              <label className="block"><span className="mb-1.5 block text-xs text-muted">Goal title</span><input autoFocus value={title} onChange={event => { setTitle(event.target.value); setAssessment(null) }} placeholder="Improve Agent runtime reliability" className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent" /></label>
              <label className="block"><span className="mb-1.5 block text-xs text-muted">Objective</span><textarea value={objective} onChange={event => { setObjective(event.target.value); setAssessment(null) }} rows={3} placeholder="Describe the outcome, scope, and boundaries." className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm text-text outline-none focus:border-accent" /></label>
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(240px,0.8fr)]">
                <label><span className="mb-1.5 block text-xs text-muted">Acceptance criteria, one per line</span><textarea value={criteria} onChange={event => { setCriteria(event.target.value); setAssessment(null) }} rows={7} placeholder={'Focused tests pass\nNo Chat regression\nRecovery survives restart'} className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm text-text outline-none focus:border-accent" /></label>
                <div className="space-y-3">
                  <label className="block"><span className="mb-1.5 block text-xs text-muted">Autonomy</span><select value={autonomy} onChange={event => setAutonomy(event.target.value as typeof autonomy)} className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text"><option value="sandbox">Local sandbox only</option><option value="pr">Create draft pull request</option><option value="merge_deploy">Owner-gated merge and deploy</option></select></label>
                  <label className="block"><span className="mb-1.5 block text-xs text-muted">Development agent</span><select value={agent} onChange={event => setAgent(event.target.value)} className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text">{codingAgents.map(item => <option key={item.slug} value={item.slug}>{item.name} - {label(item.health_status)}</option>)}</select></label>
                  <label className="block"><span className="mb-1.5 block text-xs text-muted">Independent reviewer</span><select value={reviewer} onChange={event => setReviewer(event.target.value)} className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-text">{reviewers.map(item => <option key={item.slug} value={item.slug}>{item.name}</option>)}</select></label>
                </div>
              </div>
              {assessment && <div className="border-y border-border py-4"><div className="flex flex-wrap items-center gap-2"><GoalStatus status={assessment.route} /><GoalStatus status={assessment.risk} /><span className="text-xs text-muted">Capability {assessment.score}/100 - {assessment.sprints.length} sprint{assessment.sprints.length === 1 ? '' : 's'}</span></div><div className="mt-3 grid gap-3 sm:grid-cols-2">{assessment.sprints.map(sprint => <div key={sprint.sequence} className="border-l-2 border-accent/40 pl-3"><div className="text-sm text-text">{sprint.title}</div><div className="mt-1 text-[11px] text-muted">{sprint.budget.max_files} files - {sprint.budget.max_changed_lines} lines - {sprint.budget.max_minutes} min</div></div>)}</div></div>}
              {error && <div className="border-l-2 border-danger pl-3 text-xs text-danger">{error}</div>}
            </div>
            <footer className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t border-border bg-surface/95 px-5 py-4 backdrop-blur">
              {assessment ? <><button onClick={() => setAssessment(null)} disabled={submitting} className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm text-text"><RotateCcw size={14} /> Reassess</button><button onClick={() => void submit()} disabled={busy || submitting || !agent || !reviewer} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background disabled:opacity-40">{submitting ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} Save and queue</button></> : <button onClick={() => void assess()} disabled={busy || assessing || !valid} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background disabled:opacity-40">{assessing ? <Loader2 size={15} className="animate-spin" /> : <TestTube2 size={15} />} Assess scope</button>}
            </footer>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export default function DevelopmentGoals({ goals, workers, busy, onCreate, onCommand }: {
  goals: DeveloperGoal[]; workers: DeveloperWorkerProfile[]; busy: boolean
  onCreate: Parameters<typeof GoalDialog>[0]['onCreate']
  onCommand: (id: number, command: GoalCommand) => Promise<boolean>
}) {
  const [dialogOpen, setDialogOpen] = useState(false)
  return (
    <div className="mx-auto max-w-6xl pb-8">
      <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div><div className="flex items-center gap-2"><Target size={17} className="text-accent" /><h2 className="text-base font-semibold text-text">Development goals</h2></div><p className="mt-1 text-xs text-muted">Each goal is assessed, split into bounded sprints, and kept resumable.</p></div>
        <button onClick={() => setDialogOpen(true)} className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background hover:brightness-110"><Plus size={15} /> New goal</button>
      </header>
      {!goals.length ? <div className="border-y border-border py-14 text-center"><Target size={22} className="mx-auto text-muted" /><div className="mt-3 text-sm text-text">No development goals yet</div><button onClick={() => setDialogOpen(true)} className="mt-3 text-xs text-accent hover:underline">Create the first goal</button></div> : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full min-w-[760px] border-collapse text-left">
            <thead className="bg-overlay/5 text-[10px] font-medium uppercase text-muted"><tr><th className="px-4 py-3">Goal</th><th className="px-3 py-3">Agent</th><th className="px-3 py-3">Progress</th><th className="px-3 py-3">Status</th><th className="w-24 px-3 py-3 text-right">Actions</th></tr></thead>
            <tbody>{goals.map(goal => {
              const live = ['running', 'retrying'].includes(goal.status)
              return <tr key={goal.id} className="border-t border-border/70 bg-surface/30 hover:bg-overlay/5"><td className="max-w-md px-4 py-3.5"><div className={`truncate text-sm font-medium ${live ? 'developer-goal-live' : 'text-text'}`}>{goal.title}</div><div className="mt-1 line-clamp-1 text-[11px] text-muted">{goal.objective}</div>{goal.last_error && <div className="mt-1 text-[10px] text-warning">{label(goal.last_error)}</div>}</td><td className="px-3 py-3.5 text-xs text-muted">{workers.find(item => item.slug === goal.worker_profile_slug)?.name ?? goal.worker_profile_slug ?? 'MC Native'}</td><td className="px-3 py-3.5"><div className="text-xs tabular-nums text-text">{goal.iteration_count}/{goal.max_iterations}</div><div className="mt-1 h-1 w-20 overflow-hidden rounded bg-overlay/10"><div className={`h-full rounded bg-accent ${live ? 'developer-progress-live' : ''}`} style={{ width: `${Math.max(4, Math.min(100, goal.iteration_count / Math.max(1, goal.max_iterations) * 100))}%` }} /></div></td><td className="px-3 py-3.5"><GoalStatus status={goal.status} /></td><td className="px-3 py-3.5"><div className="flex justify-end gap-1">{live && <button title="Pause goal" aria-label={`Pause ${goal.title}`} disabled={busy} onClick={() => void onCommand(goal.id, 'pause')} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-warning hover:bg-warning/10 disabled:opacity-40"><Pause size={14} /></button>}<GoalMenu goal={goal} busy={busy} onCommand={onCommand} /></div></td></tr>
            })}</tbody>
          </table>
        </div>
      )}
      <GoalDialog workers={workers} busy={busy} open={dialogOpen} onClose={() => setDialogOpen(false)} onCreate={onCreate} />
    </div>
  )
}
