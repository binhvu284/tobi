import {
  SiAnthropic, SiTelegram, SiGithub, SiNotion, SiVercel, SiSupabase,
  SiGoogle, SiGmail, SiStripe, type IconType,
} from '@icons-pack/react-simple-icons'

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

export default function BrandLogo({ id, label }: { id: string; label?: string }) {
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
