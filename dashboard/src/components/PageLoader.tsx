import { type CSSProperties } from 'react'
import { motion } from 'framer-motion'
import {
  LayoutDashboard, Network, Zap, TrendingUp, Shield, Kanban, FolderKanban,
  Terminal, HeartPulse, Settings, Brain, MessagesSquare, Share2, KeyRound, type LucideIcon,
} from 'lucide-react'

/**
 * Unified, themeable page-loading effect for the whole app.
 *
 * Every page reuses this one component via a named preset, so a new page just
 * adds an entry to LOADER_PRESETS and renders <PageLoader preset="x" />. Each
 * preset is unique (name · color · icon · skeleton layout) but the *effect*
 * (glowing icon, shimmering name, running bar, skeleton) is identical and synced.
 */

type SkelVariant = 'cards' | 'list' | 'board' | 'stats'

export type LoaderPreset = {
  name: string
  Icon: LucideIcon
  color: string        // solid CSS color — drives glow, bar, icon, name
  message?: string
  skeleton: SkelVariant
  dark?: boolean       // black canvas (Office / cyberpunk pages)
}

// Theme v2.1: preset colors are theme tokens so the loader matches the active
// theme instead of flashing dark-theme accents on light themes. `dark:true` pages
// (Office/Graph) keep their pinned cyberpunk canvas below.
export const LOADER_PRESETS = {
  dashboard:    { name: 'Dashboard',    Icon: LayoutDashboard, color: 'rgb(var(--accent))',  message: 'Syncing live operating status…',   skeleton: 'stats' },
  architecture: { name: 'Architecture', Icon: Network,         color: 'rgb(var(--chart-1))', message: 'Mapping the system topology…',      skeleton: 'cards' },
  ability:      { name: 'Ability',      Icon: Zap,             color: 'rgb(var(--warning))', message: 'Loading skill matrix…',             skeleton: 'cards' },
  evolution:    { name: 'Evolution',    Icon: TrendingUp,      color: 'rgb(var(--purple))',  message: 'Computing growth & tiers…',         skeleton: 'list'  },
  office:       { name: 'Tobi HQ',      Icon: Shield,          color: 'rgb(88,166,255)',     message: 'Initializing mission control…',     skeleton: 'board', dark: true },
  task:         { name: 'Tasks',        Icon: Kanban,          color: 'rgb(var(--chart-6))', message: 'Loading the board…',                skeleton: 'board' },
  projects:     { name: 'Projects',     Icon: FolderKanban,    color: 'rgb(var(--success))', message: 'Fetching projects…',                skeleton: 'list'  },
  control:      { name: 'Control Room', Icon: Terminal,        color: 'rgb(var(--success))', message: 'Spinning up engines…',              skeleton: 'cards' },
  health:       { name: 'Health',       Icon: HeartPulse,      color: 'rgb(var(--success))', message: 'Pinging every system…',             skeleton: 'list'  },
  settings:     { name: 'Settings',     Icon: Settings,        color: 'rgb(var(--muted))',   message: 'Loading preferences…',              skeleton: 'cards' },
  brain:        { name: 'Brain',        Icon: Brain,           color: 'rgb(var(--purple))',  message: 'Loading what I know about you…',     skeleton: 'list'  },
  chat:         { name: 'Chat',         Icon: MessagesSquare,  color: 'rgb(var(--accent))',  message: 'Waking up…',                        skeleton: 'list'  },
  graph:        { name: 'Graph',        Icon: Share2,          color: 'rgb(56,189,248)',     message: 'Weaving the second brain…',         skeleton: 'cards', dark: true },
  integrations: { name: 'Integrations', Icon: KeyRound,        color: 'rgb(var(--chart-6))', message: 'Opening the vault…',                skeleton: 'cards' },
} satisfies Record<string, LoaderPreset>

export type PresetKey = keyof typeof LOADER_PRESETS

function Skeleton({ variant }: { variant: SkelVariant }) {
  if (variant === 'stats') {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="tobi-skel h-20" />)}
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => <div key={i} className="tobi-skel h-44" />)}
        </div>
      </div>
    )
  }
  if (variant === 'board') {
    return (
      <div className="flex gap-4 overflow-hidden">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex-1 space-y-3">
            <div className="tobi-skel h-7 w-2/3" />
            {Array.from({ length: 3 }).map((_, j) => <div key={j} className="tobi-skel h-24" />)}
          </div>
        ))}
      </div>
    )
  }
  if (variant === 'list') {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, i) => <div key={i} className="tobi-skel h-16" />)}
      </div>
    )
  }
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => <div key={i} className="tobi-skel h-36" />)}
    </div>
  )
}

export default function PageLoader({
  preset,
  compact = false,
  name,
  Icon,
  color,
  message,
  skeleton,
  dark,
}: {
  preset?: PresetKey
  /** Hide the identity hero (use inside a page that already shows its header). */
  compact?: boolean
} & Partial<LoaderPreset>) {
  const p: LoaderPreset | undefined = preset ? LOADER_PRESETS[preset] : undefined
  const cfg: LoaderPreset = {
    name: name ?? p?.name ?? 'Loading',
    Icon: Icon ?? p?.Icon ?? LayoutDashboard,
    color: color ?? p?.color ?? 'rgb(var(--accent))',
    message: message ?? p?.message ?? 'Loading…',
    skeleton: skeleton ?? p?.skeleton ?? 'cards',
    dark: dark ?? p?.dark ?? false,
  }
  const IconC = cfg.Icon
  const cssVars = { '--bar-color': cfg.color, '--glow': cfg.color } as CSSProperties

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      style={cssVars}
      className={`flex h-full w-full flex-col gap-5 overflow-hidden p-5 sm:p-6 ${cfg.dark ? 'bg-[#020202]' : ''}`}
    >
      {!compact && (
        <div className="flex items-center gap-4">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 320, damping: 20 }}
            className="tobi-icon-glow flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border"
            style={{ borderColor: cfg.color, '--glow': cfg.color } as CSSProperties}
          >
            <IconC size={22} style={{ color: cfg.color }} />
          </motion.div>
          <div className="min-w-0">
            <div className="tobi-name-shimmer text-lg font-bold tracking-wide" style={{ '--name-color': cfg.color } as CSSProperties}>
              {cfg.name}
            </div>
            <div className="text-xs text-muted">{cfg.message}</div>
          </div>
        </div>
      )}

      <div className="tobi-runbar h-1 w-full" style={{ background: 'rgb(var(--border) / 0.35)' }} />

      <div className="min-h-0 flex-1 overflow-hidden opacity-70">
        <Skeleton variant={cfg.skeleton} />
      </div>
    </motion.div>
  )
}
