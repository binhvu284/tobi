import { motion } from 'framer-motion'

/**
 * Unified loading effect used across every page.
 * A glowing dual-ring orbit with a pulsing accent core — synced everywhere
 * via the shared `.tobi-loader*` classes in index.css (theme-aware).
 */
export default function Loader({
  label,
  full = false,
  size = 40,
  className = '',
}: {
  label?: string
  full?: boolean
  size?: number
  className?: string
}) {
  const spinner = (
    <motion.div
      initial={{ opacity: 0, scale: 0.92 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="flex flex-col items-center justify-center gap-3"
    >
      <div className="tobi-loader" style={{ width: size, height: size }}>
        <span className="tobi-loader-ring" />
        <span className="tobi-loader-ring tobi-loader-ring--2" />
        <span className="tobi-loader-core" />
      </div>
      {label && (
        <div className="tobi-loader-label text-xs font-medium tracking-wide text-muted">{label}</div>
      )}
    </motion.div>
  )

  return (
    <div className={`flex ${full ? 'h-full w-full' : ''} items-center justify-center p-6 ${className}`}>
      {spinner}
    </div>
  )
}
