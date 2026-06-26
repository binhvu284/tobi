import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Brain, Check } from 'lucide-react'
import { useReducedMotionPref } from '../../context/MotionProvider'

const NOUN = (n: number) => (n === 1 ? 'memory' : 'memories')

/**
 * Brain "neural ingestion" (queue #6, signature effect #1). While the import
 * parses, glyph particles stream into a glowing brain orb under a live typed log
 * of the real pipeline stages + an animated progress bar. When the real extracted
 * count returns it settles to a success state, then hands off to card review.
 * Reduced/off ⇒ plain progress bar + log, no particles or pulse.
 */
export default function NeuralIngestion({ filename, result, onReveal }: {
  filename: string
  /** extracted item count once parse resolves; null while in-flight */
  result: number | null
  /** called shortly after the count arrives to reveal the card list */
  onReveal: () => void
}) {
  const level = useReducedMotionPref()
  const reduced = level !== 'full'
  const pre = useMemo(() => [`Reading ${filename}…`, 'Parsing structure…', 'Extracting memories…'], [filename])
  const [lines, setLines] = useState<string[]>([pre[0]])
  const revealed = useRef(false)
  const done = result != null

  // Advance the pre-result stages on a timer; park on the last "extracting" line.
  useEffect(() => {
    setLines([pre[0]])
    let i = 0
    const id = setInterval(() => {
      i += 1
      if (i < pre.length) setLines(pre.slice(0, i + 1))
      else clearInterval(id)
    }, reduced ? 140 : 560)
    return () => clearInterval(id)
  }, [pre, reduced])

  // When the real count arrives: append completion lines, then hand off to review.
  useEffect(() => {
    if (result == null || revealed.current) return
    revealed.current = true
    const full = [...pre, `✓ Extracted ${result} ${NOUN(result)}`, 'Deduping & matching…', 'Ready to review']
    const ts: ReturnType<typeof setTimeout>[] = []
    ts.push(setTimeout(() => setLines(full.slice(0, pre.length + 1)), reduced ? 0 : 140))
    ts.push(setTimeout(() => setLines(full.slice(0, pre.length + 2)), reduced ? 0 : 380))
    ts.push(setTimeout(() => setLines(full), reduced ? 0 : 620))
    ts.push(setTimeout(onReveal, reduced ? 160 : 1050))
    return () => ts.forEach(clearTimeout)
  }, [result, pre, reduced, onReveal])

  const particles = useMemo(
    () =>
      Array.from({ length: 16 }).map((_, i) => {
        const angle = (i / 16) * Math.PI * 2 + (i % 2 ? 0.4 : 0)
        const r = 80 + (i % 4) * 14
        return { i, sx: Math.cos(angle) * r, sy: Math.sin(angle) * r, dur: 1.6 + (i % 5) * 0.22, delay: (i % 8) * 0.16 }
      }),
    [],
  )

  return (
    <div className="flex flex-col items-center gap-4 py-6">
      {/* orb + converging particle field */}
      <div className="relative flex h-44 w-full items-center justify-center overflow-hidden">
        {!reduced && particles.map(p => (
          <motion.span key={p.i} aria-hidden
            className="absolute left-1/2 top-1/2 h-1.5 w-1.5 rounded-full"
            style={{ marginLeft: -3, marginTop: -3, background: 'rgb(var(--accent))', filter: 'drop-shadow(0 0 4px rgb(var(--accent)))' }}
            initial={{ x: p.sx, y: p.sy, opacity: 0, scale: 0.4 }}
            animate={done ? { x: 0, y: 0, opacity: 0, scale: 0.2 } : { x: 0, y: 0, opacity: [0, 1, 0], scale: [0.4, 1, 0.3] }}
            transition={done ? { duration: 0.4 } : { duration: p.dur, repeat: Infinity, delay: p.delay, ease: 'easeIn' }} />
        ))}
        {/* glow */}
        <motion.span aria-hidden className="absolute h-28 w-28 rounded-full"
          style={{ background: 'radial-gradient(circle, rgb(var(--purple) / 0.55), transparent 65%)', filter: 'blur(8px)' }}
          animate={reduced ? { opacity: 0.5 } : { scale: done ? 1.1 : [1, 1.18, 1], opacity: done ? 0.75 : [0.45, 0.8, 0.45] }}
          transition={reduced ? undefined : { duration: 1.7, repeat: done ? 0 : Infinity, ease: 'easeInOut' }} />
        {/* core */}
        <motion.div
          className={`relative flex h-16 w-16 items-center justify-center rounded-full border ${done ? 'border-success/60 bg-success/15 text-success' : 'border-purple/50 bg-purple/15 text-purple'}`}
          animate={reduced || done ? {} : { scale: [1, 1.06, 1] }} transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}>
          {done ? <Check size={26} /> : <Brain size={26} />}
        </motion.div>
      </div>

      {/* progress bar — indeterminate while parsing, settles full on done */}
      <div className="w-full max-w-sm">
        {done ? (
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-border/40">
            <motion.div className="h-full rounded-full bg-gradient-to-r from-purple to-accent"
              initial={{ width: reduced ? '100%' : '0%' }} animate={{ width: '100%' }} transition={{ duration: reduced ? 0 : 0.5, ease: 'easeOut' }} />
          </div>
        ) : (
          <div className="tobi-runbar h-1.5 w-full" style={{ background: 'rgb(var(--border) / 0.4)' }} />
        )}
      </div>

      {/* live typed log */}
      <div className="w-full max-w-sm space-y-1 font-mono text-[11px]">
        {lines.map((ln, i) => {
          const last = i === lines.length - 1
          const ok = ln.startsWith('✓')
          return (
            <motion.div key={ln} initial={{ opacity: 0, x: reduced ? 0 : -6 }} animate={{ opacity: 1, x: 0 }}
              className={`flex items-center gap-1.5 ${ok ? 'text-success' : last && !done ? 'text-text' : 'text-muted'}`}>
              <span className="text-accent/70">›</span>
              <span>{ln}</span>
              {last && !done && !reduced && <span className="chat-caret ml-0.5 inline-block h-3 w-[2px] bg-accent align-middle" />}
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
