import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  CheckCircle2, XCircle, Lock, Brain, Cpu, Wifi,
  ChevronDown, ChevronUp, X, Clock, Zap, TrendingUp, Sparkles, Loader2,
} from 'lucide-react'
import { getEvolution, reflectNow, type EvolutionReport, type TierData, type TierAbility } from '../api'
import { useSound } from '../hooks/useSound'
import { useToast } from '../context/ToastProvider'
import { useReducedMotionPref } from '../context/MotionProvider'
import PageLoader from '../components/PageLoader'
import TierEmblem from '../components/TierEmblem'

// ── Color palette per tier ───────────────────────────────────────────────────

type TierColors = {
  hex: string
  text: string
  border: string
  glow: string
  bg: string
  gradient: string
  badgeClass?: string
  nameClass?: string
  animated?: boolean
}

const TIER_COLORS: Record<string, TierColors> = {
  gray: {
    hex: '#9CA3AF',
    text: 'color: #9CA3AF',
    border: 'border-color: rgba(156,163,175,0.35)',
    glow: 'box-shadow: 0 0 18px rgba(156,163,175,0.18)',
    bg: 'background: rgba(156,163,175,0.06)',
    gradient: 'linear-gradient(135deg,#9CA3AF,#6B7280)',
  },
  bronze: {
    hex: '#CD7F32',
    text: 'color: #CD7F32',
    border: 'border-color: rgba(205,127,50,0.45)',
    glow: 'box-shadow: 0 0 22px rgba(205,127,50,0.22)',
    bg: 'background: rgba(205,127,50,0.07)',
    gradient: 'linear-gradient(135deg,#CD7F32,#8B4513)',
  },
  gold: {
    hex: '#FFD700',
    text: 'color: #FFD700',
    border: 'border-color: rgba(255,215,0,0.45)',
    glow: 'box-shadow: 0 0 28px rgba(255,215,0,0.28)',
    bg: 'background: rgba(255,215,0,0.07)',
    gradient: 'linear-gradient(135deg,#FFD700,#FFA500)',
  },
  green: {
    hex: '#10b981',
    text: 'color: #10b981',
    border: 'border-color: rgba(16,185,129,0.45)',
    glow: 'box-shadow: 0 0 28px rgba(16,185,129,0.28)',
    bg: 'background: rgba(16,185,129,0.07)',
    gradient: 'linear-gradient(135deg,#10b981,#059669)',
  },
  neon_blue: {
    hex: '#22d3ee',
    text: 'color: #22d3ee',
    border: 'border-color: rgba(34,211,238,0.45)',
    glow: 'box-shadow: 0 0 34px rgba(34,211,238,0.3)',
    bg: 'background: rgba(34,211,238,0.07)',
    gradient: 'linear-gradient(135deg,#22d3ee,#3b82f6)',
  },
  gold_white: {
    hex: '#fef9c3',
    text: 'color: #fef9c3',
    border: 'border-color: rgba(254,249,195,0.55)',
    glow: 'box-shadow: 0 0 44px rgba(255,215,0,0.4), 0 0 90px rgba(255,255,255,0.08)',
    bg: 'background: rgba(254,249,195,0.06)',
    gradient: 'linear-gradient(135deg,#FFD700 0%,#ffffff 50%,#FFD700 100%)',
  },
  aurora: {
    hex: '#a78bfa',
    text: 'color: #a78bfa',
    border: 'border-color: rgba(167,139,250,0.45)',
    glow: 'box-shadow: 0 0 40px rgba(167,139,250,0.3), 0 0 70px rgba(34,211,238,0.15)',
    bg: 'background: rgba(167,139,250,0.06)',
    gradient: 'linear-gradient(135deg,#a78bfa,#22d3ee,#f472b6)',
    nameClass: 'aurora-text',
    animated: true,
  },
  sovereign: {
    hex: '#ffffff',
    text: 'color: #ffffff',
    border: 'border-color: rgba(255,255,255,0.5)',
    glow: 'box-shadow: 0 0 60px rgba(255,255,255,0.25), 0 0 120px rgba(255,215,0,0.15), 0 0 200px rgba(167,139,250,0.08)',
    bg: 'background: rgba(255,255,255,0.04)',
    gradient: 'linear-gradient(135deg,#FFD700,#ffffff,#22d3ee,#a78bfa,#f472b6,#FFD700)',
    nameClass: 'sovereign-text',
    animated: true,
  },
}

const PILLAR_META = {
  understand: { label: 'Understand Me', icon: Brain },
  control:    { label: 'PC Control',    icon: Cpu },
  presence:   { label: 'Always-On Presence', icon: Wifi },
}

const EFFORT_STYLE: Record<string, string> = {
  done:    'bg-green-500/15 text-green-400',
  '1 day': 'bg-blue-500/15 text-blue-300',
  '3 days':'bg-blue-500/15 text-blue-300',
  '1 week':'bg-yellow-500/15 text-yellow-300',
  '1 month':'bg-orange-500/15 text-orange-300',
  '???':   'bg-purple-500/15 text-purple-300',
}

// ── Sub-components ───────────────────────────────────────────────────────────

function ProgressRing({ pct, size = 90, stroke = 6, color = '#58a6ff' }: {
  pct: number; size?: number; stroke?: number; color?: string
}) {
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const dash = (pct / 100) * circ
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke="rgba(255,255,255,0.07)" strokeWidth={stroke} />
      <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={color} strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={circ}
        initial={{ strokeDashoffset: circ }}
        animate={{ strokeDashoffset: circ - dash }}
        transition={{ duration: 1.2, ease: 'easeOut' }}
      />
    </svg>
  )
}

function AbilityRow({ ab, locked, onClick }: { ab: TierAbility; locked: boolean; onClick: () => void }) {
  const isActive = ab.status === 'active'
  return (
    <button onClick={onClick}
      className="flex w-full items-start gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-white/5 active:bg-white/10">
      <span className="mt-0.5 shrink-0">
        {locked        ? <Lock size={14} className="text-muted/40" /> :
         isActive      ? <CheckCircle2 size={14} className="text-green-400" /> :
                         <XCircle size={14} className="text-red-400/60" />}
      </span>
      <span className={`flex-1 text-xs leading-snug ${locked ? 'text-muted/40' : isActive ? 'text-text' : 'text-muted'}`}>
        {ab.name}
      </span>
      {!isActive && ab.effort !== 'done' && (
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${EFFORT_STYLE[ab.effort] ?? 'bg-muted/10 text-muted'}`}>
          {ab.effort}
        </span>
      )}
    </button>
  )
}

function TierCard({
  tier, isCurrent, isCompleted, isLocked, onAbilityClick,
}: {
  tier: TierData
  isCurrent: boolean
  isCompleted: boolean
  isLocked: boolean
  onAbilityClick: (ab: TierAbility, tier: TierData) => void
}) {
  const [open, setOpen] = useState(isCurrent)
  const c = TIER_COLORS[tier.color_key] ?? TIER_COLORS.gray

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: tier.id * 0.06 }}
      className={`rounded-xl border transition-all ${isCurrent ? 'tier-pulse' : ''}`}
      style={{
        ...(Object.fromEntries(
          (c.border + ';' + c.bg).split(';').filter(Boolean).map(s => {
            const [k, v] = s.split(':').map(x => x.trim())
            return [k.replace(/-([a-z])/g, (_, l) => l.toUpperCase()), v]
          })
        )),
        opacity: isLocked ? 0.45 : 1,
      }}
    >
      {/* Header */}
      <button className="flex w-full items-center gap-3 px-4 py-3"
        onClick={() => !isLocked && setOpen(o => !o)}>

        {/* Tier badge */}
        <TierEmblem tier={tier.id} colorKey={tier.color_key} size={40}
          state={isCurrent ? 'current' : isLocked ? 'locked' : 'normal'} />

        <div className="flex-1 text-left">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-bold tracking-widest ${c.nameClass ?? ''}`}
              style={c.nameClass ? undefined : { color: c.hex }}>
              {tier.name}
            </span>
            {isCompleted && (
              <span className="rounded border border-green-500/30 bg-green-500/10 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-green-400">
                COMPLETE
              </span>
            )}
            {isCurrent && !isCompleted && (
              <span className="rounded border border-accent/30 bg-accent/10 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-accent">
                ACTIVE
              </span>
            )}
            {isLocked && <Lock size={12} className="text-muted/50" />}
          </div>
          <p className="mt-0.5 text-[11px] text-muted leading-tight">{tier.tagline}</p>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1">
          <div className="text-xs font-semibold" style={{ color: c.hex }}>
            {tier.active_count}/{tier.total_count}
          </div>
          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-white/10">
            <motion.div className="h-full rounded-full"
              style={{ background: c.gradient }}
              initial={{ width: 0 }}
              animate={{ width: `${tier.progress_pct}%` }}
              transition={{ duration: 0.8, ease: 'easeOut', delay: tier.id * 0.06 + 0.3 }}
            />
          </div>
          {!isLocked && (
            <span className="text-muted">{open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</span>
          )}
        </div>
      </button>

      {/* Ability list */}
      <AnimatePresence initial={false}>
        {open && !isLocked && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22 }}
            className="overflow-hidden">
            <div className="border-t border-white/5 px-3 pb-3 pt-2 space-y-3">
              {(Object.entries(tier.pillars) as [keyof typeof PILLAR_META, TierAbility[]][]).map(([key, abilities]) => {
                const meta = PILLAR_META[key]
                const Icon = meta.icon
                return (
                  <div key={key}>
                    <div className="mb-1 flex items-center gap-1.5 px-2">
                      <Icon size={11} className="text-muted" />
                      <span className="text-[10px] font-semibold uppercase tracking-widest text-muted">
                        {meta.label}
                      </span>
                    </div>
                    {abilities.map(ab => (
                      <AbilityRow key={ab.id} ab={ab} locked={isLocked}
                        onClick={() => onAbilityClick(ab, tier)} />
                    ))}
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function AbilityDrawer({ ab, tier, onClose, onReflected }: {
  ab: TierAbility; tier: TierData; onClose: () => void; onReflected: () => void
}) {
  const c = TIER_COLORS[tier.color_key] ?? TIER_COLORS.gray
  const isActive = ab.status === 'active'
  const [reflecting, setReflecting] = useState(false)
  const [reflectErr, setReflectErr] = useState<string | null>(null)
  const [reflected, setReflected] = useState<string | null>(null)

  const runReflect = async () => {
    setReflecting(true)
    setReflectErr(null)
    try {
      const r = await reflectNow()
      setReflected(r.lesson.content)
      // Let the user read the lesson, then refresh the tier data so the
      // ability flips to ACTIVE (and Genesis may complete).
      setTimeout(onReflected, 1600)
    } catch (e: unknown) {
      setReflectErr(e instanceof Error ? e.message : String(e))
    } finally {
      setReflecting(false)
    }
  }

  return (
    <motion.div initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
      transition={{ type: 'spring', stiffness: 340, damping: 32 }}
      className="fixed right-0 top-0 z-50 flex h-full w-full flex-col border-l border-border bg-surface shadow-2xl sm:w-96">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <TierEmblem tier={tier.id} colorKey={tier.color_key} size={24} />
          <span className="text-xs text-muted">{tier.name}</span>
        </div>
        <button onClick={onClose} className="rounded-md p-1 text-muted hover:text-text"><X size={16} /></button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {/* Status badge */}
        <div className="flex items-center gap-2">
          {isActive
            ? <span className="flex items-center gap-1.5 rounded-full bg-green-500/15 px-3 py-1 text-xs font-semibold text-green-400"><CheckCircle2 size={12} /> ACTIVE</span>
            : <span className="flex items-center gap-1.5 rounded-full bg-red-500/15 px-3 py-1 text-xs font-semibold text-red-400"><XCircle size={12} /> INACTIVE</span>
          }
          {ab.effort !== 'done' && (
            <span className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${EFFORT_STYLE[ab.effort] ?? ''}`}>
              <Clock size={11} /> {ab.effort}
            </span>
          )}
        </div>

        {/* Ability name */}
        <h2 className="text-base font-bold leading-snug text-heading">{ab.name}</h2>

        {/* Description */}
        <p className="text-sm text-muted leading-relaxed">{ab.description}</p>

        {/* How to unlock (if inactive) */}
        {!isActive && ab.how_to_unlock && (
          <div className="rounded-lg border border-border bg-bg/50 p-3 space-y-1.5">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-accent">
              <Zap size={11} /> How to unlock
            </div>
            <p className="text-xs text-muted leading-relaxed">{ab.how_to_unlock}</p>
          </div>
        )}

        {!isActive && !ab.how_to_unlock && (
          <div className="rounded-lg border border-border bg-bg/50 p-3">
            <p className="text-xs text-muted italic">This capability unlocks as the cumulative result of earlier tiers. Build the prerequisite tiers first.</p>
          </div>
        )}

        {/* One-click activator for the self-reflection store */}
        {!isActive && ab.id === 'lessons_store' && (
          <div className="space-y-2">
            <button onClick={runReflect} disabled={reflecting}
              className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-sm font-semibold text-black transition-opacity hover:opacity-90 disabled:opacity-60"
              style={{ background: c.gradient }}>
              {reflecting
                ? <><Loader2 size={15} className="animate-spin" /> Reflecting…</>
                : <><Sparkles size={15} /> Reflect now</>}
            </button>
            {reflectErr && (
              <p className="text-xs text-red-400">Reflection failed: {reflectErr}</p>
            )}
            {reflected && (
              <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-3">
                <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-green-400">
                  <CheckCircle2 size={11} /> Lesson #1 written
                </div>
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted">{reflected}</p>
              </div>
            )}
          </div>
        )}

        {/* Pillar tag */}
        <div className="pt-2 border-t border-border/50">
          {(Object.entries(PILLAR_META) as [keyof typeof PILLAR_META, typeof PILLAR_META[keyof typeof PILLAR_META]][]).map(([key, meta]) => {
            const hasAbility = Object.entries(tier.pillars).some(([k, abs]) => k === key && abs.some(a => a.id === ab.id))
            if (!hasAbility) return null
            const Icon = meta.icon
            return (
              <div key={key} className="flex items-center gap-1.5 text-xs text-muted">
                <Icon size={12} /> {meta.label}
              </div>
            )
          })}
        </div>
      </div>
    </motion.div>
  )
}

function TierUnlockOverlay({ tierId, tierName, colorKey, onDone }: {
  tierId: number; tierName: string; colorKey: string; onDone: () => void
}) {
  const c = TIER_COLORS[colorKey] ?? TIER_COLORS.gray
  const reduced = useReducedMotionPref() !== 'full'
  useEffect(() => {
    const t = setTimeout(onDone, 4000)
    return () => clearTimeout(t)
  }, [onDone])

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onDone}>
      <div className="relative flex flex-col items-center gap-4 select-none">
        {/* Refined glow sweep across the completing tier node (premium, not fireworks) */}
        {!reduced && (
          <motion.span aria-hidden className="pointer-events-none absolute inset-x-[-40%] top-1/2 h-28 -translate-y-1/2"
            style={{ background: `linear-gradient(90deg, transparent, ${c.hex}66, transparent)`, mixBlendMode: 'screen' }}
            initial={{ x: '-120%', opacity: 0 }} animate={{ x: '120%', opacity: [0, 0.85, 0] }}
            transition={{ duration: 1.1, ease: 'easeOut', delay: 0.3 }} />
        )}
        {/* Expanding rings */}
        {[0.4, 0.65, 1].map((delay, i) => (
          <div key={i} className="absolute rounded-full border ring-expand"
            style={{
              width: 200, height: 200,
              borderColor: c.hex,
              opacity: 0.4,
              animationDelay: `${delay}s`,
              animationFillMode: 'both',
            }} />
        ))}
        {/* Badge */}
        <TierEmblem tier={tierId} colorKey={colorKey} size={112} state="current" celebrate />
        <div className="text-center tier-unlock" style={{ animationDelay: '0.2s', animationFillMode: 'both' }}>
          <div className="text-xs font-bold uppercase tracking-[0.3em] text-muted">Tier Unlocked</div>
          <div className={`mt-1 text-2xl font-black tracking-widest ${c.nameClass ?? ''}`}
            style={c.nameClass ? undefined : { color: c.hex }}>
            {tierName}
          </div>
        </div>
        <div className="text-[11px] text-muted mt-2" style={{ animationDelay: '0.4s' }}>
          Tap anywhere to continue
        </div>
      </div>
    </motion.div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Evolution() {
  const [data, setData] = useState<EvolutionReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [drawerAb, setDrawerAb] = useState<{ ab: TierAbility; tier: TierData } | null>(null)
  const [unlockOverlay, setUnlockOverlay] = useState<{ id: number; name: string; colorKey: string } | null>(null)
  const sfx = useSound()
  const { toast } = useToast()
  const shownUnlocks = useRef<Set<number>>(new Set())

  const load = () => {
    setLoading(true)
    setError(null)
    getEvolution()
      .then(d => {
        setData(d)
        setLoading(false)
        for (const tid of d.just_unlocked) {
          if (!shownUnlocks.current.has(tid)) {
            shownUnlocks.current.add(tid)
            const t = d.tiers[tid]
            if (t) {
              setTimeout(() => {
                setUnlockOverlay({ id: tid, name: t.name, colorKey: t.color_key })
                sfx.tierUp()
                toast({ kind: 'success', title: `Tier ${tid} unlocked — ${t.name}`, detail: 'A new tier of capability is online.' })
              }, 600)
            }
          }
        }
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e)
        console.error('[Evolution] fetch failed:', msg)
        setError(msg)
        setLoading(false)
      })
  }

  useEffect(() => { load() }, [])

  if (loading) {
    return <PageLoader preset="evolution" />
  }

  if (!data) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="text-sm text-danger">Failed to load evolution data</div>
          {error && <div className="max-w-xs rounded bg-surface px-3 py-2 font-mono text-[11px] text-muted">{error}</div>}
          <button onClick={load}
            className="rounded-md bg-accent/15 px-4 py-1.5 text-xs font-semibold text-accent hover:bg-accent/25">
            Retry
          </button>
        </div>
      </div>
    )
  }

  const currentTier = data.tiers[data.current_tier]
  const nextTier = data.tiers[data.current_tier + 1]
  const currentColors = TIER_COLORS[currentTier?.color_key] ?? TIER_COLORS.gray
  const nextColors = nextTier ? (TIER_COLORS[nextTier.color_key] ?? TIER_COLORS.gray) : null

  return (
    <>
      <div className="space-y-6 p-4 md:p-6">

        {/* ── Hero section ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">

          {/* Current tier */}
          <div className="rounded-xl border p-4 flex flex-col items-center gap-2 text-center tier-pulse"
            style={{
              ...(Object.fromEntries(
                (currentColors.border + ';' + currentColors.bg).split(';').filter(Boolean).map(s => {
                  const [k, v] = s.split(':').map(x => x.trim())
                  return [k.replace(/-([a-z])/g, (_, l) => l.toUpperCase()), v]
                })
              )),
            }}>
            <div className="text-[10px] font-semibold uppercase tracking-widest text-muted">Current Tier</div>
            <TierEmblem tier={currentTier?.id ?? 0} colorKey={currentTier?.color_key ?? 'gray'} size={64} state="current" />
            <div className={`text-lg font-black tracking-widest ${currentColors.nameClass ?? ''}`}
              style={currentColors.nameClass ? undefined : { color: currentColors.hex }}>
              {currentTier?.name}
            </div>
            <p className="text-[11px] text-muted leading-tight max-w-[200px]">{currentTier?.tagline}</p>
          </div>

          {/* Jarvis % */}
          <div className="rounded-xl border border-border bg-surface/50 p-4 flex flex-col items-center justify-center gap-2 text-center">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-muted">Jarvis Readiness</div>
            <div className="relative">
              <ProgressRing pct={data.jarvis_pct} size={100} stroke={7} color="#58a6ff" />
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-black text-heading">{data.jarvis_pct}%</span>
              </div>
            </div>
            <div className="text-xs text-muted">{data.total_active}/{data.total_abilities} abilities</div>
            <div className="flex items-center gap-1 text-[11px] text-accent">
              <TrendingUp size={12} /> {data.tiers.filter(t => t.complete).length} tiers complete
            </div>
          </div>

          {/* Next tier */}
          {nextTier && nextColors ? (
            <div className="rounded-xl border border-border bg-surface/50 p-4 flex flex-col items-center gap-2 text-center opacity-80">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-muted">Next Tier</div>
              <TierEmblem tier={nextTier.id} colorKey={nextTier.color_key} size={64} state="locked" />
              <div className={`text-lg font-black tracking-widest ${nextColors.nameClass ?? ''}`}
                style={nextColors.nameClass ? undefined : { color: nextColors.hex }}>
                {nextTier.name}
              </div>
              <div className="text-xs text-muted">
                {nextTier.total_count - nextTier.active_count} abilities to unlock
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-border bg-surface/50 p-4 flex flex-col items-center justify-center gap-2 text-center">
              <div className="text-4xl">🏆</div>
              <div className="text-sm font-bold text-heading">Fully Sovereign</div>
              <div className="text-xs text-muted">All tiers complete</div>
            </div>
          )}
        </div>

        {/* ── Priority unlock (missing in current tier) ───────────────────── */}
        {data.missing_in_current_tier.length > 0 && (
          <div className="rounded-xl border border-border bg-surface/40 p-4">
            <div className="mb-3 flex items-center gap-2">
              <Zap size={14} className="text-warning" />
              <span className="text-xs font-semibold uppercase tracking-widest text-warning">
                To Complete Tier {currentTier?.roman} — {currentTier?.name}
              </span>
              <span className="ml-auto text-[11px] text-muted">{data.missing_in_current_tier.length} remaining</span>
            </div>
            <div className="space-y-1">
              {data.missing_in_current_tier.map(ab => (
                <button key={ab.id}
                  onClick={() => { setDrawerAb({ ab, tier: currentTier }); sfx.select() }}
                  className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left hover:bg-white/5 transition-colors">
                  <XCircle size={13} className="shrink-0 text-red-400/60" />
                  <span className="flex-1 text-xs text-muted">{ab.name}</span>
                  {ab.effort !== 'done' && (
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${EFFORT_STYLE[ab.effort] ?? ''}`}>
                      {ab.effort}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Tier cards ──────────────────────────────────────────────────── */}
        <div className="space-y-3">
          {data.tiers.map(tier => (
            <TierCard key={tier.id} tier={tier}
              isCurrent={tier.id === data.current_tier}
              isCompleted={tier.complete}
              isLocked={tier.id > data.current_tier}
              onAbilityClick={(ab, t) => { setDrawerAb({ ab, tier: t }); sfx.select() }}
            />
          ))}
        </div>

      </div>

      {/* ── Ability drawer ───────────────────────────────────────────────── */}
      <AnimatePresence>
        {drawerAb && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/50" onClick={() => setDrawerAb(null)} />
            <AbilityDrawer ab={drawerAb.ab} tier={drawerAb.tier} onClose={() => setDrawerAb(null)}
              onReflected={() => { setDrawerAb(null); load() }} />
          </>
        )}
      </AnimatePresence>

      {/* ── Tier-up celebration overlay ─────────────────────────────────── */}
      <AnimatePresence>
        {unlockOverlay && (
          <TierUnlockOverlay tierId={unlockOverlay.id} tierName={unlockOverlay.name}
            colorKey={unlockOverlay.colorKey} onDone={() => setUnlockOverlay(null)} />
        )}
      </AnimatePresence>
    </>
  )
}
