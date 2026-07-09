import { useMemo, type CSSProperties, type ReactNode } from 'react'
import { useTheme } from '../../context/ThemeProvider'
import type { ThemeId } from '../../context/themeTokens'
import {
  SakuraBranch, SakuraFlower, SakuraPetal, Dragon, Medallion, Cloud,
  ArcRings, HexBrackets, HexMote, Spark,
} from './ornaments'

/* ── Chat ambient ornaments (queue #13 · M2.5) ─────────────────────────────────
   Per-theme signature motifs concentrated in Chat — the owner↔TOBI surface. The
   rule is whisper-quiet elegance: pointer-events-none, aria-hidden, behind every
   message, opacity ≤~0.14, corner-anchored, and a soft radial mask so ornaments
   fade before they reach text. Honors the motion system + the per-theme
   `decorations` toggle (data-motion / data-decorations guards live in index.css).
   Only DECOR_THEMES render anything; every other theme stays deliberately clean. */

type Corner = 'tl' | 'tr' | 'bl' | 'br'
// Corner motifs may be directional (branch/dragon); hero motifs are symmetric
// (flower/medallion/arc/hex/spark) so they halo the greeting cleanly.
type MotifName = 'sakura' | 'flower' | 'dragon' | 'medallion' | 'arc' | 'hex' | 'spark'
type ParticleMotif = 'petal' | 'cloud' | 'mote'

type CornerSpec = { motif: MotifName; pos: Corner; size: number; tint: string; opacity: number; spin?: boolean }
type ParticleSpec = { motif: ParticleMotif; count: number; tint: string; opacity: number; min: number; max: number }
// Hero = a large, faint, outline-only watermark behind the empty-state greeting.
// Only symmetric outline motifs (arc/hex/medallion/spark) qualify — directional
// or filled motifs (branch/flower) stay corner-only, so no hero for those themes.
type HeroSpec = { motif: MotifName; size: number; tint: string; opacity: number; spin?: boolean }
type ThemeOrnament = { corners: CornerSpec[]; particles?: ParticleSpec; hero?: HeroSpec }

const ACCENT = 'rgb(var(--accent))'
const GOLD = 'rgb(var(--theme-accent-2))'
const PINK = 'rgb(var(--theme-accent-2))'

/** The single place motif shape maps to a theme (localized, like THEME_DEFS). */
const CHAT_ORNAMENTS: Partial<Record<ThemeId, ThemeOrnament>> = {
  japanese: {
    // Branch is directional + the blossom fill blobs → corner + petals only, no hero.
    corners: [{ motif: 'sakura', pos: 'tr', size: 172, tint: ACCENT, opacity: 0.14 }],
    particles: { motif: 'petal', count: 7, tint: ACCENT, opacity: 0.2, min: 11, max: 20 },
  },
  chinese: {
    corners: [{ motif: 'dragon', pos: 'br', size: 188, tint: GOLD, opacity: 0.1 }],
    particles: { motif: 'cloud', count: 5, tint: GOLD, opacity: 0.13, min: 34, max: 56 },
    hero: { motif: 'medallion', size: 150, tint: GOLD, opacity: 0.1, spin: true },
  },
  jarvis: {
    corners: [{ motif: 'arc', pos: 'tr', size: 230, tint: ACCENT, opacity: 0.1, spin: true }],
    hero: { motif: 'arc', size: 156, tint: ACCENT, opacity: 0.1, spin: true },
  },
  gaming: {
    corners: [{ motif: 'hex', pos: 'tr', size: 188, tint: ACCENT, opacity: 0.1 }],
    particles: { motif: 'mote', count: 8, tint: PINK, opacity: 0.18, min: 8, max: 14 },
    hero: { motif: 'hex', size: 150, tint: ACCENT, opacity: 0.1 },
  },
  claude: {
    corners: [{ motif: 'spark', pos: 'br', size: 176, tint: ACCENT, opacity: 0.07, spin: true }],
    hero: { motif: 'spark', size: 150, tint: ACCENT, opacity: 0.09, spin: true },
  },
}

function Motif({ name, size, spin }: { name: MotifName; size: number; spin?: boolean }) {
  const cls = spin ? 'chat-ambient-spin' : undefined
  switch (name) {
    case 'sakura': return <SakuraBranch size={size} className={cls} />
    case 'flower': return <SakuraFlower size={size} className={cls} />
    case 'dragon': return <Dragon size={size} className={cls} />
    case 'medallion': return <Medallion size={size} className={cls} />
    case 'arc': return <ArcRings size={size} className={cls} />
    case 'hex': return <HexBrackets size={size} className={cls} />
    case 'spark': return <Spark size={size} className={cls} />
  }
}

const CORNER_POS: Record<Corner, CSSProperties> = {
  tl: { top: '-1.5rem', left: '-1.5rem' },
  tr: { top: '-1.5rem', right: '-1.5rem' },
  bl: { bottom: '-1.5rem', left: '-1.5rem' },
  br: { bottom: '-1.5rem', right: '-1.5rem' },
}

/** A drifting particle field — deterministic per theme so it doesn't reshuffle. */
function Particles({ spec }: { spec: ParticleSpec }) {
  const items = useMemo(() => Array.from({ length: spec.count }, (_, i) => {
    // cheap deterministic hash from index
    const h = (n: number) => ((Math.sin((i + 1) * n) + 1) / 2)
    const size = spec.min + h(12.9898) * (spec.max - spec.min)
    return {
      left: 4 + h(78.233) * 90,          // %
      size,
      duration: 13 + h(37.719) * 12,     // s
      delay: -h(3.111) * 18,             // s (negative = mid-flight on load)
      drift: (h(9.7) - 0.5) * 120,       // px horizontal drift
      sway: 8 + h(5.3) * 10,
    }
  }), [spec])

  const Glyph = spec.motif === 'petal' ? SakuraPetal : spec.motif === 'cloud' ? Cloud : HexMote
  const anim = spec.motif === 'cloud' ? 'chat-cloud' : 'chat-petal'

  return (
    <div className="chat-ambient-particles" style={{ color: spec.tint, opacity: spec.opacity }}>
      {items.map((p, i) => (
        <span key={i} className="chat-ambient-particle" style={{
          left: `${p.left}%`,
          animationName: anim,
          animationDuration: `${p.duration}s`,
          animationDelay: `${p.delay}s`,
          ['--drift' as string]: `${p.drift}px`,
          ['--sway' as string]: `${p.sway}px`,
        }}>
          <Glyph size={p.size} />
        </span>
      ))}
    </div>
  )
}

/** Ambient decoration layer — mount as the first child of the Chat conversation column. */
export default function ChatAmbient() {
  const { theme } = useTheme()
  const orn = CHAT_ORNAMENTS[theme]
  if (!orn) return null
  return (
    <div className="chat-ambient" aria-hidden="true">
      {orn.corners.map((c, i) => (
        <div key={i} className="chat-ambient-corner" style={{ ...CORNER_POS[c.pos], color: c.tint, opacity: c.opacity }}>
          <Motif name={c.motif} size={c.size} spin={c.spin} />
        </div>
      ))}
      {orn.particles && <Particles spec={orn.particles} />}
    </div>
  )
}

/** Large faint outline watermark behind the empty-state greeting (themes with a
 *  symmetric hero motif only). Renders nothing for themes without one. */
export function ChatHeroMotif({ children }: { children?: ReactNode }) {
  const { theme } = useTheme()
  const h = CHAT_ORNAMENTS[theme]?.hero
  if (!h) return <>{children}</>
  return (
    <div className="chat-hero-motif" aria-hidden="true" style={{ color: h.tint, opacity: h.opacity }}>
      <Motif name={h.motif} size={h.size} spin={h.spin} />
    </div>
  )
}
