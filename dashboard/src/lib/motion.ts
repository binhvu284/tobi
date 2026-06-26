// ── TOBI "Living Machine" motion system — single source of truth ──────────────
// Tokens + reusable framer-motion variants, all reduced-motion aware via the
// `level` argument ('full' | 'reduced' | 'off'). Primitives in components/motion
// read the active level from <MotionProvider> (useReducedMotionPref) and pass it
// here so every entrance/exit degrades consistently.
//
// Budget rule (Decision #4): variants only ever touch `transform` + `opacity`.
import type { Transition, Variants } from 'framer-motion'

export type MotionLevel = 'full' | 'reduced' | 'off'

// ── Tokens ────────────────────────────────────────────────────────────────────
/** Durations (seconds). Everyday 120–220ms; signature moments 500–900ms. */
export const DUR = { xs: 0.12, sm: 0.18, md: 0.28, lg: 0.5, xl: 0.8 } as const

/** Signature easings as cubic-bezier tuples. */
export const EASE: Record<'spring' | 'out' | 'snappy', [number, number, number, number]> = {
  spring: [0.34, 1.56, 0.64, 1], // crisp spring w/ slight overshoot — entrances/toggles
  out: [0.22, 1, 0.36, 1],       // calm decel — exits/quiet moves
  snappy: [0.4, 0, 0.2, 1],      // quick everyday interactions
}

/** Spring presets for framer `transition`. */
export const SPRING = {
  soft: { type: 'spring', stiffness: 260, damping: 26 } as Transition,
  snappy: { type: 'spring', stiffness: 380, damping: 28 } as Transition,
  pop: { type: 'spring', stiffness: 500, damping: 24 } as Transition,
}

const INSTANT: Variants = { hidden: { opacity: 1 }, show: { opacity: 1 } }

// ── Variants (level-aware factories) ────────────────────────────────────────────
/** HUD panel-boot route wrapper: fade + 8px slide-up (full); fade only (reduced). */
export function panelBoot(level: MotionLevel = 'full'): Variants {
  if (level === 'off') return INSTANT
  if (level === 'reduced')
    return { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: DUR.sm, ease: EASE.out } } }
  return {
    hidden: { opacity: 0, y: 8 },
    show: { opacity: 1, y: 0, transition: { duration: DUR.md, ease: EASE.out } },
  }
}

/** Parent that cascades its variant children top-down. */
export function staggerParent(level: MotionLevel = 'full', stagger = 0.045): Variants {
  if (level === 'off') return { hidden: {}, show: {} }
  return {
    hidden: {},
    show: { transition: { staggerChildren: level === 'reduced' ? 0 : stagger, delayChildren: 0.02 } },
  }
}

/** Child of a stagger parent (or standalone Reveal). */
export function staggerChild(level: MotionLevel = 'full', y = 10): Variants {
  if (level === 'off') return INSTANT
  if (level === 'reduced')
    return { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: DUR.sm, ease: EASE.out } } }
  return {
    hidden: { opacity: 0, y },
    show: { opacity: 1, y: 0, transition: { duration: DUR.md, ease: EASE.out } },
  }
}

/** Plain fade in/out. */
export function fade(level: MotionLevel = 'full'): Variants {
  if (level === 'off') return { hidden: { opacity: 1 }, show: { opacity: 1 }, exit: { opacity: 0 } }
  return {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { duration: DUR.sm, ease: EASE.out } },
    exit: { opacity: 0, transition: { duration: DUR.xs, ease: EASE.out } },
  }
}

/** Center dialog: fade + scale-in with spring; quiet scale-out. */
export function scaleIn(level: MotionLevel = 'full'): Variants {
  if (level === 'off') return { hidden: { opacity: 1 }, show: { opacity: 1 }, exit: { opacity: 0 } }
  if (level === 'reduced')
    return {
      hidden: { opacity: 0 },
      show: { opacity: 1, transition: { duration: DUR.sm } },
      exit: { opacity: 0, transition: { duration: DUR.xs } },
    }
  return {
    hidden: { opacity: 0, scale: 0.96, y: 6 },
    show: { opacity: 1, scale: 1, y: 0, transition: SPRING.snappy },
    exit: { opacity: 0, scale: 0.97, transition: { duration: DUR.xs, ease: EASE.out } },
  }
}

/** Edge slide-over panel (Decision #26). */
export function slideOver(level: MotionLevel = 'full', from: 'right' | 'left' = 'right'): Variants {
  const sign = from === 'right' ? 1 : -1
  if (level === 'off') return { hidden: { opacity: 1 }, show: { opacity: 1 }, exit: { opacity: 0 } }
  if (level === 'reduced')
    return {
      hidden: { opacity: 0 },
      show: { opacity: 1, transition: { duration: DUR.sm } },
      exit: { opacity: 0, transition: { duration: DUR.xs } },
    }
  return {
    hidden: { x: `${sign * 100}%`, opacity: 0.4 },
    show: { x: 0, opacity: 1, transition: SPRING.soft },
    exit: { x: `${sign * 100}%`, opacity: 0, transition: { duration: DUR.sm, ease: EASE.out } },
  }
}

// Re-export the active-level hook so callers can `import { useReducedMotionPref } from '../lib/motion'`.
// (MotionProvider imports only the MotionLevel *type* from here, so there is no runtime cycle.)
export { useReducedMotionPref, useMotion } from '../context/MotionProvider'
