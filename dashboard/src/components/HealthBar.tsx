import { motion } from 'framer-motion'

type Tier = 'healthy' | 'degraded' | 'issue'

function tierOf(score: number): Tier {
  return score >= 85 ? 'healthy' : score >= 50 ? 'degraded' : 'issue'
}

const TIER = {
  healthy: { label: 'Healthy', text: 'text-success', from: '#3fb950', to: '#56d364', glow: 'rgba(63,185,80,0.45)' },
  degraded: { label: 'Degraded', text: 'text-warning', from: '#d29922', to: '#e3b341', glow: 'rgba(210,153,34,0.45)' },
  issue: { label: 'Critical', text: 'text-danger', from: '#f85149', to: '#ff7b72', glow: 'rgba(248,81,73,0.45)' },
} as const

type Props = {
  score: number
  /** 'lg' = hero bar with number + label; 'sm' = compact inline bar. */
  size?: 'lg' | 'sm'
  className?: string
}

/** A game-style HP bar visualising Tobi's overall health (0–100). */
export default function HealthBar({ score, size = 'lg', className = '' }: Props) {
  const s = Math.max(0, Math.min(100, Math.round(score)))
  const tier = tierOf(s)
  const t = TIER[tier]

  if (size === 'sm') {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-black/40 ring-1 ring-white/10">
          <motion.div
            className="h-full rounded-full"
            style={{ background: `linear-gradient(90deg, ${t.from}, ${t.to})`, boxShadow: `0 0 8px ${t.glow}` }}
            initial={{ width: 0 }}
            animate={{ width: `${s}%` }}
            transition={{ duration: 0.9, ease: 'easeOut' }}
          />
        </div>
        <span className={`shrink-0 font-mono text-xs font-bold ${t.text}`}>{s}%</span>
      </div>
    )
  }

  return (
    <div className={className}>
      <div className="mb-2 flex items-end justify-between">
        <div className="flex items-baseline gap-2">
          <span className={`font-mono text-4xl font-bold leading-none ${t.text}`}>{s}</span>
          <span className="text-sm text-muted">/ 100 HP</span>
        </div>
        <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider ${t.text} border-current/40`}>
          {t.label}
        </span>
      </div>

      {/* Track */}
      <div className="relative h-5 w-full overflow-hidden rounded-md bg-black/40 ring-1 ring-white/10">
        {/* Fill */}
        <motion.div
          className="relative h-full rounded-md"
          style={{ background: `linear-gradient(90deg, ${t.from}, ${t.to})`, boxShadow: `0 0 14px ${t.glow}` }}
          initial={{ width: 0 }}
          animate={{ width: `${s}%` }}
          transition={{ duration: 1.1, ease: 'easeOut' }}
        >
          {/* moving sheen */}
          <motion.div
            className="absolute inset-0"
            style={{ background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.35), transparent)' }}
            initial={{ x: '-100%' }}
            animate={{ x: '200%' }}
            transition={{ duration: 2.2, ease: 'easeInOut', repeat: Infinity, repeatDelay: 1.2 }}
          />
        </motion.div>
        {/* segment ticks (HP-bar feel) */}
        <div className="pointer-events-none absolute inset-0 flex">
          {Array.from({ length: 20 }).map((_, i) => (
            <div key={i} className="h-full flex-1 border-r border-bg/40 last:border-r-0" />
          ))}
        </div>
      </div>
    </div>
  )
}
