import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  ACTIVE_THEMES, THEME_DEFS, PREFS_DEFAULTS, DENSITY_FONT_FACTOR, DENSITY_SPACING,
  migratePrefs, computeCssVars, computeDataAttrs, effectiveCustomization,
  type ThemeId, type ThemePrefsV2, type ThemeCustomization, type Density,
} from './themeTokens'

/* Legacy-compatible exports: `THEMES` is now the *active* Theme v2 list and
   `THEME_META` is derived from the v2 definitions, so old imports keep working. */
export const THEMES = ACTIVE_THEMES
export type Theme = ThemeId
export const THEME_META: Record<ThemeId, { label: string; hint: string }> = Object.fromEntries(
  ACTIVE_THEMES.map(id => [id, { label: THEME_DEFS[id].label, hint: THEME_DEFS[id].description }]),
) as Record<ThemeId, { label: string; hint: string }>

const KEY = 'tobi.prefs'

type Ctx = {
  theme: ThemeId
  fontScale: number
  density: Density
  sound: boolean
  customByTheme: ThemePrefsV2['customByTheme']
  /** Effective customization of the current theme (defaults + overrides). */
  custom: ThemeCustomization
  set: (p: Partial<Pick<ThemePrefsV2, 'theme' | 'fontScale' | 'density' | 'sound'>>) => void
  /** Patch the current theme's customization (guided controls). */
  setCustom: (patch: Partial<ThemeCustomization>) => void
  /** Reset the current theme's customization to its defaults. */
  resetCustom: () => void
  /** Reset ALL appearance preferences. */
  reset: () => void
}
const ThemeCtx = createContext<Ctx>(null as unknown as Ctx)
export function useTheme() { return useContext(ThemeCtx) }

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Migration runs once on load: legacy/removed/unknown themes map to survivors,
  // malformed JSON falls back to defaults, and the upgraded v2 shape is written back.
  const [prefs, setPrefs] = useState<ThemePrefsV2>(() => {
    try { return migratePrefs(localStorage.getItem(KEY)) } catch { return PREFS_DEFAULTS }
  })

  // Track which inline CSS vars we own so switching themes removes stale overrides.
  const appliedVars = useRef<string[]>([])

  useEffect(() => {
    const r = document.documentElement
    r.setAttribute('data-theme', prefs.theme)
    r.setAttribute('data-density', prefs.density)

    // Theme identity: write the effective token set inline (instant switching).
    // Inline vars only live at <html> level, so [data-theme] scoped previews
    // (Settings swatches) and Office's pinned dark wrappers still resolve locally.
    const vars = computeCssVars(prefs.theme, prefs.customByTheme[prefs.theme])
    for (const k of appliedVars.current) if (!(k in vars)) r.style.removeProperty(k)
    for (const [k, v] of Object.entries(vars)) r.style.setProperty(k, v)
    appliedVars.current = Object.keys(vars)

    for (const [k, v] of Object.entries(computeDataAttrs(prefs.theme, prefs.customByTheme[prefs.theme]))) {
      r.setAttribute(k, v)
    }

    // Density folds into the root scale (Tailwind spacing is rem-based, so this
    // tightens padding/gaps + text together). Inline var wins over CSS rules.
    r.style.setProperty('--font-scale', String(prefs.fontScale * DENSITY_FONT_FACTOR[prefs.density]))
    r.style.setProperty('--spacing-scale', String(DENSITY_SPACING[prefs.density]))
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

  const set: Ctx['set'] = p => setPrefs(s => ({ ...s, ...p }))
  const setCustom: Ctx['setCustom'] = patch => setPrefs(s => ({
    ...s,
    customByTheme: { ...s.customByTheme, [s.theme]: { ...s.customByTheme[s.theme], ...patch } },
  }))
  const resetCustom = () => setPrefs(s => {
    const next = { ...s.customByTheme }
    delete next[s.theme]
    return { ...s, customByTheme: next }
  })
  const reset = () => setPrefs(PREFS_DEFAULTS)

  return (
    <ThemeCtx.Provider value={{
      theme: prefs.theme, fontScale: prefs.fontScale, density: prefs.density, sound: prefs.sound,
      customByTheme: prefs.customByTheme,
      custom: effectiveCustomization(prefs.theme, prefs.customByTheme[prefs.theme]),
      set, setCustom, resetCustom, reset,
    }}>
      {children}
    </ThemeCtx.Provider>
  )
}
