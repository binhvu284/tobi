import { motion } from 'framer-motion'

export function fmtDate(s?: string | null) {
  if (!s) return '—'
  try { return new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) } catch { return s }
}

export function fmtAgo(s?: string | null) {
  if (!s) return '—'
  try {
    const m = Math.floor((Date.now() - new Date(s).getTime()) / 60000)
    if (m < 1) return 'just now'
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    return `${Math.floor(h / 24)}d ago`
  } catch { return s }
}

export function fmtBytes(n?: number | null) {
  const v = n || 0
  if (v >= 1024 ** 3) return `${(v / 1024 ** 3).toFixed(1)} GB`
  if (v >= 1024 ** 2) return `${(v / 1024 ** 2).toFixed(1)} MB`
  if (v >= 1024) return `${(v / 1024).toFixed(1)} KB`
  return `${v} B`
}

export function fmtMinutes(min?: number | null) {
  const m = Math.round(min || 0)
  if (m >= 480) return `${(m / 480).toFixed(1)}d`
  if (m >= 60) return `${(m / 60).toFixed(1)}h`
  return `${m}m`
}

export function Bar({ pct, color = 'bg-accent' }: { pct: number; color?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-overlay/8">
      <motion.div className={`h-full rounded-full ${color}`}
        initial={{ width: 0 }} animate={{ width: `${Math.min(100, pct)}%` }}
        transition={{ duration: 0.5, ease: 'easeOut' }} />
    </div>
  )
}

export const TASK_STATUS_COLORS: Record<string, string> = {
  planned:           'bg-muted/15 text-muted',
  in_progress:       'bg-accent/15 text-accent',
  paused:            'bg-warning/15 text-warning',
  blocked:           'bg-danger/15 text-danger',
  needs_owner_input: 'bg-orange-400/15 text-orange-400',
  done:              'bg-success/15 text-success',
  cancelled:         'bg-muted/10 text-muted',
}

export const PRIORITY_COLORS: Record<string, string> = {
  P0: 'text-danger', P1: 'text-warning', P2: 'text-accent', P3: 'text-muted',
}

export const STATUS_CFG: Record<string, { label: string; color: string; dot: string }> = {
  idea:     { label: 'Idea',     color: 'bg-purple-500/15 text-purple-400 border-purple-500/30', dot: 'bg-purple-400' },
  active:   { label: 'Active',   color: 'bg-accent/15 text-accent border-accent/30',             dot: 'bg-accent' },
  done:     { label: 'Done',     color: 'bg-success/15 text-success border-success/30',          dot: 'bg-success' },
  archived: { label: 'Archived', color: 'bg-muted/15 text-muted border-muted/30',                dot: 'bg-muted' },
}
