import { useMemo } from 'react'

// Eagerly import every vendored brand SVG (dashboard/src/assets/logos/*.svg) as a URL.
// Add a new .svg there and it's auto-registered — no code change needed.
const logoModules = import.meta.glob('../assets/logos/*.svg', {
  eager: true,
  query: '?url',
  import: 'default',
}) as Record<string, string>

const LOGOS: Record<string, string> = {}
for (const path in logoModules) {
  const file = path.split('/').pop() || ''
  LOGOS[file.replace('.svg', '').toLowerCase()] = logoModules[path]
}

// Map provider/concept aliases → a vendored file name.
const ALIAS: Record<string, string> = {
  claude: 'anthropic',
  gpt: 'openai',
  openai: 'openai',
  'gpt-4': 'openai',
  codespace: 'github',
  'github codespace': 'github',
}

type LogoProps = {
  /** Brand/provider name, e.g. "github", "notion", "claude". Case-insensitive. */
  name: string
  /** Logo glyph size in px (chip adds padding around it). */
  size?: number
  /** Wrap in a white rounded tile for guaranteed contrast on the dark UI. Default true. */
  chip?: boolean
  className?: string
}

/**
 * Renders a real provider logo on a light tile. Falls back to a colored monogram
 * for names with no vendored brand logo (Hermes, Scheduler, etc.).
 */
export default function Logo({ name, size = 24, chip = true, className = '' }: LogoProps) {
  const key = (name || '').toLowerCase().trim()
  const src = useMemo(() => LOGOS[ALIAS[key] ?? key], [key])

  if (!src) {
    const letter = (name?.trim()?.[0] || '?').toUpperCase()
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-lg bg-purple/20 font-bold text-purple ${className}`}
        style={{ width: size + 12, height: size + 12, fontSize: size * 0.6 }}
        title={name}
        aria-label={`${name} icon`}
      >
        {letter}
      </span>
    )
  }

  const img = (
    <img
      src={src}
      alt={`${name} logo`}
      width={size}
      height={size}
      style={{ width: size, height: size, objectFit: 'contain' }}
    />
  )

  if (!chip) return <span className={`inline-flex shrink-0 ${className}`}>{img}</span>

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-lg bg-white shadow-sm ${className}`}
      style={{ width: size + 12, height: size + 12 }}
      title={name}
    >
      {img}
    </span>
  )
}
