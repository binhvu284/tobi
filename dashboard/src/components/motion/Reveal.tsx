import { motion, type HTMLMotionProps } from 'framer-motion'
import { useReducedMotionPref } from '../../context/MotionProvider'
import { DUR, EASE } from '../../lib/motion'

type Props = Omit<HTMLMotionProps<'div'>, 'initial' | 'animate'> & {
  /** Reveal when scrolled into view (whileInView) instead of immediately on mount. */
  onView?: boolean
  /** Entrance delay (seconds). */
  delay?: number
  /** Slide distance (px). */
  y?: number
}

/**
 * Standalone entrance: fade + slide-up. With `onView`, becomes a reveal-on-scroll.
 * Degrades to opacity-only (reduced) or instant (off). For orchestrated cascades
 * use <Stagger> + <StaggerItem> instead.
 */
export default function Reveal({ onView, delay = 0, y = 10, children, ...rest }: Props) {
  const level = useReducedMotionPref()
  const hidden = level === 'off' ? { opacity: 1 } : level === 'reduced' ? { opacity: 0 } : { opacity: 0, y }
  const shown =
    level === 'off'
      ? { opacity: 1 }
      : { opacity: 1, y: 0, transition: { duration: DUR.md, ease: EASE.out, delay } }
  const anim = onView
    ? { initial: hidden, whileInView: shown, viewport: { once: true, margin: '-10% 0px' } }
    : { initial: hidden, animate: shown }
  return (
    <motion.div {...anim} {...rest}>
      {children}
    </motion.div>
  )
}
