import { type CSSProperties } from 'react'

/**
 * Per-page accent atmosphere (Decision #12): a faint themed glow + grid drifting
 * behind page content. Pointer-events-none, transform/opacity only, lazy & cheap.
 * `tone` is any CSS color (defaults to the live theme accent). The drift loop is
 * neutralized under reduced/off by the `[data-motion]` CSS guard.
 */
export default function AmbientField({
  tone = 'rgb(var(--accent))',
  variant = 'both',
  className = '',
}: {
  tone?: string
  variant?: 'glow' | 'grid' | 'both'
  className?: string
}) {
  return (
    <div aria-hidden className={`ambient-field ${className}`} style={{ '--ambient': tone } as CSSProperties}>
      {(variant === 'glow' || variant === 'both') && <span className="ambient-glow" />}
      {(variant === 'grid' || variant === 'both') && <span className="ambient-grid" />}
    </div>
  )
}
