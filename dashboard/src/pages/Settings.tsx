import { useEffect, useState } from 'react'
import { softFail } from '../lib/report'
import {
  Check, Volume2, VolumeX, RotateCcw, Type, Rows, Palette, Sparkles, Globe, Save,
  SlidersHorizontal, FileUp,
} from 'lucide-react'
import { useTheme } from '../context/ThemeProvider'
import {
  THEME_DEFS, THEME_GROUPS, DECOR_THEMES, ACCENT_PRESETS, type ThemeId,
  type RadiusPreset, type CardStyle, type ButtonStyle, type BackgroundStyle,
  type ShadowDepth, type TypographyPreset, type MotionIntensity,
} from '../context/themeTokens'
import { useMotion, type MotionSetting } from '../context/MotionProvider'
import { sfx } from '../hooks/useSound'
import { getOwnerSettings, patchOwnerSettings } from '../api.brain'
import { useToast } from '../context/ToastProvider'

const MOTION_OPTS: { key: MotionSetting; label: string; hint: string }[] = [
  { key: 'full', label: 'Full', hint: 'All HUD motion & signature effects' },
  { key: 'reduced', label: 'Reduced', hint: 'Fades only — no slides, sweeps or loops' },
  { key: 'off', label: 'Off', hint: 'Instant — zero animation' },
]

/* Rich per-theme preview card. The wrapper carries data-theme={t}, so every
   token class inside resolves to THAT theme's fallback block — a real mini-UI
   (header + card + button + swatches) rendered in the theme's own colors, radius,
   shadow, and display font. Pure CSS, no iframe. Shows theme *defaults* (not the
   owner's per-theme customization) — the live page covers customization feedback. */
function ThemePreviewCard({ t, active, onPick }: { t: ThemeId; active: boolean; onPick: () => void }) {
  const def = THEME_DEFS[t]
  const Icon = def.icon
  return (
    <button onClick={onPick} data-theme={t} title={def.description}
      className={`group relative overflow-hidden rounded-xl border text-left transition-all ${
        active ? 'border-accent ring-1 ring-accent/40' : 'border-border hover:border-overlay/30'}`}
      style={{ background: 'rgb(var(--bg))' }}>
      {/* mini header bar */}
      <div className="flex items-center gap-1.5 border-b px-2.5 py-1.5"
        style={{ borderColor: 'rgb(var(--border))', background: 'rgb(var(--surface))' }}>
        <span className="h-2 w-2 rounded-full" style={{ background: 'rgb(var(--accent))' }} />
        <span className="font-display text-[11px] font-bold" style={{ color: 'rgb(var(--heading))' }}>Aa</span>
        <span className="ml-auto h-1.5 w-5 rounded-full" style={{ background: 'rgb(var(--muted) / 0.4)' }} />
      </div>
      {/* mini body: card + button + status dots */}
      <div className="space-y-2 p-2.5">
        <div className="p-1.5"
          style={{ background: 'rgb(var(--surface))', border: '1px solid rgb(var(--border))', boxShadow: 'var(--shadow-card)', borderRadius: 'var(--radius-card)' }}>
          <div className="h-1.5 w-3/4 rounded-full" style={{ background: 'rgb(var(--muted) / 0.55)' }} />
          <div className="mt-1 h-1.5 w-1/2 rounded-full" style={{ background: 'rgb(var(--muted) / 0.3)' }} />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="px-2 py-1 text-[8px] font-semibold text-white"
            style={{ background: 'rgb(var(--accent))', borderRadius: 'var(--radius-button)' }}>Aa</span>
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: 'rgb(var(--success))' }} />
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: 'rgb(var(--warning))' }} />
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: 'rgb(var(--theme-accent-2))' }} />
        </div>
      </div>
      {/* label footer */}
      <div className="flex items-center justify-between gap-1 border-t px-2.5 py-1.5"
        style={{ borderColor: 'rgb(var(--border))', background: 'rgb(var(--surface))' }}>
        <span className="flex min-w-0 items-center gap-1.5">
          <Icon size={12} style={{ color: active ? 'rgb(var(--accent))' : 'rgb(var(--muted))' }} />
          <span className="truncate text-[11px] font-semibold" style={{ color: 'rgb(var(--heading))' }}>{def.label}</span>
        </span>
        {active && <Check size={12} style={{ color: 'rgb(var(--accent))' }} />}
      </div>
    </button>
  )
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="tv2-card p-5">
      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-heading">{icon}{title}</div>
      {children}
    </div>
  )
}

/* ── Theme v2 guided customization (#13 §9) — presets, not freeform ────────── */

function Chip<T extends string>({ value, active, onPick }: { value: T; active: boolean; onPick: (v: T) => void }) {
  return (
    <button onClick={() => onPick(value)}
      className={`rounded-full border px-2.5 py-1 text-[11px] capitalize transition-colors ${
        active ? 'border-accent/40 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
      {value}
    </button>
  )
}

function ControlRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 py-1.5">
      <span className="w-24 shrink-0 text-[11px] text-muted">{label}</span>
      {children}
    </div>
  )
}

const RADIUS_OPTS: RadiusPreset[] = ['sharp', 'soft', 'rounded']
const CARD_OPTS: CardStyle[] = ['flat', 'outlined', 'glass', 'layered']
const BUTTON_OPTS: ButtonStyle[] = ['solid', 'ghost', 'outline', 'glass']
const BG_OPTS: BackgroundStyle[] = ['plain', 'grid', 'gradient', 'paper', 'hud']
const SHADOW_OPTS: ShadowDepth[] = ['flat', 'soft', 'deep', 'glow']
const TYPO_OPTS: TypographyPreset[] = ['default', 'technical', 'calm']
const ANIM_OPTS: MotionIntensity[] = ['quiet', 'standard', 'expressive']
const CONTRAST_OPTS = ['standard', 'boosted'] as const

function ThemeCustomizer() {
  const { theme, custom, customByTheme, setCustom, resetCustom } = useTheme()
  const def = THEME_DEFS[theme]
  const dirty = Object.keys(customByTheme[theme] ?? {}).length > 0

  return (
    <div className="mt-4 border-t border-border/60 pt-3">
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
          <SlidersHorizontal size={12} /> Customize {def.label}
        </div>
        <button onClick={resetCustom} disabled={!dirty}
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] text-muted transition-colors hover:text-text disabled:cursor-default disabled:opacity-40">
          <RotateCcw size={11} /> Reset theme
        </button>
      </div>

      <ControlRow label="Accent">
        <button onClick={() => setCustom({ accent: null })} title={`${def.label} default`}
          className={`flex h-6 items-center gap-1 rounded-full border px-2 text-[10px] transition-colors ${
            custom.accent === null ? 'border-accent/50 text-accent' : 'border-border text-muted hover:text-text'}`}>
          <span className="h-3 w-3 rounded-full" style={{ background: `rgb(${def.tokens.color.accent})` }} /> Default
        </button>
        {ACCENT_PRESETS.map(a => (
          <button key={a.value} onClick={() => setCustom({ accent: a.value })} title={a.label}
            className={`h-6 w-6 rounded-full border-2 transition-transform hover:scale-110 ${
              custom.accent === a.value ? 'border-heading' : 'border-transparent'}`}
            style={{ background: `rgb(${a.value})` }} />
        ))}
      </ControlRow>
      <ControlRow label="Radius">
        {RADIUS_OPTS.map(v => <Chip key={v} value={v} active={custom.radius === v} onPick={r => setCustom({ radius: r })} />)}
      </ControlRow>
      <ControlRow label="Cards">
        {CARD_OPTS.map(v => <Chip key={v} value={v} active={custom.cardStyle === v} onPick={c => setCustom({ cardStyle: c })} />)}
      </ControlRow>
      <ControlRow label="Buttons">
        {BUTTON_OPTS.map(v => <Chip key={v} value={v} active={custom.buttonStyle === v} onPick={b => setCustom({ buttonStyle: b })} />)}
      </ControlRow>
      <ControlRow label="Background">
        {BG_OPTS.map(v => <Chip key={v} value={v} active={custom.background === v} onPick={b => setCustom({ background: b })} />)}
      </ControlRow>
      <ControlRow label="Shadows">
        {SHADOW_OPTS.map(v => <Chip key={v} value={v} active={custom.shadowDepth === v} onPick={s => setCustom({ shadowDepth: s })} />)}
      </ControlRow>
      <ControlRow label="Typography">
        {TYPO_OPTS.map(v => <Chip key={v} value={v} active={custom.typography === v} onPick={t => setCustom({ typography: t })} />)}
      </ControlRow>
      <ControlRow label="Animation">
        {ANIM_OPTS.map(v => <Chip key={v} value={v} active={custom.motion === v} onPick={m => setCustom({ motion: m })} />)}
      </ControlRow>
      <ControlRow label="Contrast">
        {CONTRAST_OPTS.map(v => <Chip key={v} value={v} active={custom.contrast === v} onPick={c => setCustom({ contrast: c })} />)}
      </ControlRow>
      {/* Chat ambient ornaments — only offered on themes that have a signature motif (M2.5). */}
      {DECOR_THEMES.includes(theme) && (
        <ControlRow label="Decoration">
          {(['on', 'off'] as const).map(v => <Chip key={v} value={v} active={custom.decorations === v} onPick={d => setCustom({ decorations: d })} />)}
          <span className="text-[10px] text-muted">Chat ambient motif</span>
        </ControlRow>
      )}
      <p className="mt-1 text-[10px] text-muted">Saved per theme — switching themes remembers each one's tweaks.</p>

      {/* Theme v3 import placeholder (#13 §10): quiet + disabled, no file input. */}
      <div className="mt-3 flex items-center justify-between rounded-lg border border-dashed border-border/60 px-3 py-2.5 opacity-60">
        <div className="flex items-center gap-2 text-[11px] text-muted">
          <FileUp size={13} /> Import custom theme from file
        </div>
        <span className="rounded bg-overlay/5 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-muted">
          Coming in Theme v3
        </span>
      </div>
    </div>
  )
}

const TIMEZONES = [
  { value: 'Asia/Ho_Chi_Minh', label: 'Vietnam (UTC+7)' },
  { value: 'Asia/Bangkok', label: 'Bangkok (UTC+7)' },
  { value: 'Asia/Singapore', label: 'Singapore (UTC+8)' },
  { value: 'Asia/Shanghai', label: 'Shanghai (UTC+8)' },
  { value: 'Asia/Tokyo', label: 'Tokyo (UTC+9)' },
  { value: 'Asia/Seoul', label: 'Seoul (UTC+9)' },
  { value: 'Asia/Kolkata', label: 'India (UTC+5:30)' },
  { value: 'Europe/London', label: 'London (UTC+0/+1)' },
  { value: 'Europe/Paris', label: 'Paris (UTC+1/+2)' },
  { value: 'America/New_York', label: 'New York (UTC-5/-4)' },
  { value: 'America/Los_Angeles', label: 'Los Angeles (UTC-8/-7)' },
  { value: 'UTC', label: 'UTC' },
]

function TimezoneSection() {
  const [tz, setTz] = useState('Asia/Ho_Chi_Minh')
  const [saved, setSaved] = useState(false)
  const { toast } = useToast()

  useEffect(() => {
    getOwnerSettings().then(s => { if (s.timezone) setTz(s.timezone) }).catch(softFail('your settings'))
  }, [])

  async function save() {
    try {
      await patchOwnerSettings({ timezone: tz })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) { toast({ kind: 'error', title: 'Failed to save', detail: (e as Error).message }) }
  }

  return (
    <Section title="Timezone" icon={<Globe size={15} className="text-accent" />}>
      <div className="flex items-center gap-3">
        <select value={tz} onChange={e => { setTz(e.target.value); setSaved(false) }}
          className="flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent">
          {TIMEZONES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <button onClick={save} className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ${saved ? 'border-success/40 bg-success/10 text-success' : 'border-border text-muted hover:text-text'}`}>
          {saved ? <Check size={14} /> : <Save size={14} />} {saved ? 'Saved' : 'Save'}
        </button>
      </div>
      <p className="mt-2 text-[11px] text-muted">Used by the header clock and TOBI's datetime awareness.</p>
    </Section>
  )
}

export default function Settings() {
  const { theme, fontScale, density, sound, set, reset } = useTheme()
  const { setting: motionSetting, level: motionLevel, setSetting: setMotion } = useMotion()

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-heading">Settings</h1>
          <p className="text-xs text-muted">Customize the look & feel — saved to this browser. (Office keeps its cyberpunk theme.)</p>
        </div>
        <button onClick={reset} className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-text"
          title="Reset all appearance preferences">
          <RotateCcw size={13} /> Reset
        </button>
      </div>

      <div className="space-y-4">
        <Section title="Theme" icon={<Palette size={15} className="text-accent" />}>
          <div className="space-y-4">
            {THEME_GROUPS.map(g => (
              <div key={g.id}>
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">{g.label}</div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {g.themes.map(t => (
                    <ThemePreviewCard key={t} t={t} active={theme === t}
                      onPick={() => { set({ theme: t }); sfx.select() }} />
                  ))}
                </div>
              </div>
            ))}
          </div>
          <ThemeCustomizer />
        </Section>

        <Section title="Density" icon={<Rows size={15} className="text-accent" />}>
          <div className="flex gap-2">
            {(['compact', 'comfortable', 'spacious'] as const).map(d => (
              <button key={d} onClick={() => set({ density: d })}
                className={`flex-1 rounded-lg border px-3 py-2 text-sm capitalize transition-colors ${density === d ? 'border-accent bg-accent/10 text-accent' : 'border-border text-muted hover:text-text'}`}>
                {d}
              </button>
            ))}
          </div>
        </Section>

        <Section title="Motion" icon={<Sparkles size={15} className="text-accent" />}>
          <div className="grid grid-cols-3 gap-2">
            {MOTION_OPTS.map(o => (
              <button key={o.key} onClick={() => { setMotion(o.key); if (o.key !== 'off') sfx.select() }}
                className={`flex flex-col gap-1 rounded-lg border p-3 text-left transition-colors ${motionSetting === o.key ? 'border-accent bg-accent/10' : 'border-border hover:border-overlay/20'}`}>
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-semibold ${motionSetting === o.key ? 'text-accent' : 'text-heading'}`}>{o.label}</span>
                  {motionSetting === o.key && <Check size={14} className="text-accent" />}
                </div>
                <span className="text-[10px] leading-tight text-muted">{o.hint}</span>
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-muted">
            Controls route transitions, signature effects & ambient motion across Mission Control.
            {motionLevel !== motionSetting && <span className="text-warning"> Your OS prefers reduced motion, so effects are clamped to “{motionLevel}”.</span>}
          </p>
        </Section>

        <Section title="Text size" icon={<Type size={15} className="text-accent" />}>
          <div className="flex items-center gap-4">
            <input type="range" min={0.85} max={1.2} step={0.05} value={fontScale}
              onChange={e => set({ fontScale: Number(e.target.value) })} className="flex-1 accent-accent" />
            <span className="w-12 text-right font-mono text-sm text-text">{Math.round(fontScale * 100)}%</span>
          </div>
        </Section>

        <Section title="Sound" icon={sound ? <Volume2 size={15} className="text-accent" /> : <VolumeX size={15} className="text-muted" />}>
          <button onClick={() => { const next = !sound; set({ sound: next }); if (next) setTimeout(() => sfx.success(), 50) }}
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${sound ? 'border-accent bg-accent/10 text-accent' : 'border-border text-muted hover:text-text'}`}>
            {sound ? <Volume2 size={15} /> : <VolumeX size={15} />} UI sound ticks: {sound ? 'On' : 'Off'}
          </button>
          <p className="mt-2 text-[11px] text-muted">Subtle clicks/confirms across the app. Off by default.</p>
        </Section>

        <TimezoneSection />
      </div>
    </div>
  )
}
