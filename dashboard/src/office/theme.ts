/**
 * Bridge the dashboard's CSS theme tokens into Phaser integer colors. The page
 * canvas is a fixed dark neon-cyberpunk look, but the *accent* tracks whatever
 * theme the user picked — `ThemeProvider` writes `--accent` (an "r g b" triplet)
 * onto <html data-theme=…>, so we read it from the document root, NOT from the
 * page's local `data-theme="dark"` wrapper.
 */

const FALLBACK = 0x58a6ff // dark-theme accent

/** Parse a CSS "r g b" triplet (Tailwind token form) → 0xRRGGBB. */
export function tripletToInt(triplet: string): number {
  const parts = triplet.trim().split(/[\s,]+/).map(Number)
  if (parts.length < 3 || parts.some(n => Number.isNaN(n))) return FALLBACK
  const [r, g, b] = parts
  return ((r & 0xff) << 16) | ((g & 0xff) << 8) | (b & 0xff)
}

/** Parse a CSS color string ("#rrggbb" or "rgb(...)") → 0xRRGGBB. */
export function cssColorToInt(c: string | null | undefined): number {
  if (!c) return FALLBACK
  const s = c.trim()
  if (s.startsWith('#')) {
    const hex = s.slice(1)
    const full = hex.length === 3 ? hex.split('').map(ch => ch + ch).join('') : hex
    const n = parseInt(full, 16)
    return Number.isNaN(n) ? FALLBACK : n
  }
  const m = s.match(/-?\d+/g)
  if (m && m.length >= 3) return tripletToInt(m.slice(0, 3).join(' '))
  return FALLBACK
}

/** Current live accent (0xRRGGBB) from the root theme. */
export function accentHex(): number {
  if (typeof document === 'undefined') return FALLBACK
  const v = getComputedStyle(document.documentElement).getPropertyValue('--accent')
  return v ? tripletToInt(v) : FALLBACK
}

/** Mix two ints by t∈[0,1] (simple per-channel lerp). */
export function mixInt(a: number, b: number, t: number): number {
  const ar = (a >> 16) & 0xff, ag = (a >> 8) & 0xff, ab = a & 0xff
  const br = (b >> 16) & 0xff, bg = (b >> 8) & 0xff, bb = b & 0xff
  const r = Math.round(ar + (br - ar) * t)
  const g = Math.round(ag + (bg - ag) * t)
  const bl = Math.round(ab + (bb - ab) * t)
  return (r << 16) | (g << 8) | bl
}
