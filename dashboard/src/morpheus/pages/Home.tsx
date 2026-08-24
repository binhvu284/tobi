// Home: arrival, and the only page in Morpheus allowed to enjoy itself.
//
// Everywhere else earns its pixels. Here the job is different: this is the moment the owner
// lands after crossing the gate, and it should feel like somewhere worth being.
//
// Three ideas carry the design, and each is structural rather than decorative:
//
//   1. It knows the hour. Morpheus is an after-dark instrument, so the page reads the clock and
//      changes: the arc above the greeting shows where you are in the day, the phase is named,
//      and the greeting itself is drawn from lines that suit the hour. Opening it at 03:00 is a
//      visibly different experience from opening it at noon, which no static page can be.
//   2. It has depth. Four layers drift against each other as the cursor moves, on motion values
//      so nothing re-renders. The parallax is small on purpose; you feel it before you see it.
//   3. It is composed, not gridded. The vitals are hairline-separated figures rather than four
//      boxes, and the capabilities are one featured card against a quiet list. Equal cards in an
//      even grid is the arrangement every generated dashboard reaches for first.
//
// Everything animated here is transform or opacity. No blur filters, no blend modes: both have
// already frozen this app's renderer once.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  motion, useMotionValue, useSpring, useTransform, useReducedMotion, type MotionValue,
} from 'framer-motion'
import {
  ArrowUp, ShieldAlert, Check, Lock, ScanSearch, Fingerprint, EyeOff, Radio,
} from 'lucide-react'
import { useMorpheus } from '../MorpheusSession'
import { Btn, Rise } from '../ui'
import { Sentinel, SENTINEL_LINES } from '../Mascot'

/* ── The hour ──────────────────────────────────────────────────────────── */

type Phase = { key: string; label: string; greetings: string[] }

function phaseFor(h: number): Phase {
  if (h < 5) return { key: 'small-hours', label: 'The small hours', greetings: [
    'Welcome back, Thomas. Ready to cook?',
    'The city is asleep. You are not.',
    'Nothing is watching at this hour but me.',
  ] }
  if (h < 8) return { key: 'before-dawn', label: 'Before dawn', greetings: [
    'Early, Thomas. What are we opening?',
    'Ahead of the day again.',
    'The quiet part of the morning is yours.',
  ] }
  if (h < 12) return { key: 'morning', label: 'Morning', greetings: [
    'Morning, Thomas. Where do we start?',
    'A clean slate. What is first?',
  ] }
  if (h < 17) return { key: 'afternoon', label: 'Afternoon', greetings: [
    'Back in, Thomas. What needs looking at?',
    'Everything here is yours. Where do we start?',
  ] }
  if (h < 21) return { key: 'evening', label: 'Evening', greetings: [
    'Evening, Thomas. The gate is sealed behind you.',
    'Good hour for the work nobody else sees.',
  ] }
  return { key: 'after-dark', label: 'After dark', greetings: [
    'After dark, Thomas. Just you and the work.',
    'No filters, no watchers. Ready to cook?',
    'Back in the dark, where the good work happens.',
  ] }
}

/**
 * A thin arc showing where the current moment sits in the day, with a marker on it.
 *
 * The one piece of pure ornament on the page, and it earns its place by carrying information the
 * greeting only implies. Night is drawn heavier than day, because this is a night instrument.
 */
function DayArc({ now }: { now: Date }) {
  const reduce = useReducedMotion()
  const frac = (now.getHours() * 60 + now.getMinutes()) / 1440
  const W = 168, H = 34, R = 150
  // A shallow arc: wide and barely curved reads as an horizon, not as a gauge.
  const path = `M 9 ${H - 5} A ${R} ${R} 0 0 1 ${W - 9} ${H - 5}`
  const ref = useRef<SVGPathElement>(null)
  const [pt, setPt] = useState<{ x: number; y: number } | null>(null)

  useEffect(() => {
    const p = ref.current
    if (!p) return
    const len = p.getTotalLength()
    const at = p.getPointAtLength(len * frac)
    setPt({ x: at.x, y: at.y })
  }, [frac])

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden className="overflow-visible">
      <defs>
        <linearGradient id="arc-day" x1="0" x2="1">
          <stop offset="0%" stopColor="rgb(var(--accent))" stopOpacity="0.55" />
          <stop offset="42%" stopColor="rgb(var(--muted))" stopOpacity="0.22" />
          <stop offset="100%" stopColor="rgb(var(--accent))" stopOpacity="0.55" />
        </linearGradient>
      </defs>
      <path ref={ref} d={path} fill="none" stroke="url(#arc-day)" strokeWidth="1" strokeLinecap="round" />
      {pt && (
        <>
          <motion.circle cx={pt.x} cy={pt.y} r="6" fill="rgb(var(--accent))" fillOpacity="0.14"
            animate={reduce ? {} : { r: [5, 8, 5], fillOpacity: [0.16, 0.05, 0.16] }}
            transition={{ duration: 4.5, repeat: Infinity, ease: 'easeInOut' }} />
          <circle cx={pt.x} cy={pt.y} r="2.4" fill="rgb(var(--accent))" />
        </>
      )}
    </svg>
  )
}

/* ── Depth ─────────────────────────────────────────────────────────────── */

/** Cursor parallax, shared by every ambient layer. Motion values only: zero re-renders. */
function useParallax() {
  const mx = useMotionValue(0)
  const my = useMotionValue(0)
  const x = useSpring(mx, { stiffness: 60, damping: 20, mass: 0.6 })
  const y = useSpring(my, { stiffness: 60, damping: 20, mass: 0.6 })
  const reduce = useReducedMotion()

  useEffect(() => {
    if (reduce) return
    const onMove = (e: PointerEvent) => {
      mx.set((e.clientX / window.innerWidth - 0.5) * 2)
      my.set((e.clientY / window.innerHeight - 0.5) * 2)
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    return () => window.removeEventListener('pointermove', onMove)
  }, [mx, my, reduce])

  return { x, y }
}

function Layer({ x, y, depth, className, style }: {
  x: MotionValue<number>; y: MotionValue<number>; depth: number
  className?: string; style?: React.CSSProperties
}) {
  const tx = useTransform(x, v => v * depth)
  const ty = useTransform(y, v => v * depth * 0.6)
  return <motion.div aria-hidden className={className} style={{ ...style, x: tx, y: ty }} />
}

/* ── Material ──────────────────────────────────────────────────────────── */

/**
 * A card lit by the cursor.
 *
 * The highlight follows the pointer as a CSS variable written straight to the node, so a moving
 * mouse never enters the React render cycle. Paired with a one-pixel top highlight, it reads as
 * a lit surface rather than a rectangle with a border, which is most of the difference between
 * a panel that looks expensive and one that does not.
 */
function Lit({ children, className = '', as = 'div' }: {
  children: React.ReactNode; className?: string; as?: 'div' | 'button'
}) {
  const ref = useRef<HTMLDivElement>(null)
  const reduce = useReducedMotion()

  const track = useCallback((e: React.PointerEvent) => {
    if (reduce) return
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    el.style.setProperty('--mx', `${((e.clientX - r.left) / r.width) * 100}%`)
    el.style.setProperty('--my', `${((e.clientY - r.top) / r.height) * 100}%`)
  }, [reduce])

  const Tag = as as 'div'
  return (
    <Tag ref={ref} onPointerMove={track}
      className={`morph-lift group/lit relative overflow-hidden rounded-card border border-border
        bg-surface/50 hover:border-accent/35 hover:bg-surface/70 ${className}`}
      style={{ ['--mx' as string]: '50%', ['--my' as string]: '0%' }}>
      {/* Cursor light. Fades in slowly and out slowly, so it never snaps at the edges. */}
      <span aria-hidden className="pointer-events-none absolute inset-0 opacity-0 group-hover/lit:opacity-100"
        style={{
          background: 'radial-gradient(340px circle at var(--mx) var(--my), rgb(var(--accent) / 0.10), transparent 70%)',
          transition: 'opacity var(--t-slow) var(--ease)',
        }} />
      {/* Top highlight: the edge catching light. One pixel, and it does more than any shadow. */}
      <span aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{ background: 'linear-gradient(90deg, transparent, rgb(255 255 255 / 0.09), transparent)' }} />
      <span className="relative block">{children}</span>
    </Tag>
  )
}

/* ── Vitals ────────────────────────────────────────────────────────────── */

function useCountUp(target: number, ms = 1100) {
  const [n, setN] = useState(0)
  const reduce = useReducedMotion()
  useEffect(() => {
    if (reduce) { setN(target); return }
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / ms)
      setN(Math.round(target * (1 - Math.pow(1 - p, 4))))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    // requestAnimationFrame does not run in a background tab. A stalled animation is cosmetic;
    // a figure frozen at zero is a lie, so the true value is guaranteed either way.
    const settle = window.setTimeout(() => setN(target), ms + 150)
    return () => { cancelAnimationFrame(raf); window.clearTimeout(settle) }
  }, [target, ms, reduce])
  return n
}

function Vital({ label, value, unit, note, tone = 'default' }: {
  label: string; value: number; unit?: string; note: string; tone?: 'default' | 'danger'
}) {
  const n = useCountUp(value)
  return (
    <div className="group/v relative px-5 py-1 first:pl-0 last:pr-0">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted/80">{label}</p>
      <p className="mt-2.5 flex items-baseline gap-1">
        <span className={`font-display text-[30px] font-medium leading-none tracking-[-0.03em] tabular-nums
          transition-colors duration-300 ${tone === 'danger' ? 'text-danger' : 'text-heading'}`}>{n}</span>
        {unit && <span className="text-[12.5px] text-muted">{unit}</span>}
      </p>
      <p className="mt-2 text-[11.5px] leading-snug text-muted">{note}</p>
    </div>
  )
}

/* ── Capabilities ──────────────────────────────────────────────────────── */

type Cap = { id: string; name: string; body: string; Icon: typeof Radio; got: boolean }

const FEATURED: Cap = {
  id: 'model', name: 'No provider filter', Icon: Radio, got: true,
  body: 'Every answer comes from a model running on your own hardware. Nothing is softened on the '
    + 'way out, nothing is sent anywhere, and no policy you did not write applies.',
}

const REST: Cap[] = [
  { id: 'gate', name: 'One owner, one gate', Icon: Lock, got: true,
    body: 'Password, code and hardware key. Past it, nothing is hidden from you.' },
  { id: 'crypt', name: 'Unreadable on disk', Icon: Lock, got: true,
    body: 'A copied database file is worthless without you.' },
  { id: 'osint', name: 'Object profiler', Icon: ScanSearch, got: true,
    body: 'A cited profile of any target, from public sources.' },
  { id: 'watch', name: 'Entry forensics', Icon: Fingerprint, got: true,
    body: 'Every attempt recorded in enough detail to know whether it was you.' },
  { id: 'recovery', name: 'Recovery method', Icon: EyeOff, got: false,
    body: 'Your own private way back in. Still to be designed.' },
]

const ALL_CAPS = [FEATURED, ...REST]

/* ── Page ──────────────────────────────────────────────────────────────── */

export default function Home() {
  const { models, intrusions, objects, access } = useMorpheus()
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const { x, y } = useParallax()

  const [draft, setDraft] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  const [say, setSay] = useState<string | null>(null)
  const sayTimer = useRef<number | undefined>(undefined)

  // The clock, kept live so the arc and the phase stay honest across a long session.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(id)
  }, [])

  const phase = useMemo(() => phaseFor(now.getHours()), [now.getHours()])
  const greeting = useMemo(
    () => phase.greetings[Math.floor(Math.random() * phase.greetings.length)],
    [phase.key])

  const active = models.find(m => m.active)
  const interrupt = intrusions.length > 0 && !acknowledged
  const sources = objects.reduce((n, o) => n + o.sources, 0)
  const held = access.filter(a => !a.ok).length
  const unlocked = ALL_CAPS.filter(c => c.got).length

  const poke = useCallback(() => {
    setSay(SENTINEL_LINES[Math.floor(Math.random() * SENTINEL_LINES.length)])
    window.clearTimeout(sayTimer.current)
    sayTimer.current = window.setTimeout(() => setSay(null), 3600)
  }, [])
  useEffect(() => () => window.clearTimeout(sayTimer.current), [])

  const ask = () => {
    if (!draft.trim()) return
    navigate(`/morpheus/chat?q=${encodeURIComponent(draft.trim())}`)
  }

  if (interrupt) {
    return (
      <div className="grid h-full place-items-center overflow-y-auto px-7 py-16">
        <Rise className="w-full max-w-xl">
          <div className="rounded-card border border-danger/35 bg-danger/[0.07] px-7 py-8 text-center">
            <div className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-danger/12">
              <ShieldAlert size={19} className="text-danger" />
            </div>
            <h1 className="mt-5 font-display text-[26px] font-semibold leading-tight tracking-[-0.015em] text-heading">
              Someone tried to get in
            </h1>
            <p className="mx-auto mt-3 max-w-sm text-[14px] leading-relaxed text-text/80">
              {intrusions.length} failed {intrusions.length === 1 ? 'attempt' : 'attempts'} since you were
              last here. The gate held, and every detail was recorded.
            </p>
            <div className="mt-7 flex items-center justify-center gap-2.5">
              <Btn variant="primary" onClick={() => navigate('/morpheus/access')}>Read the log</Btn>
              <Btn variant="ghost" onClick={() => setAcknowledged(true)}>Continue</Btn>
            </div>
          </div>
        </Rise>
      </div>
    )
  }

  const clock = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })

  return (
    <div className="relative h-full overflow-y-auto">
      {/* ── Ambient depth. Four planes, each drifting a different amount. ── */}
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <Layer x={x} y={y} depth={-26}
          className="absolute left-1/2 top-[-32%] h-[660px] w-[980px] -translate-x-1/2 rounded-full"
          style={{ background: 'radial-gradient(closest-side, rgb(var(--accent) / 0.14), transparent 72%)' }} />
        <Layer x={x} y={y} depth={14}
          className="absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(rgb(var(--accent) / 0.045) 1px, transparent 1px),'
              + 'linear-gradient(90deg, rgb(var(--accent) / 0.045) 1px, transparent 1px)',
            backgroundSize: '54px 54px',
            maskImage: 'radial-gradient(closest-side at 50% 20%, #000, transparent 76%)',
            WebkitMaskImage: 'radial-gradient(closest-side at 50% 20%, #000, transparent 76%)',
          }} />
        <Layer x={x} y={y} depth={-9}
          className="absolute left-1/2 top-[16%] h-[420px] w-[420px] -translate-x-1/2 rounded-full border"
          style={{ borderColor: 'rgb(var(--accent) / 0.07)' }} />
        <Layer x={x} y={y} depth={22}
          className="absolute inset-x-0 bottom-0 h-[38%]"
          style={{ background: 'radial-gradient(120% 100% at 50% 100%, rgb(var(--accent) / 0.055), transparent 70%)' }} />
      </div>

      <div className="relative mx-auto max-w-[54rem] px-7 pb-16 pt-9">

        {/* ── Hero ─────────────────────────────────────────── */}
        <div className="flex flex-col items-center text-center">
          <Rise>
            <div className="relative">
              <Sentinel mood={intrusions.length ? 'alert' : 'idle'} onPoke={poke} />
              {say && (
                <motion.div
                  initial={{ opacity: 0, y: 6, scale: 0.97 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
                  className="absolute left-1/2 top-full z-10 w-max max-w-[17rem] -translate-x-1/2 translate-y-1
                    rounded-card border border-border bg-panel px-3.5 py-2 text-[12.5px] text-text shadow-popover">
                  {say}
                </motion.div>
              )}
            </div>
          </Rise>

          {/* The hour, drawn. */}
          <Rise delay={0.05}>
            <div className="mt-8 flex flex-col items-center">
              <DayArc now={now} />
              <p className="-mt-1 flex items-center gap-2.5 text-[10.5px] uppercase tracking-[0.26em] text-muted">
                <span className="tabular-nums">{clock}</span>
                <span aria-hidden className="h-3 w-px bg-border" />
                <span>{phase.label}</span>
              </p>
            </div>
          </Rise>

          {/* Headline, arriving a word at a time.
              An earlier version slid the whole line out from behind an `overflow-hidden` mask.
              It looked better on paper and shipped broken: Framer would not animate a percentage
              y-offset here, so the headline sat permanently half-clipped. Numeric offsets are
              what this codebase can rely on, and with no mask there is nothing to clip even if
              the animation never runs. Craft that fails open beats craft that fails shut. */}
          <h1 className="mt-5 max-w-[16ch] font-display text-[40px] font-medium leading-[1.12]
            tracking-[-0.032em] text-heading">
            {greeting.split(' ').map((word, i) => (
              <span key={`${word}-${i}`} className="morph-word"
                style={{ animationDelay: (0.12 + i * 0.045) + 's' }}>
                {word}
                {i < greeting.split(' ').length - 1 && ' '}
              </span>
            ))}
          </h1>

          <Rise delay={0.24} className="mt-8 w-full max-w-lg">
            <Lit className="!bg-surface/70 px-4 py-3 focus-within:border-accent/55">
              <div className="flex items-end gap-2">
                <textarea
                  value={draft}
                  onChange={e => setDraft(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() } }}
                  rows={1} aria-label="Ask Morpheus" placeholder="Ask Morpheus anything."
                  className="max-h-40 min-h-[26px] flex-1 resize-none bg-transparent text-left text-[14.5px]
                    leading-relaxed text-heading outline-none placeholder:text-muted/70" />
                <button onClick={ask} disabled={!draft.trim()} aria-label="Send"
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-btn bg-accent text-bg outline-none
                    transition-all duration-150 hover:bg-accent/90 active:scale-95
                    focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2
                    focus-visible:ring-offset-bg disabled:cursor-not-allowed disabled:opacity-30">
                  <ArrowUp size={15} />
                </button>
              </div>
            </Lit>
          </Rise>

          <Rise delay={0.3}>
            <p className="mt-5 text-[12.5px] text-muted">
              {active
                ? `Running ${active.name} on your machine. It answers without a provider filter.`
                : 'No model is running yet. Open Models to choose one.'}
            </p>
          </Rise>
        </div>

        {/* ── Vitals. Hairline-separated figures, not four boxes. ── */}
        <Rise delay={0.36}>
          <div className="mt-16 grid grid-cols-2 divide-y divide-border/60 border-y border-border/60
            py-6 sm:grid-cols-4 sm:divide-x sm:divide-y-0">
            <Vital label="Objects" value={objects.length} note="in your library" />
            <Vital label="Sources" value={sources} note="gathered and cited" />
            <Vital label="Gate held" value={held} unit={held === 1 ? 'time' : 'times'}
              note={held ? 'nobody got through' : 'no attempts yet'} tone={held ? 'danger' : 'default'} />
            <Vital label="Unlocked" value={unlocked} unit={`of ${ALL_CAPS.length}`} note="capabilities live" />
          </div>
        </Rise>

        {/* ── Capabilities. One featured, the rest quiet. ── */}
        <div className="mt-14">
          <Rise delay={0.42}>
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="font-display text-[19px] font-medium tracking-[-0.018em] text-heading">
                What Morpheus does that TOBI will not
              </h2>
              <span className="shrink-0 text-[11.5px] tabular-nums text-muted">
                {unlocked} of {ALL_CAPS.length}
              </span>
            </div>
          </Rise>

          <div className="mt-6 grid gap-3 lg:grid-cols-5">
            {/* Featured */}
            <Rise delay={0.46} className="lg:col-span-2">
              <Lit className="h-full p-6">
                <span className="grid h-9 w-9 place-items-center rounded-btn bg-accent/12 text-accent">
                  <FEATURED.Icon size={16} />
                </span>
                <p className="mt-4 font-display text-[17px] font-medium tracking-[-0.01em] text-heading">
                  {FEATURED.name}
                </p>
                <p className="mt-2.5 text-[13px] leading-relaxed text-muted">{FEATURED.body}</p>
                <p className="mt-5 flex items-center gap-1.5 text-[11.5px] text-success">
                  <Check size={12} /> Live now
                </p>
              </Lit>
            </Rise>

            {/* The rest: a list, hairline separated, each row lighting on hover. */}
            <Rise delay={0.52} className="lg:col-span-3">
              <div className="h-full rounded-card border border-border bg-surface/30">
                {REST.map((c, i) => (
                  <div key={c.id}
                    style={{ transition: 'background-color var(--t) var(--ease), padding-left var(--t) var(--ease)' }}
                    className={`group/row flex items-start gap-3.5 px-5 py-[15px] hover:bg-overlay/[0.045]
                      hover:pl-6 ${i > 0 ? 'border-t border-border/60' : ''}`}>
                    <span className={`morph-icon mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-btn ${
                      c.got ? 'bg-accent/10 text-accent group-hover/row:scale-110 group-hover/row:bg-accent/[0.18]'
                            : 'bg-overlay/[0.04] text-muted/60'}`}>
                      <c.Icon size={13} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 text-[13.5px] font-medium text-heading">
                        {c.name}
                        {c.got
                          ? <Check size={12} className="shrink-0 text-success opacity-0 transition-opacity
                              duration-200 group-hover/row:opacity-100" />
                          : <span className="shrink-0 rounded-full border border-border px-2 py-0.5 text-[9.5px]
                              font-semibold uppercase tracking-[0.09em] text-muted">Pending</span>}
                      </p>
                      <p className={`mt-1 text-[12.5px] leading-relaxed ${c.got ? 'text-muted' : 'text-muted/70'}`}>
                        {c.body}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </Rise>
          </div>
        </div>
      </div>
    </div>
  )
}
