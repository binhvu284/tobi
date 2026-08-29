/* One shared, always-current copy of the knowledge graph.
 *
 * Anything that draws the graph outside the Graph page reads from here rather than fetching
 * for itself. That gives two things the embeds need: every sigil on a page costs one request
 * instead of one each, and when the graph grows — a sync, a new memory, a link drawn by hand —
 * every embed picks up the new shape without being told about it individually.
 *
 * The store polls while at least one component is watching and stops the moment none is, so a
 * page with no graph on it does no network work at all.
 */
import { useSyncExternalStore } from 'react'
import { getGraph, type GraphData } from '../../api.graph'

export type GraphSnapshot = {
  data: GraphData
  loading: boolean
  /** Plain-language failure, or null. Embeds show their idle ring rather than an error. */
  error: string | null
  /** Epoch ms of the last successful load; 0 until the first one lands. */
  fetchedAt: number
}

const EMPTY: GraphData = { nodes: [], edges: [] }
const POLL_MS = 60_000
/** Two loads closer together than this are the same load; stops a page full of embeds from
 *  each triggering a fetch as they mount. */
const COALESCE_MS = 5_000
const STALE_ON_FOCUS_MS = 30_000

let snapshot: GraphSnapshot = { data: EMPTY, loading: false, error: null, fetchedAt: 0 }
const listeners = new Set<() => void>()
let inflight: Promise<void> | null = null
let timer: ReturnType<typeof setInterval> | null = null

function emit() { for (const listener of listeners) listener() }
function patch(next: Partial<GraphSnapshot>) { snapshot = { ...snapshot, ...next }; emit() }

/** Hand the store a copy someone else already fetched — the Graph page does this on every
 *  unfiltered load, so switching away from it leaves every embed instantly up to date. */
export function publishGraphSnapshot(data: GraphData): void {
  patch({ data, loading: false, error: null, fetchedAt: Date.now() })
}

export function refreshGraphSnapshot(force = false): Promise<void> {
  if (inflight) return inflight
  if (!force && snapshot.fetchedAt && Date.now() - snapshot.fetchedAt < COALESCE_MS) {
    return Promise.resolve()
  }
  patch({ loading: true })
  inflight = getGraph()
    .then(data => patch({ data, loading: false, error: null, fetchedAt: Date.now() }))
    .catch(error => patch({ loading: false, error: (error as Error).message }))
    .finally(() => { inflight = null })
  return inflight
}

function onFocus() {
  if (Date.now() - snapshot.fetchedAt > STALE_ON_FOCUS_MS) void refreshGraphSnapshot()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  if (listeners.size === 1) {
    if (!snapshot.fetchedAt) void refreshGraphSnapshot()
    timer = setInterval(() => { if (!document.hidden) void refreshGraphSnapshot() }, POLL_MS)
    window.addEventListener('focus', onFocus)
  }
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) {
      if (timer) { clearInterval(timer); timer = null }
      window.removeEventListener('focus', onFocus)
    }
  }
}

const read = () => snapshot

/** Subscribe to the shared graph. Mounting this anywhere starts the polling; unmounting the
 *  last watcher stops it. */
export function useGraphSnapshot(): GraphSnapshot {
  return useSyncExternalStore(subscribe, read, read)
}
