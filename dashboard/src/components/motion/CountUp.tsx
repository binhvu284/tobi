import { useEffect, useRef, useState } from 'react'
import { animate } from 'framer-motion'
import { useReducedMotionPref } from '../../context/MotionProvider'
import { EASE } from '../../lib/motion'

/**
 * Animates a numeric value old→new and flashes the accent on change (Decision #18).
 * Off ⇒ snaps instantly; reduced ⇒ fast tween. Optional `format` for separators/units.
 */
export default function CountUp({
  value,
  decimals = 0,
  prefix = '',
  suffix = '',
  format,
  duration,
  className = '',
}: {
  value: number
  decimals?: number
  prefix?: string
  suffix?: string
  format?: (v: number) => string
  duration?: number
  className?: string
}) {
  const level = useReducedMotionPref()
  const ref = useRef<HTMLSpanElement>(null)
  const prev = useRef(value)
  const [flash, setFlash] = useState(false)
  const render = (v: number) => `${prefix}${format ? format(v) : v.toFixed(decimals)}${suffix}`

  useEffect(() => {
    const node = ref.current
    const from = prev.current
    const to = value
    prev.current = to
    if (!node) return
    if (from === to) return

    let flashTimer: ReturnType<typeof setTimeout> | undefined
    if (level !== 'off') {
      setFlash(true)
      flashTimer = setTimeout(() => setFlash(false), 600)
    }
    if (level === 'off') {
      node.textContent = render(to)
      return () => { if (flashTimer) clearTimeout(flashTimer) }
    }
    const controls = animate(from, to, {
      duration: duration ?? (level === 'reduced' ? 0.2 : 0.7),
      ease: EASE.out,
      onUpdate: v => { node.textContent = render(v) },
    })
    return () => {
      controls.stop()
      if (flashTimer) clearTimeout(flashTimer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, level])

  return (
    <span ref={ref} className={`${flash ? 'count-flash' : ''} ${className}`}>
      {render(value)}
    </span>
  )
}
