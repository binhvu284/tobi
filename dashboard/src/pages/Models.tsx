import { useEffect, useState } from 'react'
import {
  Cpu, Lock, Unlock, RefreshCw, Save, Plus, ArrowUp, ArrowDown, Trash2,
  CheckCircle2, Circle, Zap, Server, BarChart3, Send,
} from 'lucide-react'
import {
  type LlmConfig, type LlmProvider, type AvailableModel, type HermesPush, type VaultStatus,
  type UsageSummary,
  getLlmConfig, saveLlmConfig, discoverLlmModels, pushHermesConfig,
  getVaultStatus, vaultUnlock, getLlmUsage,
} from '../api'
import { useToast } from '../context/ToastProvider'
import { AmbientField } from '../components/motion'
import LlmLogo from '../components/LlmLogo'
import KeySlots from '../components/KeySlots'
import { useVaultSession } from '../hooks/useVaultSession'

const TASKS: { id: string; label: string }[] = [
  { id: 'simple', label: 'Simple / chat' },
  { id: 'coding', label: 'Coding' },
  { id: 'research', label: 'Research' },
  { id: 'writing', label: 'Writing' },
  { id: 'planning', label: 'Planning' },
  { id: 'ceo_review', label: 'CEO review' },
]

export default function Models() {
  const { toast } = useToast()
  const hasSession = useVaultSession()
  const [cfg, setCfg] = useState<LlmConfig | null>(null)
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [models, setModels] = useState<AvailableModel[]>([])
  const [vault, setVault] = useState<VaultStatus | null>(null)
  const [baseUrls, setBaseUrls] = useState<Record<string, string>>({})
  const [master, setMaster] = useState('')
  const [saving, setSaving] = useState(false)
  const [discovering, setDiscovering] = useState<string | null>(null)
  const [hermes, setHermes] = useState<HermesPush | null>(null)
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [usageDays, setUsageDays] = useState(7)

  const load = async () => {
    try {
      const r = await getLlmConfig(); setCfg(r.config); setProviders(r.providers); setModels(r.models)
      setBaseUrls(Object.fromEntries(r.providers.map(p => [p.id, p.base_url])))
    } catch (e) { toast({ kind: 'error', title: 'Could not load config', detail: (e as Error).message }) }
    try { setVault(await getVaultStatus()) } catch { /* ignore */ }
  }
  useEffect(() => { load() /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [])
  useEffect(() => { getLlmUsage(usageDays).then(setUsage).catch(() => {}) }, [usageDays])

  const unlock = async () => {
    try { await vaultUnlock(master); setMaster(''); toast({ kind: 'success', title: 'Vault unlocked' }); load() }
    catch (e) { toast({ kind: 'error', title: 'Unlock failed', detail: (e as Error).message }) }
  }

  const discover = async (pid: string) => {
    setDiscovering(pid)
    try {
      const r = await discoverLlmModels(pid)
      setProviders(ps => ps.map(p => p.id === pid ? { ...p, models: r.models } : p))
      await load()
      toast({ kind: r.ok ? 'success' : 'info', title: r.ok ? `Found ${r.models.length} models` : 'Using known defaults' })
    } catch (e) { toast({ kind: 'error', title: 'Discover failed', detail: (e as Error).message }) }
    finally { setDiscovering(null) }
  }

  const patchCfg = (p: Partial<LlmConfig>) => setCfg(c => c ? { ...c, ...p } : c)
  const setOverride = (task: string, model: string) => {
    if (!cfg) return
    const next = { ...cfg.task_overrides }
    if (model) next[task] = model; else delete next[task]
    patchCfg({ task_overrides: next })
  }
  const setProviderField = (pid: string, field: 'enabled' | 'base_url', value: boolean | string) => {
    if (!cfg) return
    const provs = { ...cfg.providers, [pid]: { ...(cfg.providers[pid] || {}), [field]: value } }
    patchCfg({ providers: provs })
  }
  const toggleProvider = async (pid: string) => {
    // The enable/disable switch is the one setting that should persist instantly —
    // otherwise a reload silently reverts it. Fold in pending base_url edits, flip
    // the flag, optimistic-update, then save (revert on failure).
    if (!cfg) return
    const prev = cfg
    const currentlyEnabled = cfg.providers[pid]?.enabled ?? true
    const provs = { ...cfg.providers }
    providers.forEach(p => { if (p.editable_base_url && baseUrls[p.id] != null) provs[p.id] = { ...(provs[p.id] || {}), base_url: baseUrls[p.id] } })
    provs[pid] = { ...(provs[pid] || {}), enabled: !currentlyEnabled }
    const newCfg = { ...cfg, providers: provs }
    setCfg(newCfg)
    setSaving(true)
    try {
      const r = await saveLlmConfig(newCfg)
      setCfg(r.config); setProviders(r.providers); setModels(r.models)
      toast({ kind: 'success', title: currentlyEnabled ? 'Provider disabled' : 'Provider enabled' })
    } catch (e) {
      setCfg(prev)
      toast({ kind: 'error', title: 'Save failed', detail: (e as Error).message })
    } finally { setSaving(false) }
  }
  const addFallback = (model: string) => { if (cfg && model && !cfg.fallback.includes(model)) patchCfg({ fallback: [...cfg.fallback, model] }) }
  const moveFallback = (i: number, dir: -1 | 1) => {
    if (!cfg) return
    const f = [...cfg.fallback]; const j = i + dir
    if (j < 0 || j >= f.length) return
    ;[f[i], f[j]] = [f[j], f[i]]; patchCfg({ fallback: f })
  }
  const removeFallback = (i: number) => cfg && patchCfg({ fallback: cfg.fallback.filter((_, k) => k !== i) })

  const save = async () => {
    if (!cfg) return
    // fold edited base_urls into the providers config before saving
    const provs = { ...cfg.providers }
    providers.forEach(p => { if (p.editable_base_url && baseUrls[p.id] != null) provs[p.id] = { ...(provs[p.id] || {}), base_url: baseUrls[p.id] } })
    setSaving(true)
    try {
      const r = await saveLlmConfig({ ...cfg, providers: provs })
      setCfg(r.config); setProviders(r.providers); setModels(r.models); setHermes(r.hermes || null)
      toast({ kind: 'success', title: 'Saved', detail: r.hermes?.detail })
    } catch (e) { toast({ kind: 'error', title: 'Save failed', detail: (e as Error).message }) }
    finally { setSaving(false) }
  }

  const pushHermes = async () => {
    try { const r = await pushHermesConfig(); setHermes(r); toast({ kind: r.ok ? 'success' : 'info', title: 'Hermes', detail: r.detail }) }
    catch (e) { toast({ kind: 'error', title: 'Push failed', detail: (e as Error).message }) }
  }

  const locked = !!vault && vault.setup && !hasSession
  const modelLabel = (id: string) => models.find(m => m.id === id)?.label || id

  return (
    <div className="relative h-full overflow-y-auto">
      <AmbientField />
      <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent/30 bg-accent/10 text-accent"><Cpu size={18} /></div>
            <div>
              <h1 className="text-base font-bold text-heading">Models</h1>
              <p className="text-[11px] text-muted">Providers, routing & fallback — the single source of truth (also drives Hermes)</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={pushHermes} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:border-accent/40 hover:text-accent"><Send size={13} /> Push to Hermes</button>
            <button onClick={save} disabled={saving || !cfg} className="flex items-center gap-1.5 rounded-lg border border-accent/50 bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/25 disabled:opacity-40">
              {saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />} Save
            </button>
          </div>
        </div>

        {/* vault gate */}
        {locked && (
          <div className="mb-5 flex flex-col gap-2 rounded-xl border border-warning/40 bg-warning/5 p-3 sm:flex-row sm:items-center">
            <div className="flex flex-1 items-center gap-2 text-sm text-warning"><Lock size={15} /> Vault is locked — unlock to add or change provider API keys.</div>
            <div className="flex gap-2">
              <input type="password" value={master} onChange={e => setMaster(e.target.value)} onKeyDown={e => e.key === 'Enter' && unlock()}
                placeholder="Master password" className="rounded-lg border border-border bg-bg px-2.5 py-1.5 text-xs text-text outline-none focus:border-accent/50" />
              <button onClick={unlock} className="flex items-center gap-1.5 rounded-lg border border-accent/50 bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/25"><Unlock size={13} /> Unlock</button>
            </div>
          </div>
        )}

        {/* providers */}
        <section className="mb-6">
          <h2 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><Server size={13} /> Providers</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {providers.map(p => {
              const connected = p.key_present
              const enabled = cfg?.providers[p.id]?.enabled ?? p.enabled
              return (
                <div key={p.id} className="rounded-xl border border-border bg-surface/50 p-3.5">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <LlmLogo provider={p.id} size={16} />
                      <span className="truncate text-sm font-semibold text-heading">{p.label}</span>
                      {connected ? <span className="flex shrink-0 items-center gap-1 text-[10px] text-success"><CheckCircle2 size={11} /> {p.needs_key ? 'Key set' : 'Ready'}</span>
                        : <span className="flex shrink-0 items-center gap-1 text-[10px] text-muted"><Circle size={11} /> No key</span>}
                    </div>
                    <button onClick={() => toggleProvider(p.id)} disabled={saving}
                      className={`relative h-5 w-9 shrink-0 rounded-full border transition-colors disabled:opacity-50 ${enabled ? 'border-accent/50 bg-accent/30' : 'border-border bg-bg'}`}>
                      <span className={`absolute top-0.5 h-3.5 w-3.5 rounded-full bg-text transition-all ${enabled ? 'left-[18px]' : 'left-0.5'}`} />
                    </button>
                  </div>

                  {/* multi-key: several accounts per provider, one active at a time */}
                  {p.needs_key && p.key_env && (
                    <div className="mb-2">
                      <KeySlots name={p.key_env} locked={locked} envLast4={p.key_last4}
                        onChanged={r => { setProviders(r.providers); setModels(r.models) }} />
                    </div>
                  )}

                  {p.editable_base_url && (
                    <input value={baseUrls[p.id] ?? ''} onChange={e => setBaseUrls(b => ({ ...b, [p.id]: e.target.value }))}
                      placeholder="Base URL (OpenAI-compatible)" className="mb-2 w-full rounded-lg border border-border bg-bg px-2.5 py-1.5 text-xs text-text outline-none focus:border-accent/50" />
                  )}

                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] text-muted">{p.models.length} model{p.models.length === 1 ? '' : 's'}</span>
                    <button onClick={() => discover(p.id)} disabled={discovering === p.id}
                      className="flex items-center gap-1 text-[11px] text-muted hover:text-accent disabled:opacity-50">
                      <RefreshCw size={11} className={discovering === p.id ? 'animate-spin' : ''} /> Discover
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* routing */}
        <section className="mb-6 rounded-xl border border-border bg-surface/40 p-4">
          <h2 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><Zap size={13} /> Routing</h2>

          <label className="mb-3 block">
            <span className="mb-1 block text-xs font-medium text-text">Default model</span>
            <select value={cfg?.default_model || ''} onChange={e => patchCfg({ default_model: e.target.value })}
              className="w-full rounded-lg border border-border bg-bg px-2.5 py-2 text-sm text-text outline-none focus:border-accent/50">
              <option value="">— Legacy env (PRIMARY_MODEL) —</option>
              {models.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </label>

          <div className="mb-4">
            <span className="mb-1.5 block text-xs font-medium text-text">Per-task overrides</span>
            <div className="grid gap-2 sm:grid-cols-2">
              {TASKS.map(t => (
                <div key={t.id} className="flex items-center gap-2">
                  <span className="w-24 shrink-0 text-xs text-muted">{t.label}</span>
                  <select value={cfg?.task_overrides[t.id] || ''} onChange={e => setOverride(t.id, e.target.value)}
                    className="min-w-0 flex-1 rounded-lg border border-border bg-bg px-2 py-1.5 text-xs text-text outline-none focus:border-accent/50">
                    <option value="">Use default</option>
                    {models.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
                  </select>
                </div>
              ))}
            </div>
          </div>

          <div>
            <span className="mb-1.5 block text-xs font-medium text-text">Fallback chain <span className="font-normal text-muted">(try in order on error/rate-limit)</span></span>
            <div className="space-y-1.5">
              {(cfg?.fallback || []).map((m, i) => (
                <div key={m} className="flex items-center gap-2 rounded-lg border border-border bg-bg px-2.5 py-1.5">
                  <span className="flex h-5 w-5 items-center justify-center rounded bg-accent/10 text-[10px] font-bold text-accent">{i + 1}</span>
                  <span className="min-w-0 flex-1 truncate text-xs text-text">{modelLabel(m)}</span>
                  <button onClick={() => moveFallback(i, -1)} disabled={i === 0} className="text-muted hover:text-accent disabled:opacity-30"><ArrowUp size={13} /></button>
                  <button onClick={() => moveFallback(i, 1)} disabled={i === (cfg?.fallback.length || 0) - 1} className="text-muted hover:text-accent disabled:opacity-30"><ArrowDown size={13} /></button>
                  <button onClick={() => removeFallback(i)} className="text-muted hover:text-danger"><Trash2 size={13} /></button>
                </div>
              ))}
              <div className="flex items-center gap-2">
                <select value="" onChange={e => addFallback(e.target.value)}
                  className="min-w-0 flex-1 rounded-lg border border-dashed border-border bg-bg px-2.5 py-1.5 text-xs text-muted outline-none focus:border-accent/50">
                  <option value="">+ Add a fallback model…</option>
                  {models.filter(m => !cfg?.fallback.includes(m.id)).map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
                </select>
                <Plus size={14} className="text-muted" />
              </div>
            </div>
          </div>
        </section>

        {hermes && (
          <div className={`mb-6 rounded-lg border px-3 py-2 text-xs ${hermes.ok ? 'border-success/30 bg-success/5 text-success' : 'border-border bg-surface/40 text-muted'}`}>
            <span className="font-medium">Hermes:</span> {hermes.detail}
          </div>
        )}

        {/* usage analytics (P3) */}
        <section className="rounded-xl border border-border bg-surface/40 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><BarChart3 size={13} /> Usage</h2>
            <div className="flex rounded-lg border border-border p-0.5 text-[11px]">
              {[7, 30].map(d => (
                <button key={d} onClick={() => setUsageDays(d)} className={`rounded px-2 py-0.5 ${usageDays === d ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}>{d}d</button>
              ))}
            </div>
          </div>
          {!usage || usage.requests === 0 ? (
            <p className="py-4 text-center text-xs text-muted">No LLM calls logged yet — chat or run an agent and usage shows up here.</p>
          ) : (
            <>
              <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  { label: 'Tokens', value: fmtTok(usage.total_tokens) },
                  { label: 'Cost', value: `$${usage.total_cost.toFixed(usage.total_cost < 1 ? 4 : 2)}` },
                  { label: 'Requests', value: usage.requests.toLocaleString() },
                  { label: 'Avg latency', value: `${usage.avg_latency_ms}ms` },
                ].map(k => (
                  <div key={k.label} className="rounded-lg border border-border bg-bg/40 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-wide text-muted">{k.label}</div>
                    <div className="mt-0.5 text-base font-bold text-heading">{k.value}</div>
                  </div>
                ))}
              </div>

              {/* per-model columns */}
              <div className="mb-4">
                <div className="mb-1.5 text-[11px] font-medium text-text">By model</div>
                <div className="space-y-1.5">
                  {usage.by_model.slice(0, 8).map(m => {
                    const max = usage.by_model[0]?.tokens || 1
                    return (
                      <div key={m.model} className="flex items-center gap-2">
                        <span className="w-32 shrink-0 truncate text-[11px] text-muted" title={m.model}>{m.model}</span>
                        <div className="relative h-4 flex-1 overflow-hidden rounded bg-bg/50">
                          <div className="h-full rounded bg-accent/40" style={{ width: `${Math.max(3, (m.tokens / max) * 100)}%` }} />
                        </div>
                        <span className="w-16 shrink-0 text-right text-[11px] tabular-nums text-text">{fmtTok(m.tokens)}</span>
                        <span className="w-14 shrink-0 text-right text-[11px] tabular-nums text-muted">${m.cost.toFixed(m.cost < 1 ? 3 : 2)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* daily trend */}
              <div>
                <div className="mb-1.5 text-[11px] font-medium text-text">Tokens / day</div>
                <div className="flex h-20 items-end gap-1">
                  {usage.by_day.map(d => {
                    const max = Math.max(...usage.by_day.map(x => x.tokens), 1)
                    return (
                      <div key={d.day} className="group relative flex flex-1 flex-col items-center justify-end" title={`${d.day}: ${fmtTok(d.tokens)} tok · $${d.cost.toFixed(3)}`}>
                        <div className="w-full rounded-t bg-accent/40 transition-colors group-hover:bg-accent/70" style={{ height: `${Math.max(2, (d.tokens / max) * 100)}%` }} />
                        <span className="mt-1 text-[8px] text-muted">{d.day.slice(5)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}

function fmtTok(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}
