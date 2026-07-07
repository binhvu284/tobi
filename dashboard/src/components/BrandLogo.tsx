import {
  SiAnthropic, SiTelegram, SiGithub, SiNotion, SiVercel, SiSupabase,
  SiGoogle, SiGmail, SiStripe, SiYcombinator, SiReddit, SiOpenrouter,
  type IconType,
} from '@icons-pack/react-simple-icons'
import codexSvg from '@lobehub/icons-static-svg/icons/codex-color.svg?raw'

/* Accurate brand logos (Simple Icons) per integration id. `color` is chosen to
 * read clearly on the dark cards — brands whose official mark is near-black
 * (GitHub/Notion/Vercel) are shown in a light tone instead. */
type Brand = { Icon: IconType; color: string }

const BRANDS: Record<string, Brand> = {
  llm:      { Icon: SiAnthropic, color: '#D97757' }, // Claude clay
  telegram: { Icon: SiTelegram,  color: '#26A5E4' },
  github:   { Icon: SiGithub,    color: '#f0f6fc' },
  notion:   { Icon: SiNotion,    color: '#f0f6fc' },
  vercel:   { Icon: SiVercel,    color: '#f0f6fc' },
  supabase: { Icon: SiSupabase,  color: '#3FCF8E' },
  google:   { Icon: SiGoogle,    color: '#4285F4' },
  gmail:    { Icon: SiGmail,     color: '#EA4335' },
  stripe:   { Icon: SiStripe,    color: '#635BFF' },
}

const CODEX_COLOR = '#10A37F'
const EXPLORE_COLOR = '#22a3e0'

export default function BrandLogo({ id, label }: { id: string; label?: string }) {
  // Codex ships its own colored mark via @lobehub (no Simple Icons entry).
  if (id === 'codex') {
    return (
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-bg"
        style={{ boxShadow: `inset 0 0 12px ${CODEX_COLOR}1f` }}
        aria-label={label || 'Codex'}
        dangerouslySetInnerHTML={{ __html: `<span style="display:inline-flex;font-size:18px;color:${CODEX_COLOR}">${codexSvg}</span>` }} />
    )
  }
  // Explore (News) — composite of 4 overlapping source marks (HN + Reddit + GitHub
  // + OpenRouter) to signal "scouts many sources" without a single brand.
  if (id === 'explore') {
    const layers: { Icon: IconType; color: string; style: React.CSSProperties }[] = [
      { Icon: SiYcombinator, color: '#FF6600', style: { top: 3, left: 3, zIndex: 4 } },
      { Icon: SiReddit, color: '#FF4500', style: { top: 3, right: 3, zIndex: 3 } },
      { Icon: SiGithub, color: '#f0f6fc', style: { bottom: 3, left: 3, zIndex: 2 } },
      { Icon: SiOpenrouter, color: '#8B7CF6', style: { bottom: 3, right: 3, zIndex: 1 } },
    ]
    return (
      <span className="relative flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-bg"
        style={{ boxShadow: `inset 0 0 12px ${EXPLORE_COLOR}1f` }} aria-label={label || 'Explore'}>
        {layers.map(({ Icon, color, style }, i) => (
          <span key={i} className="absolute" style={style}>
            <Icon size={11} color={color} />
          </span>
        ))}
      </span>
    )
  }
  const brand = BRANDS[id]
  if (!brand) {
    return (
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-bg text-xs font-bold text-muted">
        {(label || id).slice(0, 1).toUpperCase()}
      </span>
    )
  }
  const { Icon, color } = brand
  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-bg"
      style={{ boxShadow: `inset 0 0 12px ${color}1f` }}>
      <Icon size={18} color={color} title={label} />
    </span>
  )
}
