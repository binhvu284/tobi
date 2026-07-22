// Shared auto-queue switch used by both the Process tab and the Queue tab so
// the control is identical and always reflects the same owner flag
// (developer.auto_queue). Both surfaces call the same onChange -> setAutoQueue.
export default function AutoQueueToggle({ enabled, busy = false, onChange, hint = 'Next queue item' }: {
  enabled: boolean
  busy?: boolean
  onChange: (enabled: boolean) => void
  hint?: string
}) {
  return (
    <button type="button" role="switch" aria-checked={enabled} disabled={busy} onClick={() => onChange(!enabled)}
      title="When on, the Next item starts automatically once the main thread is free"
      className="inline-flex h-8 items-center gap-2 text-left disabled:cursor-wait disabled:opacity-60">
      <span className={`relative h-5 w-9 rounded-full border transition-colors ${enabled ? 'border-accent/60 bg-accent/25' : 'border-border bg-background'}`}>
        <span className={`absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all ${enabled ? 'left-[17px] bg-accent' : 'left-0.5 bg-muted'}`} />
      </span>
      <span>
        <span className="block text-[10px] font-medium text-text">Auto</span>
        <span className="block text-[8px] text-muted">{hint}</span>
      </span>
    </button>
  )
}
