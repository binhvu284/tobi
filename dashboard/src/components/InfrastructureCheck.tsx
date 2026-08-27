import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  AlertTriangle, CheckCircle2, ChevronDown, Cpu, Layers, Loader2, ShieldCheck, Wrench,
} from 'lucide-react'
import { ActionButton, LoadFailure } from './async-ui'
import { useReducedMotionPref } from '../context/MotionProvider'
import {
  runInfrastructureCheckStream,
  type InfraSummary, type SuiteResult, type WiringCheck,
} from '../api.abilities'

/** One-click proof that the Runtime V2 foundation works on this machine.
 *
 *  Two halves, because neither is enough alone. **This server** is read-only and answers in
 *  under a second: which database file is open, whether this process can reach the internet,
 *  whether the canonical tables are there. **The foundation** runs the 22 acceptance suites,
 *  each in its own throwaway database — the same suites the release gate runs, so the page and
 *  the gate can never disagree.
 *
 *  Every row stays visible while it is pending. A sweep that reveals its rows one at a time
 *  reads as "still going"; a list that grows from nothing reads as "nothing found yet". */

type Row = { id: string; label: string; state: 'pending' | 'ok' | 'failed' }

const PACKAGE_HINT: Record<string, string> = {
  T01: 'Shared shapes', T02: 'Written history', T03: 'Durable runs', T04: 'Chat & Agent',
  T05: 'Permission', T06: 'Tools', T07: 'Tool actions', T08: 'Conductor', T09: 'Memory',
  T10: 'Workers', T11: 'Traces & quality', T11A: 'Self-description', T12: 'Security',
  T13: 'Runs page', T14: 'Rollout', T15: 'Every surface', fix: 'Repair', UI: 'Interface',
}

function Verdict({ ok, pending }: { ok?: boolean; pending?: boolean }) {
  if (pending) return <Loader2 size={14} className="shrink-0 animate-spin text-accent" />
  return ok
    ? <CheckCircle2 size={14} className="shrink-0 text-success" />
    : <AlertTriangle size={14} className="shrink-0 text-danger" />
}

export default function InfrastructureCheck() {
  const reduced = useReducedMotionPref() !== 'full'
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [ranAt, setRanAt] = useState<string>('')
  const [wiringPlan, setWiringPlan] = useState<Row[]>([])
  const [suitePlan, setSuitePlan] = useState<(Row & { package: string; proves: string })[]>([])
  const [wiring, setWiring] = useState<Record<string, WiringCheck>>({})
  const [suites, setSuites] = useState<Record<string, SuiteResult>>({})
  const [summary, setSummary] = useState<InfraSummary | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  const run = async () => {
    setRunning(true); setError(null); setSummary(null)
    setWiring({}); setSuites({}); setWiringPlan([]); setSuitePlan([])
    try {
      const result = await runInfrastructureCheckStream({
        onStart: plan => {
          setWiringPlan(plan.wiring.map(w => ({ ...w, state: 'pending' })))
          setSuitePlan(plan.suites.map(s => ({ ...s, state: 'pending' })))
        },
        onWiring: row => setWiring(prev => ({ ...prev, [row.id]: row })),
        onSuite: row => setSuites(prev => ({ ...prev, [row.id]: row })),
      })
      setSummary(result)
      setRanAt(new Date().toLocaleTimeString('en-GB'))
    } catch (e) {
      setError(e)
    } finally {
      setRunning(false)
    }
  }

  const suitesDone = suitePlan.filter(s => suites[s.id]).length
  const failed = [...Object.values(wiring), ...Object.values(suites)].filter(r => !r.ok)
  const totalChecks = Object.values(suites).reduce((n, s) => n + (s.checks || 0), 0)
  const started = wiringPlan.length > 0 || suitePlan.length > 0

  return (
    <div className="space-y-4">
      {/* Header + the one button */}
      <div className="rounded-lg border border-border bg-surface p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-heading">
              <Layers size={15} className="text-accent" /> Infrastructure test
            </div>
            <p className="mt-1 max-w-2xl text-xs text-muted">
              Proves the engine every request runs on — durable runs, written history, permissions,
              tools, security, rollout — actually works here. Checks this server first, then runs
              every acceptance suite in its own throwaway database. Your data is never touched.
              Takes about a minute.
            </p>
          </div>
          <ActionButton
            onAction={run} busy={running}
            icon={<ShieldCheck size={13} />}
            className="flex shrink-0 items-center gap-2 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20">
            {running ? `Testing… ${suitesDone}/${suitePlan.length || '…'}` : 'Run infrastructure test'}
          </ActionButton>
        </div>

        {/* Verdict banner — the answer, before any of the detail */}
        {summary && (
          <motion.div
            initial={{ opacity: 0, y: reduced ? 0 : 6 }} animate={{ opacity: 1, y: 0 }}
            className={`mt-4 rounded-lg border p-3.5 ${summary.ok === summary.total
              ? 'border-success/40 bg-success/10' : 'border-danger/40 bg-danger/10'}`}>
            <div className={`flex items-center gap-2 text-sm font-semibold ${summary.ok === summary.total ? 'text-success' : 'text-danger'}`}>
              {summary.ok === summary.total ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
              {summary.ok === summary.total
                ? `The infrastructure is sound — all ${summary.total} checks passed`
                : `${summary.total - summary.ok} of ${summary.total} checks need a look`}
            </div>
            <div className="mt-1 text-xs text-muted">
              {summary.checks.toLocaleString()} individual proofs ran across {suitePlan.length} suites
              {ranAt && ` · finished ${ranAt}`}
              {summary.flaky_ids.length > 0 && ` · ${summary.flaky_ids.length} passed only on a second run`}
            </div>
            {failed.length > 0 && (
              <ul className="mt-3 space-y-1.5">
                {failed.map(row => (
                  <li key={row.id} className="text-xs">
                    <span className="font-medium text-text">{row.label}</span>
                    <span className="text-muted"> — {row.detail}</span>
                    {'hint' in row && row.hint ? (
                      <div className="mt-0.5 flex items-start gap-1.5 text-[11px] text-warning">
                        <Wrench size={11} className="mt-0.5 shrink-0" />{row.hint}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </motion.div>
        )}

        {!started && !running && (
          <div className="mt-4 text-xs text-muted">
            No test run yet — press <b>Run infrastructure test</b> to check everything now.
          </div>
        )}
      </div>

      {error != null && <LoadFailure error={error} what="the infrastructure test" onRetry={run} />}

      {/* This server — read-only, instant, and the half that catches real incidents */}
      {wiringPlan.length > 0 && (
        <div className="rounded-lg border border-border bg-surface p-5">
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-heading">
            <Cpu size={15} className="text-accent" /> This server
          </div>
          <div className="mb-3 text-xs text-muted">
            Things only a running server can answer: which database it opened, whether it can reach
            the internet, what the rollout switches are set to.
          </div>
          <div className="grid gap-2 lg:grid-cols-2">
            {wiringPlan.map(plan => {
              const row = wiring[plan.id]
              return (
                <div key={plan.id}
                  className={`flex items-start gap-2.5 rounded border p-2.5 ${!row ? 'border-border bg-bg'
                    : row.ok ? 'border-border bg-bg' : 'border-danger/40 bg-danger/5'}`}>
                  <span className="mt-0.5"><Verdict ok={row?.ok} pending={!row} /></span>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium text-text">{plan.label}</div>
                    <div className="mt-0.5 break-words text-[11px] text-muted">
                      {row ? row.detail : 'checking…'}
                    </div>
                    {row && !row.ok && row.hint && (
                      <div className="mt-1 flex items-start gap-1.5 text-[11px] text-warning">
                        <Wrench size={11} className="mt-0.5 shrink-0" />{row.hint}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* The foundation — the acceptance suites, named by what they prove */}
      {suitePlan.length > 0 && (
        <div className="rounded-lg border border-border bg-surface p-5">
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-heading">
            <ShieldCheck size={15} className="text-accent" /> The foundation
            <span className="ml-1 rounded-full bg-bg px-2 py-0.5 text-[10px] font-normal text-muted">
              {suitesDone}/{suitePlan.length}{totalChecks ? ` · ${totalChecks} proofs` : ''}
            </span>
          </div>
          <div className="mb-3 text-xs text-muted">
            The same suites the release gate runs. Click a row to see what a green result means.
          </div>
          <div className="space-y-1.5">
            {suitePlan.map(plan => {
              const row = suites[plan.id]
              const expanded = open === plan.id
              return (
                <div key={plan.id}
                  className={`rounded border ${!row ? 'border-border bg-bg'
                    : row.ok ? 'border-border bg-bg' : 'border-danger/40 bg-danger/5'}`}>
                  <button type="button" onClick={() => setOpen(expanded ? null : plan.id)}
                    aria-expanded={expanded}
                    className="flex w-full items-center gap-2.5 px-2.5 py-2 text-left">
                    <Verdict ok={row?.ok} pending={!row} />
                    <span className="w-16 shrink-0 rounded bg-surface px-1.5 py-0.5 text-center font-mono text-[10px] text-muted"
                      title={PACKAGE_HINT[plan.package] ?? plan.package}>{plan.package}</span>
                    <span className="min-w-0 flex-1 truncate text-xs font-medium text-text">{plan.label}</span>
                    {row?.retried && row.ok && (
                      <span className="shrink-0 rounded-full bg-warning/15 px-2 py-0.5 text-[10px] text-warning"
                        title="The first run failed and the second passed — a timing flake, not a defect.">
                        passed on retry
                      </span>
                    )}
                    {row?.retried && !row.ok && (
                      <span className="shrink-0 rounded-full bg-danger/15 px-2 py-0.5 text-[10px] text-danger"
                        title="Both runs failed, so this is a confirmed failure rather than a timing flake.">
                        failed twice
                      </span>
                    )}
                    <span className="shrink-0 font-mono text-[10px] text-muted">
                      {row ? `${row.checks} checks` : 'waiting'}
                    </span>
                    {row?.duration_ms ? (
                      <span className="hidden shrink-0 font-mono text-[10px] text-muted sm:inline">
                        {(row.duration_ms / 1000).toFixed(1)}s
                      </span>
                    ) : null}
                    <ChevronDown size={13}
                      className={`shrink-0 text-muted transition-transform ${expanded ? 'rotate-180' : ''}`} />
                  </button>
                  {(expanded || (row && !row.ok)) && (
                    <div className="border-t border-border px-2.5 py-2 text-[11px] text-muted">
                      <div>{plan.proves}</div>
                      {row && !row.ok && (
                        <div className="mt-1.5 break-words font-mono text-[11px] text-danger">{row.detail}</div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
