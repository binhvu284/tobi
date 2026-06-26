import { motion, type HTMLMotionProps } from 'framer-motion'
import { useReducedMotionPref } from '../../context/MotionProvider'

type Props = HTMLMotionProps<'button'> & { className?: string }

/**
 * Primary-action button with a border-trace / light sweep on hover and a 0.96
 * press scale (Decision #13). The sweep is a pseudo-element (transform/opacity),
 * disabled under reduced/off by the `[data-motion]` guard; press-scale stays tiny.
 */
export default function TraceButton({ children, className = '', ...rest }: Props) {
  const level = useReducedMotionPref()
  return (
    <motion.button
      whileTap={level === 'off' ? undefined : { scale: 0.96 }}
      className={`trace-btn ${className}`}
      {...rest}
    >
      {children}
    </motion.button>
  )
}
