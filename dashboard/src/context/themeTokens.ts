/* ── Theme v2 token system (queue #13) ─────────────────────────────────────────
   Single source of truth for theme identity: colors, shape, elevation, density,
   typography, component feel, background, chart palette, and motion intensity.
   `index.css` keeps a per-[data-theme] CSS fallback of the same values (first
   paint + swatch previews); ThemeProvider writes the effective set — theme
   defaults merged with the owner's per-theme customization — inline on <html>,
   which preserves instant switching. Spec: docs/feature-idea-queue/
   THEME_V2_SYSTEM_UPGRADE_PLAN.md */
import {
  Moon, Sun, Gamepad2, Cpu, Flower2, Landmark, Bot, type LucideIcon,
} from 'lucide-react'

export type ThemeId = 'dark' | 'light' | 'gaming' | 'hightech' | 'japanese' | 'chinese' | 'jarvis'

/** Order = display order in every selector. */
export const ACTIVE_THEMES: ThemeId[] = ['dark', 'light', 'gaming', 'hightech', 'japanese', 'chinese', 'jarvis']

export type Density = 'compact' | 'comfortable' | 'spacious'
export type RadiusPreset = 'sharp' | 'soft' | 'rounded'
export type ShadowDepth = 'flat' | 'soft' | 'deep' | 'glow'
export type ButtonStyle = 'solid' | 'ghost' | 'outline' | 'glass'
export type CardStyle = 'flat' | 'outlined' | 'glass' | 'layered'
export type BackgroundStyle = 'plain' | 'grid' | 'gradient' | 'paper' | 'hud'
export type MotionIntensity = 'quiet' | 'standard' | 'expressive'
export type TypographyPreset = 'default' | 'technical' | 'calm'
export type Tracking = 'normal' | 'wide' | 'tight'

/** Colors are "r g b" channel triplets so Tailwind's `bg-accent/10` keeps working. */
export type ThemeV2Tokens = {
  color: {
    scheme: 'dark' | 'light'
    bg: string; surface: string; panel: string; border: string; strip: string
    muted: string; text: string; heading: string
    accent: string; success: string; warning: string; danger: string; purple: string
    accent2: string; glow: string
  }
  typography: { tracking: Tracking }
  shape: { radius: RadiusPreset }
  elevation: { shadowDepth: ShadowDepth }
  component: { buttonStyle: ButtonStyle; cardStyle: CardStyle }
  background: { style: BackgroundStyle; overlayOpacity: number }
  dataViz: { palette: [string, string, string, string, string, string]; glowCharts: boolean }
  motion: { intensity: MotionIntensity }
}

/** The guided, preset-based knobs the owner can override per theme (§9). */
export type ThemeCustomization = {
  accent: string | null // "r g b" triplet, or null = theme default
  radius: RadiusPreset
  cardStyle: CardStyle
  buttonStyle: ButtonStyle
  background: BackgroundStyle
  shadowDepth: ShadowDepth
  typography: TypographyPreset
  motion: MotionIntensity
  contrast: 'standard' | 'boosted'
}

export type ThemeDef = {
  id: ThemeId
  label: string
  description: string
  icon: LucideIcon
  mode: 'dark' | 'light'
  tokens: ThemeV2Tokens
  /** Default customization derived from tokens — what "Reset theme" restores. */
  defaults: ThemeCustomization
  /** All guided controls are available on every theme (owner decision). */
  customizable: (keyof ThemeCustomization)[]
  /** Removed v1 themes that migrate here. */
  migrationFrom: string[]
}

const ALL_CONTROLS: (keyof ThemeCustomization)[] = [
  'accent', 'radius', 'cardStyle', 'buttonStyle', 'background', 'shadowDepth', 'typography', 'motion', 'contrast',
]

function defaultsFrom(t: ThemeV2Tokens): ThemeCustomization {
  return {
    accent: null,
    radius: t.shape.radius,
    cardStyle: t.component.cardStyle,
    buttonStyle: t.component.buttonStyle,
    background: t.background.style,
    shadowDepth: t.elevation.shadowDepth,
    typography: 'default',
    motion: t.motion.intensity,
    contrast: 'standard',
  }
}

/* ── The seven active themes ─────────────────────────────────────────────── */

const DARK: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '13 17 23', surface: '22 27 34', panel: '16 21 28', border: '48 54 61', strip: '22 27 34',
    muted: '139 148 158', text: '201 209 217', heading: '240 246 252',
    accent: '88 166 255', success: '63 185 80', warning: '210 153 34', danger: '248 81 73', purple: '139 92 246',
    accent2: '139 92 246', glow: '88 166 255',
  },
  typography: { tracking: 'normal' },
  shape: { radius: 'soft' },
  elevation: { shadowDepth: 'soft' },
  component: { buttonStyle: 'solid', cardStyle: 'outlined' },
  background: { style: 'plain', overlayOpacity: 0.04 },
  dataViz: { palette: ['88 166 255', '139 92 246', '63 185 80', '210 153 34', '248 81 73', '45 212 191'], glowCharts: false },
  motion: { intensity: 'standard' },
}

const LIGHT: ThemeV2Tokens = {
  color: {
    scheme: 'light',
    bg: '247 249 252', surface: '255 255 255', panel: '241 245 249', border: '209 217 224', strip: '224 230 238',
    muted: '90 100 110', text: '30 41 59', heading: '15 23 42',
    accent: '37 99 235', success: '22 163 74', warning: '202 138 4', danger: '220 38 38', purple: '124 58 237',
    accent2: '124 58 237', glow: '37 99 235',
  },
  typography: { tracking: 'normal' },
  shape: { radius: 'soft' },
  elevation: { shadowDepth: 'soft' },
  component: { buttonStyle: 'solid', cardStyle: 'outlined' },
  background: { style: 'plain', overlayOpacity: 0.03 },
  dataViz: { palette: ['37 99 235', '124 58 237', '22 163 74', '202 138 4', '220 38 38', '13 148 136'], glowCharts: false },
  motion: { intensity: 'standard' },
}

/** Esports neon: dark surface, sharper HUD accents, lime success, purple/pink secondary. */
const GAMING: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '9 8 16', surface: '19 16 30', panel: '13 11 22', border: '62 42 88', strip: '19 16 30',
    muted: '152 140 175', text: '222 216 238', heading: '246 242 255',
    accent: '168 85 247', success: '57 255 20', warning: '255 170 0', danger: '255 45 85', purple: '217 70 239',
    accent2: '255 45 170', glow: '168 85 247',
  },
  typography: { tracking: 'wide' },
  shape: { radius: 'sharp' },
  elevation: { shadowDepth: 'glow' },
  component: { buttonStyle: 'glass', cardStyle: 'layered' },
  background: { style: 'hud', overlayOpacity: 0.06 },
  dataViz: { palette: ['168 85 247', '255 45 170', '57 255 20', '255 170 0', '34 211 238', '255 45 85'], glowCharts: true },
  motion: { intensity: 'expressive' },
}

/** Clean engineering dashboard: cool blues, teal accents, precise borders, restrained glow. */
const HIGHTECH: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '10 16 28', surface: '16 26 44', panel: '13 21 36', border: '44 62 92', strip: '16 26 44',
    muted: '128 148 178', text: '198 214 234', heading: '235 245 255',
    accent: '56 189 248', success: '45 212 191', warning: '245 191 66', danger: '248 113 113', purple: '129 140 248',
    accent2: '45 212 191', glow: '56 189 248',
  },
  typography: { tracking: 'tight' },
  shape: { radius: 'sharp' },
  elevation: { shadowDepth: 'soft' },
  component: { buttonStyle: 'outline', cardStyle: 'outlined' },
  background: { style: 'grid', overlayOpacity: 0.05 },
  dataViz: { palette: ['56 189 248', '45 212 191', '129 140 248', '245 191 66', '248 113 113', '148 163 184'], glowCharts: false },
  motion: { intensity: 'standard' },
}

/** Light washi white, soft sakura accent, calm minimal cards, soft radius. */
const JAPANESE: ThemeV2Tokens = {
  color: {
    scheme: 'light',
    bg: '250 247 245', surface: '255 255 255', panel: '247 241 240', border: '233 221 221', strip: '243 233 233',
    muted: '141 122 128', text: '74 60 66', heading: '45 33 39',
    accent: '224 93 128', success: '88 158 110', warning: '200 142 62', danger: '203 84 92', purple: '156 116 182',
    accent2: '156 116 182', glow: '224 93 128',
  },
  typography: { tracking: 'wide' },
  shape: { radius: 'rounded' },
  elevation: { shadowDepth: 'soft' },
  component: { buttonStyle: 'solid', cardStyle: 'flat' },
  background: { style: 'paper', overlayOpacity: 0.05 },
  dataViz: { palette: ['224 93 128', '156 116 182', '88 158 110', '200 142 62', '203 84 92', '120 140 160'], glowCharts: false },
  motion: { intensity: 'quiet' },
}

/** Red & gold premium SaaS: festive but professional, stronger accent hierarchy. */
const CHINESE: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '26 13 12', surface: '40 21 19', panel: '33 17 15', border: '96 52 44', strip: '40 21 19',
    muted: '196 156 138', text: '240 219 204', heading: '252 240 225',
    accent: '224 66 56', success: '106 186 116', warning: '214 168 48', danger: '250 98 86', purple: '186 108 158',
    accent2: '214 168 48', glow: '214 168 48',
  },
  typography: { tracking: 'normal' },
  shape: { radius: 'soft' },
  elevation: { shadowDepth: 'deep' },
  component: { buttonStyle: 'solid', cardStyle: 'layered' },
  background: { style: 'gradient', overlayOpacity: 0.07 },
  dataViz: { palette: ['224 66 56', '214 168 48', '106 186 116', '230 150 60', '250 98 86', '170 120 90'], glowCharts: false },
  motion: { intensity: 'standard' },
}

/** High-tech blue AI OS: dark dashboard, glowing but controlled, analytics-focused. */
const JARVIS: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '5 11 22', surface: '10 20 38', panel: '8 16 30', border: '28 52 88', strip: '10 20 38',
    muted: '108 138 172', text: '188 212 238', heading: '224 240 255',
    accent: '0 194 255', success: '62 220 172', warning: '255 188 70', danger: '255 86 100', purple: '128 122 250',
    accent2: '82 128 255', glow: '0 194 255',
  },
  typography: { tracking: 'wide' },
  shape: { radius: 'sharp' },
  elevation: { shadowDepth: 'glow' },
  component: { buttonStyle: 'outline', cardStyle: 'glass' },
  background: { style: 'hud', overlayOpacity: 0.07 },
  dataViz: { palette: ['0 194 255', '82 128 255', '62 220 172', '255 188 70', '255 86 100', '128 122 250'], glowCharts: true },
  motion: { intensity: 'expressive' },
}

export const THEME_DEFS: Record<ThemeId, ThemeDef> = {
  dark: {
    id: 'dark', label: 'Dark Default', description: 'GitHub-dark baseline — calm, familiar, precise.',
    icon: Moon, mode: 'dark', tokens: DARK, defaults: defaultsFrom(DARK),
    customizable: ALL_CONTROLS, migrationFrom: ['contrast', 'warm'],
  },
  light: {
    id: 'light', label: 'Light Default', description: 'Clean & bright — crisp premium SaaS light mode.',
    icon: Sun, mode: 'light', tokens: LIGHT, defaults: defaultsFrom(LIGHT),
    customizable: ALL_CONTROLS, migrationFrom: ['scientific'],
  },
  gaming: {
    id: 'gaming', label: 'Gaming', description: 'Esports neon — sharp HUD purple, lime, pink energy.',
    icon: Gamepad2, mode: 'dark', tokens: GAMING, defaults: defaultsFrom(GAMING),
    customizable: ALL_CONTROLS, migrationFrom: ['midnight'],
  },
  hightech: {
    id: 'hightech', label: 'High Tech', description: 'Engineering dashboard — cool blues, teal, precise lines.',
    icon: Cpu, mode: 'dark', tokens: HIGHTECH, defaults: defaultsFrom(HIGHTECH),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  japanese: {
    id: 'japanese', label: 'Japanese', description: 'Washi white & sakura — calm, minimal, soft radius.',
    icon: Flower2, mode: 'light', tokens: JAPANESE, defaults: defaultsFrom(JAPANESE),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  chinese: {
    id: 'chinese', label: 'Chinese', description: 'Red & gold premium — festive but professional.',
    icon: Landmark, mode: 'dark', tokens: CHINESE, defaults: defaultsFrom(CHINESE),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  jarvis: {
    id: 'jarvis', label: 'Jarvis OS', description: 'Blue AI operating system — glowing, analytical, alive.',
    icon: Bot, mode: 'dark', tokens: JARVIS, defaults: defaultsFrom(JARVIS),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
}

/* ── Preset value tables ─────────────────────────────────────────────────── */

export const RADIUS_PRESETS: Record<RadiusPreset, { card: string; button: string; input: string }> = {
  sharp:   { card: '6px',  button: '4px',  input: '4px' },
  soft:    { card: '12px', button: '8px',  input: '6px' },
  rounded: { card: '16px', button: '12px', input: '10px' },
}

export const SHADOW_PRESETS: Record<ShadowDepth, { card: string; popover: string }> = {
  flat: { card: 'none', popover: '0 10px 30px -12px rgb(0 0 0 / 0.40)' },
  soft: { card: '0 1px 3px rgb(0 0 0 / 0.20)', popover: '0 16px 40px -12px rgb(0 0 0 / 0.40)' },
  deep: { card: '0 10px 28px -10px rgb(0 0 0 / 0.50)', popover: '0 28px 64px -16px rgb(0 0 0 / 0.55)' },
  glow: {
    card: '0 0 0 1px rgb(var(--accent) / 0.06), 0 0 20px -4px rgb(var(--accent) / 0.18)',
    popover: '0 16px 48px -8px rgb(var(--accent) / 0.28)',
  },
}

const TRACKING: Record<Tracking, string> = { normal: '0em', wide: '0.015em', tight: '-0.01em' }
/** Typography presets resolve to a tracking choice ('default' = the theme's own). */
const TYPO_TRACKING: Record<Exclude<TypographyPreset, 'default'>, Tracking> = { technical: 'tight', calm: 'wide' }

export const DENSITY_FONT_FACTOR: Record<Density, number> = { compact: 0.9, comfortable: 1, spacious: 1.05 }
export const DENSITY_SPACING: Record<Density, number> = { compact: 0.92, comfortable: 1, spacious: 1.08 }

/** Accent presets offered in the customizer (label + "r g b" triplet). */
export const ACCENT_PRESETS: { label: string; value: string }[] = [
  { label: 'Blue', value: '88 166 255' },
  { label: 'Violet', value: '139 92 246' },
  { label: 'Teal', value: '45 212 191' },
  { label: 'Green', value: '63 185 80' },
  { label: 'Amber', value: '245 158 11' },
  { label: 'Rose', value: '244 63 94' },
  { label: 'Pink', value: '236 72 153' },
  { label: 'Cyan', value: '34 211 238' },
]

/* ── Prefs shape + migration (§5) ────────────────────────────────────────── */

export type ThemePrefsV2 = {
  version: 2
  theme: ThemeId
  fontScale: number
  density: Density
  sound: boolean
  customByTheme: Partial<Record<ThemeId, Partial<ThemeCustomization>>>
}

export const PREFS_DEFAULTS: ThemePrefsV2 = {
  version: 2, theme: 'dark', fontScale: 1, density: 'comfortable', sound: false, customByTheme: {},
}

/** Removed v1 theme → closest surviving theme (owner-approved mapping). */
export const REMOVED_THEME_MAP: Record<string, ThemeId> = {
  midnight: 'gaming',
  contrast: 'dark',
  warm: 'dark',
  scientific: 'light',
}

function isThemeId(v: unknown): v is ThemeId {
  return typeof v === 'string' && (ACTIVE_THEMES as string[]).includes(v)
}

/** Pure + defensive: never throws, always returns a valid v2 shape.
 *  Unknown theme → 'dark'; removed theme → mapped survivor; malformed JSON → defaults. */
export function migratePrefs(raw: string | null): ThemePrefsV2 {
  let parsed: Record<string, unknown> = {}
  try {
    const p: unknown = JSON.parse(raw || '{}')
    if (p && typeof p === 'object' && !Array.isArray(p)) parsed = p as Record<string, unknown>
  } catch { /* malformed → defaults */ }

  let theme: ThemeId = PREFS_DEFAULTS.theme
  if (isThemeId(parsed.theme)) theme = parsed.theme
  else if (typeof parsed.theme === 'string' && parsed.theme in REMOVED_THEME_MAP) theme = REMOVED_THEME_MAP[parsed.theme]

  const fontScale = typeof parsed.fontScale === 'number' && isFinite(parsed.fontScale)
    ? Math.min(1.2, Math.max(0.85, parsed.fontScale)) : PREFS_DEFAULTS.fontScale

  const density: Density = parsed.density === 'compact' || parsed.density === 'spacious' ? parsed.density : 'comfortable'
  const sound = typeof parsed.sound === 'boolean' ? parsed.sound : PREFS_DEFAULTS.sound

  const customByTheme: ThemePrefsV2['customByTheme'] = {}
  if (parsed.customByTheme && typeof parsed.customByTheme === 'object' && !Array.isArray(parsed.customByTheme)) {
    for (const [k, v] of Object.entries(parsed.customByTheme as Record<string, unknown>)) {
      if (isThemeId(k) && v && typeof v === 'object' && !Array.isArray(v)) {
        customByTheme[k] = v as Partial<ThemeCustomization>
      }
    }
  }

  return { version: 2, theme, fontScale, density, sound, customByTheme }
}

/* ── Effective style → CSS vars (written inline on <html>) ───────────────── */

export function effectiveCustomization(id: ThemeId, custom?: Partial<ThemeCustomization>): ThemeCustomization {
  return { ...THEME_DEFS[id].defaults, ...(custom || {}) }
}

/** Blend an "r g b" triplet toward white (dark schemes) / black (light) for boosted contrast. */
function boost(triplet: string, mode: 'dark' | 'light', amount: number): string {
  const target = mode === 'dark' ? 255 : 0
  return triplet.split(/\s+/).map(c => {
    const n = Number(c)
    return String(Math.round(n + (target - n) * amount))
  }).join(' ')
}

/** All theme-managed CSS vars for a theme + its customization. ThemeProvider
 *  writes exactly this map inline on <html> (removing stale keys on switch). */
export function computeCssVars(id: ThemeId, custom?: Partial<ThemeCustomization>): Record<string, string> {
  const def = THEME_DEFS[id]
  const t = def.tokens
  const c = effectiveCustomization(id, custom)

  const accent = c.accent || t.color.accent
  const boosted = c.contrast === 'boosted'
  const text = boosted ? boost(t.color.text, t.color.scheme, 0.35) : t.color.text
  const heading = boosted ? boost(t.color.heading, t.color.scheme, 0.5) : t.color.heading
  const muted = boosted ? boost(t.color.muted, t.color.scheme, 0.22) : t.color.muted
  const border = boosted ? boost(t.color.border, t.color.scheme, 0.18) : t.color.border

  const radius = RADIUS_PRESETS[c.radius]
  const shadow = SHADOW_PRESETS[c.shadowDepth]
  const tracking = c.typography === 'default' ? t.typography.tracking : TYPO_TRACKING[c.typography]

  const vars: Record<string, string> = {
    '--bg': t.color.bg, '--surface': t.color.surface, '--panel': t.color.panel,
    '--border': border, '--strip': t.color.strip,
    '--muted': muted, '--text': text, '--heading': heading,
    '--accent': accent, '--success': t.color.success, '--warning': t.color.warning,
    '--danger': t.color.danger, '--purple': t.color.purple,
    '--theme-accent-2': t.color.accent2,
    '--theme-glow': c.accent ? accent : t.color.glow,
    '--radius-card': radius.card, '--radius-button': radius.button, '--radius-input': radius.input,
    '--shadow-card': shadow.card, '--shadow-popover': shadow.popover,
    '--tracking-ui': TRACKING[tracking],
    '--bg-overlay-opacity': String(t.background.overlayOpacity),
  }
  t.dataViz.palette.forEach((p, i) => { vars[`--chart-${i + 1}`] = p })
  return vars
}

/** html attributes derived from the effective style (background/motion/component feel). */
export function computeDataAttrs(id: ThemeId, custom?: Partial<ThemeCustomization>): Record<string, string> {
  const c = effectiveCustomization(id, custom)
  return {
    'data-bg-style': c.background,
    'data-theme-motion': c.motion,
    'data-card-style': c.cardStyle,
    'data-button-style': c.buttonStyle,
  }
}
