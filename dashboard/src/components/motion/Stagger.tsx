import { motion, type HTMLMotionProps } from 'framer-motion'
import { useReducedMotionPref } from '../../context/MotionProvider'
import { staggerParent, staggerChild } from '../../lib/motion'

type ParentProps = Omit<HTMLMotionProps<'div'>, 'variants' | 'initial' | 'animate'> & {
  /** Per-child cascade step (seconds). */
  step?: number
}

/** Parent that cascades its <StaggerItem> children top-down (header → stats → cards). */
export function Stagger({ step = 0.045, children, ...rest }: ParentProps) {
  const level = useReducedMotionPref()
  return (
    <motion.div variants={staggerParent(level, step)} initial="hidden" animate="show" {...rest}>
      {children}
    </motion.div>
  )
}

type ItemProps = Omit<HTMLMotionProps<'div'>, 'variants'> & { y?: number }

/** A single cascading child of <Stagger>. */
export function StaggerItem({ y = 10, children, ...rest }: ItemProps) {
  const level = useReducedMotionPref()
  return (
    <motion.div variants={staggerChild(level, y)} {...rest}>
      {children}
    </motion.div>
  )
}

export default Stagger
