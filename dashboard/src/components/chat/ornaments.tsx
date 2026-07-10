import { type CSSProperties } from 'react'
import { CLAUDE_PATH } from '../../theme/brandIcons'

/* ── Theme ornament motifs (queue #13 · M2.5) ──────────────────────────────────
   Procedural inline-SVG signature motifs for the Chat ambient layer — no external
   assets, no licensing. Every motif draws in `currentColor` so ChatAmbient tints
   it from a theme var (--accent / --theme-accent-2). Kept as clean line/ink art:
   the whole point is whisper-quiet elegance, never noise. */

type MotifProps = { size?: number; className?: string; style?: CSSProperties }

/* ── Japanese · Washi — sakura ─────────────────────────────────────────────── */

/** A single cherry-blossom petal with the signature tip notch (drifting particle). */
export function SakuraPetal({ size = 16, className = '', style }: MotifProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style} aria-hidden="true">
      <path
        d="M12 2.2c2.5 2.9 4.1 6 4.1 8.9 0 2.7-1.4 5.1-3.2 7.4-.3.4-.6.8-.9 1.3-.3-.5-.6-.9-.9-1.3-1.8-2.3-3.2-4.7-3.2-7.4 0-2.9 1.6-6 4.1-8.9Z"
        fill="currentColor" />
      {/* tip cleft — a hair lighter so the petal reads as folded, not flat */}
      <path d="M12 2.2c.6 1.1 1.2 2.3 1.6 3.5-.6.5-1.1 1.1-1.6 1.8-.5-.7-1-1.3-1.6-1.8.4-1.2 1-2.4 1.6-3.5Z"
        fill="currentColor" fillOpacity="0.35" />
    </svg>
  )
}

function Blossom({ cx, cy, r, opacity = 1 }: { cx: number; cy: number; r: number; opacity?: number }) {
  const petals = [0, 72, 144, 216, 288]
  return (
    <g opacity={opacity} transform={`translate(${cx} ${cy})`}>
      {petals.map(a => (
        <path key={a} transform={`rotate(${a})`}
          d={`M0 ${r * 0.18} C ${-r * 0.5} ${-r * 0.25}, ${-r * 0.34} ${-r} 0 ${-r * 0.72}
              C ${r * 0.34} ${-r} ${r * 0.5} ${-r * 0.25} 0 ${r * 0.18} Z`}
          fill="currentColor" />
      ))}
      <circle r={r * 0.16} fill="currentColor" fillOpacity="0.55" />
    </g>
  )
}

/** A single symmetric blossom — the centred hero halo for Washi. */
export function SakuraFlower({ size = 96, className = '', style }: MotifProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="none" className={className} style={style} aria-hidden="true">
      <Blossom cx={50} cy={50} r={42} />
    </svg>
  )
}

/** A sumi-e branch with a few blossoms + buds — the corner anchor for Washi. */
export function SakuraBranch({ size = 120, className = '', style }: MotifProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" fill="none" className={className} style={style} aria-hidden="true">
      {/* branch — an organic ink stroke */}
      <path d="M2 18 C 30 26, 48 30, 66 48 C 78 60, 86 74, 92 96"
        stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" fill="none" opacity="0.85" />
      <path d="M40 33 C 52 30, 62 24, 70 14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" fill="none" opacity="0.7" />
      <path d="M70 52 C 84 50, 94 44, 102 34" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" fill="none" opacity="0.7" />
      <Blossom cx={74} cy={12} r={11} />
      <Blossom cx={104} cy={31} r={13} />
      <Blossom cx={92} cy={98} r={10} opacity={0.9} />
      {/* buds */}
      <circle cx={45} cy={31} r={3} fill="currentColor" opacity="0.7" />
      <circle cx={66} cy={49} r={2.6} fill="currentColor" opacity="0.6" />
    </svg>
  )
}

/* ── Chinese · Lacquer — hanging lanterns + auspicious clouds ──────────────── */

function LanternShape({ x, y, s, tassel = true }: { x: number; y: number; s: number; tassel?: boolean }) {
  // s = body radius. Strings start above the viewBox so lanterns read as hanging in.
  const rx = s, ry = s * 0.82
  return (
    <g transform={`translate(${x} ${y})`}>
      {/* hanging string from beyond the top edge */}
      <line x1="0" y1={-y - 20} x2="0" y2={-ry - s * 0.34} stroke="currentColor" strokeWidth="1.4" opacity="0.8" />
      {/* top + bottom caps */}
      <rect x={-s * 0.34} y={-ry - s * 0.36} width={s * 0.68} height={s * 0.2} rx={s * 0.06} fill="currentColor" opacity="0.9" />
      <rect x={-s * 0.3} y={ry + s * 0.16} width={s * 0.6} height={s * 0.17} rx={s * 0.06} fill="currentColor" opacity="0.9" />
      {/* body + vertical ribs */}
      <ellipse cx="0" cy="0" rx={rx} ry={ry} stroke="currentColor" strokeWidth="2.4" fill="none" />
      <ellipse cx="0" cy="0" rx={rx * 0.62} ry={ry} stroke="currentColor" strokeWidth="1.3" fill="none" opacity="0.75" />
      <ellipse cx="0" cy="0" rx={rx * 0.24} ry={ry} stroke="currentColor" strokeWidth="1.1" fill="none" opacity="0.6" />
      {tassel && (
        <g opacity="0.85">
          <line x1="0" y1={ry + s * 0.33} x2="0" y2={ry + s * 0.62} stroke="currentColor" strokeWidth="1.3" />
          <path d={`M${-s * 0.12} ${ry + s * 0.62} h${s * 0.24} l${-s * 0.05} ${s * 0.34} h${-s * 0.14} Z`} fill="currentColor" />
        </g>
      )}
    </g>
  )
}

/** Two staggered hanging lanterns — instantly-read corner anchor for Lacquer. */
export function Lanterns({ size = 150, className = '', style }: MotifProps) {
  return (
    <svg width={size} height={size * 1.15} viewBox="0 0 130 150" fill="none" className={className} style={style} aria-hidden="true">
      <LanternShape x={44} y={62} s={26} />
      <LanternShape x={102} y={34} s={16} />
    </svg>
  )
}

/** A symmetric concentric medallion (rings + radial ticks) — hero halo for Lacquer. */
export function Medallion({ size = 120, className = '', style }: MotifProps) {
  const ticks = Array.from({ length: 16 }, (_, i) => (i * 360) / 16)
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="none" className={className} style={style} aria-hidden="true">
      <circle cx="50" cy="50" r="46" stroke="currentColor" strokeWidth="1.2" opacity="0.6" />
      <circle cx="50" cy="50" r="39" stroke="currentColor" strokeWidth="2.4" />
      <circle cx="50" cy="50" r="22" stroke="currentColor" strokeWidth="1.4" opacity="0.75" />
      <circle cx="50" cy="50" r="6" stroke="currentColor" strokeWidth="1.6" />
      <g opacity="0.7">
        {ticks.map(a => (
          <line key={a} x1="50" y1="28" x2="50" y2="34" stroke="currentColor" strokeWidth="1.4" transform={`rotate(${a} 50 50)`} />
        ))}
      </g>
    </svg>
  )
}

/** A ruyi / xiangyun auspicious cloud scroll (drifting particle for Lacquer). */
export function Cloud({ size = 40, className = '', style }: MotifProps) {
  return (
    <svg width={size} height={size * 0.62} viewBox="0 0 50 31" fill="none" className={className} style={style} aria-hidden="true">
      <path d="M4 24 C 2 16, 10 12, 14 16 C 15 8, 27 8, 28 16 C 34 12, 42 16, 40 22"
        stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" fill="none" />
      {/* spiral scroll ends */}
      <path d="M4 24 C 4 20, 9 20, 9 24 C 9 26, 6 27, 5 25" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <path d="M46 24 C 46 20, 41 20, 41 24 C 41 26, 44 27, 45 25" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <path d="M14 24 L 40 24" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.7" />
    </svg>
  )
}

/* ── Jarvis · Arc — arc-reactor HUD rings ──────────────────────────────────── */

export function ArcRings({ size = 150, className = '', style }: MotifProps) {
  const ticks = Array.from({ length: 24 }, (_, i) => i * 15)
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="none" className={className} style={style} aria-hidden="true">
      <circle cx="50" cy="50" r="46" stroke="currentColor" strokeWidth="0.6" opacity="0.5" />
      <circle cx="50" cy="50" r="38" stroke="currentColor" strokeWidth="1" strokeDasharray="2 4" opacity="0.7" />
      {/* segmented outer ring */}
      <circle cx="50" cy="50" r="44" stroke="currentColor" strokeWidth="2.4" strokeDasharray="34 14" opacity="0.9" />
      {/* tick marks */}
      <g opacity="0.6">
        {ticks.map(a => (
          <line key={a} x1="50" y1="6" x2="50" y2="10" stroke="currentColor" strokeWidth="0.8"
            transform={`rotate(${a} 50 50)`} />
        ))}
      </g>
      {/* inner core */}
      <circle cx="50" cy="50" r="20" stroke="currentColor" strokeWidth="1.4" opacity="0.8" />
      <circle cx="50" cy="50" r="12" stroke="currentColor" strokeWidth="0.8" strokeDasharray="1 3" opacity="0.6" />
      {/* three inner spokes */}
      <g opacity="0.7">
        {[0, 120, 240].map(a => (
          <line key={a} x1="50" y1="30" x2="50" y2="38" stroke="currentColor" strokeWidth="2" transform={`rotate(${a} 50 50)`} />
        ))}
      </g>
    </svg>
  )
}

/* ── Gaming · Neon Arena — HUD targeting brackets ──────────────────────────── */

export function HexBrackets({ size = 150, className = '', style }: MotifProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="none" className={className} style={style} aria-hidden="true">
      {/* hexagon outline */}
      <path d="M50 8 L 86 29 L 86 71 L 50 92 L 14 71 L 14 29 Z" stroke="currentColor" strokeWidth="1" opacity="0.45" />
      <path d="M50 20 L 76 35 L 76 65 L 50 80 L 24 65 L 24 35 Z" stroke="currentColor" strokeWidth="0.7" strokeDasharray="3 5" opacity="0.55" />
      {/* corner targeting brackets */}
      <g stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.9">
        <path d="M8 20 L 8 8 L 20 8" />
        <path d="M92 20 L 92 8 L 80 8" />
        <path d="M8 80 L 8 92 L 20 92" />
        <path d="M92 80 L 92 92 L 80 92" />
      </g>
      {/* center reticle */}
      <g stroke="currentColor" strokeWidth="1.4" opacity="0.7">
        <line x1="50" y1="44" x2="50" y2="56" />
        <line x1="44" y1="50" x2="56" y2="50" />
      </g>
    </svg>
  )
}

/** A small hex mote (drifting particle for Neon Arena). */
export function HexMote({ size = 12, className = '', style }: MotifProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none" className={className} style={style} aria-hidden="true">
      <path d="M6 1 L 10.3 3.5 L 10.3 8.5 L 6 11 L 1.7 8.5 L 1.7 3.5 Z" fill="currentColor" />
    </svg>
  )
}

/* ── Claude — the official starburst mark (currentColor for ambient tinting) ── */

export function ClaudeMark({ size = 160, className = '', style }: MotifProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style} aria-hidden="true">
      <path d={CLAUDE_PATH} fill="currentColor" fillRule="nonzero" />
    </svg>
  )
}
