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
import { Empty, StateBadge, formatBytes, label, tone } from './format'

export function LearningView({ state, busy, onReplay }: {
  state: { records: Array<Record<string, unknown>>; playbooks: Array<Record<string, unknown>> }
  busy: boolean; onReplay: () => void
}) {
  return <div className="space-y-8">
    <section className="flex flex-col justify-between gap-3 border-y border-border py-5 sm:flex-row sm:items-center"><div><div className="flex items-center gap-2"><BookOpen size={16} className="text-accent" /><h2 className="text-sm font-semibold text-text">Evidence-backed improvement</h2></div><p className="mt-1 text-xs text-muted">{state.records.length} outcomes · {state.playbooks.length} reusable playbooks</p></div><button disabled={busy || !state.playbooks.length} onClick={onReplay} className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-accent/40 px-3 text-sm text-accent disabled:opacity-40"><TestTube2 size={14} /> Replay evaluations</button></section>
    <section><h2 className="mb-3 text-sm font-semibold text-text">Playbooks</h2>{!state.playbooks.length ? <Empty text="Playbooks appear after repeated evidence-backed outcomes." /> : <div className="border-t border-border">{state.playbooks.map((item, index) => <div key={String(item.slug ?? index)} className="grid gap-2 border-b border-border/70 py-3 sm:grid-cols-[minmax(0,1fr)_120px_120px] sm:items-center"><div><div className="text-sm text-text">{String(item.title ?? item.slug)}</div><div className="mt-1 text-xs text-muted">v{String(item.version ?? 1)} · {String(item.evidence_count ?? 0)} evidence records</div></div><StateBadge state={String(item.kind ?? 'repair')} /><div className="sm:text-right"><StateBadge state={String(item.status ?? 'candidate')} /></div></div>)}</div>}</section>
    <section><h2 className="mb-3 text-sm font-semibold text-text">Recent outcomes</h2>{!state.records.length ? <Empty text="No coding outcomes have been recorded." /> : <div className="border-t border-border">{state.records.slice(0, 50).map((item, index) => <div key={String(item.id ?? index)} className="grid gap-2 border-b border-border/70 py-3 sm:grid-cols-[minmax(0,1fr)_160px_140px] sm:items-center"><div><div className="text-sm text-text">{label(String(item.outcome ?? 'unknown'))}</div><div className="mt-1 font-mono text-[10px] text-muted">{String(item.signature ?? '')}</div></div><div className="text-xs text-muted">{String(item.worker_profile ?? 'unassigned')} · {label(String(item.stage ?? 'unknown'))}</div><div className="text-xs text-muted sm:text-right">{String(item.error_code ?? '') || 'Qualified evidence'}</div></div>)}</div>}</section>
  </div>
}

export const TOBI_REPOSITORY_URL = 'https://github.com/binhvu284/tobi'

export function releaseDate(value?: string | null) {
  if (!value) return 'Date pending'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
}

export function releaseDescription(release: DeveloperRelease) {
  if (release.notes?.trim()) return release.notes.trim()
  if (release.queue_item) return `Mission Control release for queue item #${release.queue_item}.`
  return `TOBI ${release.tier ? `${label(release.tier)} tier ` : ''}release tracked by Mission Control.`
}

export function VersionActions({ version }: { version: string }) {
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

export function VersionsView({ releases }: { releases: DeveloperRelease[] }) {
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

export function StorageView({ storage, busy, onCleanup }: { storage: DeveloperStorage | null; busy: boolean; onCleanup: (master: string) => void }) {
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

export function DataLearningView({ storage, learning, busy, onCleanup, onReplay }: {
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

export function HistoryView({ workflows }: { workflows: DeveloperWorkflow[] }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const filtered = workflows.filter(workflow => {
    const haystack = `#${workflow.queue_id} ${workflow.title} ${workflow.worker_profile_slug ?? ''}`.toLowerCase()
    return haystack.includes(query.trim().toLowerCase()) && (status === 'all' || workflow.state === status)
  })
  return <section className="overflow-hidden rounded-md border border-border bg-surface/35">
    <header className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div><h2 className="text-sm font-semibold text-text">Run history</h2><p className="mt-1 text-xs text-muted">Replay outcomes, checkpoints, evidence, and recovery state.</p></div>
      <div className="flex gap-2"><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search item or agent" className="h-8 w-52 rounded-md border border-border bg-background px-2.5 text-xs text-text outline-none focus:border-accent" /><select value={status} onChange={event => setStatus(event.target.value)} className="h-8 rounded-md border border-border bg-background px-2 text-xs text-text"><option value="all">All states</option><option value="completed">Done</option><option value="blocked">Needs action</option><option value="failed">Failed</option><option value="canceled">Canceled</option></select></div>
    </header>
    <div className="divide-y divide-border/70">{filtered.length ? filtered.map(workflow => <details key={workflow.id} className="group">
      <summary className="grid cursor-pointer list-none gap-2 px-4 py-3 hover:bg-overlay/5 sm:grid-cols-[minmax(0,1fr)_120px_140px_90px] sm:items-center"><div className="min-w-0"><div className="truncate text-xs font-medium text-text">#{workflow.queue_id} {workflow.title}</div><div className="mt-1 text-[10px] text-muted">Run #{workflow.id} · {new Date(workflow.created_at).toLocaleString()}</div></div><span className={`w-fit rounded border px-1.5 py-0.5 text-[10px] ${tone(workflow.state)}`}>{label(workflow.state)}</span><span className="truncate text-[11px] text-muted">{workflow.worker_profile_slug || 'unassigned'}</span><span className="text-right text-[11px] text-muted">{Math.round((workflow.progress || 0) * 100)}%</span></summary>
      <div className="grid gap-3 border-t border-border/60 bg-background/35 px-4 py-4 sm:grid-cols-3"><div><div className="text-[10px] uppercase text-muted">Outcome</div><div className="mt-1 text-xs text-text">{workflow.scorecard?.payload?.outcome || workflow.state}</div></div><div><div className="text-[10px] uppercase text-muted">Evidence</div><div className="mt-1 text-xs text-text">{workflow.evidence?.length ?? 0} records</div></div><div><div className="text-[10px] uppercase text-muted">Recovery</div><div className="mt-1 text-xs text-text">{workflow.blocker || 'No owner action recorded'}</div></div></div>
    </details>) : <Empty text="No runs match these filters." />}</div>
  </section>
}

export function SystemView({ storage, learning, releases, busy, onCleanup, onReplay }: {
  storage: DeveloperStorage | null; learning: { records: Array<Record<string, unknown>>; playbooks: Array<Record<string, unknown>> }
  releases: DeveloperRelease[]; busy: boolean; onCleanup: (master: string) => void; onReplay: () => void
}) {
  const [view, setView] = useState<'storage' | 'learning' | 'version'>('storage')
  return <div className="space-y-4"><div className="inline-flex rounded-md border border-border bg-surface/60 p-1">{(['storage', 'learning', 'version'] as const).map(item => <button key={item} onClick={() => setView(item)} className={`h-8 rounded px-3 text-xs font-medium ${view === item ? 'bg-accent text-background' : 'text-muted hover:text-text'}`}>{label(item)}</button>)}</div>{view === 'storage' && <StorageView storage={storage} busy={busy} onCleanup={onCleanup} />}{view === 'learning' && <LearningView state={learning} busy={busy} onReplay={onReplay} />}{view === 'version' && <VersionsView releases={releases} />}</div>
}
