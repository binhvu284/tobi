import { type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { useReducedMotionPref } from '../../context/MotionProvider'
import { panelBoot } from '../../lib/motion'
import Scanline from './Scanline'

/**
 * The route-level HUD "panel boot": fade + 8px slide-up + a one-shot scanline
 * sweep on mount. Keyed by pathname upstream so every navigation replays it.
 * Children that opt into <Stagger>/<Reveal> cascade on top.
 */
export default function PageBoot({ children, className = '' }: { children: ReactNode; className?: string }) {
  const level = useReducedMotionPref()
  return (
    <motion.div variants={panelBoot(level)} initial="hidden" animate="show" className={`relative h-full ${className}`}>
      <Scanline />
      {children}
    </motion.div>
  )
}
