import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Plus, Check, GitBranch, Sparkles, Inbox, ThumbsUp, ThumbsDown, FileCode2, ShieldAlert, Lock } from 'lucide-react'
import Logo from '../components/Logo'
import StatBar from '../components/StatBar'
import RadarChart from '../components/RadarChart'
import { AmbientField } from '../components/motion'
import {
  getAbilities, getAbilityDetail, coachAbility, getProposals, approveProposal, rejectProposal, rollbackAbility,
  getHermesSkills,
  type AbilitiesReport, type AbilityUsage, type SkillDetail, type Proposal, type HermesSkill,
} from '../api'

// ── Model ──────────────────────────────────────────────────────────
type Dim = 'autonomy' | 'reliability' | 'speed' | 'impact'
type Category = 'Communication' | 'Building' | 'Strategy' | 'Learning'

type Ability = {
  id: string
  name: string
  tagline: string
  icon: string
  category: Category
  status: 'active' | 'auto' | 'config'
  logos?: string[]
  power: Record<Dim, number>          // curated 0–100 baseline
  tokenCost: 'low' | 'medium' | 'high'
  desc: string
  trigger: string
  example: string
  levelUp: string
  limits: string
}

const DIMS: Dim[] = ['autonomy', 'reliability', 'speed', 'impact']
const DIM_LABEL: Record<Dim, string> = { autonomy: 'Autonomy', reliability: 'Reliability', speed: 'Speed', impact: 'Impact' }

const CAT: Record<Category, { color: string; glow: string; text: string }> = {
  Communication: { color: '#58a6ff', glow: 'rgba(88,166,255,0.45)', text: 'text-accent' },
  Building:      { color: '#8b5cf6', glow: 'rgba(139,92,246,0.45)', text: 'text-purple' },
  Strategy:      { color: '#d29922', glow: 'rgba(210,153,34,0.45)', text: 'text-warning' },
  Learning:      { color: '#3fb950', glow: 'rgba(63,185,80,0.45)', text: 'text-success' },
}

const ABILITIES: Ability[] = [
  // ── Communication ──
  {
    id: 'chat', name: 'Chat Assistant', tagline: 'Talks with you naturally', icon: '💬',
    category: 'Communication', status: 'active', logos: ['claude'],
    power: { autonomy: 60, reliability: 85, speed: 90, impact: 70 }, tokenCost: 'medium',
    desc: 'Understands Vietnamese and English, keeps full conversation history, and thinks alongside you across messages.',
    trigger: 'Just text it', example: '"Hey, what should I work on today?" → smart, context-aware advice',
    levelUp: 'Have longer multi-turn sessions and correct it when it drifts — coaching sharpens its replies.',
    limits: 'No long-term planning on its own; relies on Memory for persistence across restarts.',
  },
  {
    id: 'reports', name: 'Daily Reports', tagline: 'Keeps you in the loop', icon: '📧',
    category: 'Communication', status: 'auto',
    power: { autonomy: 90, reliability: 80, speed: 85, impact: 60 }, tokenCost: 'low',
    desc: 'Every morning at 08:00 GMT+7, Tobi summarises yesterday — tasks done, revenue, issues — to Telegram.',
    trigger: 'Automatic every day', example: 'Runs at 08:00 GMT+7 — check Telegram each morning',
    levelUp: 'Give feedback on what you actually want in the briefing so it prioritises the right signals.',
    limits: 'Quality depends on how much data the other engines logged that day.',
  },
  {
    id: 'telegram', name: 'Telegram Interface', tagline: 'Tobi’s ears and mouth', icon: '📨',
    category: 'Communication', status: 'active', logos: ['telegram'],
    power: { autonomy: 70, reliability: 88, speed: 95, impact: 65 }, tokenCost: 'low',
    desc: 'Polls Telegram 24/7, routes your messages to the right engine, and handles /commands.',
    trigger: 'Message the bot', example: 'Receives "write me a script" → passes to the classifier',
    levelUp: 'Becomes the single gateway once the Hermes bot consolidation lands (H16).',
    limits: 'Restricted to the owner’s user ID; if polling stops, Tobi goes quiet until restart.',
  },
  // ── Building ──
  {
    id: 'coding', name: 'Coding Agent', tagline: 'Writes and runs code for you', icon: '💻',
    category: 'Building', status: 'active', logos: ['claude'],
    power: { autonomy: 75, reliability: 70, speed: 60, impact: 90 }, tokenCost: 'high',
    desc: 'Spawns a background Claude agent that reads files, writes code, and runs bash — sandboxed.',
    trigger: 'Mention code or bugs', example: '"Fix the bug in main.py" or "write a Python CSV parser"',
    levelUp: 'Reliability climbs with every clean completed coding task — it’s live-measured from your DB.',
    limits: 'Code skills are L2 (executable) — high-risk edits route to your approval before they load.',
  },
  {
    id: 'terminal', name: 'Terminal', tagline: 'Runs commands on the box', icon: '⌨️',
    category: 'Building', status: 'active',
    power: { autonomy: 65, reliability: 72, speed: 80, impact: 75 }, tokenCost: 'medium',
    desc: 'Direct shell access for diagnostics and quick actions, inside the sandbox guardrails.',
    trigger: 'Terminal mode / agent tasks', example: '"check disk usage" → runs and reports back',
    levelUp: 'Promote from Learned to Core once it proves reliable on real tasks (needs your approval).',
    limits: 'Destructive commands are blocked by the scrubber; no access to secrets or .env.',
  },
  {
    id: 'integrations', name: 'Integrations', tagline: 'Acts across your tools', icon: '🔗',
    category: 'Building', status: 'config', logos: ['notion', 'github', 'vercel', 'supabase'],
    power: { autonomy: 55, reliability: 60, speed: 70, impact: 80 }, tokenCost: 'low',
    desc: 'Creates Notion pages, pushes to GitHub, deploys to Vercel, manages Supabase — used by the executor.',
    trigger: 'Via project tasks', example: 'Configure API keys in .env → Tobi detects and uses them',
    levelUp: 'Configure more provider keys — each one lights up a new capability (see the live count).',
    limits: 'Only as powerful as the keys present; unconfigured providers stay dark.',
  },
  {
    id: 'executor', name: 'Project Executor', tagline: 'Ships projects end-to-end', icon: '🛠️',
    category: 'Building', status: 'auto',
    power: { autonomy: 80, reliability: 68, speed: 55, impact: 88 }, tokenCost: 'high',
    desc: 'Takes approved projects and works the task list — building and shipping via the integrations.',
    trigger: 'Every 6h / on approval', example: 'Runs the execution cycle and marks tasks done',
    levelUp: 'Reliability rises as completed tasks accumulate — it’s measured from real outcomes.',
    limits: 'Bounded by integration coverage and the approval gates on high-risk steps.',
  },
  // ── Strategy ──
  {
    id: 'research', name: 'Research Engine', tagline: 'Finds opportunities', icon: '🔬',
    category: 'Strategy', status: 'active', logos: ['tavily'],
    power: { autonomy: 85, reliability: 72, speed: 50, impact: 82 }, tokenCost: 'high',
    desc: 'Searches the web via Tavily, scores niches by competition and revenue, and drafts business plans.',
    trigger: 'Ask or /research', example: '"Research profitable niches for Vietnam" or send /research',
    levelUp: 'Rate the niches it finds — your impact scores feed back into future research.',
    limits: 'Without TAVILY_API_KEY it falls back to mock data; slow by design (deep search).',
  },
  {
    id: 'ceo', name: 'CEO Strategy', tagline: 'Thinks about the big picture', icon: '🏢',
    category: 'Strategy', status: 'auto',
    power: { autonomy: 88, reliability: 75, speed: 45, impact: 85 }, tokenCost: 'high',
    desc: 'On the 1st of each month, reviews all projects, computes ROI, and updates the strategy.',
    trigger: '/ceo or monthly auto', example: 'Runs on the 1st at 09:00 GMT+7 — an automated board meeting',
    levelUp: 'Coach its strategy memos — your notes fold into the next month’s reasoning.',
    limits: 'Monthly cadence; reasoning quality depends on how much the portfolio logged.',
  },
  {
    id: 'tracker', name: 'Project Tracker', tagline: 'Monitors your portfolio', icon: '📊',
    category: 'Strategy', status: 'active',
    power: { autonomy: 70, reliability: 90, speed: 85, impact: 65 }, tokenCost: 'low',
    desc: 'Tracks every project — progress %, revenue, tasks, status — and answers status queries instantly.',
    trigger: 'Ask or /status', example: '"What’s the status of my projects?" or send /status',
    levelUp: 'Keep project data fresh; the more it tracks, the sharper its picture.',
    limits: 'Read-only view of state; it reports, it doesn’t decide.',
  },
  // ── Learning ──
  {
    id: 'learning', name: 'Self-Learning', tagline: 'Gets smarter over time', icon: '📚',
    category: 'Learning', status: 'auto',
    power: { autonomy: 82, reliability: 70, speed: 60, impact: 78 }, tokenCost: 'medium',
    desc: 'After every cycle, saves lessons (success/failure/insight) that shape future decisions.',
    trigger: 'Automatic after every cycle', example: 'Check /lessons to see what Tobi has learned',
    levelUp: 'The self-evolution engine (Hermes) will turn repeated lessons into new skills — gated on the spike.',
    limits: 'Phase 1 captures lessons; autonomous skill-generation is the gated Phase 1.5 (Hermes).',
  },
  {
    id: 'memory', name: 'Memory', tagline: 'Remembers what matters', icon: '🧠',
    category: 'Learning', status: 'active',
    power: { autonomy: 75, reliability: 85, speed: 88, impact: 80 }, tokenCost: 'low',
    desc: 'Persistent memory of conversations and facts so Tobi keeps context across restarts.',
    trigger: 'Automatic / "remember…"', example: '"Remember my startup is OneApp" → recalled later',
    levelUp: 'Becomes canonical in Hermes (H10) once the self-evolution loop lands; MC will index it.',
    limits: 'Phase 1 lives in the local DB; the Hermes memory-of-record is Phase 1.5.',
  },
]

const STATUS_BADGE: Record<string, string> = {
  active: 'bg-success/20 text-success',
  config: 'bg-warning/20 text-warning',
  auto: 'bg-accent/20 text-accent',
}
const STATUS_LABEL: Record<string, string> = { active: '● Active', config: '○ Needs config', auto: '⟳ Auto' }
const TOKEN_PIPS: Record<string, number> = { low: 1, medium: 2, high: 3 }

const RANKS: { min: number; title: string }[] = [
  { min: 90, title: 'Jarvis' },
  { min: 70, title: 'Apprentice Jarvis' },
  { min: 55, title: 'Operator' },
  { min: 40, title: 'Apprentice' },
  { min: 20, title: 'Awakening' },
  { min: 0, title: 'Dormant' },
]

// ── Derived helpers ────────────────────────────────────────────────
const clamp = (n: number) => Math.max(0, Math.min(100, n))
const overall = (p: Record<Dim, number>) => Math.round((p.autonomy + p.reliability + p.speed + p.impact) / 4)
const level = (score: number) => Math.max(1, Math.min(5, Math.ceil(score / 20)))
const rankOf = (agg: number) => RANKS.find(r => agg >= r.min)!.title

/** Blend live success_rate into the curated Reliability dimension (D44). */
function effectivePower(a: Ability, usage?: AbilityUsage): Record<Dim, number> {
  const p = { ...a.power }
  if (usage && typeof usage.success_rate === 'number') {
    p.reliability = clamp(Math.round((p.reliability + usage.success_rate * 100) / 2))
  }
  return p
}

function TokenMeter({ cost }: { cost: Ability['tokenCost'] }) {
  const pips = TOKEN_PIPS[cost]
  const color = cost === 'high' ? 'bg-danger' : cost === 'medium' ? 'bg-warning' : 'bg-success'
  return (
    <span className="inline-flex items-center gap-1" title={`Token cost: ${cost}`}>
      {[1, 2, 3].map(i => (
        <span key={i} className={`h-1.5 w-2.5 rounded-sm ${i <= pips ? color : 'bg-border'}`} />
      ))}
      <span className="ml-1 text-[10px] uppercase tracking-wide text-muted">{cost}</span>
    </span>
  )
}

function LvBadge({ lv }: { lv: number }) {
  return (
    <span className="shrink-0 whitespace-nowrap rounded border border-purple/40 bg-purple/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-purple">
      Lv {lv}
    </span>
  )
}

// ── Page ───────────────────────────────────────────────────────────
export default function Ability() {
  const [report, setReport] = useState<AbilitiesReport | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<SkillDetail | null>(null)
  const [compare, setCompare] = useState<string[]>([])
  const [compareMode, setCompareMode] = useState<'radar' | 'bars'>('radar')
  const [coachNote, setCoachNote] = useState('')
  const [coachBusy, setCoachBusy] = useState(false)
  const [inboxOpen, setInboxOpen] = useState(false)
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [hermes, setHermes] = useState<HermesSkill[]>([])   // read-only repo skills (#14)

  const usage = (id: string): AbilityUsage | undefined => report?.abilities[id]

  // Live poll (45s) — non-blocking; page renders curated values regardless.
  useEffect(() => {
    const load = () => getAbilities().then(setReport).catch(() => {})
    load()
    const t = setInterval(load, 45000)
    return () => clearInterval(t)
  }, [])

  const loadProposals = () => getProposals('pending').then(r => setProposals(r.items)).catch(() => {})
  useEffect(() => { loadProposals() }, [])

  // Hermes repo skills are static files — one quiet fetch, no polling needed (#14).
  useEffect(() => { getHermesSkills().then(r => setHermes(r.items)).catch(() => setHermes([])) }, [])

  // Fetch version history when a skill is opened.
  useEffect(() => {
    if (!selected) { setDetail(null); return }
    setDetail(null)
    getAbilityDetail(selected).then(setDetail).catch(() => {})
  }, [selected])

  const enriched = useMemo(() =>
    ABILITIES.map(a => {
      const eff = effectivePower(a, usage(a.id))
      return { ...a, eff, overall: overall(eff) }
    }), [report]) // eslint-disable-line react-hooks/exhaustive-deps

  const aggregate = useMemo(
    () => Math.round(enriched.reduce((s, a) => s + a.overall, 0) / enriched.length),
    [enriched],
  )
  const counts = useMemo(() => ({
    active: ABILITIES.filter(a => a.status === 'active').length,
    auto: ABILITIES.filter(a => a.status === 'auto').length,
    config: ABILITIES.filter(a => a.status === 'config').length,
  }), [])

  const byCategory = useMemo(() => {
    const groups: Record<Category, typeof enriched> = { Communication: [], Building: [], Strategy: [], Learning: [] }
    enriched.forEach(a => groups[a.category].push(a))
    return groups
  }, [enriched])

  const sel = enriched.find(a => a.id === selected) || null

  const toggleCompare = (id: string) => {
    setCompare(prev => prev.includes(id) ? prev.filter(x => x !== id) : prev.length >= 3 ? prev : [...prev, id])
  }

  const compareSeries = compare
    .map(id => enriched.find(a => a.id === id))
    .filter(Boolean)
    .map(a => ({ label: a!.name, color: CAT[a!.category].color, values: DIMS.map(d => a!.eff[d]) }))

  const submitCoach = async () => {
    if (!selected || !coachNote.trim()) return
    setCoachBusy(true)
    try {
      await coachAbility(selected, coachNote.trim())
      setCoachNote('')
      loadProposals()
    } catch { /* ignore */ } finally { setCoachBusy(false) }
  }

  const resolve = async (id: number, action: 'approve' | 'reject') => {
    try {
      await (action === 'approve' ? approveProposal(id) : rejectProposal(id))
      loadProposals()
      if (selected) getAbilityDetail(selected).then(setDetail).catch(() => {})
    } catch { /* ignore */ }
  }

  const rollback = async (version: number) => {
    if (!selected) return
    try {
      await rollbackAbility(selected, version)
      getAbilityDetail(selected).then(setDetail).catch(() => {})
    } catch { /* ignore */ }
  }

  return (
    <div className="relative flex h-full gap-6 p-6">
      <AmbientField tone="rgb(var(--purple))" />
      <div className="flex-1 overflow-y-auto">
        {/* Header */}
        <div className="mb-5 flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-heading">Ability</h1>
            <p className="mt-1 text-xs text-muted">Tobi&apos;s capabilities as an RPG character sheet — power, level up, and compare.</p>
          </div>
          <button
            onClick={() => { setInboxOpen(true); loadProposals() }}
            className="relative flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-xs font-medium text-text transition-colors hover:border-overlay/20"
          >
            <Inbox size={14} /> Evolution
            {proposals.length > 0 && (
              <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-purple px-1 text-[10px] font-bold text-white">
                {proposals.length}
              </span>
            )}
          </button>
        </div>

        {/* Hero — Tobi Power Level */}
        <motion.div
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
          className="mb-6 rounded-xl border border-purple/30 bg-surface/60 p-5"
          style={{ boxShadow: '0 0 30px rgba(139,92,246,0.12)' }}
        >
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-purple" />
              <span className="text-xs font-bold uppercase tracking-widest text-purple">Tobi Power Level</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="whitespace-nowrap rounded-full border border-purple/40 bg-purple/10 px-3 py-1 text-sm font-bold text-purple">
                {rankOf(aggregate)}
              </span>
              <LvBadge lv={level(aggregate)} />
            </div>
          </div>
          <StatBar value={aggregate} size="lg" />
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
            <span>{ABILITIES.length} abilities</span>
            <span className="text-success">● {counts.active} active</span>
            <span className="text-accent">⟳ {counts.auto} auto</span>
            <span className="text-warning">○ {counts.config} needs config</span>
            {hermes.length > 0 && <span className="text-purple">◆ {hermes.length} Hermes skill{hermes.length > 1 ? 's' : ''}</span>}
          </div>
        </motion.div>

        {/* Compare */}
        <div className="mb-6 rounded-xl border border-border bg-surface/40 p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-widest text-muted">Compare (pick 2–3)</span>
            {compare.length >= 2 && (
              <div className="flex overflow-hidden rounded-md border border-border text-xs">
                {(['radar', 'bars'] as const).map(m => (
                  <button
                    key={m} onClick={() => setCompareMode(m)}
                    className={`px-3 py-1 capitalize transition-colors ${compareMode === m ? 'bg-purple/20 text-purple' : 'text-muted hover:text-text'}`}
                  >{m}</button>
                ))}
              </div>
            )}
          </div>
          <div className="mb-3 flex flex-wrap gap-2">
            {enriched.map(a => {
              const on = compare.includes(a.id)
              return (
                <button
                  key={a.id} onClick={() => toggleCompare(a.id)}
                  className={`flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-xs transition-colors ${on ? 'border-purple bg-purple/15 text-purple' : 'border-border text-muted hover:text-text'}`}
                >
                  <span>{a.icon}</span>{a.name}
                </button>
              )
            })}
          </div>
          {compare.length < 2 ? (
            <div className="py-6 text-center text-xs text-muted">Select 2–3 abilities to overlay their power.</div>
          ) : compareMode === 'radar' ? (
            <div className="flex justify-center py-2">
              <RadarChart axes={DIMS.map(d => DIM_LABEL[d])} series={compareSeries} size={300} />
            </div>
          ) : (
            <div className="space-y-4 py-2">
              {DIMS.map(d => (
                <div key={d}>
                  <div className="mb-1.5 text-xs font-semibold text-text">{DIM_LABEL[d]}</div>
                  <div className="space-y-1.5">
                    {compare.map(id => {
                      const a = enriched.find(x => x.id === id)!
                      return (
                        <div key={id} className="flex items-center gap-2">
                          <span className="w-28 shrink-0 truncate text-[11px] text-muted">{a.name}</span>
                          <StatBar value={a.eff[d]} from={CAT[a.category].color} to={CAT[a.category].color} glow={CAT[a.category].glow} className="flex-1" />
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Categorized grid */}
        {(Object.keys(byCategory) as Category[]).map(cat => (
          <div key={cat} className="mb-6">
            <div className={`mb-3 text-xs font-bold uppercase tracking-widest ${CAT[cat].text}`}>{cat}</div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {byCategory[cat].map(a => {
                const isSel = selected === a.id
                const onCompare = compare.includes(a.id)
                return (
                  <motion.div
                    key={a.id} layout
                    whileHover={{ y: -2 }}
                    onClick={() => setSelected(a.id)}
                    className={`cursor-pointer rounded-lg border-2 bg-surface p-4 transition-colors ${isSel ? 'border-purple' : 'border-border hover:border-overlay/20'}`}
                  >
                    <div className="mb-2 flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl">{a.icon}</span>
                        <div>
                          <div className="text-sm font-semibold text-heading">{a.name}</div>
                          <div className="text-[11px] text-muted">{a.tagline}</div>
                        </div>
                      </div>
                      <LvBadge lv={level(a.overall)} />
                    </div>
                    <StatBar value={a.overall} from={CAT[a.category].color} to={CAT[a.category].color} glow={CAT[a.category].glow} className="mb-2" showValue={false} />
                    <div className="mb-3 grid grid-cols-4 gap-1">
                      {DIMS.map(d => (
                        <div key={d} className="text-center">
                          <div className="font-mono text-xs font-bold text-text">{a.eff[d]}</div>
                          <div className="text-[9px] uppercase text-muted">{DIM_LABEL[d].slice(0, 3)}</div>
                        </div>
                      ))}
                    </div>
                    <div className="flex items-center justify-between">
                      <span className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_BADGE[a.status]}`}>{STATUS_LABEL[a.status]}</span>
                      <div className="flex items-center gap-2">
                        {a.logos && <div className="flex gap-1">{a.logos.map(l => <Logo key={l} name={l} size={13} />)}</div>}
                        <button
                          onClick={(e) => { e.stopPropagation(); toggleCompare(a.id) }}
                          className={`flex items-center gap-0.5 rounded border px-1.5 py-0.5 text-[10px] transition-colors ${onCompare ? 'border-purple text-purple' : 'border-border text-muted hover:text-text'}`}
                        >
                          {onCompare ? <Check size={10} /> : <Plus size={10} />} compare
                        </button>
                      </div>
                    </div>
                  </motion.div>
                )
              })}
            </div>
          </div>
        ))}

        {/* ── Hermes skills (read-only repo source · #14) ── */}
        {hermes.length > 0 && (
          <div className="mb-6">
            <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-purple">
              <FileCode2 size={13} /> Hermes Skills
              <span className="rounded-full border border-purple/30 bg-purple/10 px-1.5 py-0.5 text-[9px] font-medium normal-case tracking-normal text-purple">read-only source</span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {hermes.map(s => (
                <div key={s.id} className="rounded-lg border border-border bg-surface p-4">
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-purple/10 text-purple"><FileCode2 size={16} /></span>
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-heading" title={s.name}>{s.name}</div>
                        <div className="truncate font-mono text-[10px] text-muted" title={s.file_path}>{s.file_path}</div>
                      </div>
                    </div>
                    <span className="shrink-0 whitespace-nowrap rounded border border-purple/40 bg-purple/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-purple">v{s.version}</span>
                  </div>
                  {s.description && <p className="mb-3 line-clamp-3 text-xs leading-relaxed text-muted">{s.description}</p>}
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-medium text-success"><Check size={10} /> {s.status}</span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-medium text-warning"><ShieldAlert size={10} /> {s.risk_tier.replace(/_/g, ' ')}</span>
                    <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[10px] text-muted"><Lock size={10} /> execution off</span>
                    {s.parse_warning && <span className="rounded-full bg-danger/15 px-2 py-0.5 text-[10px] text-danger">parse warning</span>}
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[10px] text-muted">
                    <span>Hermes repo file</span>
                    {s.last_modified && <span title={s.last_modified}>{s.last_modified.slice(0, 10)}</span>}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-2 text-[11px] text-muted">
              Discovered from <span className="font-mono">hermes_skills/</span> — read-only in v1. Execution stays behind Conductor human review (no autonomous runs).
            </div>
          </div>
        )}
      </div>

      {/* Detail panel */}
      <AnimatePresence mode="wait">
        {sel ? (
          <motion.div
            key={sel.id}
            initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 40 }}
            transition={{ duration: 0.22 }}
            className="sticky top-0 h-fit max-h-[calc(100vh-3rem)] w-96 flex-shrink-0 overflow-y-auto rounded-lg border border-border bg-surface p-5"
          >
            <div className="mb-4 flex items-start justify-between">
              <div className="flex items-center gap-3">
                <span className="text-3xl">{sel.icon}</span>
                <div>
                  <div className="font-bold text-heading">{sel.name}</div>
                  <div className="mt-0.5 flex items-center gap-2">
                    <span className={`text-[11px] ${CAT[sel.category].text}`}>{sel.category}</span>
                    <LvBadge lv={level(sel.overall)} />
                  </div>
                </div>
              </div>
              <button onClick={() => setSelected(null)} className="text-muted transition-colors hover:text-text"><X size={16} /></button>
            </div>

            <StatBar value={sel.overall} size="lg" className="mb-4" label="Overall power" />

            <div className="mb-4 space-y-2">
              {DIMS.map(d => (
                <div key={d}>
                  <div className="mb-0.5 flex justify-between text-[11px]"><span className="text-muted">{DIM_LABEL[d]}</span><span className="font-mono text-text">{sel.eff[d]}</span></div>
                  <StatBar value={sel.eff[d]} from={CAT[sel.category].color} to={CAT[sel.category].color} glow={CAT[sel.category].glow} showValue={false} />
                </div>
              ))}
            </div>

            <div className="mb-4 flex items-center justify-between rounded border border-border bg-bg p-2.5">
              <span className="text-[11px] uppercase tracking-wider text-muted">Token cost</span>
              <TokenMeter cost={sel.tokenCost} />
            </div>

            <p className="mb-3 text-sm leading-relaxed text-text">{sel.desc}</p>

            <div className="mb-3 rounded border border-border bg-bg p-3">
              <div className="mb-1 text-[11px] uppercase tracking-wider text-muted">How to trigger</div>
              <div className="text-sm font-medium text-accent">{sel.trigger}</div>
              <div className="mt-2 text-[11px] uppercase tracking-wider text-muted">Example</div>
              <div className="text-xs italic leading-relaxed text-text">&quot;{sel.example}&quot;</div>
            </div>

            <div className="mb-3 rounded border border-accent/30 bg-accent/10 p-3">
              <div className="mb-1 text-[11px] uppercase tracking-wider text-accent">How to level up</div>
              <div className="text-xs leading-relaxed text-text">{sel.levelUp}</div>
            </div>

            <div className="mb-3 rounded border border-warning/30 bg-warning/10 p-3">
              <div className="mb-1 text-[11px] uppercase tracking-wider text-warning">Limitations &amp; guardrails</div>
              <div className="text-xs leading-relaxed text-text">{sel.limits}</div>
            </div>

            {/* Live usage */}
            {usage(sel.id) && (
              <div className="mb-3 rounded border border-border bg-bg p-3">
                <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">Live usage</div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text">
                  {usage(sel.id)!.count != null && <span>Used <b className="font-mono">{usage(sel.id)!.count}</b>×</span>}
                  {usage(sel.id)!.last_active && <span>Last <b>{usage(sel.id)!.last_active}</b></span>}
                  {usage(sel.id)!.success_rate != null && <span>Success <b className="font-mono">{Math.round(usage(sel.id)!.success_rate! * 100)}%</b></span>}
                  {usage(sel.id)!.configured != null && <span><b className="font-mono">{usage(sel.id)!.configured}/{usage(sel.id)!.of}</b> configured</span>}
                  {usage(sel.id)!.avg_impact != null && <span>Avg impact <b className="font-mono">{usage(sel.id)!.avg_impact}</b></span>}
                </div>
              </div>
            )}

            {/* Version history (D13/D54) */}
            <div className="mb-3">
              <div className="mb-1.5 flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted">
                <GitBranch size={12} /> Version history
              </div>
              {detail?.versions?.length ? (
                <div className="space-y-1.5">
                  {detail.versions.map(v => {
                    let prov = ''
                    try { const p = JSON.parse(v.provenance_json || '{}'); prov = [p.actor, p.trigger].filter(Boolean).join(' · ') } catch { /* ignore */ }
                    return (
                      <div key={v.id} className="rounded border border-border bg-bg p-2">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs font-bold text-purple">
                            v{v.version}{v.version === detail.skill.version && <span className="ml-1 text-[9px] uppercase text-success">current</span>}
                          </span>
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] text-muted">{v.created_at?.slice(0, 16)}</span>
                            {v.version !== detail.skill.version && (
                              <button onClick={() => rollback(v.version)} className="text-[10px] text-accent hover:underline">rollback</button>
                            )}
                          </div>
                        </div>
                        {v.diff_summary && <div className="mt-0.5 text-[11px] text-text">{v.diff_summary}</div>}
                        {prov && <div className="mt-0.5 text-[10px] text-muted">{prov}</div>}
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="text-[11px] text-muted">v1 baseline — no evolutions yet.</div>
              )}
            </div>

            {/* Coach (D8/H11) */}
            <div className="rounded border border-purple/30 bg-purple/5 p-3">
              <div className="mb-1.5 text-[11px] uppercase tracking-wider text-purple">Coach this ability</div>
              <textarea
                value={coachNote} onChange={e => setCoachNote(e.target.value)}
                placeholder="e.g. always run the build before claiming done…"
                className="mb-2 h-16 w-full resize-none rounded border border-border bg-bg p-2 text-xs text-text outline-none focus:border-purple/60"
              />
              <button
                onClick={submitCoach} disabled={coachBusy || !coachNote.trim()}
                className="w-full rounded bg-purple/20 py-1.5 text-xs font-medium text-purple transition-colors hover:bg-purple/30 disabled:opacity-40"
              >
                {coachBusy ? 'Queuing…' : 'Queue coaching proposal'}
              </button>
              <div className="mt-1.5 text-[10px] leading-relaxed text-muted">Coaching is queued for your approval in the Evolution inbox — no autonomous change.</div>
            </div>
          </motion.div>
        ) : (
          <div className="hidden w-96 flex-shrink-0 items-center justify-center xl:flex">
            <div className="text-center text-muted">
              <div className="mb-3 text-4xl">🎮</div>
              <div className="text-sm">Click an ability to open its character sheet</div>
            </div>
          </div>
        )}
      </AnimatePresence>

      {/* Evolution inbox */}
      <AnimatePresence>
        {inboxOpen && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/60" onClick={() => setInboxOpen(false)} />
            <motion.div
              initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 40 }}
              transition={{ duration: 0.22 }}
              className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-border bg-surface p-5 shadow-2xl"
            >
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2 font-bold text-heading"><Inbox size={16} /> Evolution inbox</div>
                <button onClick={() => setInboxOpen(false)} className="text-muted hover:text-text"><X size={16} /></button>
              </div>
              <div className="mb-3 text-xs text-muted">Pending proposals (D13/D48). Approving writes a new version; high-risk skills always land here.</div>
              <div className="flex-1 space-y-2 overflow-y-auto">
                {proposals.length === 0 ? (
                  <div className="py-10 text-center text-sm text-muted">Nothing pending. Coach an ability to queue one.</div>
                ) : proposals.map(p => (
                  <div key={p.id} className="rounded-lg border border-border bg-bg p-3">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-sm font-semibold text-heading">{p.title || `${p.kind} ${p.skill_id}`}</span>
                      <span className={`shrink-0 whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${p.risk_tier === 'high' ? 'bg-danger/20 text-danger' : 'bg-success/20 text-success'}`}>{p.risk_tier}</span>
                    </div>
                    <div className="mb-2 flex items-center gap-2 text-[11px] text-muted">
                      <span className="whitespace-nowrap rounded border border-border px-1.5 py-0.5 uppercase">{p.kind}</span>
                      {p.skill_id && <span>{p.skill_id}</span>}
                      <span>{p.created_at?.slice(0, 16)}</span>
                    </div>
                    {p.rationale && <p className="mb-2 text-xs leading-relaxed text-text">{p.rationale}</p>}
                    <div className="flex gap-2">
                      <button onClick={() => resolve(p.id, 'approve')} className="flex flex-1 items-center justify-center gap-1 rounded bg-success/20 py-1.5 text-xs font-medium text-success hover:bg-success/30">
                        <ThumbsUp size={12} /> Approve
                      </button>
                      <button onClick={() => resolve(p.id, 'reject')} className="flex flex-1 items-center justify-center gap-1 rounded bg-danger/20 py-1.5 text-xs font-medium text-danger hover:bg-danger/30">
                        <ThumbsDown size={12} /> Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}
