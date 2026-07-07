import { useEffect, useState } from 'react'
import { KeyRound, Plus, Trash2, Loader2, Lock } from 'lucide-react'
import {
  type KeySlot, type KeySlotsResponse,
  listKeySlots, addKeySlot, activateKeySlot, deactivateKeySlots, deleteKeySlot,
} from '../api'
import { useToast } from '../context/ToastProvider'

/**
 * Multi-key manager for one secret (env-var name): several stored accounts,
 * ONE active at a time. Toggling a key on switches the provider to that account
 * live; toggling the active key off disconnects the provider (key stays stored).
 * Used by the Models provider cards and the Integrations secret fields.
 */
export default function KeySlots({ name, locked, envLast4, onChanged }: {
  name: string
  locked: boolean
  envLast4?: string | null   // last4 of a key coming from .env — shown read-only when vault is locked
  onChanged?: (r: KeySlotsResponse) => void
}) {
  const { toast } = useToast()
  const [slots, setSlots] = useState<KeySlot[] | null>(null)
  const [unavailable, setUnavailable] = useState(false)  // vault not set up / crypto missing
  const [busy, setBusy] = useState<string | null>(null)
  const [newKey, setNewKey] = useState('')
  const [newLabel, setNewLabel] = useState('')

  useEffect(() => {
    if (locked) { setSlots(null); return }
    setUnavailable(false)
    listKeySlots(name).then(r => setSlots(r.slots)).catch(() => { setSlots([]); setUnavailable(true) })
  }, [name, locked])

  const run = async (op: string, fn: () => Promise<KeySlotsResponse>) => {
    setBusy(op)
    try {
      const r = await fn()
      setSlots(r.slots); onChanged?.(r)
      return true
    } catch (e) {
      toast({ kind: 'error', title: 'Key change failed', detail: (e as Error).message })
      return false
    } finally { setBusy(null) }
  }

  const add = async () => {
    const v = newKey.trim()
    if (!v) return
    const activate = !(slots || []).some(s => s.active)  // first/only key goes live
    if (await run('add', () => addKeySlot(name, v, newLabel.trim() || undefined, activate))) {
      setNewKey(''); setNewLabel('')
      toast({ kind: 'success', title: activate ? 'Key added & live' : 'Key added', detail: activate ? undefined : 'Toggle it on to switch accounts.' })
    }
  }
  const toggle = (s: KeySlot) =>
    run(`t:${s.label}`, () => (s.active ? deactivateKeySlots(name) : activateKeySlot(name, s.label)))
  const remove = (s: KeySlot) => run(`d:${s.label}`, () => deleteKeySlot(name, s.label))

  if (locked) return (
    <div className="space-y-1">
      {envLast4 && (
        <div className="flex items-center gap-2 rounded-lg border border-accent/40 bg-accent/5 px-2 py-1.5">
          <KeyRound size={12} className="shrink-0 text-accent" />
          <span className="min-w-0 flex-1 truncate text-xs text-text">Current key</span>
          <code className="shrink-0 text-[10px] text-muted">••••{envLast4}</code>
          <span className="shrink-0 rounded-full bg-accent/15 px-1.5 py-0.5 text-[9px] font-semibold text-accent">FROM .ENV</span>
        </div>
      )}
      <p className="px-0.5 py-0.5 text-[11px] text-muted">Unlock the vault to add or switch keys.</p>
    </div>
  )

  // Vault not set up / crypto missing → the slot API is unreachable. Still show the
  // live .env key (read-only) so the card reflects reality, and point at the vault.
  if (unavailable) return (
    <div className="space-y-1">
      {envLast4 ? (
        <div className="flex items-center gap-2 rounded-lg border border-accent/40 bg-accent/5 px-2 py-1.5">
          <KeyRound size={12} className="shrink-0 text-accent" />
          <span className="min-w-0 flex-1 truncate text-xs text-text">Current key</span>
          <code className="shrink-0 text-[10px] text-muted">••••{envLast4}</code>
          <span className="shrink-0 rounded-full bg-accent/15 px-1.5 py-0.5 text-[9px] font-semibold text-accent">FROM .ENV</span>
        </div>
      ) : null}
      <p className="px-0.5 py-0.5 text-[11px] text-muted">Set up the vault to store multiple keys per provider.</p>
    </div>
  )

  return (
    <div className="space-y-1.5">
      {slots === null ? (
        <div className="flex items-center gap-1.5 px-0.5 py-1 text-[11px] text-muted"><Loader2 size={11} className="animate-spin" /> Loading keys…</div>
      ) : (
        <>
          {slots.map(s => (
            <div key={s.label} className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 ${s.active ? 'border-accent/40 bg-accent/5' : 'border-border bg-bg/40'}`}>
              <KeyRound size={12} className={s.active ? 'shrink-0 text-accent' : 'shrink-0 text-muted'} />
              <span className="min-w-0 flex-1 truncate text-xs text-text">{s.env ? 'Current key' : s.label}</span>
              <code className="shrink-0 text-[10px] text-muted">••••{s.last4 || ''}</code>
              {s.env
                ? <span className="shrink-0 rounded-full bg-accent/15 px-1.5 py-0.5 text-[9px] font-semibold text-accent" title="Loaded from your .env file">FROM .ENV</span>
                : s.active && <span className="shrink-0 rounded-full bg-accent/15 px-1.5 py-0.5 text-[9px] font-semibold text-accent">ACTIVE</span>}
              {s.env ? (
                <span className="shrink-0 p-0.5 text-muted" title="Loaded from .env (read-only). Add a key below to store switchable accounts.">
                  <Lock size={12} />
                </span>
              ) : (
                <>
                  <button onClick={() => toggle(s)} disabled={busy != null} title={s.active ? 'Turn off (disconnects provider)' : 'Switch to this key'}
                    className={`relative h-4 w-8 shrink-0 rounded-full border transition-colors disabled:opacity-40 ${s.active ? 'border-accent/50 bg-accent/30' : 'border-border bg-bg'}`}>
                    <span className={`absolute top-0.5 h-2.5 w-2.5 rounded-full bg-text transition-all ${s.active ? 'left-[17px]' : 'left-0.5'}`} />
                  </button>
                  <button onClick={() => remove(s)} disabled={busy != null} title="Delete this key"
                    className="shrink-0 text-muted transition-colors hover:text-danger disabled:opacity-40">
                    {busy === `d:${s.label}` ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                  </button>
                </>
              )}
            </div>
          ))}
          <div className="flex gap-1.5">
            <input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="Label"
              className="w-20 rounded-lg border border-border bg-bg px-2 py-1.5 text-[11px] text-text outline-none focus:border-accent/50" />
            <input type="password" value={newKey} onChange={e => setNewKey(e.target.value)} onKeyDown={e => e.key === 'Enter' && add()}
              placeholder={slots.length ? 'Add another key (e.g. 2nd account)' : 'API key'}
              className="min-w-0 flex-1 rounded-lg border border-border bg-bg px-2 py-1.5 text-[11px] text-text outline-none focus:border-accent/50" />
            <button onClick={add} disabled={busy != null || !newKey.trim()}
              className="flex items-center gap-1 rounded-lg border border-border px-2 py-1.5 text-[11px] text-muted transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-40">
              {busy === 'add' ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />} Add
            </button>
          </div>
        </>
      )}
    </div>
  )
}
