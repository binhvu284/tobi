import { useEffect, useMemo, useState } from 'react'
import { softFail } from '../lib/report'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Stethoscope, Play, Zap, Sparkles, GitCommitHorizontal, Plus, Check,
  ChevronDown, TrendingUp, AlertTriangle, Loader2,
} from 'lucide-react'
import { Stagger, StaggerItem } from './motion'
import { useReducedMotionPref } from '../context/MotionProvider'
import { getPerformance, runPerformance, createPerformanceTask, type PerfReport, type PerfFinding, type PerfSubsystem } from '../api.performance'

// grade → theme color family
function gradeColor(grade: string): { text: string; bg: string; ring: string } {
  const g = grade[0]
  if (g === 'A') return { text: 'text-success', bg: 'bg-success/15', ring: 'var(--success)' }
  if (g === 'B') return { text: 'text-accent', bg: 'bg-accent/15', ring: 'var(--accent)' }
  if (g === 'C') return { text: 'text-warning', bg: 'bg-warning/15', ring: 'var(--warning)' }
  return { text: 'text-danger', bg: 'bg-danger/15', ring: 'var(--danger)' }
}
const SEV: Record<string, { cls: string; label: string }> = {
  high: { cls: 'bg-danger/15 text-danger', label: 'HIGH' },
  med: { cls: 'bg-warning/15 text-warning', label: 'MED' },
  low: { cls: 'bg-border/50 text-muted', label: 'LOW' },
}
const EFFORT: Record<string, string> = { S: 'small', M: 'medium', L: 'large' }
const PHASES = ['Mapping the codebase…', 'Measuring coupling & size…', 'Grading subsystems…', 'Ranking findings…']
const DEEP_PHASES = [...PHASES, 'Writing the diagnosis…']

/** Circular score gauge (SVG ring) that sweeps up to the score. */
function Gauge({ score, grade, animate }: { score: number; grade: string; animate: boolean }) {
  const c = gradeColor(grade)
  const R = 52, C = 2 * Math.PI * R
  const pct = Math.max(0, Math.min(100, score)) / 100
  return (
    <div className="relative h-32 w-32 shrink-0">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <circle cx="60" cy="60" r={R} fill="none" stroke="var(--border)" strokeWidth="9" opacity="0.5" />
        <motion.circle
          cx="60" cy="60" r={R} fill="none" stroke={c.ring} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={C}
          initial={{ strokeDashoffset: animate ? C : C * (1 - pct) }}
          animate={{ strokeDashoffset: C * (1 - pct) }}
          transition={{ duration: animate ? 1.1 : 0, ease: 'easeOut' }}
          style={{ filter: `drop-shadow(0 0 6px ${c.ring})` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-3xl font-bold leading-none ${c.text}`}>{grade}</span>
        <span className="mt-1 text-xs text-muted">{score.toFixed(0)}/100</span>
      </div>
    </div>
  )
}

/** Tiny trend sparkline of past scores. */
function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null
  const w = 120, h = 30, min = Math.min(...points), max = Math.max(...points)
  const span = max - min || 1
  const path = points.map((p, i) =>
    `${(i / (points.length - 1)) * w},${h - ((p - min) / span) * (h - 4) - 2}`).join(' ')
  const up = points[points.length - 1] >= points[0]
  return (
    <div className="flex items-center gap-1.5">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-7 w-[120px]" preserveAspectRatio="none">
        <polyline points={path} fill="none" stroke={up ? 'var(--success)' : 'var(--warning)'}
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <TrendingUp size={12} className={up ? 'text-success' : 'text-warning rotate-180'} />
    </div>
  )
}

function FindingRow({ f, reduced }: { f: PerfFinding; reduced: boolean }) {
  const [open, setOpen] = useState(false)
  const [taskState, setTaskState] = useState<'idle' | 'saving' | 'done' | 'err'>('idle')
  const sev = SEV[f.severity] ?? SEV.low
  const addTask = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (taskState === 'saving' || taskState === 'done') return
    setTaskState('saving')
    try {
      await createPerformanceTask({ title: f.title, detail: f.detail, subsystem: f.subsystem, severity: f.severity })
      setTaskState('done')
    } catch { setTaskState('err') }
  }
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-bg">
      <button onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-2.5 p-2.5 text-left transition-colors hover:bg-surface">
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wide ${sev.cls}`}>{sev.label}</span>
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-text">{f.title}</span>
        <span className="hidden shrink-0 rounded bg-border/40 px-1.5 py-0.5 text-[9px] text-muted sm:inline">{EFFORT[f.effort] ?? f.effort} effort</span>
        <span className="shrink-0 text-[10px] text-muted">{f.subsystem}</span>
        <button onClick={addTask} title="Create a task from this finding"
          className={`flex shrink-0 items-center gap-1 rounded border px-1.5 py-1 text-[10px] font-medium transition-colors ${
            taskState === 'done' ? 'border-success/40 bg-success/10 text-success'
              : taskState === 'err' ? 'border-danger/40 bg-danger/10 text-danger'
              : 'border-accent/40 bg-accent/10 text-accent hover:bg-accent/20'}`}>
          {taskState === 'saving' ? <Loader2 size={11} className="animate-spin" />
            : taskState === 'done' ? <Check size={11} /> : <Plus size={11} />}
          {taskState === 'done' ? 'Added' : taskState === 'err' ? 'Retry' : 'Task'}
        </button>
        <ChevronDown size={13} className={`shrink-0 text-muted transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: reduced ? 'auto' : 0, opacity: reduced ? 1 : 0 }}
            animate={{ height: 'auto', opacity: 1 }} exit={{ height: reduced ? 'auto' : 0, opacity: 0 }}
            transition={{ duration: 0.22 }} className="overflow-hidden">
            <div className="border-t border-border px-3 py-2 text-[11px] leading-relaxed text-muted">
              {f.detail} <span className="text-text/70">→ {f.target}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function SubsystemCard({ s }: { s: PerfSubsystem }) {
  const c = gradeColor(s.grade)
  return (
    <div className="rounded-lg border border-border bg-bg p-3">
      <div className="flex items-center justify-between">
        <span className="truncate text-xs font-semibold text-heading">{s.name}</span>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-bold ${c.bg} ${c.text}`}>{s.grade}</span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-border/40">
        <motion.div className="h-full rounded-full" style={{ background: c.ring }}
          initial={{ width: 0 }} animate={{ width: `${s.score}%` }} transition={{ duration: 0.8, ease: 'easeOut' }} />
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-2.5 gap-y-0.5 text-[10px] text-muted">
        <span>{(s.total_loc / 1000).toFixed(1)}k LOC</span>
        {s.oversized > 0 && <span className="text-warning">{s.oversized} oversized</span>}
        {s.god_modules > 0 && <span className="text-danger">{s.god_modules} hub{s.god_modules > 1 ? 's' : ''}</span>}
        {s.todos > 0 && <span>{s.todos} TODO</span>}
      </div>
    </div>
  )
}

/** The smooth "running diagnostics" sweep — cycling phase + shimmering placeholder cards. */
function RunningSweep({ deep, reduced }: { deep: boolean; reduced: boolean }) {
  const phases = deep ? DEEP_PHASES : PHASES
  const [pi, setPi] = useState(0)
  useEffect(() => {
    if (reduced) return
    const t = setInterval(() => setPi(p => (p + 1) % phases.length), 900)
    return () => clearInterval(t)
  }, [reduced, phases.length])
  return (
    <div className="rounded-xl border border-accent/30 bg-surface p-5">
      <div className="mb-4 flex items-center gap-3">
        <span className="relative flex h-9 w-9 items-center justify-center rounded-full bg-accent/10">
          {!reduced && <span className="absolute inset-0 animate-ping rounded-full bg-accent/20" />}
          <Stethoscope size={16} className="relative text-accent" />
        </span>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-heading">Running diagnostics</div>
          <div className="h-4 overflow-hidden text-xs text-accent/90">
            <AnimatePresence mode="wait">
              <motion.div key={pi} initial={{ y: reduced ? 0 : 8, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
                exit={{ y: reduced ? 0 : -8, opacity: 0 }} transition={{ duration: 0.3 }}>
                {phases[pi]}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="relative h-14 overflow-hidden rounded-lg border border-border bg-bg">
            {!reduced && <span className="radar-scan-overlay" style={{ animationDelay: `${i * 0.14}s` }} />}
            <div className="flex h-full flex-col justify-center gap-1.5 px-3">
              <div className="h-2 w-1/2 rounded bg-border/60" />
              <div className="h-1.5 w-3/4 rounded bg-border/40" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function PerformanceDoctor() {
  const reduced = useReducedMotionPref() !== 'full'
  const [report, setReport] = useState<PerfReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [deep, setDeep] = useState(false)
  const [firstLoad, setFirstLoad] = useState(true)
  const [justRan, setJustRan] = useState(false)

  useEffect(() => {
    getPerformance().then(r => { if (r && r.available !== false) setReport(r) })
      .catch(softFail('the performance report')).finally(() => setFirstLoad(false))
  }, [])

  const run = async () => {
    setLoading(true); setJustRan(false)
    try {
      const r = await runPerformance(deep ? 'deep' : 'quick')
      setReport(r); setJustRan(true)
    } catch (error) { softFail('the performance report')(error) } finally { setLoading(false) }
  }

  const trendScores = useMemo(() => (report?.trend ?? []).map(t => t.score), [report])
  const has = report && report.overall && (report.subsystems?.length ?? 0) > 0
  const highCount = report?.findings?.filter(f => f.severity === 'high').length ?? 0

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4">
        <div className="flex items-center gap-2">
          <Stethoscope size={18} className="text-accent" />
          <div>
            <div className="text-sm font-semibold text-heading">System doctor</div>
            <div className="text-xs text-muted">Analyze MC performance & architecture — is it optimized, or does it need a refactor?</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex overflow-hidden rounded-lg border border-border text-xs">
            <button onClick={() => setDeep(false)}
              className={`flex items-center gap-1 px-2.5 py-1.5 transition-colors ${!deep ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}>
              <Zap size={12} /> Quick
            </button>
            <button onClick={() => setDeep(true)}
              className={`flex items-center gap-1 border-l border-border px-2.5 py-1.5 transition-colors ${deep ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}>
              <Sparkles size={12} /> Deep
            </button>
          </div>
          <button onClick={run} disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50">
            {loading ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
            {loading ? 'Analyzing…' : 'Run analysis'}
          </button>
        </div>
      </div>

      {loading && <RunningSweep deep={deep} reduced={reduced} />}

      {!loading && !has && !firstLoad && (
        <div className="rounded-xl border border-dashed border-border bg-surface p-8 text-center">
          <Stethoscope size={28} className="mx-auto text-muted" />
          <p className="mt-2 text-sm text-heading">No analysis yet</p>
          <p className="mt-1 text-xs text-muted">Run a Quick scan (near-free) to see the current optimization picture, or a Deep audit for TOBI's written diagnosis.</p>
        </div>
      )}

      {!loading && has && report && (
        <motion.div initial={justRan && !reduced ? { opacity: 0, y: 8 } : false}
          animate={{ opacity: 1, y: 0 }} className="space-y-4">
          {/* Score hero */}
          <div className="flex flex-col items-center gap-5 rounded-xl border border-border bg-surface p-5 sm:flex-row">
            <Gauge score={report.overall!.score} grade={report.overall!.grade} animate={justRan && !reduced} />
            <div className="min-w-0 flex-1 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-heading">Optimization score</span>
                {highCount > 0
                  ? <span className="flex items-center gap-1 rounded-full bg-danger/15 px-2 py-0.5 text-[11px] font-medium text-danger"><AlertTriangle size={11} />{highCount} high-severity</span>
                  : <span className="rounded-full bg-success/15 px-2 py-0.5 text-[11px] font-medium text-success">no high-severity items</span>}
                {report.deep_synthesized && <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] text-accent">deep</span>}
              </div>
              <p className="text-xs leading-relaxed text-muted"
                dangerouslySetInnerHTML={{ __html: mdBold(report.diagnosis ?? '') }} />
              <div className="flex flex-wrap items-center gap-3 pt-1 text-[10px] text-muted">
                {trendScores.length >= 2 && <Sparkline points={trendScores} />}
                <span className="flex items-center gap-1"><GitCommitHorizontal size={11} />
                  map {report.freshness?.stale ? report.freshness?.behind_label ?? 'stale' : 'fresh'}</span>
                {report.counts && <span>{report.counts.files} files analyzed</span>}
                {report.generated_ms != null && <span>{report.generated_ms}ms</span>}
              </div>
            </div>
          </div>

          {/* Subsystem grades */}
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Subsystems (weakest first)</div>
            <Stagger className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" step={0.05}>
              {report.subsystems!.map(s => <StaggerItem key={s.name}><SubsystemCard s={s} /></StaggerItem>)}
            </Stagger>
          </div>

          {/* Findings */}
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Findings ({report.findings?.length ?? 0}) — ranked by severity × effort
            </div>
            {(report.findings?.length ?? 0) === 0 ? (
              <div className="rounded-lg border border-success/30 bg-success/5 p-3 text-xs text-success">
                Nothing flagged — the system looks well-factored, sir.
              </div>
            ) : (
              <Stagger className="space-y-1.5" step={0.04}>
                {report.findings!.map((f, i) => <StaggerItem key={i}><FindingRow f={f} reduced={reduced} /></StaggerItem>)}
              </Stagger>
            )}
          </div>
        </motion.div>
      )}
    </div>
  )
}

// minimal **bold** → <strong> for the diagnosis line (backend emits markdown bold)
function mdBold(s: string): string {
  const esc = s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc.replace(/\*\*(.+?)\*\*/g, '<strong class="text-text">$1</strong>')
}
