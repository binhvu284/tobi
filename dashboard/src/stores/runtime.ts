import { useEffect, useSyncExternalStore } from 'react'
import {
  getRuntimeLoops,
  getRuntimeRollout,
  getRuntimeRun,
  getRuntimeRuns,
  setDeveloperLoop,
  type RuntimeLoopRecipe,
  type RuntimeLoopSelection,
  type RuntimeRolloutStatus,
  type RuntimeRunDetail,
  type RuntimeRunSummary,
} from '../api.runtime'

type RuntimeConnection = 'idle' | 'loading' | 'ready' | 'reconnecting' | 'error'

export type RuntimeStoreState = {
  runs: RuntimeRunSummary[]
  nextCursor: string | null
  selectedRunId: string | null
  detail: RuntimeRunDetail | null
  loops: RuntimeLoopRecipe[]
  loopSelection: RuntimeLoopSelection | null
  rollout: RuntimeRolloutStatus | null
  connection: RuntimeConnection
  error: string | null
  surface: string
  status: string
}

const initialState: RuntimeStoreState = {
  runs: [], nextCursor: null, selectedRunId: null, detail: null,
  loops: [], loopSelection: null, rollout: null, connection: 'idle', error: null,
  surface: '', status: '',
}

class RuntimeStore {
  private state = initialState
  private listeners = new Set<() => void>()
  private consumers = 0
  private timer: number | null = null
  private requestVersion = 0

  getSnapshot = () => this.state

  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private update(patch: Partial<RuntimeStoreState>) {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach(listener => listener())
  }

  attach = () => {
    this.consumers += 1
    if (this.consumers === 1) {
      void this.load()
      this.timer = window.setInterval(() => void this.refreshSelected(), 4000)
    }
    return () => {
      this.consumers = Math.max(0, this.consumers - 1)
      if (this.consumers === 0 && this.timer !== null) {
        window.clearInterval(this.timer)
        this.timer = null
      }
    }
  }

  load = async () => {
    const version = ++this.requestVersion
    if (!this.state.runs.length) this.update({ connection: 'loading', error: null })
    try {
      const [page, loops, rollout] = await Promise.all([
        getRuntimeRuns({ surface: this.state.surface, status: this.state.status }),
        getRuntimeLoops(),
        getRuntimeRollout(),
      ])
      if (version !== this.requestVersion) return
      const selectedRunId = page.items.some(run => run.run_id === this.state.selectedRunId)
        ? this.state.selectedRunId
        : page.items[0]?.run_id ?? null
      let detail = selectedRunId && this.state.detail?.run.run_id === selectedRunId
        ? this.state.detail
        : null
      if (selectedRunId && !detail) detail = await getRuntimeRun(selectedRunId)
      if (version !== this.requestVersion) return
      this.update({
        runs: page.items,
        nextCursor: page.next_cursor,
        selectedRunId,
        detail,
        loops: loops.items,
        loopSelection: loops.developer_selection,
        rollout,
        connection: 'ready',
        error: null,
      })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.update({ connection: 'error', error: (error as Error).message })
    }
  }

  setFilters = (surface: string, status: string) => {
    if (surface === this.state.surface && status === this.state.status) return
    this.update({ surface, status, runs: [], selectedRunId: null, detail: null, nextCursor: null })
    void this.load()
  }

  loadMore = async () => {
    if (!this.state.nextCursor) return
    try {
      const page = await getRuntimeRuns({
        cursor: this.state.nextCursor,
        surface: this.state.surface,
        status: this.state.status,
      })
      const known = new Set(this.state.runs.map(run => run.run_id))
      this.update({
        runs: [...this.state.runs, ...page.items.filter(run => !known.has(run.run_id))],
        nextCursor: page.next_cursor,
        error: null,
      })
    } catch (error) {
      this.update({ error: (error as Error).message })
    }
  }

  selectRun = async (runId: string) => {
    if (runId === this.state.selectedRunId && this.state.detail) return
    const version = ++this.requestVersion
    this.update({ selectedRunId: runId, detail: null, connection: 'loading', error: null })
    try {
      const detail = await getRuntimeRun(runId)
      if (version !== this.requestVersion) return
      this.update({ detail, connection: 'ready' })
    } catch (error) {
      if (version !== this.requestVersion) return
      this.update({ connection: 'error', error: (error as Error).message })
    }
  }

  refreshSelected = async () => {
    const current = this.state.detail
    if (!this.state.selectedRunId || this.state.connection === 'loading') return
    try {
      const next = await getRuntimeRun(this.state.selectedRunId, current?.last_sequence ?? 0)
      if (this.state.selectedRunId !== next.run.run_id) return
      const events = current
        ? [...current.events, ...next.events.filter(event => !current.events.some(item => item.sequence === event.sequence))]
            .sort((a, b) => a.sequence - b.sequence)
        : next.events
      this.update({
        detail: { ...next, events },
        runs: this.state.runs.map(run => run.run_id === next.run.run_id ? next.run : run),
        connection: 'ready',
        error: null,
      })
    } catch (error) {
      this.update({ connection: current ? 'reconnecting' : 'error', error: (error as Error).message })
    }
  }

  saveLoopSelection = async (selection: RuntimeLoopSelection) => {
    const saved = await setDeveloperLoop(selection)
    this.update({ loopSelection: saved, error: null })
    return saved
  }
}

export const runtimeStore = new RuntimeStore()

export function useRuntimeStore() {
  const state = useSyncExternalStore(runtimeStore.subscribe, runtimeStore.getSnapshot, runtimeStore.getSnapshot)
  useEffect(() => runtimeStore.attach(), [])
  return state
}
