// Morpheus UI primitives.
//
// Every page composes from these. That is the point: consistency in a design system has to be
// structural, not a thing each page remembers to do. One button component means one radius, one
// press response, one focus ring and one contrast guarantee across the whole app -- and a new
// page cannot quietly invent a fifth button style.
//
// Rules encoded here rather than left to discipline:
//   - one radius family (cards 12 / controls 9 / inputs 7), from the tokens
//   - labels never wrap: primary actions are two or three words
//   - every interactive element has hover, focus-visible and active states
//   - inputs put the label ABOVE and the error BELOW, never a placeholder-as-label
import { forwardRef, type ReactNode, type ButtonHTMLAttributes, type InputHTMLAttributes } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { GRAIN_SVG } from './tokens'

/* ── Surfaces ──────────────────────────────────────────────────────────── */

/**
 * Subtle texture over the whole viewport, to stop large flat near-blacks banding on 8-bit panels.
 *
 * Two earlier attempts had to be thrown away, and the reasons are worth keeping:
 *   - `mix-blend-overlay` on a full-screen fixed layer forces the compositor to re-blend the
 *     entire viewport against everything under it, every frame.
 *   - An SVG `feTurbulence` noise tile is re-rasterised as it repeats across the viewport.
 * Either one alone was enough to freeze the renderer outright. This is a static, GPU-cheap
 * gradient wash instead: less literal than film grain, and it costs nothing.
 */
export function Grain() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-[60] opacity-[0.028]"
      style={{ backgroundImage: GRAIN_SVG, backgroundRepeat: 'repeat' }} />
  )
}

/**
 * The gate's atmosphere: a layered dark scene that works with or without a photograph.
 *
 * Depth is built from four planes (haze, horizon glow, vignette, grain) rather than one image,
 * so it degrades to something intentional instead of an empty box when no photo is present.
 */
export function Atmosphere({ image }: { image?: string }) {
  return (
    <div aria-hidden className="absolute inset-0 overflow-hidden bg-bg">
      {image && (
        <img src={image} alt="" onError={e => { e.currentTarget.style.display = 'none' }}
          className="absolute inset-0 h-full w-full object-cover opacity-[0.28] grayscale-[0.4]" />
      )}
      {/* Horizon: a low, wide glow that reads as a city under cloud. */}
      <div className="absolute inset-x-0 bottom-0 h-[52%]"
        style={{ background: 'radial-gradient(120% 100% at 50% 100%, rgb(var(--accent) / 0.16), transparent 70%)' }} />
      {/* Haze above it, cooler and fainter, to give the scene a top and a bottom. */}
      <div className="absolute inset-x-0 top-0 h-[46%]"
        style={{ background: 'radial-gradient(90% 100% at 50% 0%, rgb(var(--accent) / 0.07), transparent 72%)' }} />
      {/* Vignette, so the centre of the screen is where the eye lands. */}
      <div className="absolute inset-0"
        style={{ background: 'radial-gradient(75% 60% at 50% 45%, transparent, rgb(var(--bg)) 88%)' }} />
    </div>
  )
}

export function Card({ children, className = '', as: As = 'div' }: {
  children: ReactNode; className?: string; as?: 'div' | 'section' | 'article'
}) {
  return (
    <As className={`rounded-card border border-border bg-surface/60
      transition-[border-color,background-color,box-shadow] duration-[var(--t)] ${className}`}
      style={{ transitionTimingFunction: 'var(--ease)' }}>
      {children}
    </As>
  )
}

/* ── Page furniture ────────────────────────────────────────────────────── */

/**
 * The one page header. Title, one line of context, optional actions.
 *
 * Deliberately has no "eyebrow" slot. A small uppercase label above every single section header
 * is the most templated rhythm in generated interfaces, and the page's position in the sidebar
 * already says what it is.
 */
export function PageHeader({ title, lede, actions }: {
  title: string; lede?: string; actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="font-display text-[26px] font-semibold leading-tight tracking-[-0.015em] text-heading">
          {title}
        </h1>
        {lede && <p className="mt-2 max-w-xl text-[13.5px] leading-relaxed text-muted">{lede}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

/** Section label. Used sparingly, and only where a group genuinely needs naming. */
export function SectionLabel({ children, count }: { children: ReactNode; count?: number }) {
  return (
    <h2 className="flex items-baseline gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
      {children}
      {count !== undefined && <span className="tabular-nums font-normal opacity-70">{count}</span>}
    </h2>
  )
}

/** Standard page frame: one max width, one horizontal rhythm, one vertical rhythm. */
export function Page({ children, width = 'md' }: {
  children: ReactNode; width?: 'sm' | 'md' | 'lg'
}) {
  const max = width === 'sm' ? 'max-w-2xl' : width === 'lg' ? 'max-w-5xl' : 'max-w-3xl'
  return (
    <div className="h-full overflow-y-auto">
      <div className={`mx-auto ${max} px-7 py-9`}>{children}</div>
    </div>
  )
}

/* ── Controls ──────────────────────────────────────────────────────────── */

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  icon?: ReactNode
}

const VARIANTS: Record<NonNullable<BtnProps['variant']>, string> = {
  // Dark ink on the accent: comfortably above WCAG AA, and it stops the accent reading as neon.
  primary: 'bg-accent text-bg hover:bg-accent/90 disabled:hover:bg-accent',
  secondary: 'border border-border bg-surface text-text hover:border-muted/60 hover:text-heading',
  ghost: 'text-muted hover:bg-overlay/[0.06] hover:text-heading',
  danger: 'border border-danger/40 bg-danger/10 text-danger hover:bg-danger/15 hover:border-danger/60',
}

/**
 * The only button in Morpheus. Labels stay short so they never wrap at desktop.
 *
 * Colour and shadow ride the app-wide baseline transition; transform is declared here because
 * the press response wants to be quicker than a hover tint. A button that returns from its press
 * as slowly as it changes colour feels sluggish, which is the opposite of the intent.
 */
export const Btn = forwardRef<HTMLButtonElement, BtnProps>(function Btn(
  { variant = 'secondary', size = 'md', icon, className = '', children, ...rest }, ref,
) {
  const pad = size === 'sm' ? 'h-8 px-3 text-[12.5px] gap-1.5' : 'h-9 px-4 text-[13px] gap-2'
  return (
    <button ref={ref} {...rest}
      style={{ transitionProperty: 'color, background-color, border-color, box-shadow, transform' }}
      className={`inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-btn font-medium
        outline-none will-change-transform
        focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg
        hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.97]
        disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0 disabled:active:scale-100
        ${VARIANTS[variant]} ${pad} ${className}`}>
      {icon}
      {children}
    </button>
  )
})

/** Selectable pill, for object types and filters. */
export function Pill({ on, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { on?: boolean }) {
  return (
    <button {...rest} aria-pressed={on}
      style={{ transitionProperty: 'color, background-color, border-color, transform' }}
      className={`rounded-full border px-3 py-1 text-[12.5px] outline-none active:scale-[0.96]
        focus-visible:ring-2 focus-visible:ring-accent/50 ${
        on ? 'border-accent/50 bg-accent/12 text-accent'
           : 'border-border text-muted hover:border-muted/60 hover:bg-overlay/[0.04] hover:text-text'}`}>
      {children}
    </button>
  )
}

const TONES = {
  neutral: 'bg-overlay/[0.07] text-muted',
  accent: 'bg-accent/12 text-accent',
  success: 'bg-success/12 text-success',
  warning: 'bg-warning/12 text-warning',
  danger: 'bg-danger/12 text-danger',
} as const

export function Badge({ tone = 'neutral', icon, children }: {
  tone?: keyof typeof TONES; icon?: ReactNode; children: ReactNode
}) {
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px]
      font-semibold uppercase tracking-[0.06em] ${TONES[tone]}`}>
      {icon}{children}
    </span>
  )
}

/** Label above, error below. Never a placeholder standing in for a label. */
export function Field({ label, hint, error, children, htmlFor }: {
  label: string; hint?: string; error?: string; children: ReactNode; htmlFor?: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted">
        {label}
      </label>
      {children}
      {error
        ? <p className="text-[12px] text-danger">{error}</p>
        : hint ? <p className="text-[12px] text-muted">{hint}</p> : null}
    </div>
  )
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className = '', ...rest }, ref) {
    return (
      <input ref={ref} {...rest}
        className={`w-full rounded-input border border-border bg-bg px-3 py-2 text-[13.5px] text-heading
          outline-none transition-colors duration-150 placeholder:text-muted/70
          focus:border-accent/60 focus:ring-2 focus:ring-accent/15 ${className}`} />
    )
  })

/**
 * Toggle. Reads as on or off at a glance without needing colour vision.
 *
 * The knob moves on `transform`, not `left`. Animating a layout property forces the browser to
 * re-lay-out on every frame; a transform is handled by the compositor and is the difference
 * between a switch that glides and one that stutters. It also squashes slightly while travelling,
 * which is the small physical touch that makes a toggle feel satisfying.
 */
export function Toggle({ on, disabled, onToggle, label }: {
  on: boolean; disabled?: boolean; onToggle: () => void; label: string
}) {
  return (
    <button role="switch" aria-checked={on} aria-label={label} disabled={disabled} onClick={onToggle}
      className={`group/sw relative h-[22px] w-[38px] shrink-0 rounded-full outline-none
        focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg
        ${on ? 'bg-accent' : 'bg-border hover:bg-border/70'} ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}>
      <span
        className="absolute left-[3px] top-[3px] h-4 w-4 rounded-full bg-bg shadow-sm
          group-active/sw:scale-x-90"
        style={{
          transform: `translateX(${on ? 16 : 0}px)`,
          transition: 'transform var(--t) var(--ease)',
        }} />
    </button>
  )
}

/* ── States ────────────────────────────────────────────────────────────── */

/** Composed empty state. Says what is missing and how to fix it, never just "no data". */
export function Empty({ icon, title, body, action }: {
  icon?: ReactNode; title: string; body?: string; action?: ReactNode
}) {
  return (
    <div className="grid h-full place-items-center px-6 py-16 text-center">
      <div className="max-w-sm">
        {icon && (
          <div className="mx-auto mb-4 grid h-11 w-11 place-items-center rounded-card border border-border bg-surface/70 text-muted">
            {icon}
          </div>
        )}
        <p className="text-[15px] font-medium text-heading">{title}</p>
        {body && <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{body}</p>}
        {action && <div className="mt-5 flex justify-center">{action}</div>}
      </div>
    </div>
  )
}

/** Skeleton, shaped like the content it stands in for. Only where nothing exists yet. */
export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2.5" aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-[54px] animate-pulse rounded-card border border-border bg-surface/40"
          style={{ animationDelay: `${i * 90}ms` }} />
      ))}
    </div>
  )
}

/** Inline failure. States what did not load and offers the retry, rather than rendering nothing. */
export function Failure({ what, onRetry }: { what: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-card border border-danger/35 bg-danger/[0.07] px-4 py-3.5">
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] font-medium text-heading">{what} could not load.</p>
        <p className="mt-0.5 text-[12.5px] text-muted">Nothing was changed. Try again, or check the model is running.</p>
      </div>
      {onRetry && <Btn size="sm" onClick={onRetry}>Retry</Btn>}
    </div>
  )
}

/* ── Motion ────────────────────────────────────────────────────────────── */

/**
 * Entrance for page content. One easing curve, used everywhere, so the app feels like one thing.
 *
 * CSS, not Framer, and that is the whole point. Every open tab stays mounted, and a pane is
 * `display: none` while it is not the active one. A JavaScript enter-animation started against a
 * hidden element never runs, so the element was left sitting at its `initial` state: opacity 0,
 * forever. Entire pages rendered perfectly in the DOM and were invisible on screen.
 *
 * A CSS animation with `animation-fill-mode: backwards` cannot fail that way. The element's
 * natural, un-animated state is fully visible, so if the animation never plays (hidden at mount,
 * motion disabled, animations unsupported) the content is simply there. The animation only ever
 * subtracts from a visible baseline. Entrances must fail open.
 */
export function Rise({ children, delay = 0, className = '' }: {
  children: ReactNode; delay?: number; className?: string
}) {
  return (
    <div className={`morph-rise ${className}`} style={{ animationDelay: `${delay}s` }}>
      {children}
    </div>
  )
}
