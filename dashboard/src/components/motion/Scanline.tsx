import { useReducedMotionPref } from '../../context/MotionProvider'

/**
 * One-shot HUD scanline sweep (top→bottom). Pure CSS keyframe (transform/opacity).
 * Self-removes from the layout under reduced/off via the `[data-motion]` guard.
 */
export default function Scanline({ className = '' }: { className?: string }) {
  const level = useReducedMotionPref()
  if (level !== 'full') return null
  return <span aria-hidden className={`page-scanline ${className}`} />
}
