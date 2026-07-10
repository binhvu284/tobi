/* ── Theme v2.1 token system (queue #13) ───────────────────────────────────────
   Single source of truth for theme identity: colors, shape, elevation, density,
   typography (incl. per-theme fonts), component feel, background, chart palette,
   motion intensity, and Chat ornaments. `index.css` keeps a per-[data-theme] CSS
   fallback of the same values (first paint + Settings previews + Office's pinned
   dark wrappers); ThemeProvider writes the effective set — theme defaults merged
   with the owner's per-theme customization — inline on <html>, which preserves
   instant switching. THE TWO MUST STAY IN SYNC (a node parity test enforces it).
   12 active themes in 3 groups: core (dark/light/hightech), expressive (gaming/
   japanese/chinese/jarvis), brand (vercel/notion/linear/chatgpt/claude).
   Spec: docs/feature-idea-queue/THEME_V2_SYSTEM_UPGRADE_PLAN.md (+ v2.1 design pass) */
import type { CSSProperties, ReactNode } from 'react'
import {
  Moon, Sun, Gamepad2, Cpu, Flower2, Landmark, Bot,
  Triangle, FileText, Command,
} from 'lucide-react'
import { ClaudeLogo, OpenAILogo } from '../theme/brandIcons'

/** Theme selector icon — a bare call signature so both lucide's forwardRef icons
 *  and the official brand-mark components satisfy it. */
export type ThemeIcon = (props: { size?: number; className?: string; style?: CSSProperties }) => ReactNode

export type ThemeId =
  | 'dark' | 'light' | 'hightech'
  | 'gaming' | 'japanese' | 'chinese' | 'jarvis'
  | 'vercel' | 'notion' | 'linear' | 'chatgpt' | 'claude'

/** Order = display order in every selector. */
export const ACTIVE_THEMES: ThemeId[] = [
  'dark', 'light', 'hightech',
  'gaming', 'japanese', 'chinese', 'jarvis',
  'vercel', 'notion', 'linear', 'chatgpt', 'claude',
]

export type ThemeGroup = 'core' | 'expressive' | 'brand'
export type Density = 'compact' | 'comfortable' | 'spacious'
export type RadiusPreset = 'sharp' | 'soft' | 'rounded'
export type ShadowDepth = 'flat' | 'soft' | 'deep' | 'glow'
export type ButtonStyle = 'solid' | 'ghost' | 'outline' | 'glass'
export type CardStyle = 'flat' | 'outlined' | 'glass' | 'layered'
export type BackgroundStyle = 'plain' | 'grid' | 'gradient' | 'paper' | 'hud'
export type MotionIntensity = 'quiet' | 'standard' | 'expressive'
export type TypographyPreset = 'default' | 'technical' | 'calm'
export type Tracking = 'normal' | 'wide' | 'tight'
export type NumericStyle = 'normal' | 'tabular'
export type DecorationSetting = 'on' | 'off'

/** System stacks (fonts.ts self-hosts the branded families via @fontsource). */
export const SYSTEM_UI = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
const SERIF = 'Georgia, "Times New Roman", serif'
const font = (family: string) => `"${family}", ${SYSTEM_UI}`

/** Colors are "r g b" channel triplets so Tailwind's `bg-accent/10` keeps working. */
export type ThemeV2Tokens = {
  color: {
    scheme: 'dark' | 'light'
    bg: string; surface: string; panel: string; border: string; strip: string
    muted: string; text: string; heading: string
    accent: string; success: string; warning: string; danger: string; purple: string
    accent2: string; glow: string
    /** Hover/wash tint — '255 255 255' on dark schemes, an ink triplet on light. */
    overlay: string
    /** ::selection tint (usually the accent). */
    selection: string
  }
  typography: {
    tracking: Tracking
    /** Full CSS font stack for UI text, or null = system stack. */
    fontUi: string | null
    /** Display/heading stack, or null = falls back to fontUi. */
    fontDisplay: string | null
    numeric: NumericStyle
  }
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
  /** Chat ambient ornaments (sakura/dragon/arc…) — only affects decorated themes. */
  decorations: DecorationSetting
}

export type ThemeDef = {
  id: ThemeId
  label: string
  description: string
  icon: ThemeIcon
  mode: 'dark' | 'light'
  group: ThemeGroup
  tokens: ThemeV2Tokens
  /** Default customization derived from tokens — what "Reset theme" restores. */
  defaults: ThemeCustomization
  /** All guided controls are available on every theme (owner decision). */
  customizable: (keyof ThemeCustomization)[]
  /** Removed v1 themes that migrate here. */
  migrationFrom: string[]
}

const ALL_CONTROLS: (keyof ThemeCustomization)[] = [
  'accent', 'radius', 'cardStyle', 'buttonStyle', 'background', 'shadowDepth', 'typography', 'motion', 'contrast', 'decorations',
]

/** Theme ids that render a Chat ambient ornament (M2.5). Single source of truth —
 *  ChatAmbient renders these, Settings shows the decoration toggle only for these. */
export const DECOR_THEMES: ThemeId[] = ['gaming', 'japanese', 'chinese', 'jarvis', 'claude']

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
    decorations: 'on',
  }
}

/* ── Core themes ─────────────────────────────────────────────────────────── */

const DARK: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '13 17 23', surface: '22 27 34', panel: '16 21 28', border: '48 54 61', strip: '22 27 34',
    muted: '139 148 158', text: '201 209 217', heading: '240 246 252',
    accent: '88 166 255', success: '63 185 80', warning: '210 153 34', danger: '248 81 73', purple: '139 92 246',
    accent2: '139 92 246', glow: '88 166 255', overlay: '255 255 255', selection: '88 166 255',
  },
  typography: { tracking: 'normal', fontUi: null, fontDisplay: null, numeric: 'normal' },
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
    accent2: '124 58 237', glow: '37 99 235', overlay: '15 23 42', selection: '37 99 235',
  },
  typography: { tracking: 'normal', fontUi: null, fontDisplay: null, numeric: 'normal' },
  shape: { radius: 'soft' },
  elevation: { shadowDepth: 'soft' },
  component: { buttonStyle: 'solid', cardStyle: 'outlined' },
  background: { style: 'plain', overlayOpacity: 0.03 },
  dataViz: { palette: ['37 99 235', '124 58 237', '22 163 74', '202 138 4', '220 38 38', '13 148 136'], glowCharts: false },
  motion: { intensity: 'standard' },
}

/** Clean engineering dashboard: cool blues, teal accents, precise borders, restrained glow. */
const HIGHTECH: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '10 16 28', surface: '16 26 44', panel: '13 21 36', border: '44 62 92', strip: '16 26 44',
    muted: '128 148 178', text: '198 214 234', heading: '235 245 255',
    accent: '56 189 248', success: '45 212 191', warning: '245 191 66', danger: '248 113 113', purple: '129 140 248',
    accent2: '45 212 191', glow: '56 189 248', overlay: '255 255 255', selection: '56 189 248',
  },
  typography: { tracking: 'tight', fontUi: null, fontDisplay: null, numeric: 'normal' },
  shape: { radius: 'sharp' },
  elevation: { shadowDepth: 'soft' },
  component: { buttonStyle: 'outline', cardStyle: 'outlined' },
  background: { style: 'grid', overlayOpacity: 0.05 },
  dataViz: { palette: ['56 189 248', '45 212 191', '129 140 248', '245 191 66', '248 113 113', '148 163 184'], glowCharts: false },
  motion: { intensity: 'standard' },
}

/* ── Expressive themes (v2.1 redesign — calm-premium, strong identity) ────── */

/** Neon Arena — charcoal-violet stage, electric violet, tempered lime, pink for highlights. */
const GAMING: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '15 13 22', surface: '22 19 32', panel: '18 16 27', border: '52 46 74', strip: '22 19 32',
    muted: '148 142 168', text: '224 221 235', heading: '245 243 252',
    accent: '155 92 240', success: '140 220 90', warning: '245 176 46', danger: '244 63 94', purple: '196 100 245',
    accent2: '236 72 153', glow: '155 92 240', overlay: '255 255 255', selection: '155 92 240',
  },
  typography: { tracking: 'wide', fontUi: null, fontDisplay: font('Rajdhani'), numeric: 'normal' },
  shape: { radius: 'sharp' },
  elevation: { shadowDepth: 'glow' },
  component: { buttonStyle: 'glass', cardStyle: 'layered' },
  background: { style: 'hud', overlayOpacity: 0.04 },
  dataViz: { palette: ['155 92 240', '236 72 153', '140 220 90', '245 176 46', '34 211 238', '244 63 94'], glowCharts: true },
  motion: { intensity: 'expressive' },
}

/** Washi — warm paper, deepened sakura, matcha, Muji-calm minimal cards. */
const JAPANESE: ThemeV2Tokens = {
  color: {
    scheme: 'light',
    bg: '252 250 247', surface: '255 255 255', panel: '248 245 240', border: '229 222 214', strip: '243 238 231',
    muted: '122 113 108', text: '43 42 51', heading: '32 30 36',
    accent: '216 82 120', success: '104 159 92', warning: '196 138 58', danger: '198 76 82', purple: '138 116 180',
    accent2: '138 116 180', glow: '216 82 120', overlay: '43 42 51', selection: '216 82 120',
  },
  typography: { tracking: 'wide', fontUi: null, fontDisplay: font('Zen Maru Gothic'), numeric: 'normal' },
  shape: { radius: 'rounded' },
  elevation: { shadowDepth: 'soft' },
  component: { buttonStyle: 'solid', cardStyle: 'flat' },
  background: { style: 'paper', overlayOpacity: 0.04 },
  dataViz: { palette: ['216 82 120', '138 116 180', '104 159 92', '196 138 58', '198 76 82', '120 140 160'], glowCharts: false },
  motion: { intensity: 'quiet' },
}

/** Lacquer — maroon-brown lacquer, softened vermilion, champagne gold, ivory. Premium not festive. */
const CHINESE: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '25 17 15', surface: '38 27 24', panel: '31 22 20', border: '82 58 48', strip: '38 27 24',
    muted: '178 150 134', text: '236 222 208', heading: '250 241 228',
    accent: '200 60 50', success: '110 168 110', warning: '214 158 62', danger: '234 88 76', purple: '170 110 150',
    accent2: '212 175 111', glow: '212 175 111', overlay: '255 255 255', selection: '212 175 111',
  },
  typography: { tracking: 'normal', fontUi: null, fontDisplay: font('ZCOOL XiaoWei'), numeric: 'normal' },
  shape: { radius: 'soft' },
  elevation: { shadowDepth: 'deep' },
  component: { buttonStyle: 'solid', cardStyle: 'layered' },
  background: { style: 'gradient', overlayOpacity: 0.05 },
  dataViz: { palette: ['200 60 50', '212 175 111', '110 168 110', '230 150 60', '234 88 76', '170 120 90'], glowCharts: false },
  motion: { intensity: 'standard' },
}

/** Arc — deep space navy, desaturated cyan, electric-blue secondary, quiet HUD, tabular metrics. */
const JARVIS: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '7 13 26', surface: '12 22 40', panel: '9 17 32', border: '32 54 86', strip: '12 22 40',
    muted: '116 142 174', text: '192 214 238', heading: '228 241 255',
    accent: '44 188 240', success: '62 214 170', warning: '250 184 76', danger: '250 92 104', purple: '128 122 250',
    accent2: '82 128 255', glow: '44 188 240', overlay: '255 255 255', selection: '44 188 240',
  },
  typography: { tracking: 'wide', fontUi: null, fontDisplay: font('Chakra Petch'), numeric: 'tabular' },
  shape: { radius: 'sharp' },
  elevation: { shadowDepth: 'glow' },
  component: { buttonStyle: 'outline', cardStyle: 'glass' },
  background: { style: 'hud', overlayOpacity: 0.05 },
  dataViz: { palette: ['44 188 240', '82 128 255', '62 214 170', '250 184 76', '250 92 104', '128 122 250'], glowCharts: true },
  motion: { intensity: 'expressive' },
}

/* ── Brand-inspired themes (tasteful homage; no logos/asset cloning) ──────── */

/** Vercel — monochrome precision; blue only where it means action. */
const VERCEL: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '10 10 10', surface: '20 20 20', panel: '15 15 15', border: '46 46 46', strip: '20 20 20',
    muted: '160 160 160', text: '224 224 224', heading: '250 250 250',
    accent: '0 112 243', success: '69 212 131', warning: '245 166 35', danger: '229 72 77', purple: '121 40 202',
    accent2: '237 237 237', glow: '0 112 243', overlay: '255 255 255', selection: '0 112 243',
  },
  typography: { tracking: 'tight', fontUi: font('Geist Variable'), fontDisplay: null, numeric: 'normal' },
  shape: { radius: 'sharp' },
  elevation: { shadowDepth: 'flat' },
  component: { buttonStyle: 'solid', cardStyle: 'outlined' },
  background: { style: 'plain', overlayOpacity: 0.03 },
  dataViz: { palette: ['0 112 243', '121 40 202', '80 230 217', '245 166 35', '229 72 77', '136 136 136'], glowCharts: false },
  motion: { intensity: 'quiet' },
}

/** Notion Calm — paper-quiet workspace, minimal borders, low shadow. */
const NOTION: ThemeV2Tokens = {
  color: {
    scheme: 'light',
    bg: '247 246 243', surface: '255 255 255', panel: '247 246 243', border: '233 231 226', strip: '241 239 234',
    muted: '120 119 116', text: '55 53 47', heading: '25 23 17',
    accent: '35 131 226', success: '68 131 97', warning: '203 145 47', danger: '212 76 71', purple: '144 101 176',
    accent2: '144 101 176', glow: '35 131 226', overlay: '55 53 47', selection: '35 131 226',
  },
  typography: { tracking: 'normal', fontUi: null, fontDisplay: null, numeric: 'normal' },
  shape: { radius: 'soft' },
  elevation: { shadowDepth: 'flat' },
  component: { buttonStyle: 'solid', cardStyle: 'flat' },
  background: { style: 'plain', overlayOpacity: 0.03 },
  dataViz: { palette: ['35 131 226', '144 101 176', '68 131 97', '203 145 47', '212 76 71', '159 107 83'], glowCharts: false },
  motion: { intensity: 'quiet' },
}

/** Linear Flow — refined dark, indigo signal, crisp lines, subtle flow glow. */
const LINEAR: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '13 14 20', surface: '21 23 31', panel: '17 18 26', border: '42 45 58', strip: '21 23 31',
    muted: '138 143 158', text: '210 214 225', heading: '244 245 248',
    accent: '94 106 210', success: '76 183 130', warning: '242 153 74', danger: '235 87 87', purple: '176 136 240',
    accent2: '133 144 229', glow: '94 106 210', overlay: '255 255 255', selection: '94 106 210',
  },
  typography: { tracking: 'tight', fontUi: font('Inter Variable'), fontDisplay: null, numeric: 'normal' },
  shape: { radius: 'soft' },
  elevation: { shadowDepth: 'soft' },
  component: { buttonStyle: 'solid', cardStyle: 'outlined' },
  background: { style: 'gradient', overlayOpacity: 0.04 },
  dataViz: { palette: ['94 106 210', '133 144 229', '76 183 130', '242 153 74', '235 87 87', '148 155 176'], glowCharts: false },
  motion: { intensity: 'standard' },
}

/** ChatGPT — the chatgpt.com dark chat UI: neutral charcoal (#212121 canvas,
 *  #171717 rail, #2F2F2F input), soft white text, the signature teal as signal. */
const CHATGPT: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '33 33 33', surface: '47 47 47', panel: '23 23 23', border: '61 61 61', strip: '23 23 23',
    muted: '158 158 158', text: '236 236 236', heading: '255 255 255',
    accent: '16 163 127', success: '82 196 110', warning: '236 154 60', danger: '239 83 80', purple: '171 104 255',
    accent2: '236 236 236', glow: '16 163 127', overlay: '255 255 255', selection: '16 163 127',
  },
  typography: { tracking: 'normal', fontUi: null, fontDisplay: null, numeric: 'normal' },
  shape: { radius: 'rounded' },
  elevation: { shadowDepth: 'flat' },
  component: { buttonStyle: 'solid', cardStyle: 'flat' },
  background: { style: 'plain', overlayOpacity: 0.03 },
  dataViz: { palette: ['16 163 127', '171 104 255', '96 165 250', '236 154 60', '239 83 80', '142 142 147'], glowCharts: false },
  motion: { intensity: 'quiet' },
}

/** Claude — the claude.ai dark chat UI: warm charcoal (#262624 canvas, #1F1E1D
 *  rail, #302F2C cards), cream text, book-cloth terracotta, serif display. */
const CLAUDE: ThemeV2Tokens = {
  color: {
    scheme: 'dark',
    bg: '38 38 36', surface: '48 47 44', panel: '31 30 29', border: '66 64 59', strip: '31 30 29',
    muted: '163 158 148', text: '232 229 222', heading: '248 246 240',
    accent: '217 119 87', success: '108 178 126', warning: '214 158 62', danger: '237 85 78', purple: '158 134 214',
    accent2: '193 95 60', glow: '217 119 87', overlay: '255 255 255', selection: '217 119 87',
  },
  typography: { tracking: 'normal', fontUi: null, fontDisplay: `"Lora Variable", ${SERIF}`, numeric: 'normal' },
  shape: { radius: 'rounded' },
  elevation: { shadowDepth: 'soft' },
  component: { buttonStyle: 'solid', cardStyle: 'flat' },
  background: { style: 'plain', overlayOpacity: 0.04 },
  dataViz: { palette: ['217 119 87', '108 178 126', '158 134 214', '214 158 62', '237 85 78', '168 162 150'], glowCharts: false },
  motion: { intensity: 'quiet' },
}

export const THEME_DEFS: Record<ThemeId, ThemeDef> = {
  dark: {
    id: 'dark', label: 'Dark Default', description: 'GitHub-dark baseline — calm, familiar, precise.',
    icon: Moon, mode: 'dark', group: 'core', tokens: DARK, defaults: defaultsFrom(DARK),
    customizable: ALL_CONTROLS, migrationFrom: ['contrast', 'warm'],
  },
  light: {
    id: 'light', label: 'Light Default', description: 'Clean & bright — crisp premium SaaS light mode.',
    icon: Sun, mode: 'light', group: 'core', tokens: LIGHT, defaults: defaultsFrom(LIGHT),
    customizable: ALL_CONTROLS, migrationFrom: ['scientific'],
  },
  hightech: {
    id: 'hightech', label: 'High Tech', description: 'Engineering dashboard — cool blues, teal, precise lines.',
    icon: Cpu, mode: 'dark', group: 'core', tokens: HIGHTECH, defaults: defaultsFrom(HIGHTECH),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  gaming: {
    id: 'gaming', label: 'Neon Arena', description: 'Esports HUD — electric violet on charcoal, sakura-lime energy.',
    icon: Gamepad2, mode: 'dark', group: 'expressive', tokens: GAMING, defaults: defaultsFrom(GAMING),
    customizable: ALL_CONTROLS, migrationFrom: ['midnight'],
  },
  japanese: {
    id: 'japanese', label: 'Washi', description: 'Warm paper & sakura — Muji-calm, minimal, quietly elegant.',
    icon: Flower2, mode: 'light', group: 'expressive', tokens: JAPANESE, defaults: defaultsFrom(JAPANESE),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  chinese: {
    id: 'chinese', label: 'Lacquer', description: 'Lacquer & champagne gold — premium, festive but composed.',
    icon: Landmark, mode: 'dark', group: 'expressive', tokens: CHINESE, defaults: defaultsFrom(CHINESE),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  jarvis: {
    id: 'jarvis', label: 'Jarvis OS', description: 'Arc-reactor blue — deep-space navy, glowing, analytical.',
    icon: Bot, mode: 'dark', group: 'expressive', tokens: JARVIS, defaults: defaultsFrom(JARVIS),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  vercel: {
    id: 'vercel', label: 'Vercel', description: 'Monochrome precision — pure black, Geist, blue for action only.',
    icon: Triangle, mode: 'dark', group: 'brand', tokens: VERCEL, defaults: defaultsFrom(VERCEL),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  notion: {
    id: 'notion', label: 'Notion Calm', description: 'Paper-quiet workspace — off-white, ink text, low shadow.',
    icon: FileText, mode: 'light', group: 'brand', tokens: NOTION, defaults: defaultsFrom(NOTION),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  linear: {
    id: 'linear', label: 'Linear Flow', description: 'Refined dark — indigo signal, Inter, crisp issue-tracker feel.',
    icon: Command, mode: 'dark', group: 'brand', tokens: LINEAR, defaults: defaultsFrom(LINEAR),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  chatgpt: {
    id: 'chatgpt', label: 'ChatGPT', description: 'The chatgpt.com dark UI — neutral charcoal, teal signal.',
    icon: OpenAILogo, mode: 'dark', group: 'brand', tokens: CHATGPT, defaults: defaultsFrom(CHATGPT),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
  claude: {
    id: 'claude', label: 'Claude', description: 'The claude.ai dark UI — warm charcoal, terracotta, serif.',
    icon: ClaudeLogo, mode: 'dark', group: 'brand', tokens: CLAUDE, defaults: defaultsFrom(CLAUDE),
    customizable: ALL_CONTROLS, migrationFrom: [],
  },
}

/** Grouped view for selectors (derived — guaranteed to partition ACTIVE_THEMES). */
export const THEME_GROUPS: { id: ThemeGroup; label: string; themes: ThemeId[] }[] = [
  { id: 'core', label: 'Core', themes: ACTIVE_THEMES.filter(t => THEME_DEFS[t].group === 'core') },
  { id: 'expressive', label: 'Expressive', themes: ACTIVE_THEMES.filter(t => THEME_DEFS[t].group === 'expressive') },
  { id: 'brand', label: 'Brand', themes: ACTIVE_THEMES.filter(t => THEME_DEFS[t].group === 'brand') },
]

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
  // Softened in v2.1: glow was too harsh on the expressive/HUD themes.
  glow: {
    card: '0 0 0 1px rgb(var(--accent) / 0.05), 0 0 14px -6px rgb(var(--accent) / 0.12)',
    popover: '0 16px 44px -12px rgb(var(--accent) / 0.20)',
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
  const fontUi = t.typography.fontUi ?? SYSTEM_UI
  const fontDisplay = t.typography.fontDisplay ?? t.typography.fontUi ?? SYSTEM_UI

  const vars: Record<string, string> = {
    '--bg': t.color.bg, '--surface': t.color.surface, '--panel': t.color.panel,
    '--border': border, '--strip': t.color.strip,
    '--muted': muted, '--text': text, '--heading': heading,
    '--accent': accent, '--success': t.color.success, '--warning': t.color.warning,
    '--danger': t.color.danger, '--purple': t.color.purple,
    '--theme-accent-2': t.color.accent2,
    '--theme-glow': c.accent ? accent : t.color.glow,
    '--overlay': t.color.overlay,
    '--selection': c.accent ? accent : t.color.selection,
    '--font-ui': fontUi, '--font-display': fontDisplay,
    '--font-numeric': t.typography.numeric === 'tabular' ? 'tabular-nums' : 'normal',
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
    'data-decorations': c.decorations,
  }
}
