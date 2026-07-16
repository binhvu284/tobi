// Pure helpers + mode config extracted from pages/Chat.tsx.
import { MessageSquarePlus, Wrench, Terminal, Search, Briefcase } from 'lucide-react'
import type { ChatMode } from './chatTypes'
import type { ChatPicker, ChatAttachment } from '../../api'

// Local YouTube detection for the composer chip only — the backend does the real
// fetch after Send (a pasted link is consent to read the transcript). (#14)
export const YT_RE = /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)([A-Za-z0-9_-]{11})/gi
export const findYouTube = (text: string): string[] => {
  const ids = new Set<string>()
  for (const m of (text || '').matchAll(YT_RE)) ids.add(m[1])
  return [...ids]
}

export const DEFAULT_STARTERS = ['What should I focus on today?', 'Give me a status report of the office.', 'Draft a message for me', 'Plan my day']
// #16 [D23]: the main selector is Chat / Agent. The legacy five-mode list stays reachable
// behind the chat.mode_v2 feature flag (rollback path, D27/D29).
export const CHAT_MODES_V2: { id: ChatMode; label: string; hint: string; Icon: typeof MessageSquarePlus }[] = [
  { id: 'chat', label: 'Chat', hint: 'Fast conversation', Icon: MessageSquarePlus },
  { id: 'agent', label: 'Agent', hint: 'Plans, acts, reports — with a work timeline', Icon: Wrench },
]
export const CHAT_MODES_LEGACY: { id: ChatMode; label: string; hint: string; Icon: typeof MessageSquarePlus }[] = [
  { id: 'chat', label: 'Chat', hint: 'Fast conversation', Icon: MessageSquarePlus },
  { id: 'agent', label: 'Agent', hint: 'Plans and uses tools', Icon: Wrench },
  { id: 'terminal', label: 'Terminal', hint: 'Command intent', Icon: Terminal },
  { id: 'research', label: 'Research', hint: 'Web-backed answers', Icon: Search },
  { id: 'project', label: 'Project', hint: 'PM-aware work', Icon: Briefcase },
]
// Safe one-time migration of the persisted mode [spec §15]: terminal→agent (command
// execution lives in Agent now), research/project→chat (DR toggle / auto context).
export const MODE_MIGRATE: Record<string, ChatMode> = { terminal: 'agent', research: 'chat', project: 'chat' }
export const migrateStoredMode = (raw: string | null, v2: boolean): ChatMode => {
  const m = (raw || 'chat') as ChatMode
  if (!v2) return (['chat', 'agent', 'terminal', 'research', 'project'] as ChatMode[]).includes(m) ? m : 'chat'
  const mapped = MODE_MIGRATE[m] ?? m
  return mapped === 'agent' ? 'agent' : 'chat'
}

// Manual picker (Feature 3): the owner asks TOBI to "ask me for my details" → this default
// context set. TOBI can also raise a tailored picker itself via the ask_owner_details tool.
export const DEFAULT_DETAIL_PICKER: ChatPicker = {
  topic: 'A few details about you',
  questions: [
    { question: 'What should I focus on helping you with right now?' },
    { question: 'What are you working on this week?' },
    { question: "What's your preferred communication style?", options: ['Concise & direct', 'Detailed & thorough', 'Casual & friendly', 'Formal'] },
    { question: 'Any deadlines, constraints, or context I should keep in mind?' },
  ],
}
export const shortModel = (id?: string | null) => (id || '').split(':').pop()?.split('/').pop() || ''
export const fmtTime = (s?: string) => { if (!s) return ''; try { return new Date(s).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) } catch { return '' } }
export const fmtAbsolute = (s?: string) => { if (!s) return ''; try { return new Date(s).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) } catch { return '' } }
export const fmtRelative = (s?: string) => {
  if (!s) return ''
  try {
    const diff = Math.floor((Date.now() - new Date(s).getTime()) / 1000)
    if (diff < 60) return 'just now'
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return fmtTime(s)
  } catch { return '' }
}
export const minuteKey = (s?: string) => { if (!s) return ''; try { const d = new Date(s); return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}-${d.getHours()}-${d.getMinutes()}` } catch { return '' } }

export const COLUMN = 'mx-auto w-full max-w-[760px]'
export const fmtBytes = (n: number) => n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`
export const attBytes = (a: ChatAttachment) =>
  a.data_url ? Math.round((a.data_url.length - (a.data_url.indexOf(',') + 1)) * 0.75) : (a.text?.length || 0)

export const readDataURL = (f: File) => new Promise<string>((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result as string); r.onerror = rej; r.readAsDataURL(f) })
