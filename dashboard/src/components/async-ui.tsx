// Shared affordances for asynchronous work.
//
// CLAUDE.md requires every control that triggers async work to show a loading state for the
// duration and re-enable on both success and failure. That rule kept being lost because it
// was per-site discipline: each button re-implemented pending tracking, so a button written
// without it looked no different in review. These primitives make the affordance structural
// -- a control cannot be added without one, because the component owns it.
//
// Pick by blast radius:
//   ActionButton  the control itself is the only thing affected
//   BusyOverlay   one section's data is being replaced
//   ActivityBar   a page-wide refetch is in flight; content stays readable underneath
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

/** Runs an async action while owning its own pending state.
 *
 *  The `finally` is the point: an action that throws must still re-enable its button, and a
 *  hand-written try/catch that forgets it leaves the control dead until the page reloads. */
export function ActionButton({
  onAction, children, icon, disabled = false, title, className = '', type = 'button', busy = false,
}: {
  onAction: () => unknown | Promise<unknown>
  children?: ReactNode
  /** Rendered when idle; swapped for a spinner while pending so the layout does not shift. */
  icon?: ReactNode
  disabled?: boolean
  title?: string
  className?: string
  type?: 'button' | 'submit'
  /** External pending state, for actions owned by a parent. ORed with the internal one. */
  busy?: boolean
}) {
  const [pending, setPending] = useState(false)
  const mounted = useRef(true)
  useEffect(() => () => { mounted.current = false }, [])

  const click = useCallback(async () => {
    if (pending || busy || disabled) return
    setPending(true)
    try {
      await onAction()
    } finally {
      // Re-enable even when the action threw. Unmount-guarded so a control inside a modal
      // that closes on success does not warn about setting state after teardown.
      if (mounted.current) setPending(false)
    }
  }, [onAction, pending, busy, disabled])

  const showSpinner = pending || busy
  return (
    <button type={type} title={title} disabled={showSpinner || disabled} onClick={() => void click()}
      aria-busy={showSpinner} className={`${className} disabled:cursor-not-allowed disabled:opacity-45`}>
      {showSpinner ? <Loader2 size={13} className="animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  )
}

/** Dims a section and blocks interaction while its data is being replaced.
 *
 *  Preferred over swapping in a skeleton when content already exists: a skeleton flash
 *  destroys the reader's place on every refresh, while this keeps the old content legible
 *  and simply marks it stale. */
export function BusyOverlay({ pending, label, children, className = '' }: {
  pending: boolean
  label?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`relative ${className}`} aria-busy={pending}>
      <div className={pending ? 'pointer-events-none select-none opacity-45 transition-opacity' : 'transition-opacity'}>
        {children}
      </div>
      {pending && (
        <div className="absolute inset-0 z-10 flex items-start justify-center pt-8">
          <span className="inline-flex items-center gap-2 rounded-md border border-border bg-surface/95 px-3 py-1.5 text-[11px] text-muted shadow-lg backdrop-blur">
            <Loader2 size={13} className="animate-spin text-accent" />{label ?? 'Updating…'}
          </span>
        </div>
      )}
    </div>
  )
}

/** Indeterminate bar pinned to the top of a page while a page-wide refetch runs.
 *
 *  This is the answer to "the screen looks frozen": a page-scoped action leaves every section
 *  showing correct-but-stale data, with nothing anywhere saying work is in flight. */
export function ActivityBar({ pending, label }: { pending: boolean; label?: string }) {
  if (!pending) return null
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 z-40" role="status" aria-live="polite">
      <div className="h-0.5 w-full overflow-hidden bg-accent/15">
        <div className="tobi-activity-bar h-full w-1/3 bg-accent" />
      </div>
      {label && (
        <div className="flex justify-center">
          <span className="mt-1.5 inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/95 px-2.5 py-1 text-[10px] text-muted shadow backdrop-blur">
            <Loader2 size={11} className="animate-spin text-accent" />{label}
          </span>
        </div>
      )}
    </div>
  )
}

/** Neutral block skeleton for a section whose data has not arrived yet.
 *
 *  Use only where there is nothing to show. Once content exists, BusyOverlay is correct. */
export function SectionSkeleton({ rows = 3, className = '' }: { rows?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`} aria-busy role="status">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="tobi-skeleton h-12 rounded-md border border-border/60 bg-surface/40"
          style={{ animationDelay: `${index * 90}ms` }} />
      ))}
    </div>
  )
}
