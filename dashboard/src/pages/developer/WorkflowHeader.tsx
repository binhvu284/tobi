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
import { StateBadge, TERMINAL_STATES, label } from '../../components/developer/format'

export function DeveloperSkeleton() {
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

export function WorkflowActions({ workflow, busy, onCommand }: {
  workflow: DeveloperWorkflow; busy: boolean
  onCommand: (command: 'pause' | 'resume' | 'cancel' | 'retry' | 'sync_delivery') => void
}) {
  const active = !TERMINAL_STATES.has(workflow.state)
  const retryBlocked = ['repeated_failure', 'validation_infrastructure_failed'].includes(workflow.error_code || '')
  const resumable = ['paused', 'blocked', 'failed', 'approved'].includes(workflow.state) && !retryBlocked
  const awaitingOwnerMerge = workflow.state === 'awaiting_owner_merge'
  return (
    <div className="flex flex-wrap gap-2">
      {awaitingOwnerMerge && (
        <button onClick={() => onCommand('sync_delivery')} disabled={busy} title="Synchronize GitHub delivery"
          className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background hover:brightness-110 disabled:opacity-50">
          <RefreshCw size={15} /> Sync status
        </button>
      )}
      {active && !resumable && !awaitingOwnerMerge && workflow.state !== 'awaiting_merge_deploy_approval' && (
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

export function ApprovalGate({ workflow, busy, onApprove }: {
  workflow: DeveloperWorkflow; busy: boolean
  onApprove: (purpose: 'special_paths' | 'merge_deploy', master: string) => void
}) {
  const required = workflow.state === 'awaiting_merge_deploy_approval'
    ? 'merge_deploy'
    : workflow.error_code === 'special_approval_required' ? 'special_paths' : null
  const [master, setMaster] = useState('')
  if (!required) return null
  const deploymentIncluded = required === 'merge_deploy'
    && String(workflow.blocker ?? '').toLowerCase().includes('merge and deploy')
  return (
    <section className="mt-5 border-l-2 border-warning bg-warning/5 px-4 py-4">
      <div className="flex items-start gap-3">
        <KeyRound size={18} className="mt-0.5 shrink-0 text-warning" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-text">
            {required === 'merge_deploy'
              ? deploymentIncluded ? 'Merge and deployment approval' : 'Merge approval'
              : 'Protected-path approval'}
          </h3>
          <p className="mt-1 text-xs leading-5 text-muted">
            {required === 'merge_deploy'
              ? deploymentIncluded
                ? `Approve squash merge of ${workflow.branch ?? 'the feature branch'} and immediate deployment with rollback.`
                : `Approve squash merge of ${workflow.branch ?? 'the feature branch'}. Deployment is disabled by reviewed policy.`
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

export function WorkflowHeader({ workflow, busy, onCommand, onApprove }: {
  workflow: DeveloperWorkflow; busy: boolean
  onCommand: (command: 'pause' | 'resume' | 'cancel' | 'retry' | 'sync_delivery') => void
  onApprove: (purpose: 'special_paths' | 'merge_deploy', master: string) => void
}) {
  const stopped = TERMINAL_STATES.has(workflow.state) || ['paused', 'blocked', 'failed', 'awaiting_owner_merge', 'awaiting_merge_deploy_approval'].includes(workflow.state)
  const ownerAction = workflow.state === 'awaiting_merge_deploy_approval'
    ? 'Review and approve the merge and deployment gate.'
    : workflow.state === 'awaiting_owner_merge'
      ? 'Merge the pull request on GitHub. Mission Control will synchronize its status.'
    : workflow.error_code === 'special_approval_required'
      ? 'Review protected-path access before this run continues.'
      : workflow.error_code === 'repeated_failure'
        ? 'Revise the item or switch agents. Retrying the same failure is disabled.'
        : workflow.error_code === 'validation_infrastructure_failed'
          ? 'Repair the development environment before continuing this run.'
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
