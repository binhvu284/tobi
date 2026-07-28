import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  HardDrive, Coins, RefreshCw, Search, Database, TrendingUp, Wallet,
  ChevronRight, Layers, AlertTriangle, Save, Plus, Trash2, FolderTree,
} from 'lucide-react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as ReTooltip, AreaChart, Area, PieChart, Pie, Cell, Treemap,
} from 'recharts'
import { AmbientField, CountUp, SpotlightCard } from '../components/motion'
import { useTheme } from '../context/ThemeProvider'
import { useToast } from '../context/ToastProvider'
import { useReducedMotionPref } from '../context/MotionProvider'
import { getStorageOverview, getStorageCategory, runStorageScan, getUsageOverview, getUsageCalls, getUsagePlans, setUsagePlans, getUsageBudget, setUsageBudget, type StorageOverview, type StorageCategoryDetail, type UsageOverview, type UsageCall, type UsagePlan, type UsageBudget, type UsageBucket, type UsageMetric } from '../api.storage'
import PageLoader from '../components/PageLoader'
import { fmtBytes, fmtUsd, fmtTok } from '../lib/format'

const fmtDelta = (n: number) => `${n >= 0 ? '+' : '−'}${fmtBytes(Math.abs(n))}`

// ── theme-aware chart colors ──────────────────────────────────────────────────
// Charts read the live CSS variables so every one of the 8 themes just works.
// Categorical hues are assigned in FIXED order per entity (never cycled by rank),
// with legends + direct labels as the required secondary encoding.
function useChartColors() {
  const { theme } = useTheme()
  return useMemo(() => {
    const css = getComputedStyle(document.documentElement)
    const v = (name: string) => `rgb(${css.getPropertyValue(name).trim().split(/\s+/).join(' ')})`
    const va = (name: string, a: number) => `rgb(${css.getPropertyValue(name).trim().split(/\s+/).join(' ')} / ${a})`
    // Theme v2 (#13): prefer the theme's dedicated chart palette (--chart-1..6),
    // falling back to the semantic tokens for any theme that doesn't define it.
    const chart = (n: number, fb: string) => (css.getPropertyValue(`--chart-${n}`).trim() ? v(`--chart-${n}`) : v(fb))
    return {
      accent: v('--accent'), purple: v('--purple'), success: v('--success'),
      warning: v('--warning'), danger: v('--danger'), muted: v('--muted'),
      border: v('--border'), surface: v('--surface'), text: v('--text'),
      grid: va('--border', 0.5), accentSoft: va('--accent', 0.25),
      cat: [chart(1, '--accent'), chart(2, '--purple'), chart(3, '--success'),
        chart(4, '--warning'), chart(5, '--danger'), chart(6, '--muted')],
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme])
}

// Fixed entity→hue order so colors follow the entity, not its rank [dataviz rule]
const FEATURE_ORDER = ['Brain', 'Graph', 'Chat', 'Agent', 'Developer', 'Office',
  'Tasks', 'Projects', 'Documents', 'News', 'Evolution', 'Abilities', 'Health',
  'Codebase', 'Backups', 'Vault', 'MCP', 'System', 'Other']
const SURFACE_ORDER = ['chat', 'agent', 'office', 'research', 'brain', 'ceo', 'classifier', 'terminal']
function entityColor(name: string, order: string[], cat: string[]): string {
  const i = order.indexOf(name)
  const idx = i >= 0 ? i : order.length + Math.abs(name.split('').reduce((a, c) => a + c.charCodeAt(0), 0))
  return cat[idx % cat.length]
}

// ── shared chart bits ─────────────────────────────────────────────────────────
function ChartTip({ active, payload, label, fmt }: {
  active?: boolean; payload?: { name: string; value: number; color?: string }[]
  label?: string; fmt: (v: number) => string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-xl">
      {label && <div className="mb-1 font-semibold text-heading">{label}</div>}
      {payload.filter(p => p.value !== 0 || payload.length === 1).map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted">{p.name}</span>
          <span className="ml-auto pl-3 font-mono text-text">{fmt(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

function Legend({ items }: { items: { name: string; color: string; value?: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
      {items.map(it => (
        <span key={it.name} className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ background: it.color }} />
          <span className="text-muted">{it.name}</span>
          {it.value && <span className="font-mono text-text">{it.value}</span>}
        </span>
      ))}
    </div>
  )
}

function Section({ title, icon, right, children }: {
  title: string; icon?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
          {icon}{title}
        </h2>
        {right}
      </div>
      {children}
    </section>
  )
}

// Treemap cell: label carries identity; fill is a single-hue magnitude ramp.
function TreemapCell(props: {
  x?: number; y?: number; width?: number; height?: number; name?: string
  value?: number; colors?: ReturnType<typeof useChartColors>; max?: number
}) {
  const { x = 0, y = 0, width = 0, height = 0, name, value = 0, colors, max = 1 } = props
  if (!colors || width < 4 || height < 4 || !name) return <g />
  const t = Math.sqrt(Math.min(1, value / max)) * 0.55 + 0.15
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} rx={4}
        fill={colors.accent} fillOpacity={t} stroke={colors.surface} strokeWidth={2} />
      {width > 58 && height > 30 && (
        <>
          <text x={x + 8} y={y + 17} fill={colors.text} fontSize={11} fontWeight={600}>{name}</text>
          <text x={x + 8} y={y + 31} fill={colors.muted} fontSize={10} fontFamily="monospace">{fmtBytes(value)}</text>
        </>
      )}
    </g>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
export default function Storage() {
  const colors = useChartColors()
  const motionLevel = useReducedMotionPref()
  const animate = motionLevel === 'full'
  const { toast } = useToast()

  const [tab, setTab] = useState<'storage' | 'usage'>('storage')
  const [ov, setOv] = useState<StorageOverview | null>(null)
  const [scanning, setScanning] = useState(false)
  const [drill, setDrill] = useState<StorageCategoryDetail | null>(null)
  const [drillFor, setDrillFor] = useState<string>('')

  const [range, setRange] = useState<'day' | 'week' | 'month' | 'all'>('month')
  const [usageMetric, setUsageMetric] = useState<UsageMetric>('tokens')
  const [uo, setUo] = useState<UsageOverview | null>(null)
  const [budget, setBudget] = useState<UsageBudget | null>(null)
  const [plans, setPlans] = useState<UsagePlan[]>([])
  const warned = useRef(false)

  useEffect(() => { getStorageOverview().then(setOv).catch(() => {}) }, [])
  useEffect(() => { getUsageOverview(range, usageMetric).then(setUo).catch(() => {}) }, [range, usageMetric])
  useEffect(() => {
    getUsagePlans().then(r => setPlans(r.plans)).catch(() => {})
    getUsageBudget().then(b => {
      setBudget(b)
      if (!warned.current && (b.level === 'warn' || b.level === 'over')) {
        warned.current = true
        toast({
          kind: b.level === 'over' ? 'error' : 'info',
          title: b.level === 'over' ? 'LLM budget exceeded' : 'LLM budget warning',
          detail: `${fmtUsd(b.spent_usd)} of ${fmtUsd(b.monthly_cap_usd)} this month (${b.pct}%)`,
        })
      }
    }).catch(() => {})
  }, [toast])

  const scanNow = useCallback(async () => {
    setScanning(true)
    try {
      const r = await runStorageScan('all')
      setOv(r.overview)
      toast({ kind: 'success', title: 'Storage scan complete' })
      if (drillFor) getStorageCategory(drillFor).then(setDrill).catch(() => {})
    } catch {
      toast({ kind: 'error', title: 'Scan failed' })
    } finally {
      setScanning(false)
    }
  }, [toast, drillFor])

  const openDrill = useCallback((feature: string) => {
    setDrillFor(feature)
    setDrill(null)
    getStorageCategory(feature).then(setDrill).catch(() => setDrillFor(''))
  }, [])

  if (!ov) return <PageLoader />

  const dataFeatures = ov.features.filter(f => f.feature !== 'System' && f.feature !== '__meta__')
  const donutData = (() => {
    const top = dataFeatures.slice(0, 5)
    const rest = dataFeatures.slice(5).reduce((a, f) => a + f.bytes, 0)
    const items = top.map(f => ({ name: f.feature, value: f.bytes }))
    if (rest > 0) items.push({ name: 'Other', value: rest })
    return items
  })()
  const treeData = dataFeatures.filter(f => f.bytes > 0)
    .map(f => ({ name: f.feature, size: f.bytes }))
  const treeMax = Math.max(...treeData.map(t => t.size), 1)

  return (
    <div className="relative mx-auto max-w-6xl space-y-5 p-4 md:p-6">
      <AmbientField />

      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent">
            <HardDrive size={20} />
          </span>
          <div>
            <h1 className="text-xl font-bold text-heading">Storage & Usage</h1>
            <p className="text-xs text-muted">
              {ov.scanned_at.fs ? `Last scan ${new Date(ov.scanned_at.fs).toLocaleString()}` : 'Not scanned yet'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-border bg-bg p-0.5 text-xs">
            {(['storage', 'usage'] as const).map(t => (
              <button key={t} onClick={() => setTab(t)}
                className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
                  tab === t ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}>
                {t === 'storage' ? 'Storage' : 'LLM Usage'}
              </button>
            ))}
          </div>
          <button onClick={scanNow} disabled={scanning}
            className="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-text transition-colors hover:border-accent/40 disabled:opacity-50">
            <RefreshCw size={13} className={scanning ? 'animate-spin' : ''} />
            {scanning ? 'Scanning…' : 'Scan now'}
          </button>
        </div>
      </div>

      {/* overview KPIs [S12] */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <SpotlightCard className="rounded-xl border border-border bg-surface p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Total storage</div>
          <CountUp value={ov.total_bytes} format={fmtBytes} className="text-lg font-bold text-heading" />
          <div className="text-[10px] text-muted">{fmtBytes(ov.data_bytes)} data · {fmtBytes(ov.system_bytes)} system</div>
        </SpotlightCard>
        <SpotlightCard className="rounded-xl border border-border bg-surface p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">agent.db</div>
          <CountUp value={ov.db.size_bytes} format={fmtBytes} className="text-lg font-bold text-heading" />
          <div className="text-[10px] text-muted">{ov.db.total_rows.toLocaleString()} rows · {ov.db.table_count} tables</div>
        </SpotlightCard>
        <SpotlightCard className="rounded-xl border border-border bg-surface p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Biggest consumer</div>
          <div className="truncate text-lg font-bold text-heading">{ov.biggest?.feature ?? '—'}</div>
          <div className="text-[10px] text-muted">{ov.biggest ? fmtBytes(ov.biggest.bytes) : 'no data yet'}</div>
        </SpotlightCard>
        <SpotlightCard className="rounded-xl border border-border bg-surface p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Growth / week</div>
          <div className={`text-lg font-bold ${ov.growth.week_delta_bytes > 0 ? 'text-warning' : 'text-success'}`}>
            {fmtDelta(ov.growth.week_delta_bytes)}
          </div>
          <div className="text-[10px] text-muted">≈{fmtBytes(ov.growth.projection_30d_bytes)} in 30d</div>
        </SpotlightCard>
        <SpotlightCard className="rounded-xl border border-border bg-surface p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Spend ({range})</div>
          <CountUp value={uo?.total_cost ?? 0} format={fmtUsd} className="text-lg font-bold text-heading" />
          <div className="text-[10px] text-muted">{fmtTok(uo?.total_tokens ?? 0)} tokens · {uo?.requests ?? 0} calls</div>
        </SpotlightCard>
        <SpotlightCard className="rounded-xl border border-border bg-surface p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Budget</div>
          {budget && budget.level !== 'off' ? (
            <>
              <div className={`text-lg font-bold ${
                budget.level === 'over' ? 'text-danger' : budget.level === 'warn' ? 'text-warning' : 'text-heading'}`}>
                {budget.pct}%
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-bg">
                <div className={`h-full rounded-full ${
                  budget.level === 'over' ? 'bg-danger' : budget.level === 'warn' ? 'bg-warning' : 'bg-accent'}`}
                  style={{ width: `${Math.min(100, budget.pct)}%` }} />
              </div>
              <div className="mt-0.5 text-[10px] text-muted">{fmtUsd(budget.spent_usd)} / {fmtUsd(budget.monthly_cap_usd)}</div>
            </>
          ) : (
            <>
              <div className="text-lg font-bold text-muted">—</div>
              <div className="text-[10px] text-muted">no cap set</div>
            </>
          )}
        </SpotlightCard>
      </div>

      {budget && budget.level === 'over' && (
        <div className="flex items-center gap-2 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
          <AlertTriangle size={14} /> Monthly LLM budget exceeded — {fmtUsd(budget.spent_usd)} of {fmtUsd(budget.monthly_cap_usd)}.
        </div>
      )}

      {tab === 'storage'
        ? <StorageTab ov={ov} colors={colors} animate={animate} donutData={donutData}
            treeData={treeData} treeMax={treeMax} dataFeatures={dataFeatures}
            drill={drill} drillFor={drillFor} openDrill={openDrill} />
        : <UsageTab uo={uo} colors={colors} animate={animate} range={range} setRange={setRange}
            metric={usageMetric} setMetric={setUsageMetric}
            plans={plans} setPlansState={setPlans} budget={budget} setBudgetState={setBudget} />}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
function StorageTab({ ov, colors, animate, donutData, treeData, treeMax, dataFeatures,
  drill, drillFor, openDrill }: {
  ov: StorageOverview
  colors: ReturnType<typeof useChartColors>
  animate: boolean
  donutData: { name: string; value: number }[]
  treeData: { name: string; size: number }[]
  treeMax: number
  dataFeatures: StorageOverview['features']
  drill: StorageCategoryDetail | null
  drillFor: string
  openDrill: (f: string) => void
}) {
  const barData = dataFeatures.filter(f => f.bytes > 0).slice(0, 10)
    .map(f => ({ name: f.feature, bytes: f.bytes }))
  const system = ov.features.find(f => f.feature === 'System')

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        {/* ranked horizontal bars [S10] */}
        <Section title="Storage by feature" icon={<Layers size={13} />}
          right={<span className="text-[10px] text-muted">click a bar to drill down</span>}>
          {barData.length === 0 ? (
            <p className="py-6 text-center text-xs text-muted">Nothing scanned yet — hit Scan now.</p>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(160, barData.length * 34)}>
              <BarChart data={barData} layout="vertical" margin={{ left: 8, right: 48, top: 0, bottom: 0 }}>
                <CartesianGrid horizontal={false} stroke={colors.grid} />
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={84} tickLine={false} axisLine={false}
                  tick={{ fill: colors.muted, fontSize: 11 }} />
                <ReTooltip cursor={{ fill: colors.accentSoft, opacity: 0.15 }}
                  content={<ChartTip fmt={fmtBytes} />} />
                <Bar dataKey="bytes" name="Size" fill={colors.accent} barSize={14}
                  radius={[0, 4, 4, 0]} isAnimationActive={animate}
                  onClick={(d: { name?: string }) => d?.name && openDrill(d.name)}
                  className="cursor-pointer"
                  label={{ position: 'right', fill: colors.muted, fontSize: 10,
                           formatter: (v: number) => fmtBytes(v).replace(' ', '') }} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Section>

        {/* treemap [S10] */}
        <Section title="What's eating disk" icon={<FolderTree size={13} />}>
          {treeData.length === 0 ? (
            <p className="py-6 text-center text-xs text-muted">No data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <Treemap data={treeData} dataKey="size" nameKey="name" isAnimationActive={animate}
                content={<TreemapCell colors={colors} max={treeMax} />}>
                <ReTooltip content={<ChartTip fmt={fmtBytes} />} />
              </Treemap>
            </ResponsiveContainer>
          )}
        </Section>

        {/* growth area [S8][S10] */}
        <Section title="Growth over time" icon={<TrendingUp size={13} />}>
          {ov.trend.length < 2 ? (
            <p className="py-6 text-center text-xs text-muted">
              Growth appears after a few scans — snapshots build the history.
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={ov.trend} margin={{ left: 8, right: 8, top: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="growthFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={colors.accent} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={colors.accent} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke={colors.grid} />
                <XAxis dataKey="day" tickLine={false} axisLine={false}
                  tick={{ fill: colors.muted, fontSize: 10 }} tickFormatter={(d: string) => d.slice(5)} />
                <YAxis tickLine={false} axisLine={false} width={52}
                  tick={{ fill: colors.muted, fontSize: 10 }} tickFormatter={fmtBytes} />
                <ReTooltip content={<ChartTip fmt={fmtBytes} />} />
                <Area type="monotone" dataKey="bytes" name="Total" stroke={colors.accent}
                  strokeWidth={2} fill="url(#growthFill)" isAnimationActive={animate} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Section>
      </div>

      <div className="space-y-4">
        {/* donut share [S10] */}
        <Section title="Share of data" icon={<Database size={13} />}>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={donutData} dataKey="value" nameKey="name" innerRadius={48} outerRadius={72}
                paddingAngle={2} stroke={colors.surface} strokeWidth={2} isAnimationActive={animate}>
                {donutData.map(d => (
                  <Cell key={d.name} fill={entityColor(d.name, FEATURE_ORDER, colors.cat)} />
                ))}
              </Pie>
              <ReTooltip content={<ChartTip fmt={fmtBytes} />} />
            </PieChart>
          </ResponsiveContainer>
          <Legend items={donutData.map(d => ({
            name: d.name, color: entityColor(d.name, FEATURE_ORDER, colors.cat), value: fmtBytes(d.value),
          }))} />
        </Section>

        {/* System bucket [S7] */}
        <Section title="System (deps & build)" icon={<HardDrive size={13} />}>
          <div className="flex items-baseline justify-between">
            <span className="text-lg font-bold text-heading">{fmtBytes(system?.bytes ?? 0)}</span>
            <button onClick={() => openDrill('System')} className="flex items-center gap-0.5 text-[11px] text-accent hover:underline">
              details <ChevronRight size={12} />
            </button>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-muted">
            venv, node_modules, build output & logs — kept out of the feature charts so dev bulk
            never drowns your real data. Re-measured weekly.
          </p>
        </Section>

        {/* drill-down [S9] */}
        <Section title={drillFor ? `Inside ${drillFor}` : 'Drill-down'} icon={<Search size={13} />}>
          {!drillFor ? (
            <p className="py-4 text-center text-xs text-muted">Click a feature bar to see its biggest items.</p>
          ) : !drill ? (
            <p className="py-4 text-center text-xs text-muted">Loading…</p>
          ) : (
            <div className="space-y-3 text-xs">
              {drill.note && <p className="rounded bg-bg px-2 py-1.5 text-[11px] text-muted">{drill.note}</p>}
              {drill.tables.length > 0 && (
                <div>
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">DB tables</div>
                  <div className="space-y-1">
                    {drill.tables.map(t => (
                      <div key={t.table} className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-text">{t.table}</span>
                        <span className="shrink-0 text-muted">{t.rows.toLocaleString()} rows · {fmtBytes(t.bytes)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {drill.fs_items.length > 0 && (
                <div>
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">Files & dirs</div>
                  <div className="space-y-1">
                    {drill.fs_items.map(f => (
                      <div key={f.name} className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-text">{f.name}</span>
                        <span className="shrink-0 text-muted">{fmtBytes(f.bytes)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {drill.tables.length === 0 && drill.fs_items.length === 0 && (
                <p className="py-2 text-center text-muted">Nothing sizable in {drill.feature} yet.</p>
              )}
            </div>
          )}
        </Section>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
function UsageTab({ uo, colors, animate, range, setRange, metric, setMetric, plans, setPlansState,
  budget, setBudgetState }: {
  uo: UsageOverview | null
  colors: ReturnType<typeof useChartColors>
  animate: boolean
  range: 'day' | 'week' | 'month' | 'all'
  setRange: (r: 'day' | 'week' | 'month' | 'all') => void
  metric: UsageMetric
  setMetric: (m: UsageMetric) => void
  plans: UsagePlan[]
  setPlansState: (p: UsagePlan[]) => void
  budget: UsageBudget | null
  setBudgetState: (b: UsageBudget) => void
}) {
  const { toast } = useToast()
  const surfaces = uo?.surfaces ?? []
  const sColor = (s: string) => entityColor(s, SURFACE_ORDER, colors.cat)

  // call log [S20]
  const [calls, setCalls] = useState<UsageCall[]>([])
  const [callTotal, setCallTotal] = useState(0)
  const [q, setQ] = useState('')
  const [sFilter, setSFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const loadCalls = useCallback((offset = 0, append = false) => {
    getUsageCalls({ limit: 25, offset, q, surface: sFilter, status: statusFilter }).then(r => {
      setCallTotal(r.total)
      setCalls(prev => append ? [...prev, ...r.calls] : r.calls)
    }).catch(() => {})
  }, [q, sFilter, statusFilter])
  useEffect(() => { const t = setTimeout(() => loadCalls(0), 250); return () => clearTimeout(t) }, [loadCalls])

  // plan / budget editors
  const [editPlans, setEditPlans] = useState(false)
  const [draftPlans, setDraftPlans] = useState<UsagePlan[]>([])
  const [editBudget, setEditBudget] = useState(false)
  const [draftCap, setDraftCap] = useState('')
  const [draftPct, setDraftPct] = useState('80')

  const savePlans = async () => {
    try {
      const r = await setUsagePlans(draftPlans.filter(p => p.provider && p.plan_name))
      setPlansState(r.plans); setEditPlans(false)
      toast({ kind: 'success', title: 'Plans saved' })
    } catch { toast({ kind: 'error', title: 'Failed to save plans' }) }
  }
  const saveBudget = async () => {
    try {
      const b = await setUsageBudget(parseFloat(draftCap) || 0, parseInt(draftPct) || 80)
      setBudgetState(b); setEditBudget(false)
      toast({ kind: 'success', title: b.monthly_cap_usd ? `Budget cap ${fmtUsd(b.monthly_cap_usd)}` : 'Budget cap removed' })
    } catch { toast({ kind: 'error', title: 'Failed to save budget' }) }
  }

  if (!uo) return <p className="py-10 text-center text-sm text-muted">Loading usage…</p>

  const dims: { title: string; data: UsageBucket[]; key: keyof UsageBucket }[] = [
    { title: 'By model', data: uo.by_model.slice(0, 8), key: 'model' },
    { title: 'By provider', data: uo.by_provider.slice(0, 6), key: 'provider' },
    { title: 'By feature / engine', data: uo.by_surface.slice(0, 8), key: 'surface' },
    { title: 'By purpose', data: uo.by_purpose.slice(0, 8), key: 'purpose' },
  ]
  const metricValue = (bucket: UsageBucket) =>
    metric === 'cost' ? bucket.cost
      : metric === 'requests' ? bucket.requests
        : metric === 'latency' ? bucket.avg_latency_ms
          : bucket.tokens
  const metricText = (bucket: UsageBucket) =>
    metric === 'cost' ? fmtUsd(bucket.cost)
      : metric === 'requests' ? `${bucket.requests} calls`
        : metric === 'latency' ? `${bucket.avg_latency_ms}ms`
          : `${fmtTok(bucket.tokens)} tokens`

  return (
    <div className="space-y-4">
      {/* range and metric selectors [S19] */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex rounded-lg border border-border bg-bg p-0.5 text-xs">
          {(['day', 'week', 'month', 'all'] as const).map(r => (
            <button key={r} onClick={() => setRange(r)}
              className={`rounded-md px-3 py-1 font-medium capitalize transition-colors ${
                range === r ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}>
              {r}
            </button>
          ))}
        </div>
        <div className="flex rounded-lg border border-border bg-bg p-0.5 text-xs" aria-label="Usage ranking metric">
          {(['tokens', 'requests', 'cost', 'latency'] as UsageMetric[]).map(item => (
            <button key={item} onClick={() => setMetric(item)}
              className={`rounded-md px-2.5 py-1 font-medium capitalize transition-colors ${
                metric === item ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}>
              {item === 'requests' ? 'Calls' : item}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-6">
        {[
          ['Model calls', uo.requests.toLocaleString(), `${uo.attempts.toLocaleString()} provider attempts`],
          ['Failed attempts', uo.failed_attempts.toLocaleString(), 'Provider/API failures'],
          ['Fallbacks', uo.fallback_calls.toLocaleString(), 'Completed by another model'],
          ['Attribution', `${uo.coverage.attribution_pct}%`, `${uo.coverage.attributed_calls} calls identified`],
          ['Calls / turn', uo.calls_per_turn == null ? '—' : String(uo.calls_per_turn), 'New attributed turns only'],
          ['Developer sessions', uo.developer_sessions.total.toLocaleString(), 'External CLI work'],
        ].map(([label, value, detail]) => (
          <div key={label} className="rounded-lg border border-border bg-surface/40 px-3 py-2">
            <div className="text-[9px] font-semibold uppercase tracking-wider text-muted">{label}</div>
            <div className="mt-0.5 text-base font-semibold text-heading">{value}</div>
            <div className="truncate text-[10px] text-muted">{detail}</div>
          </div>
        ))}
      </div>

      <Section title="Workload coverage" icon={<Layers size={13} />}>
        <div className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {uo.workloads.map(workload => (
            <div key={workload.workload} className="bg-bg px-3 py-2.5">
              <div className="text-xs font-medium text-text">{workload.workload}</div>
              <div className="mt-1 text-sm font-semibold text-heading">
                {workload.model_calls == null ? `${workload.sessions || 0} sessions` : `${workload.model_calls} calls`}
              </div>
              <div className="mt-0.5 text-[10px] text-muted">
                {workload.usage_reported
                  ? `${fmtTok(workload.tokens || 0)} tokens · ${fmtUsd(workload.cost || 0)}`
                  : 'External CLI token usage not reported'}
              </div>
            </div>
          ))}
        </div>
        {uo.developer_agents.length > 0 && (
          <div className="mt-3 divide-y divide-border/60 border-t border-border">
            {uo.developer_agents.map(agent => (
              <div key={agent.profile_slug} className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 py-2 text-xs">
                <div className="min-w-0">
                  <div className="truncate font-medium text-text">{agent.agent}</div>
                  <div className="truncate text-[10px] text-muted">{agent.adapter} · {agent.model || 'CLI managed model'}</div>
                </div>
                <span className="text-muted">{agent.sessions} sessions</span>
                <span className="text-muted">{agent.completed} completed · {agent.failed} failed</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* spend over time, stacked by surface [S19] */}
      <Section title="Spend over time" icon={<Coins size={13} />}
        right={<Legend items={surfaces.map(s => ({ name: s, color: sColor(s) }))} />}>
        {uo.by_day.every(d => !d.cost) ? (
          <p className="py-6 text-center text-xs text-muted">No spend in this range.</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={uo.by_day} margin={{ left: 8, right: 8, top: 4, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={colors.grid} />
              <XAxis dataKey="day" tickLine={false} axisLine={false} minTickGap={28}
                tick={{ fill: colors.muted, fontSize: 10 }} tickFormatter={(d: string) => d.slice(5)} />
              <YAxis tickLine={false} axisLine={false} width={56}
                tick={{ fill: colors.muted, fontSize: 10 }} tickFormatter={(v: number) => fmtUsd(v)} />
              <ReTooltip content={<ChartTip fmt={fmtUsd} />} />
              {surfaces.map(s => (
                <Area key={s} type="monotone" dataKey={s} stackId="1" name={s}
                  stroke={sColor(s)} strokeWidth={1.5} fill={sColor(s)} fillOpacity={0.3}
                  isAnimationActive={animate} />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Section>

      {/* breakdown dims [S15][S16] */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {dims.map(dim => (
          <Section key={dim.title} title={dim.title} icon={<Layers size={13} />}>
            {dim.data.length === 0 ? (
              <p className="py-4 text-center text-xs text-muted">No data in this range.</p>
            ) : (
              <div className="space-y-2">
                {dim.data.map(b => {
                  const label = String(b[dim.key] ?? '?')
                  const max = Math.max(...dim.data.map(metricValue), 0.000001)
                  return (
                    <div key={label} className="text-xs">
                      <div className="mb-0.5 flex items-baseline justify-between gap-2">
                        <span className="truncate font-mono text-text">{label}</span>
                        <span className="shrink-0 text-muted">
                          {metricText(b)}
                        </span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-bg">
                        <div className="h-full rounded-full bg-accent" style={{ width: `${Math.max(2, metricValue(b) / max * 100)}%` }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Section>
        ))}
      </div>

      {/* plans [S17] + budget [S18] */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Section title="Provider plans" icon={<Wallet size={13} />}
          right={
            <button onClick={() => { setDraftPlans(plans.length ? plans.map(p => ({ ...p })) : [{ provider: '', plan_name: '', limit_type: 'usd', limit_value: 0, period: 'month' }]); setEditPlans(!editPlans) }}
              className="text-[11px] text-accent hover:underline">{editPlans ? 'cancel' : 'edit'}</button>
          }>
          {editPlans ? (
            <div className="space-y-2 text-xs">
              {draftPlans.map((p, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <input value={p.provider} onChange={e => setDraftPlans(d => d.map((x, j) => j === i ? { ...x, provider: e.target.value } : x))}
                    placeholder="provider" className="w-24 rounded border border-border bg-bg px-2 py-1 text-text placeholder:text-muted/60" />
                  <input value={p.plan_name} onChange={e => setDraftPlans(d => d.map((x, j) => j === i ? { ...x, plan_name: e.target.value } : x))}
                    placeholder="plan name" className="flex-1 rounded border border-border bg-bg px-2 py-1 text-text placeholder:text-muted/60" />
                  <select value={p.limit_type} onChange={e => setDraftPlans(d => d.map((x, j) => j === i ? { ...x, limit_type: e.target.value as UsagePlan['limit_type'] } : x))}
                    className="rounded border border-border bg-bg px-1 py-1 text-text">
                    <option value="usd">$</option><option value="tokens">tok</option><option value="requests">req</option>
                  </select>
                  <input type="number" value={p.limit_value || ''} onChange={e => setDraftPlans(d => d.map((x, j) => j === i ? { ...x, limit_value: parseFloat(e.target.value) || 0 } : x))}
                    placeholder="limit" className="w-20 rounded border border-border bg-bg px-2 py-1 text-text placeholder:text-muted/60" />
                  <button onClick={() => setDraftPlans(d => d.filter((_, j) => j !== i))} className="text-muted hover:text-danger"><Trash2 size={13} /></button>
                </div>
              ))}
              <div className="flex items-center justify-between pt-1">
                <button onClick={() => setDraftPlans(d => [...d, { provider: '', plan_name: '', limit_type: 'usd', limit_value: 0, period: 'month' }])}
                  className="flex items-center gap-1 text-[11px] text-accent hover:underline"><Plus size={12} /> add plan</button>
                <button onClick={savePlans}
                  className="flex items-center gap-1 rounded-md bg-accent/15 px-2.5 py-1 text-[11px] font-medium text-accent hover:bg-accent/25">
                  <Save size={12} /> Save
                </button>
              </div>
            </div>
          ) : plans.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted">
              No plans configured — add your Claude Max / OpenAI tier / OpenRouter credits to get usage-vs-limit bars.
            </p>
          ) : (
            <div className="space-y-2.5">
              {plans.map(p => {
                const pct = Math.min(100, p.pct ?? 0)
                const tone = pct >= 100 ? 'bg-danger' : pct >= 80 ? 'bg-warning' : 'bg-accent'
                const unit = p.limit_type === 'usd' ? fmtUsd(p.used ?? 0) : fmtTok(p.used ?? 0)
                const cap = p.limit_type === 'usd' ? fmtUsd(p.limit_value) : fmtTok(p.limit_value)
                return (
                  <div key={`${p.provider}-${p.plan_name}`} className="text-xs">
                    <div className="mb-0.5 flex items-baseline justify-between">
                      <span className="text-text">{p.provider} · {p.plan_name}</span>
                      <span className="text-muted">{unit} / {cap} ({p.pct ?? 0}%)</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-bg">
                      <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.max(1, pct)}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Section>

        <Section title="Monthly budget" icon={<Coins size={13} />}
          right={
            <button onClick={() => { setDraftCap(String(budget?.monthly_cap_usd || '')); setDraftPct(String(budget?.alert_pct ?? 80)); setEditBudget(!editBudget) }}
              className="text-[11px] text-accent hover:underline">{editBudget ? 'cancel' : 'edit'}</button>
          }>
          {editBudget ? (
            <div className="flex items-end gap-2 text-xs">
              <label className="flex-1">
                <span className="mb-1 block text-[10px] uppercase tracking-wider text-muted">Cap (USD / month, 0 = off)</span>
                <input type="number" value={draftCap} onChange={e => setDraftCap(e.target.value)} min={0}
                  className="w-full rounded border border-border bg-bg px-2 py-1.5 text-text" />
              </label>
              <label className="w-28">
                <span className="mb-1 block text-[10px] uppercase tracking-wider text-muted">Warn at %</span>
                <input type="number" value={draftPct} onChange={e => setDraftPct(e.target.value)} min={1} max={100}
                  className="w-full rounded border border-border bg-bg px-2 py-1.5 text-text" />
              </label>
              <button onClick={saveBudget}
                className="flex items-center gap-1 rounded-md bg-accent/15 px-2.5 py-1.5 text-[11px] font-medium text-accent hover:bg-accent/25">
                <Save size={12} /> Save
              </button>
            </div>
          ) : budget && budget.level !== 'off' ? (
            <div className="text-xs">
              <div className="mb-1 flex items-baseline justify-between">
                <span className="text-2xl font-bold text-heading">{fmtUsd(budget.spent_usd)}</span>
                <span className="text-muted">of {fmtUsd(budget.monthly_cap_usd)} · warn at {budget.alert_pct}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-bg">
                <div className={`h-full rounded-full ${
                  budget.level === 'over' ? 'bg-danger' : budget.level === 'warn' ? 'bg-warning' : 'bg-success'}`}
                  style={{ width: `${Math.min(100, budget.pct)}%` }} />
              </div>
              <p className="mt-2 text-[11px] text-muted">
                Alerts stay in-app (here + the bell inbox) — TOBI never pushes to Telegram unprompted.
              </p>
            </div>
          ) : (
            <p className="py-4 text-center text-xs text-muted">No monthly cap set — add one to get warnings before spend runs away.</p>
          )}
        </Section>
      </div>

      {/* per-call log [S20] */}
      <Section title="Call log" icon={<Search size={13} />}
        right={<span className="text-[10px] text-muted">{callTotal.toLocaleString()} attempts</span>}>
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
          <div className="relative">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" />
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search model / feature / provider"
              className="w-56 rounded-md border border-border bg-bg py-1.5 pl-7 pr-2 text-text placeholder:text-muted/60" />
          </div>
          <select value={sFilter} onChange={e => setSFilter(e.target.value)}
            className="rounded-md border border-border bg-bg px-2 py-1.5 text-text">
            <option value="">all surfaces</option>
            {surfaces.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="rounded-md border border-border bg-bg px-2 py-1.5 text-text">
            <option value="">all attempts</option>
            <option value="succeeded">succeeded</option>
            <option value="failed">failed</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-border text-[10px] uppercase tracking-wider text-muted">
                <th className="py-1.5 pr-3 font-semibold">Time</th>
                <th className="py-1.5 pr-3 font-semibold">Surface</th>
                <th className="py-1.5 pr-3 font-semibold">Requested → actual</th>
                <th className="py-1.5 pr-3 font-semibold">Attempt</th>
                <th className="py-1.5 pr-3 text-right font-semibold">Tokens</th>
                <th className="py-1.5 pr-3 text-right font-semibold">Cost</th>
                <th className="py-1.5 text-right font-semibold">Latency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {calls.length === 0 ? (
                <tr><td colSpan={7} className="py-6 text-center text-muted">No calls match.</td></tr>
              ) : calls.map(c => (
                <tr key={c.id} className="hover:bg-overlay/5">
                  <td className="whitespace-nowrap py-1.5 pr-3 font-mono text-muted">
                    {c.ts ? new Date(c.ts).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                  </td>
                  <td className="py-1.5 pr-3">
                    <span className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: sColor(c.surface) }} />
                      <span className="text-text">{c.surface}</span>
                      {c.feature && <span className="text-muted">· {c.feature}</span>}
                    </span>
                  </td>
                  <td className="max-w-[260px] py-1.5 pr-3 font-mono text-text">
                    <div className="truncate">{c.requested_model || c.actual_model || c.model}</div>
                    {c.requested_model && c.actual_model && c.requested_model !== c.actual_model && (
                      <div className="truncate text-[10px] text-warning">→ {c.actual_model}</div>
                    )}
                    {c.error_code && <div className="truncate text-[10px] text-danger">{c.error_code}</div>}
                  </td>
                  <td className="py-1.5 pr-3">
                    <span className={`rounded border px-1.5 py-0.5 text-[10px] ${
                      c.status === 'failed' ? 'border-danger/30 text-danger' : 'border-success/30 text-success'}`}>
                      {c.status} · {c.attempt}
                    </span>
                  </td>
                  <td className="py-1.5 pr-3 text-right font-mono text-muted">{fmtTok((c.prompt_tokens || 0) + (c.completion_tokens || 0))}</td>
                  <td className="py-1.5 pr-3 text-right font-mono text-text">{fmtUsd(c.cost_est || 0)}</td>
                  <td className="py-1.5 text-right font-mono text-muted">{c.latency_ms || 0}ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {calls.length < callTotal && (
          <button onClick={() => loadCalls(calls.length, true)}
            className="mt-2 w-full rounded-md border border-border py-1.5 text-[11px] text-muted transition-colors hover:border-accent/40 hover:text-text">
            Load more ({calls.length} of {callTotal.toLocaleString()})
          </button>
        )}
      </Section>
    </div>
  )
}
