import { useRef, type ReactNode, type PointerEvent } from 'react'

/**
 * Card wrapper with a cursor-follow radial glow (Decision #14). Updates the
 * `--mx/--my` CSS vars on pointermove; the glow is a pseudo-element (opacity
 * only, no layout cost). Hidden under reduced/off by the `[data-motion]` guard.
 */
export default function SpotlightCard({
  children,
  className = '',
  onClick,
  title,
}: {
  children: ReactNode
  className?: string
  onClick?: () => void
  title?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    el.style.setProperty('--mx', `${e.clientX - r.left}px`)
    el.style.setProperty('--my', `${e.clientY - r.top}px`)
  }
  return (
    <div ref={ref} onPointerMove={onMove} onClick={onClick} title={title} className={`spotlight-card ${className}`}>
      {children}
    </div>
  )
}
