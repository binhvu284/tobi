// Per-table refresh (#23, owner QA): every table gets its OWN header refresh icon
// that refreshes ONLY that table's sources (never the whole tab) and drives a
// skeleton over that table while the scoped job runs. One shared hook + button so
// GitHub, Releases, Tool Discovery and Source Explore all behave identically.
import { useCallback, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { getNewsV2RefreshJob, postNewsV2Refresh } from '../../api'

type Tab = 'home' | 'trending' | 'feed'
const TERMINAL = new Set(['completed', 'partial', 'failed', 'canceled'])

/** Kick a source-scoped refresh and resolve when its job reaches a terminal state,
 *  polling gently. `refreshing` gates the caller's skeleton. Never throws to the UI. */
export function useTableRefresh(tab: Tab, sources: string[], onDone: () => void | Promise<void>) {
  const [refreshing, setRefreshing] = useState(false)
  const active = useRef(false)

  const refresh = useCallback(async () => {
    if (active.current) return
    active.current = true
    setRefreshing(true)
    try {
      const { job_id } = await postNewsV2Refresh(tab, sources)
      // poll up to ~90s; a long content-generation refresh still resolves the skeleton
      for (let i = 0; i < 90; i++) {
        await new Promise(r => setTimeout(r, 1000))
        try {
          const job = await getNewsV2RefreshJob(job_id)
          if (TERMINAL.has(job.state)) break
        } catch { /* transient — keep polling */ }
      }
      await onDone()
    } catch { /* refresh failure is surfaced by the reload/empty state, never a crash */ } finally {
      active.current = false
      setRefreshing(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, sources.join(','), onDone])

  return { refreshing, refresh }
}

/** The small header-corner refresh icon (spins while its table refreshes). */
export function RefreshIconButton({ refreshing, onClick, title = 'Refresh this table' }: {
  refreshing: boolean; onClick: () => void; title?: string
}) {
  return (
    <button onClick={onClick} disabled={refreshing} title={title} aria-label={title}
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border text-muted transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-60">
      <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
    </button>
  )
}

/** Uniform table skeleton rows (owner: "skeleton effect when I click refresh"). */
export function TableSkeleton({ rows = 4, className = '' }: { rows?: number; className?: string }) {
  return (
    <div className={`space-y-2 p-4 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="h-9 w-9 shrink-0 animate-pulse rounded-md bg-overlay/10" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 w-1/3 animate-pulse rounded bg-overlay/10" />
            <div className="h-2.5 w-3/4 animate-pulse rounded bg-overlay/[0.07]" />
          </div>
        </div>
      ))}
    </div>
  )
}
