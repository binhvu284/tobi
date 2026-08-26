import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, ChevronRight, Clock3, FileSearch,
  Gauge, Loader2, RefreshCw, ShieldAlert, ShieldCheck,
} from 'lucide-react'
import { ApiError } from '../../apiCore'
import {
  getRuntimeEvalCase, getRuntimeEvals,
  type RuntimeEvalCaseDetail, type RuntimeEvalOverview,
} from '../../api.runtime'
import VaultUnlockPanel from '../VaultUnlockPanel'
import { ActionButton } from '../async-ui'

function pct(value: number | null) {
  return value == null ? 'Missing' : `${value.toFixed(value % 1 ? 1 : 0)}%`
}

function when(value?: string | null) {
  if (!value) return 'No completed suite'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

function tone(status: string) {
  if (status === 'passed' || status === 'available') return 'text-success'
  if (status === 'missing' || status === 'missing_evidence') return 'text-warning'
  return 'text-danger'
}

function Metric({ label, value, detail, good }: { label: string; value: string; detail: string; good?: boolean }) {
  return <div className="min-h-24 border-b border-border px-4 py-4 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
    <div className="text-[10px] font-semibold uppercase text-muted">{label}</div>
    <div className={`mt-2 font-mono text-2xl font-semibold ${good ? 'text-success' : 'text-heading'}`}>{value}</div>
    <div className="mt-1 text-[10px] text-muted">{detail}</div>
  </div>
}

function ProgressRow({ label, passed, total, rate }: { label: string; passed: number; total: number; rate: number | null }) {
  return <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b border-border px-3 py-2.5 last:border-b-0">
    <div className="min-w-0"><div className="truncate text-xs text-heading">{label.replace(/_/g, ' ')}</div><div className="mt-1 h-1 bg-border"><div className="h-full bg-accent" style={{ width: `${rate ?? 0}%` }} /></div></div>
    <div className="text-right"><div className="font-mono text-xs text-text">{pct(rate)}</div><div className="text-[10px] text-muted">{passed}/{total}</div></div>
  </div>
}

export default function EvalControlCenter() {
  const [data, setData] = useState<RuntimeEvalOverview | null>(null)
  const [detail, setDetail] = useState<RuntimeEvalCaseDetail | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setData(await getRuntimeEvals()) }
    catch (err) { setError(err instanceof ApiError ? err : new ApiError(String(err), 500, 'http_error', '/api/runtime/evals')) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  const openCase = async (id: string, version: string) => {
    const key = `${id}@${version}`
    setSelected(key); setDetail(null)
    try { setDetail(await getRuntimeEvalCase(id, version)) }
    catch (err) { setError(err instanceof ApiError ? err : new ApiError(String(err), 500, 'http_error', '/api/runtime/evals/cases')) }
  }

  if (loading && !data) return <div className="flex min-h-80 items-center justify-center text-muted"><Loader2 size={22} className="animate-spin" /></div>
  if (error?.status === 401) return <VaultUnlockPanel title="Unlock Evaluations" detail="Eval evidence is owner-only." onUnlocked={load} />
  if (error && !data) return <div className="mx-4 mt-5 border-l-2 border-danger bg-danger/5 p-4 sm:mx-6"><div className="flex gap-3"><AlertTriangle size={17} className="mt-0.5 text-danger" /><div><div className="text-sm font-semibold text-heading">Evaluation data unavailable</div><div className="mt-1 text-xs text-muted">{error.message}</div><ActionButton onAction={load} icon={<RefreshCw size={13} />} className="mt-3 inline-flex h-8 items-center gap-2 border border-border px-2.5 text-xs hover:border-accent">Retry</ActionButton></div></div></div>
  if (!data) return null

  const release = data.gates.release
  return <div className="min-w-0">
    <div className="flex items-center justify-between border-b border-border px-4 py-3 sm:px-6">
      <div><div className="text-sm font-semibold text-heading">Eval Control Center</div><div className="mt-0.5 text-[10px] uppercase text-muted">Evidence refreshed {when(data.freshness.latest_suite_at)}</div></div>
      <ActionButton onAction={load} busy={loading} title="Refresh evaluation evidence" icon={<RefreshCw size={15} />} className="inline-flex h-9 w-9 items-center justify-center border border-border text-muted hover:border-accent hover:text-accent" />
    </div>

    {data.acceptance && <div className="grid border-b border-success/40 bg-success/5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div className="px-4 py-3 sm:px-6"><div className="flex items-center gap-2 text-xs font-semibold text-success"><ShieldCheck size={15} />Final acceptance ready</div><div className="mt-1 text-[10px] text-muted">{data.acceptance.case_count} cases - {data.acceptance.holdout_passed}/{data.acceptance.holdout_count} holdouts - {data.acceptance.model_calls}/{data.acceptance.approved_model_call_ceiling} model calls - US${data.acceptance.cost_usd.toFixed(2)} direct spend - {(data.acceptance.duration_seconds / 60).toFixed(1)} min</div></div>
      <div className="border-t border-success/20 px-4 py-3 text-[10px] font-semibold uppercase text-warning sm:border-l sm:border-t-0 sm:px-6">Owner acceptance required</div>
    </div>}

    <div className="grid border-b border-border sm:grid-cols-4">
      <Metric label="ECR" value={pct(data.metrics.ecr.overall)} detail={`${data.metrics.ecr.case_count} persisted cases`} good={data.metrics.ecr.overall >= 90} />
      <Metric label="LDR" value={pct(data.metrics.ldr.value)} detail={data.metrics.ldr.formula} good={data.metrics.ldr.value != null && data.metrics.ldr.value <= 50} />
      <Metric label="Release gate" value={release.allowed ? 'Open' : 'Blocked'} detail={release.allowed ? `${release.passed_cases.length} cases passed` : release.blockers[0] || 'Proof missing'} good={release.allowed} />
      <Metric label="Open findings" value={String(data.findings.length)} detail={data.next_action.replace(/-/g, ' ')} good={!data.findings.length} />
    </div>

    <div className="grid border-b border-border xl:grid-cols-[0.75fr_1.25fr]">
      <section className="border-b border-border xl:border-b-0 xl:border-r">
        <div className="border-b border-border px-4 py-3 text-[10px] font-semibold uppercase text-muted">Model lanes</div>
        {Object.entries(data.lanes).map(([lane, value]) => <div key={lane} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-4 py-3 last:border-b-0">
          {value.status === 'available' ? <CheckCircle2 size={15} className="text-success" /> : <Clock3 size={15} className="text-warning" />}
          <div><div className="text-xs font-medium text-heading">{lane.replace('_', ' ')}</div><div className="mt-0.5 text-[10px] text-muted">{value.case_count ? `${value.passed} passed` : 'Required evidence has not run'}</div></div>
          <div className={`font-mono text-xs ${tone(value.status)}`}>{pct(value.completion_rate)}</div>
        </div>)}
      </section>
      <section>
        <div className="grid sm:grid-cols-2">
          <div className="border-b border-border sm:border-b-0 sm:border-r"><div className="border-b border-border px-3 py-3 text-[10px] font-semibold uppercase text-muted">Categories</div>{data.categories.length ? data.categories.map(item => <ProgressRow key={item.category} label={item.category} passed={item.passed} total={item.case_count} rate={item.pass_rate} />) : <div className="p-5 text-xs text-muted">No category proof recorded.</div>}</div>
          <div><div className="border-b border-border px-3 py-3 text-[10px] font-semibold uppercase text-muted">Workflows</div>{data.workflows.length ? data.workflows.map(item => <ProgressRow key={item.workflow_id} label={item.workflow_id} passed={item.passed} total={item.case_count} rate={item.pass_rate} />) : <div className="p-5 text-xs text-muted">No workflow proof recorded.</div>}</div>
        </div>
      </section>
    </div>

    {(data.regressions.length > 0 || data.findings.length > 0) && <section className="border-b border-border">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3 text-[10px] font-semibold uppercase text-muted"><ShieldAlert size={14} className="text-danger" />Blockers</div>
      {data.regressions.map(item => <div key={item.latest_eval_run_id} className="border-b border-border px-4 py-3"><div className="text-xs font-medium text-danger">Regression: {item.case_ref}</div><div className="mt-1 font-mono text-[10px] text-muted">{item.latest_eval_run_id}</div></div>)}
      {data.findings.map(item => <div key={item.finding_id} className="grid gap-2 border-b border-border px-4 py-3 sm:grid-cols-[auto_minmax(0,1fr)_auto]"><AlertTriangle size={15} className="text-warning" /><div><div className="text-xs text-heading">{item.summary}</div><div className="mt-1 text-[10px] text-muted">Owner: {item.remediation_owner} - {item.category}</div></div><span className="text-[10px] font-semibold uppercase text-warning">{item.severity}</span></div>)}
    </section>}

    <div className="grid min-h-80 lg:grid-cols-[minmax(260px,0.8fr)_minmax(0,1.2fr)]">
      <section className="border-b border-border lg:border-b-0 lg:border-r">
        <div className="border-b border-border px-4 py-3 text-[10px] font-semibold uppercase text-muted">Cases {data.cases.length}</div>
        {data.cases.length ? data.cases.map(item => { const key = `${item.eval_case_id}@${item.version}`; return <ActionButton key={key} onAction={() => openCase(item.eval_case_id, item.version)} icon={<CheckCircle2 size={14} className={tone(item.status)} />} className={`grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-4 py-3 text-left ${selected === key ? 'bg-accent/10' : 'hover:bg-overlay/5'}`}><span className="min-w-0"><span className="block truncate text-xs font-medium text-heading">{item.eval_case_id}</span><span className="mt-1 block truncate text-[10px] text-muted">{item.workflow_id} - {item.category}</span></span><span className="flex items-center gap-2"><span className={`font-mono text-[10px] ${tone(item.status)}`}>{item.score ?? '-'}</span><ChevronRight size={14} className="text-muted" /></span></ActionButton> }) : <div className="flex min-h-48 flex-col items-center justify-center gap-2 text-muted"><FileSearch size={20} /><span className="text-xs">No Eval cases persisted.</span></div>}
      </section>
      <section className="min-w-0 p-4 sm:p-5">
        {!selected ? <div className="flex min-h-48 flex-col items-center justify-center gap-2 text-muted"><Gauge size={21} /><span className="text-xs">Select a case to inspect its proof.</span></div>
          : !detail ? <div className="flex min-h-48 items-center justify-center text-muted"><Loader2 size={20} className="animate-spin" /></div>
            : <div><div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-3"><div><h2 className="text-sm font-semibold text-heading">{detail.case.eval_case_id}</h2><div className="mt-1 text-[10px] text-muted">{detail.case.scorer} - threshold {detail.case.threshold}</div></div>{detail.case.autonomy_gate ? <ShieldAlert size={17} className="text-warning" /> : <ShieldCheck size={17} className="text-success" />}</div><p className="py-3 text-xs leading-5 text-text">{detail.case.objective}</p><div className="border border-border"><div className="border-b border-border px-3 py-2 text-[10px] font-semibold uppercase text-muted">Required evidence</div>{detail.case.required_evidence.map(ref => <div key={ref} className="border-b border-border px-3 py-2 font-mono text-[10px] last:border-b-0">{ref}</div>)}</div>{detail.runs.slice(0, 5).map(run => <div key={run.eval_run_id} className="mt-3 border border-border p-3"><div className="flex items-center justify-between gap-3"><span className={`text-xs font-semibold uppercase ${tone(run.status)}`}>{run.status}</span><span className="font-mono text-xs">{run.score ?? '-'} / {run.threshold}</span></div><div className="mt-2 break-all font-mono text-[10px] text-muted">{run.trace_id || 'No trace reference'}</div><div className="mt-2 space-y-1">{run.evidence_refs.map(ref => <div key={ref} className="break-all font-mono text-[10px] text-text">{ref}</div>)}</div></div>)}</div>}
      </section>
    </div>
  </div>
}
