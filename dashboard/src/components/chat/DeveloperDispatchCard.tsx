import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, CirclePause, Code2, ExternalLink, Loader2, RotateCcw, XCircle } from 'lucide-react'
import { getDeveloperDispatch, retryDeveloperDispatch, type ChatDeveloperDispatch } from '../../api.chat'


const ACTIVE = new Set(['proposed', 'preflighting', 'running', 'waiting_approval', 'blocked'])

const label: Record<string, string> = {
  proposed: 'Waiting for confirmation',
  preflighting: 'Checking readiness',
  running: 'Developer is working',
  waiting_approval: 'Owner approval required',
  blocked: 'Needs action',
  failed: 'Failed',
  canceled: 'Canceled',
  completed: 'Completed',
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'completed') return <CheckCircle2 size={14} className="text-success" />
  if (status === 'failed') return <XCircle size={14} className="text-danger" />
  if (status === 'blocked' || status === 'waiting_approval') return <CirclePause size={14} className="text-warning" />
  if (status === 'canceled') return <XCircle size={14} className="text-muted" />
  return <Loader2 size={14} className="animate-spin text-accent" />
}

export default function DeveloperDispatchCard({ dispatchId }: { dispatchId: string }) {
  const [dispatch, setDispatch] = useState<ChatDeveloperDispatch | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    const refresh = async () => {
      try {
        const next = await getDeveloperDispatch(dispatchId)
        if (stopped) return
        setDispatch(next); setUnavailable(false)
        if (ACTIVE.has(next.status)) timer = window.setTimeout(refresh, 2500)
      } catch {
        if (!stopped) { setUnavailable(true); timer = window.setTimeout(refresh, 5000) }
      }
    }
    void refresh()
    return () => { stopped = true; if (timer) window.clearTimeout(timer) }
  }, [dispatchId, refreshKey])

  const retry = async () => {
    setRetrying(true)
    setRetryError('')
    try {
      const result = await retryDeveloperDispatch(dispatchId)
      setDispatch(result.developer_dispatch)
      setRefreshKey(value => value + 1)
    } catch (error) {
      setRetryError(error instanceof Error ? error.message : 'Developer retry failed')
    } finally {
      setRetrying(false)
    }
  }

  if (!dispatch) {
    return (
      <div className="mt-2 flex min-h-12 items-center gap-2 rounded-lg border border-border bg-bg/45 px-3 text-xs text-muted">
        {unavailable ? <AlertTriangle size={14} className="text-warning" /> : <Loader2 size={14} className="animate-spin text-accent" />}
        {unavailable ? 'Developer status is temporarily unavailable' : 'Loading Developer status'}
      </div>
    )
  }

  return (
    <section className="mt-2 rounded-lg border border-border bg-bg/45 p-3" aria-label="Developer run status">
      <div className="flex items-start gap-2">
        <StatusIcon status={dispatch.status} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-xs font-semibold text-heading">{label[dispatch.status] || dispatch.status}</span>
            {dispatch.workflow_id && <span className="text-[10px] text-muted">Run #{dispatch.workflow_id}</span>}
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-text">{dispatch.title}</p>
        </div>
        <Link to={dispatch.developer_url} title="Open in Developer" aria-label="Open this run in Developer"
          className="rounded p-1 text-muted hover:bg-accent/10 hover:text-accent">
          <ExternalLink size={14} />
        </Link>
      </div>
      {dispatch.workflow_id && (
        <div className="mt-2">
          <div className="mb-1 flex items-center justify-between text-[10px] text-muted">
            <span className="flex items-center gap-1"><Code2 size={10} /> {dispatch.stage || 'queued'}</span>
            <span>{Math.max(0, Math.min(100, dispatch.progress || 0))}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded bg-border/70">
            <div className="h-full bg-accent transition-[width]" style={{ width: `${Math.max(0, Math.min(100, dispatch.progress || 0))}%` }} />
          </div>
        </div>
      )}
      {dispatch.blocker && <p className="mt-2 text-[11px] leading-relaxed text-warning">{dispatch.blocker}</p>}
      {retryError && <p className="mt-2 text-[11px] leading-relaxed text-danger">{retryError}</p>}
      {dispatch.can_retry && (
        <button type="button" onClick={() => void retry()} disabled={retrying}
          className="mt-2 inline-flex h-8 items-center gap-1.5 rounded border border-border px-2.5 text-xs font-medium text-text hover:border-accent hover:text-accent disabled:cursor-wait disabled:opacity-60">
          {retrying ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />}
          {retrying ? 'Retrying' : 'Retry'}
        </button>
      )}
      {(dispatch.changes.files.length > 0 || dispatch.checks.length > 0 || dispatch.artifacts.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-muted">
          <span>{dispatch.changes.files.length} changed file{dispatch.changes.files.length === 1 ? '' : 's'}</span>
          <span>{dispatch.checks.length} check{dispatch.checks.length === 1 ? '' : 's'}</span>
          <span>{dispatch.artifacts.length} artifact{dispatch.artifacts.length === 1 ? '' : 's'}</span>
        </div>
      )}
    </section>
  )
}
