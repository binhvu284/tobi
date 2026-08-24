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
//   LoadFailure   the data never arrived, and the reader has to be told
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, Loader2, RotateCw } from 'lucide-react'

/** Runs an async action while owning its own pending state.
 *
 *  The `finally` is the point: an action that throws must still re-enable its button, and a
 *  hand-written try/catch that forgets it leaves the control dead until the page reloads. */
export function ActionButton({
  onAction, children, icon, disabled = false, title, ariaLabel, className = '', type = 'button', busy = false,
}: {
  onAction: () => unknown | Promise<unknown>
  children?: ReactNode
  /** Rendered when idle; swapped for a spinner while pending so the layout does not shift. */
  icon?: ReactNode
  disabled?: boolean
  title?: string
  /** Accessible name. Defaults to `title` for icon-only buttons, which have no other name. */
  ariaLabel?: string
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
    <button type={type} title={title} aria-label={ariaLabel ?? (children ? undefined : title)}
      disabled={showSpinner || disabled} onClick={() => void click()}
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

/** Turns a caught fetch error into something the reader can act on.
 *
 *  Pages used to write `.catch(() => {})`, which renders identically to having no data — so a
 *  broken request and an empty result looked the same on screen and neither could be trusted.
 *  This says which thing failed, quotes the real reason underneath, and offers one retry.
 *
 *  `reason` is deliberately the raw message. A generic "something went wrong" is what sent the
 *  owner to the wrong place twice on 2026-08-01; "Connection refused" tells him the server is
 *  down, which is the whole difference. */
export function LoadFailure({ error, onRetry, what, className = '', compact = false }: {
  /** Whatever the catch received. Anything not an Error is still shown, stringified. */
  error: unknown
  /** Re-runs only the failed request. Omit when a retry is not meaningful. */
  onRetry?: () => unknown | Promise<unknown>
  /** What did not load, in the owner's words: "your storage data", "the project list". */
  what: string
  className?: string
  /** One line, for inline slots where a full block would push content around. */
  compact?: boolean
}) {
  if (!error) return null
  const raw = error instanceof Error ? error.message : String(error)
  const reason = raw.trim() || 'No reason was reported.'
  return (
    <div role="alert" aria-live="polite"
      className={`flex items-start gap-2 rounded border border-warning/40 bg-warning/5 ${compact ? 'px-2 py-1.5' : 'p-3'} ${className}`}>
      <AlertTriangle size={compact ? 12 : 14} className="mt-0.5 shrink-0 text-warning" aria-hidden />
      <div className="min-w-0 flex-1">
        <div className={`font-medium text-text ${compact ? 'text-[11px]' : 'text-xs'}`}>
          Couldn&rsquo;t load {what}.
        </div>
        <div className={`mt-0.5 break-words text-muted ${compact ? 'text-[10px]' : 'text-[11px]'}`}>{reason}</div>
      </div>
      {onRetry && (
        <ActionButton onAction={onRetry} icon={<RotateCw size={12} aria-hidden />}
          title={`Try loading ${what} again`}
          className="shrink-0 inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[11px] text-text hover:bg-surface">
          Try again
        </ActionButton>
      )}
    </div>
  )
}
