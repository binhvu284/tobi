import { useState, type FormEvent } from 'react'
import { Loader2, LockKeyhole, Unlock } from 'lucide-react'
import { vaultUnlock } from '../api.genesis'
import { useToast } from '../context/ToastProvider'

type Props = {
  mode?: 'inline' | 'page'
  title?: string
  detail?: string
  onUnlocked?: () => void | Promise<void>
}

export default function VaultUnlockPanel({
  mode = 'page',
  title = 'Unlock Mission Control',
  detail = 'Unlock once to authorize protected tools across this browser tab.',
  onUnlocked,
}: Props) {
  const { toast } = useToast()
  const [master, setMaster] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!master || busy) return
    setBusy(true); setError(null)
    try {
      await vaultUnlock(master)
      setMaster('')
      await onUnlocked?.()
      toast({ kind: 'success', title: 'Vault unlocked', detail: 'Developer, Integrations, Models, and MCP are authorized.' })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Vault unlock failed.')
    } finally {
      setBusy(false)
    }
  }

  const panel = (
    <form onSubmit={submit} className={mode === 'page'
      ? 'w-full max-w-md rounded-md border border-border bg-surface p-5 shadow-xl'
      : 'border-l-2 border-warning bg-warning/5 px-4 py-4'}>
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-warning/30 bg-warning/10 text-warning">
          <LockKeyhole size={17} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-heading">{title}</div>
          <p className="mt-1 text-xs leading-5 text-muted">{detail}</p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input type="password" value={master} onChange={event => setMaster(event.target.value)}
              autoComplete="current-password" placeholder="Master password" aria-label="Vault master password"
              className="h-9 min-w-0 flex-1 rounded-md border border-border bg-background px-3 text-sm text-text outline-none focus:border-accent" />
            <button type="submit" disabled={!master || busy}
              className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-background disabled:opacity-40">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Unlock size={14} />} Unlock
            </button>
          </div>
          {error && <p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
        </div>
      </div>
    </form>
  )

  return mode === 'page' ? <div className="flex h-full items-center justify-center p-6">{panel}</div> : panel
}
