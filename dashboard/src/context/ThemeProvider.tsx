import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'

export const THEMES = ['dark', 'light', 'midnight', 'contrast', 'warm', 'gaming', 'hightech', 'scientific'] as const
export type Theme = typeof THEMES[number]
export const THEME_META: Record<Theme, { label: string; hint: string }> = {
  dark: { label: 'Dark', hint: 'GitHub-dark default' },
  light: { label: 'Light', hint: 'Clean & bright' },
  midnight: { label: 'Midnight Neon', hint: 'Deep black + neon cyan' },
  contrast: { label: 'High-contrast', hint: 'Max readability' },
  warm: { label: 'Warm', hint: 'Solarized, easy on eyes' },
  gaming: { label: 'Gaming', hint: 'Neon purple + lime' },
  hightech: { label: 'High-tech', hint: 'Cool sky + teal' },
  scientific: { label: 'Scientific', hint: 'Bright lab' },
}

type Density = 'comfortable' | 'compact'
type Prefs = { theme: Theme; fontScale: number; density: Density; sound: boolean }
const DEFAULTS: Prefs = { theme: 'dark', fontScale: 1, density: 'comfortable', sound: false }
const KEY = 'tobi.prefs'

type Ctx = Prefs & { set: (p: Partial<Prefs>) => void; reset: () => void }
const ThemeCtx = createContext<Ctx>(null as unknown as Ctx)
export function useTheme() { return useContext(ThemeCtx) }

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(() => {
    try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') } } catch { return DEFAULTS }
  })
  useEffect(() => {
    const r = document.documentElement
    r.setAttribute('data-theme', prefs.theme)
    r.setAttribute('data-density', prefs.density)
    // Density folds into the root scale (Tailwind spacing is rem-based, so this
    // tightens padding/gaps + text together). Inline var wins over CSS rules.
    r.style.setProperty('--font-scale', String(prefs.fontScale * (prefs.density === 'compact' ? 0.9 : 1)))
    try { localStorage.setItem(KEY, JSON.stringify(prefs)) } catch { /* ignore */ }
  }, [prefs])

  // Theme crossfade (queue #6): open a brief window where color-bearing props
  // transition (~300ms), only during an actual theme switch — never on mount or
  // on everyday interactions. The [data-theme-anim] CSS rule does the fade.
  const firstRun = useRef(true)
  useEffect(() => {
    if (firstRun.current) { firstRun.current = false; return }
    const r = document.documentElement
    r.setAttribute('data-theme-anim', '')
    const t = setTimeout(() => r.removeAttribute('data-theme-anim'), 340)
    return () => clearTimeout(t)
  }, [prefs.theme])

  const set = (p: Partial<Prefs>) => setPrefs(s => ({ ...s, ...p }))
  const reset = () => setPrefs(DEFAULTS)
  return <ThemeCtx.Provider value={{ ...prefs, set, reset }}>{children}</ThemeCtx.Provider>
}
