// The neuron head: the memory graph on a canvas, under the instrument rings. Fixed at the
// top of the console, it never scrolls away. The graph answers to the same state the status
// line does: still when nothing is happening, and the plate turns the other way while he is
// taking sound in.
import { useEffect, useRef } from 'react'
import { advance, ensureBuilt, paint, type BrainState, type Panel } from './brain'
import type { Mood } from './model'

const C = 2 * Math.PI * 118   // the context ring's circumference

export function Neuron({ variant, mood = 'idle', ctxPct = 0, label, still }: {
  variant: BrainState; mood?: Mood; ctxPct?: number; label: string; still: boolean
}) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const el = ref.current
    const ctx = el?.getContext('2d')
    if (!el || !ctx) return
    ensureBuilt()
    const panel: Panel = { ctx, W: 0, H: 0, CX: 0, CY: 0, R: 0 }
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const box = el.getBoundingClientRect()
      panel.W = box.width; panel.H = box.height
      el.width = Math.round(panel.W * dpr); el.height = Math.round(panel.H * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      panel.CX = panel.W / 2; panel.CY = panel.H / 2; panel.R = Math.min(panel.W, panel.H) * 0.375
    }
    const bootStart = variant === 'booting' ? performance.now() / 1000 : 0
    let raf = 0
    const frame = (ts: number) => {
      const t = still ? 1.0 : ts * 0.001
      advance(t)
      if (panel.W > 8) paint(panel, variant, t, still, bootStart)   // a hidden state has nothing to draw into
      if (!still) raf = requestAnimationFrame(frame)
    }
    resize()
    raf = requestAnimationFrame(frame)
    const ro = new ResizeObserver(() => { resize(); if (still) paint(panel, variant, 1.0, true, bootStart) })
    ro.observe(el)
    return () => { cancelAnimationFrame(raf); ro.disconnect() }
  }, [variant, still])

  const cls = variant === 'live' ? `neuron s-${mood}` : `neuron ${variant}`
  const on = Math.max(0, Math.min(100, ctxPct)) / 100
  const ang = (-90 + 360 * on) * Math.PI / 180
  const ex = 144 + 118 * Math.cos(ang), ey = 144 + 118 * Math.sin(ang)

  return (
    <div className={cls} role="img" aria-label={label}>
      <span className="disc" aria-hidden="true" />
      <span className="sweep" aria-hidden="true" />
      <canvas ref={ref} className="brain" data-state={variant} aria-hidden="true" />
      {variant === 'asleep' && (
        <svg viewBox="0 0 288 288">
          <defs>
            <radialGradient id="ui2-bloom-asleep" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#58a6ff" stopOpacity=".06" />
              <stop offset="52%" stopColor="#58a6ff" stopOpacity=".02" />
              <stop offset="100%" stopColor="#58a6ff" stopOpacity="0" />
            </radialGradient>
            <filter id="ui2-halo-asleep" x="-90%" y="-90%" width="280%" height="280%"><feGaussianBlur stdDeviation="9" /></filter>
          </defs>
          <circle cx="144" cy="144" r="142" fill="url(#ui2-bloom-asleep)" />
          <circle cx="144" cy="144" r="118" fill="none" stroke="#58a6ff" strokeOpacity=".06" />
          <circle className="n-bezel" cx="144" cy="144" r="129" fill="none" stroke="#58a6ff" strokeOpacity=".13"
            strokeWidth="4" strokeDasharray="1.1 7.35" style={{ transformOrigin: '144px 144px' }} />
          <circle cx="144" cy="144" r="118" fill="none" stroke="#232b35" strokeWidth="2.5" />
          <circle className="n-glow" cx="144" cy="144" r="22" fill="#58a6ff" opacity=".22" filter="url(#ui2-halo-asleep)" />
        </svg>
      )}
      {variant === 'booting' && (
        <svg viewBox="0 0 288 288">
          <defs>
            <radialGradient id="ui2-bloom-booting" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#58a6ff" stopOpacity=".16" />
              <stop offset="52%" stopColor="#58a6ff" stopOpacity=".04" />
              <stop offset="100%" stopColor="#58a6ff" stopOpacity="0" />
            </radialGradient>
            <filter id="ui2-halo-booting" x="-90%" y="-90%" width="280%" height="280%"><feGaussianBlur stdDeviation="9" /></filter>
          </defs>
          <circle cx="144" cy="144" r="142" fill="url(#ui2-bloom-booting)" />
          <circle cx="144" cy="144" r="118" fill="none" stroke="#58a6ff" strokeOpacity=".1" />
          <circle className="n-bezel" cx="144" cy="144" r="129" fill="none" stroke="#58a6ff" strokeOpacity=".2"
            strokeWidth="4" strokeDasharray="1.1 7.35" style={{ transformOrigin: '144px 144px' }} />
          <circle cx="144" cy="144" r="118" fill="none" stroke="#232b35" strokeWidth="2.5" />
          <circle cx="144" cy="144" r="118" fill="none" stroke="#58a6ff" strokeWidth="3" strokeLinecap="round"
            strokeDasharray="22 700.7" transform="rotate(-90 144 144)" />
          <circle className="n-glow" cx="144" cy="144" r="22" fill="#58a6ff" opacity=".22" filter="url(#ui2-halo-booting)" />
        </svg>
      )}
      {variant === 'live' && (
        <svg viewBox="0 0 288 288">
          <defs>
            <radialGradient id="ui2-bloom" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#58a6ff" stopOpacity=".20" />
              <stop offset="52%" stopColor="#58a6ff" stopOpacity=".05" />
              <stop offset="100%" stopColor="#58a6ff" stopOpacity="0" />
            </radialGradient>
            <filter id="ui2-halo" x="-90%" y="-90%" width="280%" height="280%"><feGaussianBlur stdDeviation="9" /></filter>
            <filter id="ui2-glow" x="-70%" y="-70%" width="240%" height="240%">
              <feGaussianBlur stdDeviation="2.6" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          <circle cx="144" cy="144" r="142" fill="url(#ui2-bloom)" />
          <circle cx="144" cy="144" r="118" fill="none" stroke="#58a6ff" strokeOpacity=".12" />
          {/* instrument bezel: hairline ticks, turning slowly against the sweep */}
          <circle className="n-bezel" cx="144" cy="144" r="129" fill="none" stroke="#58a6ff" strokeOpacity=".26"
            strokeWidth="4" strokeDasharray="1.1 7.35" style={{ transformOrigin: '144px 144px' }} />
          {/* context: the track, then what is actually used, with a lit endpoint */}
          <circle cx="144" cy="144" r="118" fill="none" stroke="#232b35" strokeWidth="2.5" />
          <circle className="n-ring-lit" cx="144" cy="144" r="118" fill="none" stroke="#58a6ff" strokeWidth="2.5" filter="url(#ui2-glow)" />
          <circle cx="144" cy="144" r="118" fill="none" stroke="#58a6ff" strokeWidth="3" strokeLinecap="round"
            strokeDasharray={`${(C * on).toFixed(1)} ${(C - C * on).toFixed(1)}`} transform="rotate(-90 144 144)" />
          {on > 0 && <circle cx={ex.toFixed(1)} cy={ey.toFixed(1)} r="3.4" fill="#bcdcff" filter="url(#ui2-glow)" />}
          {/* the core reads as a bloom over the densest cluster, not an object */}
          <circle className="n-glow" cx="144" cy="144" r="22" fill="#58a6ff" opacity=".38" filter="url(#ui2-halo)" />
        </svg>
      )}
    </div>
  )
}
