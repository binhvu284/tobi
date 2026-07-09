import { motion } from 'framer-motion'

type Props = {
  /** 0–100 power/XP value. */
  value: number
  /** Gradient stops + glow. Defaults to the accent→purple "power" gradient. */
  from?: string
  to?: string
  glow?: string
  /** 'lg' = hero XP bar with ticks + sheen; 'sm' = compact dimension/card bar. */
  size?: 'lg' | 'sm'
  /** Show the numeric value on the right (sm) or as a big number (lg). */
  showValue?: boolean
  /** Optional caption shown above an 'lg' bar. */
  label?: string
  className?: string
}

/**
 * A gamified XP / power bar (0–100). Shares HealthBar's gradient + sheen +
 * segment-tick recipe, but with a neutral "power" gradient (NOT health's
 * red-for-low tiers) so any dimension/ability can colour it freely.
 */
export default function StatBar({
  value,
  from = 'rgb(var(--accent))',
  to = 'rgb(var(--purple))',
  glow = 'rgb(var(--purple) / 0.45)',
  size = 'sm',
  showValue = true,
  label,
  className = '',
}: Props) {
  const s = Math.max(0, Math.min(100, Math.round(value)))

  if (size === 'sm') {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-bg ring-1 ring-border/70">
          <motion.div
            className="h-full rounded-full"
            style={{ background: `linear-gradient(90deg, ${from}, ${to})`, boxShadow: `0 0 8px ${glow}` }}
            initial={{ width: 0 }}
            animate={{ width: `${s}%` }}
            transition={{ duration: 0.9, ease: 'easeOut' }}
          />
        </div>
        {showValue && <span className="w-7 shrink-0 text-right font-mono text-xs font-bold text-text">{s}</span>}
      </div>
    )
  }

  return (
    <div className={className}>
      {(label || showValue) && (
        <div className="mb-2 flex items-end justify-between">
          {label && <span className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</span>}
          {showValue && (
            <div className="flex items-baseline gap-1">
              <span className="font-mono text-3xl font-bold leading-none text-heading">{s}</span>
              <span className="text-xs text-muted">/ 100</span>
            </div>
          )}
        </div>
      )}

      <div className="relative h-4 w-full overflow-hidden rounded-md bg-bg ring-1 ring-border/70">
        <motion.div
          className="relative h-full rounded-md"
          style={{ background: `linear-gradient(90deg, ${from}, ${to})`, boxShadow: `0 0 14px ${glow}` }}
          initial={{ width: 0 }}
          animate={{ width: `${s}%` }}
          transition={{ duration: 1.1, ease: 'easeOut' }}
        >
          <motion.div
            className="absolute inset-0"
            style={{ background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.35), transparent)' }}
            initial={{ x: '-100%' }}
            animate={{ x: '200%' }}
            transition={{ duration: 2.2, ease: 'easeInOut', repeat: Infinity, repeatDelay: 1.2 }}
          />
        </motion.div>
        {/* segment ticks (XP-bar feel) */}
        <div className="pointer-events-none absolute inset-0 flex">
          {Array.from({ length: 20 }).map((_, i) => (
            <div key={i} className="h-full flex-1 border-r border-bg/40 last:border-r-0" />
          ))}
        </div>
      </div>
    </div>
  )
}
