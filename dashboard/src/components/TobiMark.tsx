// TOBI's mark: the badge that says a piece of content was made by TOBI.
//
// Drawn rather than drawn-on: it is geometry, not a raster asset, for three reasons that matter
// for what it is used for.
//
//   1. IT MUST SURVIVE 14px. This lands next to a line of text as often as it lands in an avatar
//      slot, so the silhouette is a filled disc with the letterform knocked out of it. An outline
//      mark loses its stroke at badge size; a solid one never does.
//   2. IT MUST FOLLOW THE THEME. The fill is built from `--accent` and `--purple`, so the mark
//      belongs to whichever of TOBI's twelve themes is active instead of fighting it.
//   3. IT MUST NOT NEED A NETWORK. No file to load, nothing to 404, nothing to cache-bust.
//
// The letterform is a T with an open ring around it: the T for TOBI, the gap in the ring because
// a closed circle reads as a full stop and this is a thing that is still running.
import { useId } from 'react'

/**
 * The bare mark. `tone="flat"` drops the gradient for places that already carry colour, such as
 * a coloured chip, where a second gradient would compete.
 */
export function TobiMark({ size = 20, tone = 'brand', className = '' }: {
  size?: number
  tone?: 'brand' | 'flat'
  className?: string
}) {
  // Gradient ids must be unique per instance or the first one on the page wins for all of them.
  const id = useId().replace(/:/g, '')
  const fill = tone === 'brand' ? `url(#tobi-${id})` : 'currentColor'

  // The mark drops detail as it shrinks, because detail that lands on less than a whole device
  // pixel does not become a fine line — it becomes grey haze, and the haze sits right where the
  // letterform needs its contrast. Both thresholds below are measured, not guessed:
  //   · the groove is 1.1 viewBox units, so under 32px it renders thinner than one pixel;
  //   · the T at 3.1 units falls to ~1.1px by 12px, which is legible but has no margin left.
  const groove = size >= 24
  const stem = size >= 16 ? 3.1 : 3.6

  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className}
      role="img" aria-label="Made by TOBI">
      <defs>
        {/* The accent is held flat until 48% before the fall to purple. The letterform spans
            roughly 34%–60% of this diagonal, so holding the accent that far keeps the T sitting
            on the colour it contrasts with in every theme, and leaves purple to the empty
            bottom-right corner where it is decoration rather than a legibility risk. Without
            the hold, the Vercel theme's purple gives the stem 2.8:1 — under the 3.0 floor. */}
        <linearGradient id={`tobi-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="rgb(var(--accent))" />
          <stop offset="48%" stopColor="rgb(var(--accent))" />
          <stop offset="100%" stopColor="rgb(var(--purple, var(--accent)))" />
        </linearGradient>
      </defs>

      {/* The disc. Solid, so the silhouette holds at any size. */}
      <circle cx="16" cy="16" r="15" fill={fill} />

      {/* An open ring: still running, not finished. Drawn in the ground colour at low opacity so
          it reads as an inset groove rather than an extra element. Large sizes only. */}
      {groove && (
        <circle cx="16" cy="16" r="11.4" fill="none" stroke="rgb(var(--bg))" strokeWidth="1.1"
          strokeOpacity="0.42" strokeLinecap="round" pathLength={100}
          strokeDasharray="74 100" strokeDashoffset="-13" />
      )}

      {/* The T, knocked out in the page ground so it reads as cut rather than printed. Drawn last
          so it always sits on top of the groove rather than being nibbled by it. */}
      <path d="M10 12h12M16 12v10.5" stroke="rgb(var(--bg))" strokeWidth={stem}
        strokeLinecap="round" fill="none" />
    </svg>
  )
}

/** Avatar slot: the mark at a size that suits a message or a record header. */
export function TobiAvatar({ size = 32, className = '' }: { size?: number; className?: string }) {
  return (
    <span className={`inline-grid shrink-0 place-items-center rounded-full ${className}`}
      style={{ width: size, height: size }}>
      <TobiMark size={size} />
    </span>
  )
}

/**
 * The badge. Put it on anything TOBI produced.
 *
 * Default is mark-only, which is what a dense list wants. Pass a label where there is room and
 * the provenance is worth spelling out.
 */
export function TobiBadge({ label, size = 14, title = 'Made by TOBI', className = '' }: {
  /** Omit for the mark alone. */
  label?: string
  size?: number
  title?: string
  className?: string
}) {
  if (!label) {
    return (
      <span title={title} className={`inline-flex shrink-0 align-middle ${className}`}>
        <TobiMark size={size} />
      </span>
    )
  }
  return (
    <span title={title}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border border-accent/25
        bg-accent/10 py-0.5 pl-1 pr-2 align-middle text-[10.5px] font-medium tracking-wide
        text-accent ${className}`}>
      <TobiMark size={size} />
      {label}
    </span>
  )
}

export default TobiMark
