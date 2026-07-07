/**
 * SourceLogo — brand mark for the Explore/News data sources (HN, GitHub, Product
 * Hunt, Reddit, X, RSS, GNews, Tavily, OpenRouter, NewsData, GDELT). Same visual
 * language as LlmLogo: a brand-tinted rounded tile via color-mix. Two variants:
 *   - `tile`  (default): full rounded chip, sized like LlmLogo
 *   - `inline`: bare mark only, for tight badges (font-size driven)
 *
 * `name` is the explore source id (hackernews, github, …) or 'openrouter'.
 */
import {
  SiYcombinator, SiGithub, SiProducthunt, SiReddit, SiX, SiRss,
  SiGooglenews, SiOpenrouter, type IconType,
} from '@icons-pack/react-simple-icons'
import { Newspaper, Globe } from 'lucide-react'
import tavilySvg from '@lobehub/icons-static-svg/icons/tavily-color.svg?raw'

type Mark =
  | { kind: 'icon'; Icon: IconType; color: string }
  | { kind: 'lucide'; Icon: any; color: string }
  | { kind: 'raw'; svg: string; color: string }

const MARKS: Record<string, Mark> = {
  hackernews:  { kind: 'icon',   Icon: SiYcombinator, color: '#FF6600' },
  github:      { kind: 'icon',   Icon: SiGithub,      color: '#f0f6fc' },
  producthunt: { kind: 'icon',   Icon: SiProducthunt, color: '#DA552F' },
  reddit:      { kind: 'icon',   Icon: SiReddit,      color: '#FF4500' },
  x:           { kind: 'icon',   Icon: SiX,           color: '#a0a0a0' },
  rss:         { kind: 'icon',   Icon: SiRss,         color: '#FFA500' },
  gnews:       { kind: 'icon',   Icon: SiGooglenews,  color: '#4285F4' },
  openrouter:  { kind: 'icon',   Icon: SiOpenrouter,  color: '#8B7CF6' },
  tavily:      { kind: 'raw',    svg: tavilySvg,      color: '#6C5CE7' },
  newsdata:    { kind: 'lucide', Icon: Newspaper,     color: '#22a3e0' },
  gdelt:       { kind: 'lucide', Icon: Globe,         color: '#2ecc71' },
}

export const SOURCE_META: Record<string, { label: string; color: string }> = {
  hackernews: { label: 'Hacker News', color: '#FF6600' },
  github: { label: 'GitHub', color: '#f0f6fc' },
  producthunt: { label: 'Product Hunt', color: '#DA552F' },
  reddit: { label: 'Reddit', color: '#FF4500' },
  x: { label: 'X', color: '#a0a0a0' },
  rss: { label: 'RSS', color: '#FFA500' },
  gnews: { label: 'GNews', color: '#4285F4' },
  openrouter: { label: 'OpenRouter', color: '#8B7CF6' },
  tavily: { label: 'Tavily', color: '#6C5CE7' },
  newsdata: { label: 'NewsData.io', color: '#22a3e0' },
  gdelt: { label: 'GDELT', color: '#2ecc71' },
}

export function sourceMeta(name?: string | null) {
  return SOURCE_META[(name || '').toLowerCase()] || { label: name || 'source', color: '#8B949E' }
}

function Inner({ m, size }: { m: Mark; size: number }) {
  if (m.kind === 'icon') return <m.Icon size={size} color={m.color} />
  if (m.kind === 'lucide') return <m.Icon size={size} color={m.color} />
  return <span style={{ display: 'inline-flex', fontSize: size, color: m.color }} dangerouslySetInnerHTML={{ __html: m.svg }} />
}

export default function SourceLogo({ name, size = 13, variant = 'tile', className = '' }: {
  name?: string | null; size?: number; variant?: 'tile' | 'inline'; className?: string
}) {
  const key = (name || '').toLowerCase()
  const m = MARKS[key] || { kind: 'lucide' as const, Icon: Newspaper, color: '#8B949E' }
  if (variant === 'inline') {
    return <Inner m={m} size={size} />
  }
  const meta = sourceMeta(name)
  return (
    <span title={meta.label} aria-label={meta.label}
      className={`flex shrink-0 items-center justify-center rounded-md ${className}`}
      style={{
        width: size + 9, height: size + 9,
        background: `color-mix(in srgb, ${meta.color} 16%, rgb(var(--surface)))`,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${meta.color} 30%, transparent)`,
      }}>
      <Inner m={m} size={size} />
    </span>
  )
}
