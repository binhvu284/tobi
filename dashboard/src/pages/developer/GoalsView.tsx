// Extracted from Developer.tsx (pre-#21 refactor) — verbatim move.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, Archive, BookOpen, CheckCircle2, Circle, Clock3, Code2, Download, ExternalLink,
  ChevronDown, ChevronUp, GitBranch, Github, HardDrive, KeyRound, ListTree, Loader2, MoreHorizontal, Pause, Play, Plus, Radio, RefreshCw,
  RotateCcw, Save, ScrollText, ShieldCheck, Square, Target,
  TerminalSquare, TestTube2, Trash2, Upload, WifiOff, Wrench, XCircle,
} from 'lucide-react'
import type { AvailableModel, LlmProvider } from '../../api.chat'
import { approveDeveloperWorkflow, assessDeveloperGoal, commandDeveloperGoal, commandDeveloperWorkflow, createDeveloperGoal, getDeveloperHistory, getDeveloperLearning, getDeveloperOverview, getDeveloperQueue, getDeveloperStorage, getDeveloperVersions, getDeveloperGoals, getDeveloperWorkerLogin, getDeveloperWorkerModels, getDeveloperWorkers, probeDeveloperWorker, replayDeveloperLearning, saveDeveloperWorker, startDeveloperWorkflow, streamDeveloperEvents, switchDeveloperWorker, cleanupDeveloperStorage, rejectDeveloperWorkflow, setDeveloperProcessSettings, type DeveloperAssessment, type DeveloperEvent, type DeveloperOverview, type DeveloperGoal, type DeveloperQueueItem, type DeveloperQueueState, type DeveloperRelease, type DeveloperStorage, type DeveloperWorkerLogin, type DeveloperWorkerModels, type DeveloperWorkerProfile, type DeveloperWorkflow } from '../../api.developer'
import { Empty, StateBadge, label } from './format'

export function GoalsView({ goals, workers, busy, onCreate, onCommand }: {
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
