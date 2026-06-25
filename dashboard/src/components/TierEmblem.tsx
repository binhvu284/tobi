import { useId } from 'react'
import { motion, useReducedMotion } from 'framer-motion'

/**
 * TierEmblem — an evolving glossy robot-face medal for the Evolution tiers.
 *
 * One robot identity that levels up: the FACE wears the tier's metal finish, and
 * regalia (antenna → ears → circlet → crown → halo → wings → gems) accumulate as
 * the tier rises. `state='current'` breathes a soft aura; `state='locked'` shows a
 * darkened silhouette of what's coming; `celebrate` plays the rank-up pop + shine
 * sweep + particle burst. All motion respects prefers-reduced-motion.
 */

type Material = { l: string; m: string; d: string; glow: string; eye: string }

// Per-tier metals, aligned to Evolution's color_key palette.
const MATERIALS: Record<string, Material> = {
  gray:       { l: '#C7CDD6', m: '#9CA3AF', d: '#565E6E', glow: '#9CA3AF', eye: '#E5E7EB' },
  bronze:     { l: '#E8A766', m: '#CD7F32', d: '#6E4019', glow: '#CD7F32', eye: '#FFD9A0' },
  gold:       { l: '#FFE970', m: '#FFD700', d: '#A8810A', glow: '#FFD700', eye: '#FFF6C0' },
  green:      { l: '#5EE6B5', m: '#10B981', d: '#06624A', glow: '#10B981', eye: '#C6FFE9' },
  neon_blue:  { l: '#7EE7F7', m: '#22D3EE', d: '#0C7081', glow: '#22D3EE', eye: '#DFFAFF' },
  gold_white: { l: '#FFFFFF', m: '#FFE36E', d: '#B98E1F', glow: '#FFD700', eye: '#FFFFFF' },
  aurora:     { l: '#CDBcFF', m: '#A78BFA', d: '#553BA8', glow: '#A78BFA', eye: '#ECE4FF' },
  sovereign:  { l: '#FFFFFF', m: '#E8E8F2', d: '#B9A24E', glow: '#FFE36E', eye: '#FFFFFF' },
}
const LOCKED: Material = { l: '#3A4150', m: '#262B36', d: '#171A22', glow: '#000000', eye: '#404857' }

const GEMS = ['#FF5D8F', '#22D3EE', '#A78BFA']

export type TierEmblemProps = {
  tier: number
  colorKey: string
  size?: number
  state?: 'normal' | 'current' | 'locked'
  celebrate?: boolean
  className?: string
}

export default function TierEmblem({
  tier, colorKey, size = 40, state = 'normal', celebrate = false, className,
}: TierEmblemProps) {
  const uid = useId().replace(/:/g, '')
  const reduce = useReducedMotion()
  const locked = state === 'locked'
  const current = state === 'current'
  const mat = locked ? LOCKED : (MATERIALS[colorKey] ?? MATERIALS.gray)

  // Regalia gates — accumulate with tier.
  const antennaLit = tier >= 1
  const hasEars    = tier >= 2
  const hasCirclet = tier >= 3 && tier < 4
  const hasCrown   = tier >= 4
  const hasHalo    = tier >= 5
  const hasWings   = tier >= 6
  const hasGems    = tier >= 7
  const eyeGlow = !locked

  const baseGlow = Math.min(0.2 + tier * 0.045, 0.5)

  return (
    <motion.div
      className={`relative shrink-0 ${className ?? ''}`}
      style={{ width: size, height: size }}
      {...(celebrate && !reduce
        ? { initial: { scale: 0.6, opacity: 0 }, animate: { scale: [0.6, 1.14, 1], opacity: 1 }, transition: { duration: 0.7, ease: 'easeOut' } }
        : {})}
    >
      <svg viewBox="0 0 96 96" width={size} height={size} className="block">
        <defs>
          <linearGradient id={`metal-${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={mat.l} />
            <stop offset="48%" stopColor={mat.m} />
            <stop offset="100%" stopColor={mat.d} />
          </linearGradient>
          <linearGradient id={`crown-${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#FFF0A8" />
            <stop offset="55%" stopColor="#FFD700" />
            <stop offset="100%" stopColor="#A8810A" />
          </linearGradient>
          <radialGradient id={`glow-${uid}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={mat.glow} stopOpacity="0.9" />
            <stop offset="100%" stopColor={mat.glow} stopOpacity="0" />
          </radialGradient>
          <linearGradient id={`spec-${uid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
          </linearGradient>
          <filter id={`soft-${uid}`} x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="1.6" />
          </filter>
        </defs>

        {/* aura */}
        <motion.circle
          cx="48" cy="50" r="46" fill={`url(#glow-${uid})`}
          {...(current && !reduce
            ? { initial: { opacity: baseGlow }, animate: { opacity: [baseGlow, baseGlow + 0.2, baseGlow] }, transition: { duration: 3, repeat: Infinity, ease: 'easeInOut' } }
            : { opacity: locked ? 0 : baseGlow })}
        />

        {/* wings (behind) */}
        {hasWings && (
          <g opacity={locked ? 0.6 : 0.92}>
            <path d="M27 52 C9 44 6 60 19 65 C11 62 16 53 27 58 Z" fill={`url(#metal-${uid})`} />
            <path d="M69 52 C87 44 90 60 77 65 C85 62 80 53 69 58 Z" fill={`url(#metal-${uid})`} />
          </g>
        )}

        {/* ears */}
        {hasEars && (
          <g opacity={locked ? 0.6 : 1}>
            <rect x="21" y="47" width="6" height="13" rx="3" fill={`url(#metal-${uid})`} />
            <rect x="69" y="47" width="6" height="13" rx="3" fill={`url(#metal-${uid})`} />
          </g>
        )}

        {/* antenna (until a crown takes over) */}
        {!hasCrown && (
          <g opacity={locked ? 0.6 : 1}>
            <line x1="48" y1="33" x2="48" y2="22" stroke={mat.l} strokeWidth="2.2" strokeLinecap="round" />
            <circle cx="48" cy="19.5" r="3.2" fill={antennaLit && !locked ? mat.glow : mat.m}
              filter={antennaLit && !locked ? `url(#soft-${uid})` : undefined} />
          </g>
        )}

        {/* head */}
        <rect x="28" y="32" width="40" height="40" rx="13" fill={`url(#metal-${uid})`}
          stroke="rgba(255,255,255,0.18)" strokeWidth="1.5" opacity={locked ? 0.66 : 1} />
        {/* glossy highlight */}
        {!locked && <ellipse cx="48" cy="42" rx="15" ry="7.5" fill={`url(#spec-${uid})`} />}

        {/* eyes */}
        <g filter={eyeGlow ? `url(#soft-${uid})` : undefined}>
          <rect x="37" y="46" width="8" height="10" rx="3" fill={mat.eye} opacity={locked ? 0.5 : 1} />
          <rect x="51" y="46" width="8" height="10" rx="3" fill={mat.eye} opacity={locked ? 0.5 : 1} />
        </g>
        {/* mouth/visor */}
        <rect x="40" y="62" width="16" height="4.6" rx="2.3" fill="rgba(0,0,0,0.32)" />

        {/* circlet (tier 3) */}
        {hasCirclet && (
          <path d="M33 33 Q48 26 63 33" fill="none" stroke={`url(#crown-${uid})`} strokeWidth="3" strokeLinecap="round" opacity={locked ? 0.6 : 1} />
        )}

        {/* crown (tier 4+) */}
        {hasCrown && (
          <g opacity={locked ? 0.6 : 1}>
            <path d="M31 31 L37 19 L43 27 L48 14 L53 27 L59 19 L65 31 Z"
              fill={locked ? `url(#metal-${uid})` : `url(#crown-${uid})`}
              stroke="rgba(0,0,0,0.18)" strokeWidth="0.8" strokeLinejoin="round" />
            {hasGems && !locked && (
              <>
                <circle cx="48" cy="22" r="2.1" fill={GEMS[0]} />
                <circle cx="37" cy="26" r="1.7" fill={GEMS[1]} />
                <circle cx="59" cy="26" r="1.7" fill={GEMS[2]} />
              </>
            )}
          </g>
        )}

        {/* halo (tier 5+) */}
        {hasHalo && !locked && (
          <ellipse cx="48" cy={hasCrown ? 12 : 16} rx="19" ry="5.5" fill="none"
            stroke={mat.glow} strokeWidth="2.4" opacity="0.9" filter={`url(#soft-${uid})`} />
        )}
        {hasHalo && locked && (
          <ellipse cx="48" cy={hasCrown ? 12 : 16} rx="19" ry="5.5" fill="none" stroke={mat.l} strokeWidth="2" opacity="0.5" />
        )}
      </svg>

      {/* rank-up shine sweep */}
      {celebrate && !reduce && (
        <div className="pointer-events-none absolute inset-0 overflow-hidden" style={{ borderRadius: '26%' }}>
          <motion.div className="absolute inset-y-0 w-1/2"
            style={{ background: 'linear-gradient(105deg, transparent, rgba(255,255,255,0.6), transparent)' }}
            initial={{ x: '-160%' }} animate={{ x: '260%' }}
            transition={{ duration: 0.9, delay: 0.3, repeat: 1, repeatDelay: 0.5, ease: 'easeInOut' }} />
        </div>
      )}

      {/* rank-up particle burst */}
      {celebrate && !reduce && (
        <div className="pointer-events-none absolute inset-0">
          {Array.from({ length: 10 }).map((_, i) => {
            const ang = (i / 10) * Math.PI * 2
            const dist = size * 0.62
            return (
              <motion.span key={i}
                className="absolute left-1/2 top-1/2 h-1 w-1 rounded-full"
                style={{ background: i % 3 === 0 ? mat.glow : '#FFFFFF', marginLeft: -2, marginTop: -2 }}
                initial={{ x: 0, y: 0, opacity: 0, scale: 0.4 }}
                animate={{ x: Math.cos(ang) * dist, y: Math.sin(ang) * dist, opacity: [0, 1, 0], scale: [0.4, 1.1, 0.2] }}
                transition={{ duration: 0.85, delay: 0.18, ease: 'easeOut' }} />
            )
          })}
        </div>
      )}
    </motion.div>
  )
}
