import { useCallback, useEffect, useMemo, useState } from 'react'
import { softFail } from '../lib/report'
import {
  KeyRound, Lock, ShieldCheck, Eye, EyeOff, Check, X, RefreshCw, Plus, Trash2,
  ExternalLink, AlertTriangle, ScrollText, Download, Upload, Loader2, Sparkles, Copy,
  Wand2, SkipForward, ChevronDown, Cpu,
} from 'lucide-react'
import { getLlmConfig, type LlmProvider } from '../api.chat'
import { getIntegrations, vaultSetup, vaultLock, vaultReload, getVaultAudit, vaultExport, vaultImport, createVaultProfile, connectIntegration, testIntegration, revealSecret, addCustomSecret, removeIntegration, googleOAuthUrl, googleOAuthStatus, googleDisconnect, type IntegrationsResponse, type Integration, type IntegrationField, type AuditEntry, type GenesisStatus } from '../api.genesis'
import { useToast } from '../context/ToastProvider'
import { useSound } from '../hooks/useSound'
import PageLoader from '../components/PageLoader'
import BrandLogo from '../components/BrandLogo'
import LlmLogo from '../components/LlmLogo'
import KeySlots from '../components/KeySlots'
import VaultUnlockPanel from '../components/VaultUnlockPanel'
import { useVaultSession } from '../hooks/useVaultSession'

const CAT_LABEL: Record<string, string> = {
  core: 'Core prerequisites', tools: 'Tools', coming_soon: 'Coming in Awakening',
}

export default function Integrations() {
  const { toast } = useToast()
  const sfx = useSound()
  const [data, setData] = useState<IntegrationsResponse | null>(null)
  const [providers, setProviders] = useState<LlmProvider[]>([])   // LLM/model providers → vault keys
  const [loading, setLoading] = useState(true)
  const session = useVaultSession()
  const [showAudit, setShowAudit] = useState(false)
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [wizardOpen, setWizardOpen] = useState(false)
  const wasComplete = useMemo(() => data?.genesis.complete, [data?.genesis.complete]) // eslint-disable-line

  const load = useCallback(async () => {
    try { setData(await getIntegrations()) }
    catch (e) { toast({ kind: 'error', title: 'Could not load integrations', detail: (e as Error).message }) }
    finally { setLoading(false) }
    try { setProviders((await getLlmConfig()).providers) } catch (error) { softFail('your integrations')(error) }
  }, [toast])

  useEffect(() => { load() }, [load, session])

  const onLocked = () => { toast({ kind: 'info', title: 'Vault locked', detail: 'Unlock to continue.' }) }

  // celebrate when Genesis flips to complete
  const celebrate = (g: GenesisStatus | undefined) => {
    if (g?.complete && !wasComplete) { sfx.tierUp(); toast({ kind: 'success', title: 'Genesis complete!', detail: 'All 12 abilities active — Tier 0 unlocked.' }) }
  }

  const refreshAudit = useCallback(async () => {
    try { setAudit((await getVaultAudit(80)).entries) } catch (error) { softFail('your integrations')(error) }
  }, [])

  if (loading) return <PageLoader preset="integrations" />

  const vault = data?.vault
  if (!vault?.crypto_available) {
    return <Centered icon={<AlertTriangle className="text-warning" />} title="Vault unavailable"
      body="The 'cryptography' package isn't installed on the backend. Run: pip install cryptography, then restart." />
  }

  // ── gates ──
  if (!session) {
    return vault.setup
      ? <VaultUnlockPanel title="Unlock Integrations" detail="One unlock authorizes protected Mission Control tools in this browser tab." />
      : <SetupGate onDone={load} />
  }

  const genesis = data!.genesis
  const groups = (cat: string) => data!.integrations.filter(i => i.category === cat)
  // Keys already surfaced by a registry integration above (e.g. Anthropic/OpenRouter in
  // the "LLM Provider" card) shouldn't appear twice — the AI Models section shows the rest.
  const coveredKeys = new Set(data!.integrations.flatMap(i => i.fields.map(f => f.name)))
  const modelProviders = providers.filter(p => p.needs_key && p.key_env && !coveredKeys.has(p.key_env))

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-5 py-6">
        {/* Header */}
        <div className="mb-5 flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent"><KeyRound size={18} /></div>
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-bold text-heading">Integrations & Secrets</h1>
            <p className="text-xs text-muted">Configure the keys that power Tobi — encrypted, in Mission Control.</p>
          </div>
          <Toolbar onReload={async () => { try { await vaultReload(); toast({ kind: 'success', title: 'Reloaded into the live process' }); load() } catch (e) { handleErr(e, onLocked, toast) } }}
            onLock={async () => { await vaultLock(); toast({ kind: 'info', title: 'Vault locked' }) }}
            onAudit={() => { setShowAudit(s => !s); refreshAudit() }}
            onExport={() => exportFlow(toast)} onImport={() => importFlow(toast, () => load())}
            profiles={vault.profiles.map(p => p.name)} active={vault.active_profile}
            onProfile={async (name) => { try { await createVaultProfile(name); toast({ kind: 'success', title: `Profile: ${name}` }); load() } catch (e) { handleErr(e, onLocked, toast) } }} />
        </div>

        {/* Genesis progress */}
        <GenesisHeader genesis={genesis} onStartWizard={() => setWizardOpen(true)} />

        {/* Sections — full-width collapsible rows, one integration per line */}
        {(['core', 'tools', 'coming_soon'] as const).map(cat => {
          const items = groups(cat)
          if (!items.length) return null
          return (
            <section key={cat} className="mt-6">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-muted">
                {cat === 'core' && <ShieldCheck size={13} className="text-accent" />} {CAT_LABEL[cat]}
              </div>
              <div className="space-y-2">
                {items.map(it => (
                  <IntegrationCard key={it.id} it={it}
                    onChanged={(g) => { celebrate(g); load() }} onLocked={onLocked} />
                ))}
              </div>
            </section>
          )
        })}

        {/* AI Models — providers from the Models page, keys stored in this same vault */}
        {modelProviders.length > 0 && (
          <section className="mt-6">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-muted">
              <Cpu size={13} className="text-accent" /> AI Models
            </div>
            <div className="space-y-2">
              {modelProviders.map(p => (
                <ModelProviderRow key={p.id} p={p} onChanged={() => load()} />
              ))}
            </div>
          </section>
        )}

        <CustomSecrets onAdded={(g) => { celebrate(g); load() }} onLocked={onLocked} />

        {showAudit && <AuditPanel entries={audit} onClose={() => setShowAudit(false)} />}
      </div>

      {wizardOpen && (
        <GenesisWizard integrations={data!.integrations} genesis={genesis}
          onChanged={(g) => { celebrate(g); load() }} onClose={() => setWizardOpen(false)} onLocked={onLocked} />
      )}
    </div>
  )
}

// ── helpers ─────────────────────────────────────────────────────────
function handleErr(e: unknown, onLocked: () => void, toast: ReturnType<typeof useToast>['toast']) {
  const err = e as { status?: number; message?: string }
  if (err.status === 401) { onLocked(); return }
  toast({ kind: 'error', title: 'Failed', detail: err.message || 'Error' })
}

async function exportFlow(toast: ReturnType<typeof useToast>['toast']) {
  const pw = window.prompt('Backup password (you will need it to restore):')
  if (!pw) return
  try {
    const { blob } = await vaultExport(pw)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([blob], { type: 'text/plain' }))
    a.download = `tobi-vault-backup-${new Date().toISOString().slice(0, 10)}.txt`
    a.click(); URL.revokeObjectURL(a.href)
    toast({ kind: 'success', title: 'Encrypted backup downloaded' })
  } catch (e) { toast({ kind: 'error', title: 'Export failed', detail: (e as Error).message }) }
}

function importFlow(toast: ReturnType<typeof useToast>['toast'], reload: () => void) {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.txt'
  input.onchange = async () => {
    const file = input.files?.[0]; if (!file) return
    const pw = window.prompt('Backup password:')
    if (!pw) return
    try {
      const blob = (await file.text()).trim()
      const r = await vaultImport(blob, pw)
      toast({ kind: 'success', title: `Restored ${r.imported} secret(s)` }); reload()
    } catch (e) { toast({ kind: 'error', title: 'Import failed', detail: (e as Error).message }) }
  }
  input.click()
}

// ── gates ───────────────────────────────────────────────────────────
function Centered({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-surface">{icon}</div>
      <div className="text-sm font-semibold text-heading">{title}</div>
      <div className="max-w-md text-xs leading-relaxed text-muted">{body}</div>
    </div>
  )
}

function SetupGate({ onDone }: { onDone: () => void }) {
  const { toast } = useToast()
  const [pw, setPw] = useState(''); const [pw2, setPw2] = useState(''); const [busy, setBusy] = useState(false)
  const submit = async () => {
    if (pw.length < 6) return toast({ kind: 'error', title: 'Use at least 6 characters' })
    if (pw !== pw2) return toast({ kind: 'error', title: 'Passwords do not match' })
    setBusy(true)
    try { await vaultSetup(pw, true); toast({ kind: 'success', title: 'Vault created', detail: 'Imported any keys already in your environment.' }); onDone() }
    catch (e) { toast({ kind: 'error', title: 'Setup failed', detail: (e as Error).message }) }
    finally { setBusy(false) }
  }
  return (
    <GateShell title="Create your vault" icon={<KeyRound size={20} />}>
      <p className="mb-3 text-xs leading-relaxed text-muted">
        Set a master password to encrypt your API keys at rest (AES-256-GCM). It's held only in memory while unlocked.
      </p>
      <div className="mb-3 flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-2.5 text-[11px] text-warning">
        <AlertTriangle size={14} className="mt-0.5 shrink-0" />
        <span>If you lose this password the vault is <b>unrecoverable</b> by design. Make an encrypted backup after setup.</span>
      </div>
      <input type="password" value={pw} onChange={e => setPw(e.target.value)} placeholder="Master password"
        className={inputCls} onKeyDown={e => e.key === 'Enter' && submit()} />
      <input type="password" value={pw2} onChange={e => setPw2(e.target.value)} placeholder="Confirm password"
        className={`${inputCls} mt-2`} onKeyDown={e => e.key === 'Enter' && submit()} />
      <button onClick={submit} disabled={busy} className={btnPrimary}>
        {busy ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />} Create vault
      </button>
    </GateShell>
  )
}

function GateShell({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-surface p-6">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent">{icon}</div>
          <div className="text-sm font-bold text-heading">{title}</div>
        </div>
        {children}
      </div>
    </div>
  )
}

// ── Genesis header ──────────────────────────────────────────────────
function GenesisHeader({ genesis, onStartWizard }: { genesis: GenesisStatus; onStartWizard?: () => void }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-heading">
          <Sparkles size={15} className={genesis.complete ? 'text-success' : 'text-accent'} />
          Genesis (Tier 0){genesis.complete && <span className="rounded-full bg-success/20 px-2 py-0.5 text-[10px] text-success">COMPLETE</span>}
        </div>
        <div className="flex items-center gap-2">
          <div className="text-xs text-muted">{genesis.active} / {genesis.total} abilities</div>
          {!genesis.complete && onStartWizard && (
            <button onClick={onStartWizard} className="flex items-center gap-1 rounded-lg bg-accent/20 px-2.5 py-1 text-[11px] font-semibold text-accent transition-colors hover:bg-accent/30">
              <Wand2 size={12} /> Complete Genesis
            </button>
          )}
        </div>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-border/40">
        <div className={`h-full rounded-full transition-all duration-700 ${genesis.complete ? 'bg-success' : 'bg-accent'}`} style={{ width: `${genesis.pct}%` }} />
      </div>
      <div className="mt-1.5 text-[11px] text-muted">
        {genesis.complete ? 'Every Genesis ability is active. 🎉' : `${genesis.pct}% — connect the required integrations below to complete Genesis.`}
      </div>
    </div>
  )
}

// ── Complete-Genesis wizard ─────────────────────────────────────────
function GenesisWizard({ integrations, genesis, onChanged, onClose, onLocked }: {
  integrations: Integration[]; genesis: GenesisStatus
  onChanged: (g?: GenesisStatus) => void; onClose: () => void; onLocked: () => void
}) {
  const { toast } = useToast()
  // Snapshot the steps once: available integrations that still unlock an inactive
  // Genesis ability — required ones first.
  const [order] = useState<string[]>(() =>
    integrations
      .filter(i => i.available && i.abilities.some(a => !a.active))
      .sort((a, b) => Number(b.required) - Number(a.required))
      .map(i => i.id))
  const [idx, setIdx] = useState(0)
  const [vals, setVals] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const cur = idx < order.length ? integrations.find(i => i.id === order[idx]) : undefined
  const finished = idx >= order.length

  const connect = async () => {
    if (!cur) return
    const fields = Object.fromEntries(Object.entries(vals).filter(([, v]) => v.trim()))
    if (!Object.keys(fields).length) return toast({ kind: 'error', title: 'Enter a value first' })
    setBusy(true); setErr(null)
    try {
      const r = await connectIntegration(cur.id, fields)
      toast({ kind: 'success', title: `${cur.label} connected`, detail: r.message })
      setVals({}); onChanged(r.genesis); setIdx(i => i + 1)
    } catch (e) {
      const ex = e as { status?: number; message?: string }
      if (ex.status === 401) { onLocked(); onClose(); return }
      setErr(ex.message || 'Failed')
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div onClick={e => e.stopPropagation()} className="w-full max-w-md overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl">
        <div className="border-b border-border p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-bold text-heading"><Wand2 size={16} className="text-accent" /> Complete Genesis</div>
            <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-border/40">
            <div className={`h-full rounded-full transition-all duration-700 ${genesis.complete ? 'bg-success' : 'bg-accent'}`} style={{ width: `${genesis.pct}%` }} />
          </div>
          <div className="mt-1.5 flex justify-between text-[11px] text-muted">
            <span>{genesis.active} / {genesis.total} abilities</span>
            {!genesis.complete && !finished && <span>Step {idx + 1} of {order.length}</span>}
          </div>
        </div>

        {genesis.complete ? (
          <div className="flex flex-col items-center gap-2 p-8 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-success/15 text-success"><Sparkles size={26} /></div>
            <div className="text-base font-bold text-heading">Genesis complete! 🎉</div>
            <p className="text-xs text-muted">All {genesis.total} Tier 0 abilities are active.</p>
            <button onClick={onClose} className="mt-2 rounded-lg bg-accent/20 px-4 py-2 text-xs font-semibold text-accent hover:bg-accent/30">Done</button>
          </div>
        ) : finished || !cur ? (
          <div className="flex flex-col items-center gap-2 p-8 text-center">
            <div className="text-sm font-semibold text-heading">Integrations done — {genesis.pct}%</div>
            <p className="max-w-xs text-xs text-muted">The remaining abilities come from non-integration sources (SOUL.md, conversation history, the lessons store) rather than keys.</p>
            <button onClick={onClose} className="mt-2 rounded-lg border border-border px-4 py-2 text-xs text-muted hover:text-text">Close</button>
          </div>
        ) : (
          <div className="space-y-3 p-4">
            <div className="flex items-start gap-2.5">
              <BrandLogo id={cur.id} label={cur.label} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-heading">{cur.label}</span>
                  {cur.required
                    ? <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[9px] font-bold uppercase text-accent">Required</span>
                    : <span className="rounded bg-muted/20 px-1.5 py-0.5 text-[9px] uppercase text-muted">Optional</span>}
                </div>
                <p className="mt-0.5 text-[11px] leading-snug text-muted">{cur.blurb}</p>
              </div>
            </div>
            {cur.abilities.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {cur.abilities.map(a => (
                  <span key={a.id} className={`flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ${a.active ? 'bg-success/15 text-success' : 'bg-border/40 text-muted'}`}>
                    {a.active ? <Check size={9} /> : <span className="h-1.5 w-1.5 rounded-full bg-current opacity-50" />}{a.name}
                  </span>
                ))}
              </div>
            )}
            {cur.fields.map(f => (
              <div key={f.name}>
                <div className="mb-0.5 flex items-center justify-between">
                  <span className="text-[10px] uppercase tracking-wide text-muted">{f.label}</span>
                  {f.help_url && <a href={f.help_url} target="_blank" rel="noreferrer" className="flex items-center gap-0.5 text-[10px] text-accent hover:underline">get key <ExternalLink size={9} /></a>}
                </div>
                <input type="password" value={vals[f.name] || ''} onChange={e => setVals(s => ({ ...s, [f.name]: e.target.value }))}
                  placeholder={f.set ? `connected ••••${f.last4 || ''} — replace` : f.name} className={inputCls} />
              </div>
            ))}
            {err && <div className="rounded border border-danger/30 bg-danger/10 px-2 py-1 text-[11px] text-danger">{err}</div>}
            <div className="flex items-center gap-2 pt-1">
              <button onClick={connect} disabled={busy} className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-accent/20 py-2 text-xs font-semibold text-accent hover:bg-accent/30 disabled:opacity-50">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Connect & continue
              </button>
              <button onClick={() => { setVals({}); setErr(null); setIdx(i => i + 1) }}
                className="flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-xs text-muted hover:text-text">
                <SkipForward size={12} /> Skip
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Row shell: a full-width, one-line header that expands to reveal keys ──
function RowShell({ logo, title, badges, subtitle, pill, open, onToggle, accent, dim, children }: {
  logo: React.ReactNode; title: string; badges?: React.ReactNode; subtitle?: string
  pill?: React.ReactNode; open: boolean; onToggle: () => void; accent?: boolean; dim?: boolean
  children?: React.ReactNode
}) {
  return (
    <div className={`overflow-hidden rounded-xl border bg-surface transition-colors ${dim ? 'border-border opacity-70' : accent ? 'border-accent/40' : 'border-border'}`}>
      <button onClick={onToggle} className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left">
        {logo}
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span className="truncate text-sm font-semibold text-heading">{title}</span>
          {badges}
        </div>
        {pill}
        <ChevronDown size={16} className={`shrink-0 text-muted transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="border-t border-border/60 px-3.5 pb-3.5 pt-3">
          {subtitle && <p className="mb-2.5 text-[11px] leading-snug text-muted">{subtitle}</p>}
          {children}
        </div>
      )}
    </div>
  )
}

function AbilityChips({ abilities }: { abilities: Integration['abilities'] }) {
  if (!abilities.length) return null
  return (
    <div className="mb-2.5 flex flex-wrap gap-1">
      {abilities.map(a => (
        <span key={a.id} className={`flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ${a.active ? 'bg-success/15 text-success' : 'bg-border/40 text-muted'}`}>
          {a.active ? <Check size={9} /> : <span className="h-1.5 w-1.5 rounded-full bg-current opacity-50" />}{a.name}
        </span>
      ))}
    </div>
  )
}

// ── Integration row (full-width, collapsible; API keys → multi-key vault slots) ──
function IntegrationCard({ it, onChanged, onLocked }: { it: Integration; onChanged: (g?: GenesisStatus) => void; onLocked: () => void }) {
  const { toast } = useToast()
  const [vals, setVals] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<'' | 'connect' | 'test' | 'remove' | 'oauth'>('')
  const [err, setErr] = useState<string | null>(null)
  const [open, setOpen] = useState(it.available && !it.connected)   // needs attention → start open
  const locked = !it.available
  const formFields = it.fields.filter(f => f.type !== 'api_key')    // url/oauth/webhook still use Connect
  const isGoogle = it.id === 'google'
  const [gConnected, setGConnected] = useState(false)
  const [gEmail, setGEmail] = useState('')
  const [gRedirectUri, setGRedirectUri] = useState('')

  // Poll Google OAuth status when the card is open and it's Google
  useEffect(() => {
    if (!isGoogle || !open) return
    let alive = true
    const poll = () => googleOAuthStatus().then(s => {
      if (!alive) return
      setGConnected(s.connected)
      setGEmail(s.email)
      setGRedirectUri(s.redirect_uri)
    }).catch(() => {})
    poll()
    const iv = setInterval(poll, 3000)
    return () => { alive = false; clearInterval(iv) }
  }, [isGoogle, open])

  const connect = async () => {
    const fields = Object.fromEntries(Object.entries(vals).filter(([, v]) => v.trim()))
    if (!Object.keys(fields).length) return toast({ kind: 'error', title: 'Enter a value first' })
    setBusy('connect'); setErr(null)
    try {
      const r = await connectIntegration(it.id, fields)
      toast({ kind: 'success', title: `${it.label} connected`, detail: r.message }); setVals({}); onChanged(r.genesis)
    } catch (e) {
      const ex = e as { status?: number; message?: string }
      if (ex.status === 401) return onLocked()
      setErr(ex.message || 'Failed'); toast({ kind: 'error', title: `${it.label} test failed`, detail: ex.message })
    } finally { setBusy('') }
  }
  const test = async () => {
    setBusy('test'); setErr(null)
    try { const r = await testIntegration(it.id); toast({ kind: r.ok ? 'success' : 'error', title: r.ok ? 'Test passed' : 'Test failed', detail: r.message }); if (!r.ok) setErr(r.message); onChanged(r.genesis) }
    catch (e) { handleErr(e, onLocked, toast) } finally { setBusy('') }
  }
  const remove = async () => {
    if (!window.confirm(`Remove ${it.label} and its secrets?`)) return
    setBusy('remove')
    try { const r = await removeIntegration(it.id); toast({ kind: 'success', title: `${it.label} removed` }); onChanged(r.genesis) }
    catch (e) { handleErr(e, onLocked, toast) } finally { setBusy('') }
  }

  const startOAuth = async () => {
    setBusy('oauth')
    try {
      const url = await googleOAuthUrl()
      const popup = window.open(url, 'google-oauth', 'width=500,height=650')
      if (!popup) { toast({ kind: 'error', title: 'Popup blocked', detail: 'Allow popups for this page.' }); return }
      toast({ kind: 'info', title: 'Google consent opened', detail: 'Authorize in the popup window.' })
    } finally { setBusy('') }
  }

  const disconnectGoogle = async () => {
    if (!window.confirm('Disconnect Google? Tokens will be revoked.')) return
    setBusy('oauth')
    try { await googleDisconnect(); setGConnected(false); setGEmail(''); toast({ kind: 'success', title: 'Google disconnected' }); onChanged() }
    catch { toast({ kind: 'error', title: 'Disconnect failed' }) } finally { setBusy('') }
  }

  return (
    <RowShell open={open} onToggle={() => setOpen(o => !o)} accent={it.connected} dim={locked}
      logo={<BrandLogo id={it.id} label={it.label} />} title={it.label} subtitle={it.blurb || undefined} pill={<StatusPill it={it} />}
      badges={<>
        {it.required && <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[9px] font-bold uppercase text-accent">Required</span>}
        {locked && <span className="rounded bg-muted/20 px-1.5 py-0.5 text-[9px] uppercase text-muted">{it.coming_in}</span>}
      </>}>
      <AbilityChips abilities={it.abilities} />
      {locked ? (
        <p className="text-[11px] text-muted">Configurable when {it.coming_in || 'a later tier'} lands.</p>
      ) : (
        <div className="space-y-2.5">
          {it.fields.map(f => (
            f.type === 'api_key'
              ? (
                <div key={f.name}>
                  <FieldLabel field={f} />
                  <KeySlots name={f.name} locked={false} envLast4={f.last4} onChanged={() => onChanged()} />
                </div>
              )
              : (
                <SecretField key={f.name} field={f} value={vals[f.name] || ''}
                  onChange={v => setVals(s => ({ ...s, [f.name]: v }))} />
              )
          ))}
          {err && <div className="rounded border border-danger/30 bg-danger/10 px-2 py-1 text-[11px] text-danger">{err}</div>}
          <div className="flex items-center gap-1.5 pt-0.5">
            {formFields.length > 0 && (
              <button onClick={connect} disabled={!!busy} className={cardBtn('accent')}>
                {busy === 'connect' ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} {it.connected ? 'Update' : 'Save'}
              </button>
            )}
            {it.connected && <button onClick={test} disabled={!!busy} className={cardBtn()}>{busy === 'test' ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />} Test</button>}
            {it.connected && <button onClick={remove} disabled={!!busy} className={cardBtn('danger')}><Trash2 size={12} /> Remove</button>}
          </div>
          {isGoogle && it.connected && (
            <div className="rounded-lg border border-border bg-surface/50 p-2.5">
              {!gConnected && (
                <div className="mb-2 rounded bg-accent/5 px-2 py-1 text-[10px] text-muted">
                  <span className="font-medium text-text">Redirect URI for Google Console:</span>
                  <code className="block break-all text-[10px] text-accent">{gRedirectUri}</code>
                  <span className="text-[9px]">Add this exact URI to your OAuth client's "Authorized redirect URIs".</span>
                </div>
              )}
              {gConnected ? (
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-success/15 text-success"><Check size={12} /></span>
                    <div>
                      <p className="text-[11px] font-medium text-text">Connected{gEmail ? ` as ${gEmail}` : ''}</p>
                      <p className="text-[10px] text-muted">Drive, Gmail & Calendar active</p>
                    </div>
                  </div>
                  <button onClick={disconnectGoogle} disabled={!!busy} className={cardBtn('danger')}>
                    {busy === 'oauth' ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />} Revoke
                  </button>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-[11px] font-medium text-text">Not authorized yet</p>
                    <p className="text-[10px] text-muted">Click to grant Drive, Gmail & Calendar access</p>
                  </div>
                  <button onClick={startOAuth} disabled={!!busy} className="flex items-center gap-1.5 rounded-lg bg-[#4285F4] px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-[#3367D6] disabled:opacity-50">
                    {busy === 'oauth' ? <Loader2 size={12} className="animate-spin" /> : <ShieldCheck size={12} />} Authorize
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </RowShell>
  )
}

// ── AI Model provider row (Models-page providers, keys in this same vault) ──
function ModelProviderRow({ p, onChanged }: { p: LlmProvider; onChanged: () => void }) {
  const [open, setOpen] = useState(!p.key_present)
  const pill = p.key_present
    ? <span className="shrink-0 rounded-full bg-success/15 px-2 py-0.5 text-[10px] text-success">Key set</span>
    : <span className="shrink-0 rounded-full bg-border/40 px-2 py-0.5 text-[10px] text-muted">No key</span>
  return (
    <RowShell open={open} onToggle={() => setOpen(o => !o)} accent={p.key_present}
      logo={<LlmLogo provider={p.id} size={18} />} title={p.label} pill={pill}
      badges={<span className="rounded bg-muted/15 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted">{p.models.length} model{p.models.length === 1 ? '' : 's'}</span>}>
      <KeySlots name={p.key_env!} locked={false} envLast4={p.key_last4} onChanged={onChanged} />
    </RowShell>
  )
}

function FieldLabel({ field }: { field: IntegrationField }) {
  return (
    <div className="mb-1 flex items-center justify-between">
      <span className="text-[10px] uppercase tracking-wide text-muted">{field.label}</span>
      {field.help_url && <a href={field.help_url} target="_blank" rel="noreferrer" className="flex items-center gap-0.5 text-[10px] text-accent hover:underline">get key <ExternalLink size={9} /></a>}
    </div>
  )
}

function StatusPill({ it }: { it: Integration }) {
  if (!it.available) return <span className="shrink-0 rounded-full bg-muted/15 px-2 py-0.5 text-[10px] text-muted">Soon</span>
  const anyFailed = it.fields.some(f => f.test_status === 'failed')
  if (!it.connected) return <span className="shrink-0 rounded-full bg-border/40 px-2 py-0.5 text-[10px] text-muted">Not set</span>
  if (anyFailed) return <span className="shrink-0 rounded-full bg-danger/15 px-2 py-0.5 text-[10px] text-danger">Failing</span>
  return <span className="shrink-0 rounded-full bg-success/15 px-2 py-0.5 text-[10px] text-success">Connected</span>
}

function SecretField({ field, value, onChange }: {
  field: IntegrationField; value: string; onChange: (v: string) => void
}) {
  const { toast } = useToast()
  const [revealed, setRevealed] = useState<string | null>(null)
  const [asking, setAsking] = useState(false)
  const [pw, setPw] = useState(''); const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  const doReveal = async () => {
    if (!pw) return
    setBusy(true)
    try {
      const r = await revealSecret(field.name, pw)
      setRevealed(r.value); setAsking(false); setPw('')
      setTimeout(() => setRevealed(null), 20000)  // auto-hide after 20s
    } catch (e) { toast({ kind: 'error', title: 'Reveal failed', detail: (e as Error).message }) }
    finally { setBusy(false) }
  }
  const copy = async () => {
    if (!revealed) return
    try { await navigator.clipboard.writeText(revealed); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* ignore */ }
  }

  return (
    <div>
      <div className="mb-0.5 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wide text-muted">{field.label}</span>
        {field.help_url && <a href={field.help_url} target="_blank" rel="noreferrer" className="flex items-center gap-0.5 text-[10px] text-accent hover:underline">get key <ExternalLink size={9} /></a>}
      </div>
      {field.set ? (
        <div className="flex items-center gap-1.5">
          <code onClick={revealed ? copy : undefined} title={revealed ? 'Click to copy' : undefined}
            className={`flex-1 truncate rounded border border-border bg-bg px-2 py-1.5 text-[11px] ${revealed ? 'cursor-pointer text-accent' : 'text-text'}`}>
            {copied ? 'copied!' : (revealed ?? `••••••••${field.last4 || ''}`)}
          </code>
          {revealed && (
            <button onClick={copy} title="Copy to clipboard"
              className="rounded border border-border p-1.5 text-muted transition-colors hover:text-accent">{copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}</button>
          )}
          <button onClick={() => (revealed ? setRevealed(null) : setAsking(true))} title={revealed ? 'Hide' : 'Reveal'}
            className="rounded border border-border p-1.5 text-muted transition-colors hover:text-accent">{revealed ? <EyeOff size={12} /> : <Eye size={12} />}</button>
          <input type="password" value={value} onChange={e => onChange(e.target.value)} placeholder="replace…" className="w-24 rounded border border-border bg-bg px-2 py-1.5 text-[11px] text-text outline-none focus:border-accent/60" />
        </div>
      ) : (
        <input type="password" value={value} onChange={e => onChange(e.target.value)} placeholder={field.name} className="w-full rounded border border-border bg-bg px-2 py-1.5 text-[11px] text-text outline-none focus:border-accent/60" />
      )}

      {asking && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => setAsking(false)}>
          <div onClick={e => e.stopPropagation()} className="w-full max-w-xs rounded-xl border border-border bg-surface p-4 shadow-2xl">
            <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-heading"><Eye size={14} className="text-accent" /> Reveal {field.name}</div>
            <p className="mb-3 text-[11px] leading-relaxed text-muted">Re-enter your master password to view this secret.</p>
            <input autoFocus type="password" value={pw} onChange={e => setPw(e.target.value)} onKeyDown={e => e.key === 'Enter' && doReveal()}
              placeholder="Master password" className={inputCls} />
            <div className="mt-3 flex gap-2">
              <button onClick={doReveal} disabled={busy || !pw} className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-accent/20 py-2 text-xs font-semibold text-accent hover:bg-accent/30 disabled:opacity-50">
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Eye size={13} />} Reveal
              </button>
              <button onClick={() => { setAsking(false); setPw('') }} className="rounded-lg border border-border px-3 py-2 text-xs text-muted hover:text-text">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── custom secrets ──────────────────────────────────────────────────
function CustomSecrets({ onAdded, onLocked }: { onAdded: (g?: GenesisStatus) => void; onLocked: () => void }) {
  const { toast } = useToast()
  const [name, setName] = useState(''); const [val, setVal] = useState(''); const [busy, setBusy] = useState(false)
  const add = async () => {
    if (!name.trim() || !val.trim()) return
    setBusy(true)
    try { const r = await addCustomSecret(name.trim(), val.trim()); toast({ kind: 'success', title: `Saved ${name.trim().toUpperCase()}` }); setName(''); setVal(''); onAdded(r.genesis) }
    catch (e) { handleErr(e, onLocked, toast) } finally { setBusy(false) }
  }
  return (
    <section className="mt-6">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">Custom secret</div>
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-surface p-3">
        <input value={name} onChange={e => setName(e.target.value)} placeholder="ENV_VAR_NAME" className="w-44 rounded border border-border bg-bg px-2 py-1.5 text-xs text-text outline-none focus:border-accent/60" />
        <input type="password" value={val} onChange={e => setVal(e.target.value)} placeholder="value" className="flex-1 rounded border border-border bg-bg px-2 py-1.5 text-xs text-text outline-none focus:border-accent/60" />
        <button onClick={add} disabled={busy} className={cardBtn('accent')}>{busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Add</button>
      </div>
    </section>
  )
}

// ── toolbar + audit ─────────────────────────────────────────────────
function Toolbar({ onReload, onLock, onAudit, onExport, onImport, profiles, active, onProfile }: {
  onReload: () => void; onLock: () => void; onAudit: () => void; onExport: () => void; onImport: () => void
  profiles: string[]; active: string; onProfile: (name: string) => void
}) {
  const tb = 'flex items-center gap-1 rounded-lg border border-border px-2 py-1.5 text-[11px] text-muted hover:text-text hover:border-accent/40 transition-colors'
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <select value={active} onChange={e => { const v = e.target.value; if (v === '__new') { const n = window.prompt('New profile name (e.g. vps):'); if (n) onProfile(n) } else onProfile(v) }}
        className="rounded-lg border border-border bg-bg px-2 py-1.5 text-[11px] text-text outline-none">
        {profiles.map(p => <option key={p} value={p}>{p}</option>)}
        <option value="__new">+ new profile…</option>
      </select>
      <button onClick={onAudit} className={tb}><ScrollText size={13} /> Audit</button>
      <button onClick={onExport} className={tb}><Download size={13} /></button>
      <button onClick={onImport} className={tb}><Upload size={13} /></button>
      <button onClick={onReload} className={tb}><RefreshCw size={13} /> Reload</button>
      <button onClick={onLock} className={`${tb} text-accent`}><Lock size={13} /> Lock</button>
    </div>
  )
}

function AuditPanel({ entries, onClose }: { entries: AuditEntry[]; onClose: () => void }) {
  return (
    <section className="mt-6 rounded-xl border border-border bg-surface p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-muted"><ScrollText size={13} /> Audit log</div>
        <button onClick={onClose} className="text-muted hover:text-text"><X size={14} /></button>
      </div>
      <div className="max-h-64 space-y-1 overflow-y-auto">
        {entries.length === 0 && <div className="py-4 text-center text-xs text-muted">No activity yet.</div>}
        {entries.map((a, i) => (
          <div key={i} className="flex items-center gap-2 border-b border-border/40 py-1 text-[11px] last:border-0">
            <span className={`w-14 shrink-0 font-mono ${a.ok === false ? 'text-danger' : a.ok ? 'text-success' : 'text-muted'}`}>{a.action}</span>
            <span className="flex-1 truncate text-text">{a.name || a.integration_id || a.detail || '—'}</span>
            <span className="shrink-0 text-muted">{new Date(a.ts).toLocaleString()}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

// ── shared styles ───────────────────────────────────────────────────
const inputCls = 'w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent/60'
const btnPrimary = 'mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-accent/20 py-2 text-sm font-semibold text-accent transition-colors hover:bg-accent/30 disabled:opacity-50'
function cardBtn(kind: 'accent' | 'danger' | '' = '') {
  const base = 'flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors disabled:opacity-50'
  if (kind === 'accent') return `${base} bg-accent/20 text-accent hover:bg-accent/30`
  if (kind === 'danger') return `${base} bg-danger/15 text-danger hover:bg-danger/25`
  return `${base} border border-border text-muted hover:text-text`
}
