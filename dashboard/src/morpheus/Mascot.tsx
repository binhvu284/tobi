// The Sentinel: Morpheus's mascot.
//
// It is the same eye as the gate's mark, grown into a character. It watches the cursor, blinks
// on its own, dilates when you come near, and reacts when you poke it. That is the whole job --
// it makes the Home page feel inhabited rather than printed.
//
// Cursor tracking runs entirely on motion values, never React state. A `useState` on mousemove
// re-renders this component (and everything under it) on every pointer event, which collapses to
// a slideshow the moment anything else on the page is animating. `useMotionValue` writes straight
// to the DOM and never touches the render cycle.
import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, useMotionValue, useSpring, useTransform, useReducedMotion } from 'framer-motion'

type Mood = 'idle' | 'alert' | 'pleased'

export function Sentinel({ size = 148, mood = 'idle', onPoke }: {
  size?: number
  /** `alert` when something needs the owner's attention; `pleased` right after an interaction. */
  mood?: Mood
  onPoke?: () => void
}) {
  const reduce = useReducedMotion()
  const wrap = useRef<HTMLDivElement>(null)

  // Where the pupil is looking, in the range -1..1 on each axis.
  const lookX = useMotionValue(0)
  const lookY = useMotionValue(0)
  const sx = useSpring(lookX, { stiffness: 140, damping: 18, mass: 0.5 })
  const sy = useSpring(lookY, { stiffness: 140, damping: 18, mass: 0.5 })

  // The iris travels further than the pupil, which reads as depth rather than a flat sticker.
  const irisX = useTransform(sx, v => v * 9)
  const irisY = useTransform(sy, v => v * 6)
  const pupilX = useTransform(sx, v => v * 13)
  const pupilY = useTransform(sy, v => v * 8.5)
  const glintX = useTransform(sx, v => v * -4)
  const glintY = useTransform(sy, v => v * -3)

  const [blink, setBlink] = useState(false)
  const [near, setNear] = useState(false)
  const [poked, setPoked] = useState(0)

  // Track the pointer across the whole page: the Sentinel should notice you anywhere on Home,
  // not only when the cursor is over it.
  useEffect(() => {
    if (reduce) return
    const onMove = (e: PointerEvent) => {
      const el = wrap.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const cx = r.left + r.width / 2
      const cy = r.top + r.height / 2
      const dx = e.clientX - cx
      const dy = e.clientY - cy
      // Normalise against a generous radius so the eye tracks smoothly instead of snapping.
      const radius = Math.max(window.innerWidth, window.innerHeight) * 0.42
      lookX.set(Math.max(-1, Math.min(1, dx / radius)))
      lookY.set(Math.max(-1, Math.min(1, dy / radius)))
      setNear(Math.hypot(dx, dy) < r.width * 1.35)
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    return () => window.removeEventListener('pointermove', onMove)
  }, [lookX, lookY, reduce])

  // Irregular blinking. A fixed interval reads as a machine; an uneven one reads as alive.
  useEffect(() => {
    if (reduce) return
    let timer: number
    const schedule = () => {
      timer = window.setTimeout(() => {
        setBlink(true)
        window.setTimeout(() => setBlink(false), 140)
        schedule()
      }, 2600 + Math.random() * 4200)
    }
    schedule()
    return () => window.clearTimeout(timer)
  }, [reduce])

  const poke = useCallback(() => {
    setPoked(n => n + 1)
    onPoke?.()
  }, [onPoke])

  const ring = mood === 'alert' ? 'rgb(var(--danger))' : 'rgb(var(--accent))'
  const lidShut = blink && !reduce

  return (
    <div ref={wrap} className="relative grid place-items-center" style={{ width: size, height: size }}>
      {/* Orbit rings. Pure rotation, so the compositor handles them with no repaint. */}
      {!reduce && (
        <>
          <motion.span aria-hidden
            className="absolute rounded-full border border-dashed"
            style={{ inset: 0, borderColor: 'rgb(var(--accent) / 0.22)' }}
            animate={{ rotate: 360 }}
            transition={{ duration: 34, repeat: Infinity, ease: 'linear' }} />
          <motion.span aria-hidden
            className="absolute rounded-full border"
            style={{ inset: size * 0.11, borderColor: 'rgb(var(--accent) / 0.14)' }}
            animate={{ rotate: -360 }}
            transition={{ duration: 22, repeat: Infinity, ease: 'linear' }} />
        </>
      )}

      {/* Pulse emitted on poke. Keyed so each poke restarts it cleanly. */}
      {poked > 0 && !reduce && (
        <motion.span key={poked} aria-hidden
          className="pointer-events-none absolute rounded-full border-2"
          style={{ inset: size * 0.2, borderColor: ring }}
          initial={{ scale: 0.7, opacity: 0.75 }}
          animate={{ scale: 2.1, opacity: 0 }}
          transition={{ duration: 0.9, ease: 'easeOut' }} />
      )}

      <motion.button
        type="button"
        onClick={poke}
        aria-label="The Sentinel. Poke it."
        className="relative grid place-items-center rounded-full outline-none
          focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-4 focus-visible:ring-offset-bg"
        style={{ width: size * 0.78, height: size * 0.78 }}
        animate={reduce ? {} : { y: [0, -5, 0] }}
        transition={{ duration: 6.5, repeat: Infinity, ease: 'easeInOut' }}
        whileHover={reduce ? {} : { scale: 1.05 }}
        whileTap={reduce ? {} : { scale: 0.94 }}>

        <svg viewBox="0 0 120 120" width="100%" height="100%" aria-hidden>
          <defs>
            <radialGradient id="sentinel-iris" cx="50%" cy="45%" r="60%">
              <stop offset="0%" stopColor="rgb(var(--accent))" stopOpacity="0.95" />
              <stop offset="70%" stopColor="rgb(var(--accent))" stopOpacity="0.45" />
              <stop offset="100%" stopColor="rgb(var(--accent))" stopOpacity="0.12" />
            </radialGradient>
            <clipPath id="sentinel-lid">
              <path d="M8 60C8 60 30 26 60 26C90 26 112 60 112 60C112 60 90 94 60 94C30 94 8 60 8 60Z" />
            </clipPath>
          </defs>

          {/* Sclera */}
          <path d="M8 60C8 60 30 26 60 26C90 26 112 60 112 60C112 60 90 94 60 94C30 94 8 60 8 60Z"
            fill="rgb(var(--surface))" stroke={ring} strokeWidth="1.6" strokeOpacity="0.75" />

          <g clipPath="url(#sentinel-lid)">
            <motion.g style={{ x: irisX, y: irisY }}>
              <circle cx="60" cy="60" r="23" fill="url(#sentinel-iris)" />
              <circle cx="60" cy="60" r="23" fill="none" stroke={ring} strokeWidth="1.1" strokeOpacity="0.55" />
            </motion.g>
            <motion.g style={{ x: pupilX, y: pupilY }}>
              <motion.circle cx="60" cy="60" fill="rgb(var(--bg))"
                animate={{ r: near && !reduce ? 12.5 : 9.5 }}
                transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }} />
            </motion.g>
            <motion.circle cx="53" cy="52" r="4" fill="rgb(var(--heading))" fillOpacity="0.85"
              style={{ x: glintX, y: glintY }} />

            {/* The lid. Sweeps down on a blink. */}
            <motion.rect x="0" y="0" width="120" fill="rgb(var(--panel))"
              initial={false}
              animate={{ height: lidShut ? 120 : 0 }}
              transition={{ duration: 0.09, ease: 'easeOut' }} />
          </g>

          <path d="M8 60C8 60 30 26 60 26C90 26 112 60 112 60C112 60 90 94 60 94C30 94 8 60 8 60Z"
            fill="none" stroke={ring} strokeWidth="2" strokeOpacity="0.9" strokeLinecap="round" />
        </svg>
      </motion.button>
    </div>
  )
}

/** Lines the Sentinel says. Short, dry, and in Morpheus's voice rather than a chatbot's. */
export const SENTINEL_LINES = [
  'I see everything in here. That is the job.',
  'Nobody is listening but me.',
  'Poke me again. I have nothing else on.',
  'The gate held while you were away.',
  'Ask me something they would not answer.',
  'I do not soften things. You knew that.',
  'Still watching. Always watching.',
  'Your secrets are heavier than most.',
]
