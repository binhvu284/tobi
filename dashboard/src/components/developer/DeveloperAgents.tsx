import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Check, CheckCheck, CheckCircle2, ChevronDown, Clipboard, ExternalLink, Loader2,
  Pencil, Play, RefreshCw, Save, TerminalSquare, UserRound, X,
} from 'lucide-react'
import { ActionButton } from '../async-ui'
import type { AvailableModel, LlmProvider } from '../../api.chat'
import type { DeveloperWorkerLogin, DeveloperWorkerModels, DeveloperWorkerProfile } from '../../api.developer'
import LlmLogo, { BRAND_META, brandForModel, brandForProvider } from '../LlmLogo'
import ModelMenu from '../chat/ModelMenu'
import DeveloperToolLogo, { developerToolName, type DeveloperTool } from './DeveloperToolLogo'

type Routing = { default_model: string; coding: string; coding_review: string }

function label(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function statusTone(status: string) {
  if (status === 'ready') return 'text-success border-success/30 bg-success/10'
  if (status === 'needs_auth') return 'text-warning border-warning/30 bg-warning/10'
  if (['failed', 'unavailable'].includes(status)) return 'text-danger border-danger/30 bg-danger/10'
  return 'text-muted border-border bg-overlay/5'
}

function avatarText(profile: DeveloperWorkerProfile) {
  const configured = String(profile.config?.avatar || '').trim()
  if (configured) return configured.slice(0, 3)
  return profile.name.split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase()
}

function routeModel(profile: DeveloperWorkerProfile, routing: Routing) {
  if (profile.model) return profile.model
  return profile.adapter === 'model_review'
    ? routing.coding_review || routing.default_model
    : profile.adapter === 'native' ? routing.coding || routing.default_model : ''
}

function toolFor(profile: DeveloperWorkerProfile): DeveloperTool {
  return profile.adapter === 'hermes' ? 'native' : profile.adapter
}

function AgentRow({ profile, models, providers, routing, busy, onSave, onProbe, onLogin, onModels }: {
  profile: DeveloperWorkerProfile; models: AvailableModel[]; providers: LlmProvider[]; routing: Routing; busy: boolean
  onSave: (slug: string, profile: DeveloperWorkerProfile, success?: string) => Promise<DeveloperWorkerProfile | null>
  onProbe: (slug: string) => Promise<DeveloperWorkerProfile | null>
  onLogin: (slug: string) => Promise<DeveloperWorkerLogin | null>
  onModels: (slug: string, refresh?: boolean) => Promise<DeveloperWorkerModels | null>
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(profile)
  const [auth, setAuth] = useState<DeveloperWorkerLogin | null>(null)
  const [cliCatalog, setCliCatalog] = useState<DeveloperWorkerModels | null>(null)
  const [localBusy, setLocalBusy] = useState<'save' | 'test' | 'auth' | 'models' | 'toggle' | null>(null)
  // Clipboard writes are async and can be refused by the browser. Without a confirmation the
  // owner cannot tell a successful copy from a silently denied one.
  const [commandCopied, setCommandCopied] = useState(false)
  const copyCommand = async (value: string) => {
    await navigator.clipboard.writeText(value)
    setCommandCopied(true)
    window.setTimeout(() => setCommandCopied(false), 1500)
  }
  const reviewer = profile.adapter === 'model_review'

  useEffect(() => { setDraft(profile) }, [profile.slug])
  useEffect(() => {
    setDraft(current => ({
      ...current,
      enabled: profile.enabled,
      health_status: profile.health_status,
      health_detail: profile.health_detail,
      last_probed_at: profile.last_probed_at,
      runner: profile.runner,
      runner_mode: profile.runner_mode,
    }))
  }, [
    profile.enabled, profile.health_status, profile.health_detail, profile.last_probed_at,
    profile.runner, profile.runner_mode,
  ])

  const update = <K extends keyof DeveloperWorkerProfile>(key: K, value: DeveloperWorkerProfile[K]) =>
    setDraft(current => ({ ...current, [key]: value }))
  const dirty = JSON.stringify({
    name: draft.name, adapter: draft.adapter, model: draft.model, auth_mode: draft.auth_mode,
    credential_env: draft.credential_env, enabled: draft.enabled, config: draft.config,
  }) !== JSON.stringify({
    name: profile.name, adapter: profile.adapter, model: profile.model, auth_mode: profile.auth_mode,
    credential_env: profile.credential_env, enabled: profile.enabled, config: profile.config,
  })
  const sharedManaged = draft.adapter === 'native' || draft.adapter === 'model_review'
  const currentCatalog = sharedManaged ? models : cliCatalog?.models ?? []
  const effectiveModel = routeModel(draft, routing)
  const modelRow = [...models, ...(cliCatalog?.models ?? [])].find(item => item.id === effectiveModel)
  const providerId = draft.adapter === 'codex' ? 'codex'
    : draft.adapter === 'opencode' ? (modelRow?.provider || effectiveModel.split('/')[0] || 'opencode')
      : modelRow?.provider || effectiveModel.split(':')[0] || ''
  const provider = providers.find(item => item.id === providerId)
  const providerName = provider?.label || BRAND_META[brandForProvider(providerId)].name || label(providerId)
  const modelName = modelRow?.label || modelRow?.model || effectiveModel || (sharedManaged ? 'Shared route' : 'CLI default')
  const authorized = ['codex', 'opencode'].includes(draft.adapter) && profile.health_status === 'ready'
  const displayStatus = !profile.enabled ? 'Off' : profile.health_status === 'ready' ? 'Ready' : label(profile.health_status)
  const toolOptions: Array<{ id: DeveloperTool; detail: string; soon?: boolean }> = reviewer
    ? [{ id: 'model_review', detail: 'Independent quality gate' }]
    : [
      { id: 'native', detail: 'Models-page providers' },
      { id: 'codex', detail: 'OpenAI coding CLI' },
      { id: 'opencode', detail: 'Multi-provider coding CLI' },
      { id: 'claude', detail: 'Coming soon', soon: true },
    ]

  const changeTool = (tool: DeveloperTool) => {
    if (tool === 'claude' || tool === 'model_review' && !reviewer) return
    setAuth(null); setCliCatalog(null)
    setDraft(current => ({
      ...current,
      adapter: tool as DeveloperWorkerProfile['adapter'],
      model: '', credential_env: '',
      auth_mode: tool === 'codex' || tool === 'opencode' ? 'native_login' : 'inherited',
    }))
  }
  const save = async () => {
    setLocalBusy('save')
    try {
      const updated = await onSave(profile.slug, draft)
      if (updated) setDraft(updated)
      return updated
    } finally { setLocalBusy(null) }
  }
  const ensureSaved = async () => dirty ? save() : profile
  const test = async () => {
    setLocalBusy('test')
    try {
      const saved = await ensureSaved()
      if (!saved) return
      const updated = await onProbe(profile.slug)
      if (updated) setDraft(current => ({ ...current, ...updated }))
      if (updated?.health_status === 'ready' && ['codex', 'opencode'].includes(updated.adapter)) {
        const result = await onModels(profile.slug, true)
        if (result) setCliCatalog(result)
      }
    } finally { setLocalBusy(null) }
  }
  const authorize = async () => {
    setLocalBusy('auth')
    try {
      const saved = await ensureSaved()
      if (!saved) return
      setAuth(await onLogin(profile.slug))
    } finally { setLocalBusy(null) }
  }
  const loadModels = async (refresh = false) => {
    if (sharedManaged || profile.health_status !== 'ready') return
    setLocalBusy('models')
    try {
      const result = await onModels(profile.slug, refresh)
      if (result) setCliCatalog(result)
    } finally { setLocalBusy(null) }
  }
  useEffect(() => {
    if (open && !sharedManaged && profile.health_status === 'ready' && !cliCatalog) void loadModels()
  }, [open, sharedManaged, profile.health_status])

  const working = busy || localBusy !== null
  const toggleEnabled = async () => {
    const enabled = !profile.enabled
    setDraft(current => ({ ...current, enabled }))
    setLocalBusy('toggle')
    try {
      const updated = await onSave(
        profile.slug,
        { ...profile, enabled },
        enabled ? 'Agent activated' : 'Agent deactivated',
      )
      setDraft(current => ({ ...current, enabled: updated?.enabled ?? profile.enabled }))
    } finally { setLocalBusy(null) }
  }
  return (
    <motion.section layout className={`relative overflow-visible rounded-md border transition-colors ${open ? 'z-40 border-accent/35 bg-surface/75 shadow-[0_18px_50px_rgb(0_0_0/0.12)]' : profile.enabled ? 'z-0 border-border/70 bg-surface/35 hover:border-border hover:bg-surface/60' : 'z-0 border-border/50 bg-surface/20 hover:border-border/70'}`}>
      <div className="flex min-h-16 w-full items-stretch">
        <button type="button" onClick={() => setOpen(value => !value)} className="grid min-w-0 flex-1 grid-cols-[auto_minmax(0,1fr)] items-center gap-3 px-3 text-left sm:grid-cols-[auto_minmax(150px,1fr)_120px_minmax(190px,1fr)] sm:px-4">
          <span className="flex h-9 w-9 items-center justify-center rounded-md border border-border/70 bg-background text-xs font-semibold text-text">{avatarText(profile)}</span>
          <span className="min-w-0"><span className={`block truncate text-sm font-medium ${profile.enabled ? 'text-text' : 'text-muted'}`}>{profile.name}</span><span className="mt-0.5 block truncate text-[10px] text-muted sm:hidden">{developerToolName(toolFor(profile))} - {modelName}</span></span>
          <span className={`hidden w-fit rounded border px-2 py-0.5 text-[10px] font-medium sm:inline-flex ${statusTone(profile.enabled ? profile.health_status : 'off')}`}>{displayStatus}</span>
          <span className="hidden min-w-0 items-center gap-2 sm:flex"><LlmLogo model={effectiveModel} provider={providerId} size={13} /><span className="min-w-0"><span className="block truncate text-xs text-text">{providerName}</span><span className="block truncate text-[10px] text-muted">{modelName}</span></span></span>
        </button>
        <div className="flex shrink-0 items-center gap-2 pr-3 sm:pr-4">
          <button
            type="button"
            role="switch"
            aria-checked={profile.enabled}
            aria-label={`${profile.enabled ? 'Deactivate' : 'Activate'} ${profile.name} for new goals`}
            title={`${profile.enabled ? 'Deactivate' : 'Activate'} for new goals`}
            disabled={working}
            onClick={() => void toggleEnabled()}
            className="inline-flex h-9 items-center gap-2 rounded-md px-1.5 text-left transition-colors hover:bg-overlay/5 disabled:cursor-wait disabled:opacity-60"
          >
            <span className={`relative h-5 w-9 rounded-full border transition-colors ${profile.enabled ? 'border-success/60 bg-success/20' : 'border-border bg-background'}`}>
              <span className={`absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all ${profile.enabled ? 'left-[17px] bg-success' : 'left-0.5 bg-muted'}`} />
            </span>
            <span className={`hidden text-[10px] font-medium lg:block ${profile.enabled ? 'text-success' : 'text-muted'}`}>{localBusy === 'toggle' ? <Loader2 size={12} className="animate-spin" /> : profile.enabled ? 'Active' : 'Off'}</span>
          </button>
          <button type="button" title={open ? 'Collapse agent' : 'Expand agent'} onClick={() => setOpen(value => !value)} className="flex h-9 w-7 items-center justify-center rounded-md text-muted hover:bg-overlay/5 hover:text-text"><ChevronDown size={16} className={`transition-transform ${open ? 'rotate-180' : ''}`} /></button>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {open && <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.18 }} className="overflow-visible">
          <div className="border-t border-border/60 px-4 py-5 sm:px-5">
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.8fr)]">
              <div className="space-y-5">
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_150px]">
                  <label><span className="mb-1.5 block text-[11px] font-medium text-muted">Agent name</span><div className="relative"><Pencil size={13} className="absolute left-3 top-3 text-muted" /><input value={draft.name} onChange={event => update('name', event.target.value)} className="h-10 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm text-text outline-none focus:border-accent" /></div></label>
                  <label><span className="mb-1.5 block text-[11px] font-medium text-muted">Avatar</span><div className="relative"><UserRound size={13} className="absolute left-3 top-3 text-muted" /><input value={String(draft.config?.avatar || '')} onChange={event => update('config', { ...draft.config, avatar: event.target.value.slice(0, 3) })} placeholder="TB" className="h-10 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm text-text outline-none focus:border-accent" /></div></label>
                </div>
                <div><div className="mb-2 text-[11px] font-medium text-muted">Developer tool</div><div className="grid gap-2 sm:grid-cols-2">{toolOptions.map(option => {
                  const selected = draft.adapter === option.id
                  return <button key={option.id} type="button" disabled={option.soon || reviewer} onClick={() => changeTool(option.id)} className={`flex items-center gap-3 rounded-md border px-3 py-2.5 text-left transition-colors ${selected ? 'border-accent/45 bg-accent/10' : 'border-border/70 hover:border-border hover:bg-overlay/5'} disabled:cursor-default disabled:opacity-70`}><DeveloperToolLogo tool={option.id} size={16} /><span className="min-w-0 flex-1"><span className="flex items-center gap-2 text-xs font-medium text-text">{developerToolName(option.id)}{option.soon && <span className="rounded bg-overlay/10 px-1.5 py-0.5 text-[9px] text-muted">Soon</span>}</span><span className="mt-0.5 block text-[10px] text-muted">{option.detail}</span></span>{selected && <Check size={14} className="text-accent" />}</button>
                })}</div></div>
              </div>

              <div className="space-y-4 border-t border-border/60 pt-5 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
                <div className="flex items-center justify-between gap-3"><div><div className="text-[11px] font-medium text-muted">Model fuel</div><div className="mt-1 flex items-center gap-2 text-xs text-text"><DeveloperToolLogo tool={toolFor(draft)} size={13} /> {developerToolName(toolFor(draft))}</div></div>{['codex', 'opencode'].includes(draft.adapter) && <span className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-[10px] ${authorized ? 'border-success/30 bg-success/10 text-success' : 'border-warning/30 bg-warning/10 text-warning'}`}>{authorized ? <CheckCircle2 size={12} /> : <TerminalSquare size={12} />}{authorized ? 'Authorized' : 'Authorization needed'}</span>}</div>
                {sharedManaged ? <><ModelMenu models={models} value={draft.model || null} onChange={model => update('model', model)} autoLabel={`Shared route - ${modelName}`} align="left" wide /><p className="text-[10px] leading-4 text-muted">Uses the same enabled providers and models as Chat.</p><a href="/models" className="inline-flex items-center gap-1 text-[10px] text-accent hover:underline">Manage Models page <ExternalLink size={10} /></a></> : authorized ? <><ModelMenu models={currentCatalog} value={draft.model || null} onChange={model => update('model', model)} autoLabel={`${developerToolName(toolFor(draft))} default`} align="left" wide /><div className="flex items-start justify-between gap-3 text-[10px] leading-4 text-muted"><span>{cliCatalog?.detail || 'Loading models from the authorized CLI.'}</span><button title="Refresh model catalog" onClick={() => void loadModels(true)} disabled={working} className="shrink-0 text-accent"><RefreshCw size={12} className={localBusy === 'models' ? 'animate-spin' : ''} /></button></div></> : <button type="button" onClick={() => void authorize()} disabled={working} className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-warning/40 bg-warning/5 text-xs font-medium text-warning hover:bg-warning/10 disabled:opacity-40">{localBusy === 'auth' ? <Loader2 size={14} className="animate-spin" /> : <TerminalSquare size={14} />} Authorize {developerToolName(toolFor(draft))}</button>}
                <label className="flex cursor-pointer items-center justify-between gap-3 border-t border-border/60 pt-3 text-xs text-muted"><span>Available for new goals</span><input type="checkbox" checked={draft.enabled} onChange={event => update('enabled', event.target.checked)} className="h-4 w-4 accent-[rgb(var(--accent))]" /></label>
              </div>
            </div>

            <AnimatePresence>
              {auth && <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }} className="mt-5 overflow-hidden rounded-md border border-border bg-background/80 font-mono text-xs">
                <div className="flex items-center justify-between border-b border-border px-3 py-2 text-muted"><span className="inline-flex items-center gap-2"><TerminalSquare size={13} /> Authorization terminal</span><button title="Close terminal" onClick={() => setAuth(null)}><X size={14} /></button></div>
                <div className="space-y-3 px-3 py-3"><div className="flex items-start gap-2 text-text"><span className="text-success">$</span><code className="min-w-0 flex-1 break-all">{auth.command?.join(' ') || 'Provider login is managed externally.'}</code>{auth.command && <ActionButton title="Copy command" onAction={() => copyCommand(auth.command!.join(' '))}
                  icon={commandCopied ? <CheckCheck size={13} className="text-success" /> : <Clipboard size={13} />}
                  className="text-muted hover:text-text" />}</div><div className="text-[10px] leading-5 text-muted">{auth.detail}</div>{auth.steps?.map((step, index) => <div key={step} className="flex gap-2 text-[10px] text-muted"><span className="text-accent">{index + 1}.</span><span>{step}</span></div>)}<div className="flex flex-wrap gap-2 pt-1"><button onClick={() => void test()} disabled={working} className="inline-flex h-8 items-center gap-2 rounded border border-accent/40 px-2.5 text-[10px] text-accent">{localBusy === 'test' ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />} Check authorization</button></div></div>
              </motion.div>}
            </AnimatePresence>

            <div className="mt-5 flex flex-col gap-3 border-t border-border/60 pt-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 text-[10px] leading-4 text-muted"><span className={`mr-2 inline-block h-2 w-2 rounded-full ${profile.health_status === 'ready' ? 'bg-success' : 'bg-warning'}`} />{profile.health_detail || 'Run a connection test before assigning this agent.'}</div>
              <div className="flex shrink-0 gap-2"><button type="button" onClick={() => void test()} disabled={working} className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-xs text-text hover:bg-overlay/5 disabled:opacity-40">{localBusy === 'test' ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Test agent</button>{dirty && <button type="button" onClick={() => void save()} disabled={working || draft.name.trim().length < 2} className="inline-flex h-9 items-center gap-2 rounded-md bg-accent px-3 text-xs font-medium text-background disabled:opacity-40">{localBusy === 'save' ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save changes</button>}</div>
            </div>
          </div>
        </motion.div>}
      </AnimatePresence>
    </motion.section>
  )
}

export default function DeveloperAgents({ workers, models, providers, routing, busy, onSave, onProbe, onLogin, onModels }: {
  workers: DeveloperWorkerProfile[]; models: AvailableModel[]; providers: LlmProvider[]; routing: Routing; busy: boolean
  onSave: (slug: string, profile: DeveloperWorkerProfile, success?: string) => Promise<DeveloperWorkerProfile | null>
  onProbe: (slug: string) => Promise<DeveloperWorkerProfile | null>
  onLogin: (slug: string) => Promise<DeveloperWorkerLogin | null>
  onModels: (slug: string, refresh?: boolean) => Promise<DeveloperWorkerModels | null>
}) {
  const agents = useMemo(() => workers.filter(item => item.adapter !== 'hermes').sort((a, b) => {
    const order: Record<string, number> = { native: 0, codex: 1, opencode: 2, model_review: 3 }
    return (order[a.adapter] ?? 9) - (order[b.adapter] ?? 9) || a.name.localeCompare(b.name)
  }), [workers])
  const ready = agents.filter(item => item.enabled && item.health_status === 'ready').length
  return (
    <div className="mx-auto max-w-6xl pb-8">
      <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><h2 className="text-base font-semibold text-text">Development agents</h2><p className="mt-1 text-xs text-muted">Choose the tool and model each agent uses to implement or review a goal.</p></div><div className="inline-flex w-fit items-center gap-2 rounded-md border border-border/70 bg-surface/50 px-2.5 py-1.5 text-[11px] text-muted"><span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-40" /><span className="relative inline-flex h-2 w-2 rounded-full bg-success" /></span>{ready} of {agents.length} ready</div></header>
      <div className="space-y-2">{agents.map(agent => <AgentRow key={agent.slug} profile={agent} models={models} providers={providers} routing={routing} busy={busy} onSave={onSave} onProbe={onProbe} onLogin={onLogin} onModels={onModels} />)}</div>
    </div>
  )
}
