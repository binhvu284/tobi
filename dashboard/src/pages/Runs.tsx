import { useMemo, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowDown, Box, CheckCircle2, ChevronRight, Clock3,
  FileSearch, Gauge, Layers3, Loader2, RefreshCw, RotateCcw, ShieldCheck, Workflow,
} from 'lucide-react'
import { runtimeStore, useRuntimeStore } from '../stores/runtime'
import { ActionButton } from '../components/async-ui'
import type { RuntimeRunSummary } from '../api.runtime'

type DetailTab = 'timeline' | 'trace' | 'evals' | 'context'

const SURFACES = ['', 'chat', 'agent', 'developer', 'office', 'projects', 'mcp', 'telegram', 'cli', 'scheduler']
const STATUSES = ['', 'accepted', 'routing', 'clarifying', 'planned', 'waiting_approval', 'running', 'waiting_external', 'recovering', 'waiting_owner', 'succeeded', 'failed', 'cancelled']

function when(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function compact(value: string) {
  return value.replace(/_/g, ' ')
}

function statusTone(status: string) {
  if (status === 'succeeded' || status === 'passed' || status === 'ready') return 'text-success'
  if (status === 'failed' || status === 'error' || status === 'cancelled') return 'text-danger'
  if (status.includes('waiting') || status === 'recovering') return 'text-warning'
  return 'text-accent'
}

function emptyRunsMessage(state: ReturnType<typeof useRuntimeStore>) {
  if (state.connection === 'loading') return 'Loading runs'
  if (state.rollout?.rollback) return 'Runtime rollout is rolled back; canonical runs are paused'
  const directChat = state.rollout?.decisions?.direct_chat
  if (state.rollout?.stage === 'shadow' && directChat && !directChat.allowed) {
    const firstBlocker = directChat.blockers[0]
    return firstBlocker
      ? `No canonical runs yet; direct Chat rollout is blocked by ${firstBlocker}`
      : 'No canonical runs yet; direct Chat rollout is not active'
  }
  return state.surface || state.status ? 'No matching runs' : 'No canonical runs yet'
}

function RunRow({ run, selected, onSelect }: { run: RuntimeRunSummary; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`grid min-h-20 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-3 py-3 text-left transition-colors last:border-b-0 ${selected ? 'bg-accent/10' : 'hover:bg-overlay/5'}`}
    >
      <span className="min-w-0">
        <span className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-heading">{run.label}</span>
          <span className={`shrink-0 text-[10px] font-semibold uppercase ${statusTone(run.status)}`}>{compact(run.status)}</span>
        </span>
        <span className="mt-1 block truncate font-mono text-[10px] text-muted">{run.run_id}</span>
        <span className="mt-1 flex flex-wrap gap-x-3 text-[10px] text-muted">
          <span>{run.surface}</span><span>{run.mode}</span><span>{when(run.updated_at)}</span>
        </span>
      </span>
      <ChevronRight size={15} className={selected ? 'text-accent' : 'text-muted'} />
    </button>
  )
}

function ReferenceList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="border-b border-border py-3 last:border-b-0">
      <div className="mb-2 text-[10px] font-semibold uppercase text-muted">{title} <span className="ml-1 text-text">{items.length}</span></div>
      {items.length ? <div className="space-y-1">{items.map(item => <div key={item} className="break-all font-mono text-[11px] text-text">{item}</div>)}</div>
        : <div className="text-xs text-muted">None</div>}
    </div>
  )
}

export default function Runs() {
  const state = useRuntimeStore()
  const [tab, setTab] = useState<DetailTab>('timeline')
  const detail = state.detail
  const usage = useMemo(() => Object.entries(detail?.trace.usage ?? {}), [detail])
  const filtersChanged = (surface: string, status: string) => runtimeStore.setFilters(surface, status)

  return (
    <div className="min-h-full bg-bg text-text">
      <header className="border-b border-border px-4 py-4 sm:px-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center border border-border bg-surface text-accent"><Activity size={17} /></span>
            <div><h1 className="text-lg font-semibold text-heading">Runs</h1><p className="text-[10px] uppercase text-muted">Runtime activity and evidence</p></div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`flex items-center gap-1.5 text-[10px] font-semibold uppercase ${state.connection === 'error' ? 'text-danger' : state.connection === 'reconnecting' ? 'text-warning' : 'text-muted'}`}>
              {state.connection === 'loading' ? <Loader2 size={12} className="animate-spin" /> : state.connection === 'reconnecting' ? <RotateCcw size={12} /> : <span className="h-1.5 w-1.5 bg-success" />}
              {state.connection}
            </span>
            <ActionButton title="Refresh runs" onAction={() => runtimeStore.load()} icon={<RefreshCw size={15} />}
              className="inline-flex h-9 w-9 items-center justify-center border border-border text-muted transition-colors hover:border-accent hover:text-accent" />
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <select aria-label="Filter runs by surface" value={state.surface} onChange={event => filtersChanged(event.target.value, state.status)}
            className="h-9 border border-border bg-surface px-2 text-xs capitalize text-text outline-none focus:border-accent">
            {SURFACES.map(surface => <option key={surface || 'all'} value={surface}>{surface || 'All surfaces'}</option>)}
          </select>
          <select aria-label="Filter runs by status" value={state.status} onChange={event => filtersChanged(state.surface, event.target.value)}
            className="h-9 border border-border bg-surface px-2 text-xs capitalize text-text outline-none focus:border-accent">
            {STATUSES.map(status => <option key={status || 'all'} value={status}>{status ? compact(status) : 'All statuses'}</option>)}
          </select>
        </div>
      </header>

      {state.error && <div className="flex items-center gap-2 border-b border-danger/40 bg-danger/5 px-4 py-2 text-xs text-danger sm:px-6"><AlertTriangle size={14} />{state.error}</div>}

      <main className="grid min-h-[calc(100vh-12rem)] lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,2fr)]">
        <aside className="border-b border-border lg:border-b-0 lg:border-r">
          <div className="flex h-10 items-center justify-between border-b border-border px-3 text-[10px] font-semibold uppercase text-muted">
            <span>{state.runs.length} runs</span><span>Newest first</span>
          </div>
          {state.runs.length ? state.runs.map(run => <RunRow key={run.run_id} run={run} selected={run.run_id === state.selectedRunId} onSelect={() => void runtimeStore.selectRun(run.run_id)} />)
            : <div className="flex min-h-48 flex-col items-center justify-center gap-2 px-4 text-center text-muted"><Activity size={22} /><span className="max-w-xs text-xs">{emptyRunsMessage(state)}</span></div>}
          {state.nextCursor && <ActionButton onAction={() => runtimeStore.loadMore()} icon={<ArrowDown size={13} />} className="flex h-10 w-full items-center justify-center gap-2 border-t border-border text-xs text-muted hover:text-accent">Load more</ActionButton>}
        </aside>

        <section className="min-w-0">
          {!detail ? (
            <div className="flex min-h-80 flex-col items-center justify-center gap-2 text-muted">
              {state.connection === 'loading' ? <Loader2 size={24} className="animate-spin" /> : <FileSearch size={24} />}
              <span className="text-xs">{state.connection === 'loading' ? 'Loading run' : 'Select a run'}</span>
            </div>
          ) : <>
            <div className="border-b border-border px-4 py-4 sm:px-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="text-base font-semibold text-heading">{detail.run.label}</h2><span className={`text-[10px] font-semibold uppercase ${statusTone(detail.run.status)}`}>{compact(detail.run.status)}</span></div><div className="mt-1 break-all font-mono text-[10px] text-muted">{detail.run.run_id}</div></div>
                <div className="grid grid-cols-2 gap-x-5 gap-y-1 text-[10px] sm:text-right"><span className="text-muted">Surface</span><span>{detail.run.surface}</span><span className="text-muted">Updated</span><span>{when(detail.run.updated_at)}</span><span className="text-muted">Events</span><span>{detail.last_sequence}</span></div>
              </div>
            </div>

            <div className="flex overflow-x-auto border-b border-border px-4 sm:px-5">
              {([
                ['timeline', Activity, 'Timeline'], ['trace', Workflow, 'Trace'], ['evals', Gauge, 'Evals'], ['context', Layers3, 'Context'],
              ] as const).map(([id, Icon, label]) => <button key={id} type="button" onClick={() => setTab(id)} className={`flex h-11 shrink-0 items-center gap-2 border-b-2 px-3 text-xs ${tab === id ? 'border-accent text-accent' : 'border-transparent text-muted hover:text-text'}`}><Icon size={13} />{label}</button>)}
            </div>

            <div className="px-4 py-4 sm:px-5">
              {tab === 'timeline' && <div className="border border-border bg-surface">
                {detail.events.length ? detail.events.map(event => <div key={event.event_id} className="grid min-h-14 grid-cols-[2.5rem_minmax(0,1fr)] border-b border-border px-3 py-2 last:border-b-0"><div className="font-mono text-[10px] text-muted">#{event.sequence}</div><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="text-xs font-medium text-heading">{compact(event.event_type)}</span><span className="text-[10px] uppercase text-accent">{compact(event.stage)}</span></div><div className="mt-1 flex flex-wrap gap-x-3 text-[10px] text-muted"><span>{event.actor}</span><span>{when(event.timestamp)}</span>{Object.entries(event.payload).map(([key, value]) => <span key={key}>{compact(key)}: {String(value)}</span>)}</div></div></div>)
                  : <div className="p-6 text-center text-xs text-muted">No events recorded</div>}
              </div>}

              {tab === 'trace' && <div className="space-y-4">
                <div className="grid grid-cols-2 gap-px border border-border bg-border sm:grid-cols-4">{usage.map(([key, value]) => <div key={key} className="min-h-16 bg-surface p-3"><div className="text-[10px] uppercase text-muted">{compact(key)}</div><div className="mt-1 font-mono text-sm text-heading">{value.toLocaleString()}</div></div>)}</div>
                <div className="border border-border bg-surface px-3"><ReferenceList title="Models" items={detail.trace.model_refs} /><ReferenceList title="Tools" items={detail.trace.tool_refs} /><ReferenceList title="Policy decisions" items={detail.trace.policy_decision_refs} /><ReferenceList title="Approvals" items={detail.trace.approval_refs} /><ReferenceList title="Receipts" items={detail.trace.receipt_refs} /><ReferenceList title="Outcomes" items={detail.trace.outcome_refs} /></div>
              </div>}

              {tab === 'evals' && <div className="border border-border bg-surface">
                {detail.evaluations.length ? detail.evaluations.map(evaluation => <div key={evaluation.eval_run_id} className="grid min-h-16 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-3 py-2 last:border-b-0">{evaluation.status === 'passed' ? <CheckCircle2 size={16} className="text-success" /> : <AlertTriangle size={16} className="text-danger" />}<div className="min-w-0"><div className="truncate text-xs font-medium text-heading">{evaluation.eval_case_id}</div><div className="mt-1 text-[10px] text-muted">{evaluation.category} - {evaluation.evidence_refs.length} evidence refs</div></div><div className={`font-mono text-xs ${statusTone(evaluation.status)}`}>{evaluation.score ?? '-'} / {evaluation.threshold ?? '-'}</div></div>)
                  : <div className="flex min-h-48 flex-col items-center justify-center gap-2 text-muted"><ShieldCheck size={22} /><span className="text-xs">No evaluations recorded</span></div>}
              </div>}

              {tab === 'context' && <div className="grid gap-4 xl:grid-cols-2">
                <div className="border border-border bg-surface px-3"><ReferenceList title="Context references" items={detail.context_refs} /><ReferenceList title="Recovery references" items={detail.trace.recovery_refs} /></div>
                <div className="border border-border bg-surface">
                  <div className="border-b border-border px-3 py-3 text-[10px] font-semibold uppercase text-muted">Capabilities <span className="ml-1 text-text">{detail.capabilities.length}</span></div>
                  {detail.capabilities.length ? detail.capabilities.map(capability => <div key={capability.entity_id} className="flex min-h-14 items-center gap-3 border-b border-border px-3 py-2 last:border-b-0"><Box size={14} className="shrink-0 text-accent" /><div className="min-w-0 flex-1"><div className="truncate text-xs font-medium text-heading">{capability.name}</div><div className="truncate font-mono text-[10px] text-muted">{capability.canonical_key}</div></div><span className={`text-[10px] uppercase ${statusTone(capability.status)}`}>{capability.status}</span></div>)
                    : <div className="p-6 text-center text-xs text-muted">No capabilities indexed</div>}
                </div>
                {detail.loop && <div className="border border-border bg-surface p-3 xl:col-span-2"><div className="flex flex-wrap items-center gap-3"><Clock3 size={14} className="text-accent" /><span className="text-xs font-medium text-heading">{detail.loop.recipe_id}@{detail.loop.recipe_version}</span><span className={`text-[10px] uppercase ${statusTone(detail.loop.status)}`}>{detail.loop.status}</span><span className="text-[10px] text-muted">Iteration {detail.loop.iteration}</span>{detail.loop.stop_reason && <span className="text-[10px] text-warning">{detail.loop.stop_reason}</span>}</div></div>}
              </div>}
            </div>
          </>}
        </section>
      </main>
    </div>
  )
}
