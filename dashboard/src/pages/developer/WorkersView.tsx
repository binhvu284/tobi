// Extracted from Developer.tsx (pre-#21 refactor) — verbatim move.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, Archive, BookOpen, CheckCircle2, Circle, Clock3, Code2, Download, ExternalLink,
  ChevronDown, ChevronUp, GitBranch, Github, HardDrive, KeyRound, ListTree, Loader2, MoreHorizontal, Pause, Play, Plus, Radio, RefreshCw,
  RotateCcw, Save, ScrollText, ShieldCheck, Square, Target,
  TerminalSquare, TestTube2, Trash2, Upload, WifiOff, Wrench, XCircle,
} from 'lucide-react'
import LlmLogo, { BRAND_META, brandForModel, brandForProvider } from '../../components/LlmLogo'
import ModelMenu from '../../components/chat/ModelMenu'
import type { AvailableModel, LlmProvider } from '../../api'
import { approveDeveloperWorkflow, assessDeveloperGoal, commandDeveloperGoal, commandDeveloperWorkflow, createDeveloperGoal, getDeveloperHistory, getDeveloperLearning, getDeveloperOverview, getDeveloperQueue, getDeveloperStorage, getDeveloperVersions, getDeveloperGoals, getDeveloperWorkerLogin, getDeveloperWorkerModels, getDeveloperWorkers, probeDeveloperWorker, replayDeveloperLearning, saveDeveloperWorker, startDeveloperWorkflow, streamDeveloperEvents, switchDeveloperWorker, cleanupDeveloperStorage, rejectDeveloperWorkflow, setDeveloperProcessSettings, type DeveloperAssessment, type DeveloperEvent, type DeveloperOverview, type DeveloperGoal, type DeveloperQueueItem, type DeveloperQueueState, type DeveloperRelease, type DeveloperStorage, type DeveloperWorkerLogin, type DeveloperWorkerModels, type DeveloperWorkerProfile, type DeveloperWorkflow } from '../../api.developer'
import { Empty, StateBadge, label } from './format'

export function WorkersView({ workers, models, providers, routing, busy, onSave, onProbe, onLogin }: {
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
