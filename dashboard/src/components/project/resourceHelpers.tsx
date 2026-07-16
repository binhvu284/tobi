// Resource type-icon map + helpers, extracted from ResourcesTab.tsx.
import {
  FileText, FileSpreadsheet, Presentation, FileImage, FileVideo, FileAudio,
  FileArchive, FileCode2, File as FileIcon, Youtube, Github, Globe2, Link2,
} from 'lucide-react'

export const RTYPE_ICON: Record<string, { Icon: typeof FileIcon; tone: string }> = {
  doc:     { Icon: FileText,        tone: 'text-sky-400' },
  pdf:     { Icon: FileText,        tone: 'text-red-400' },
  sheet:   { Icon: FileSpreadsheet, tone: 'text-emerald-400' },
  slides:  { Icon: Presentation,    tone: 'text-amber-400' },
  image:   { Icon: FileImage,       tone: 'text-violet-400' },
  video:   { Icon: FileVideo,       tone: 'text-pink-400' },
  audio:   { Icon: FileAudio,       tone: 'text-teal-400' },
  archive: { Icon: FileArchive,     tone: 'text-orange-400' },
  code:    { Icon: FileCode2,       tone: 'text-cyan-400' },
  youtube: { Icon: Youtube,         tone: 'text-red-500' },
  github:  { Icon: Github,          tone: 'text-text' },
  web:     { Icon: Globe2,          tone: 'text-sky-400' },
  link:    { Icon: Link2,           tone: 'text-accent' },
  file:    { Icon: FileIcon,        tone: 'text-muted' },
}

export function RTypeIcon({ rtype, size = 16, className = '' }: { rtype?: string | null; size?: number; className?: string }) {
  const { Icon, tone } = RTYPE_ICON[rtype || 'file'] ?? RTYPE_ICON.file
  return <Icon size={size} className={`${tone} ${className}`} />
}

export function ytId(url: string): string | null {
  const m = (url || '').match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/|youtube\.com\/embed\/)([A-Za-z0-9_-]{11})/)
  return m ? m[1] : null
}
