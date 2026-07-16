// Connector catalog + glyphs, extracted from pages/Chat.tsx.
import { SiGithub, SiGoogle, SiNotion, SiVercel, SiSupabase, type IconType } from '@icons-pack/react-simple-icons'

export type ConnectorCatalogItem = {
  id: string
  label: string
  desc: string
  match: string[]
  color: string
  Icon?: IconType
  CustomIcon?: (props: { size?: number }) => JSX.Element
}

export function SlackLogo({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true">
      <rect x="6.8" y="1" width="2.4" height="6.1" rx="1.2" fill="#36C5F0" />
      <rect x="1" y="6.8" width="6.1" height="2.4" rx="1.2" fill="#2EB67D" />
      <rect x="6.8" y="8.9" width="2.4" height="6.1" rx="1.2" fill="#ECB22E" />
      <rect x="8.9" y="6.8" width="6.1" height="2.4" rx="1.2" fill="#E01E5A" />
      <circle cx="5.2" cy="5.2" r="1.2" fill="#2EB67D" />
      <circle cx="10.8" cy="5.2" r="1.2" fill="#36C5F0" />
      <circle cx="5.2" cy="10.8" r="1.2" fill="#ECB22E" />
      <circle cx="10.8" cy="10.8" r="1.2" fill="#E01E5A" />
    </svg>
  )
}

export const CONNECTOR_CATALOG: ConnectorCatalogItem[] = [
  { id: 'github', label: 'GitHub', desc: 'Repos, PRs, issues', match: ['github'], color: '#F0F6FC', Icon: SiGithub },
  { id: 'google', label: 'Google Workspace', desc: 'Drive, Gmail, Calendar', match: ['google', 'gmail', 'drive', 'calendar'], color: '#4285F4', Icon: SiGoogle },
  { id: 'notion', label: 'Notion', desc: 'Docs and knowledge base', match: ['notion'], color: '#F0F0F0', Icon: SiNotion },
  { id: 'vercel', label: 'Vercel', desc: 'Deploys & previews', match: ['vercel'], color: 'currentColor', Icon: SiVercel },
  { id: 'supabase', label: 'Supabase', desc: 'Database & auth', match: ['supabase'], color: '#3FCF8E', Icon: SiSupabase },
  { id: 'slack', label: 'Slack', desc: 'Team messages and channels', match: ['slack'], color: '#E01E5A', CustomIcon: SlackLogo },
]

export function connectorMatches(item: ConnectorCatalogItem, opt: { id: string; label: string }) {
  const haystack = `${opt.id} ${opt.label}`.toLowerCase()
  return item.match.some(m => haystack.includes(m))
}

export function ConnectorGlyph({ item, size = 15 }: { item: ConnectorCatalogItem; size?: number }) {
  const Icon = item.Icon
  if (Icon) return <Icon size={size} color={item.color} />
  if (item.CustomIcon) return <item.CustomIcon size={size} />
  return <span className="text-[10px] font-bold" style={{ color: item.color }}>{item.label.slice(0, 1)}</span>
}

export function ConnectorMark({ item, size = 15 }: { item: ConnectorCatalogItem; size?: number }) {
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-bg/50">
      <ConnectorGlyph item={item} size={size} />
    </span>
  )
}
