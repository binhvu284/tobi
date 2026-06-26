import { Check, Volume2, VolumeX, RotateCcw, Type, Rows, Palette, Sparkles } from 'lucide-react'
import { useTheme, THEMES, THEME_META, type Theme } from '../context/ThemeProvider'
import { useMotion, type MotionSetting } from '../context/MotionProvider'
import { sfx } from '../hooks/useSound'

const MOTION_OPTS: { key: MotionSetting; label: string; hint: string }[] = [
  { key: 'full', label: 'Full', hint: 'All HUD motion & signature effects' },
  { key: 'reduced', label: 'Reduced', hint: 'Fades only — no slides, sweeps or loops' },
  { key: 'off', label: 'Off', hint: 'Instant — zero animation' },
]

function ThemeSwatch({ t }: { t: Theme }) {
  // data-theme on the swatch resolves the tokens to THAT theme — real preview.
  return (
    <div data-theme={t} className="flex gap-1 rounded bg-bg p-1.5 ring-1 ring-border">
      <span className="h-4 w-4 rounded-sm bg-accent" />
      <span className="h-4 w-4 rounded-sm bg-success" />
      <span className="h-4 w-4 rounded-sm bg-warning" />
      <span className="h-4 w-4 rounded-sm bg-surface ring-1 ring-border" />
    </div>
  )
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-heading">{icon}{title}</div>
      {children}
    </div>
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
        <button onClick={reset} className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-text">
          <RotateCcw size={13} /> Reset
        </button>
      </div>

      <div className="space-y-4">
        <Section title="Theme" icon={<Palette size={15} className="text-accent" />}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {THEMES.map((t: Theme) => (
              <button key={t} onClick={() => { set({ theme: t }); sfx.select() }}
                className={`flex flex-col gap-2 rounded-lg border p-3 text-left transition-colors ${theme === t ? 'border-accent bg-accent/10' : 'border-border hover:border-white/20'}`}>
                <div className="flex items-center justify-between">
                  <ThemeSwatch t={t} />
                  {theme === t && <Check size={14} className="text-accent" />}
                </div>
                <div>
                  <div className="text-xs font-semibold text-heading">{THEME_META[t].label}</div>
                  <div className="text-[10px] text-muted">{THEME_META[t].hint}</div>
                </div>
              </button>
            ))}
          </div>
        </Section>

        <Section title="Density" icon={<Rows size={15} className="text-accent" />}>
          <div className="flex gap-2">
            {(['comfortable', 'compact'] as const).map(d => (
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
                className={`flex flex-col gap-1 rounded-lg border p-3 text-left transition-colors ${motionSetting === o.key ? 'border-accent bg-accent/10' : 'border-border hover:border-white/20'}`}>
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
      </div>
    </div>
  )
}
