import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence, LayoutGroup } from 'framer-motion'
import {
  LayoutDashboard, Network, Zap, Building2, Kanban, HeartPulse, Settings,
  Menu, X, Bell, Palette, Circle, FolderKanban, TrendingUp,
  ChevronsLeft, ChevronsRight, ChevronUp, ChevronDown, Brain, MessagesSquare,
  Share2, KeyRound, Inbox, FileText, Code2, Workflow, History, Cpu, HardDrive,
  Newspaper, Activity, Plus, Search,
} from 'lucide-react'
import { useTheme } from '../context/ThemeProvider'
import { THEME_GROUPS, THEME_DEFS } from '../context/themeTokens'
import { useToast } from '../context/ToastProvider'
import { WORKSPACE_ROUTES, MAX_WORKSPACE_TABS, getWorkspaceRouteMeta, useWorkspaceTabs } from '../context/WorkspaceTabsContext'
import { getOfficeStats, getEvolution, pmListProjects, type OfficeStats, type EvolutionReport, type PMProject } from '../api'
import CommandPalette from './CommandPalette'
import TierEmblem from './TierEmblem'
import ClockCalendar from './ClockCalendar'
import ProjectIcon from './project/ProjectIcon'
import { SPRING, DUR, EASE } from '../lib/motion'

const APP_VERSION = 'v3.0'

const NAV = [
  { group: 'Main', links: [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/inbox', icon: Inbox, label: 'Inbox' },
    { to: '/chat', icon: MessagesSquare, label: 'Chat' },
    { to: '/projects', icon: FolderKanban, label: 'Projects' },
  ] },
  { group: 'Persona', links: [
    { to: '/brain', icon: Brain, label: 'Brain' },
    { to: '/graph', icon: Share2, label: 'Graph' },
    { to: '/architecture', icon: Network, label: 'Architecture' },
    { to: '/ability', icon: Zap, label: 'Ability' },
    { to: '/evolution', icon: TrendingUp, label: 'Evolution' },
    { to: '/health', icon: HeartPulse, label: 'Health' },
    { to: '/actions', icon: History, label: 'Actions' },
  ] },
  { group: 'Operation', links: [
    { to: '/office', icon: Building2, label: 'Office' },
    { to: '/task', icon: Kanban, label: 'Tasks' },
  ] },
  { group: 'Explore', links: [
    { to: '/news', icon: Newspaper, label: 'News' },
  ] },
]
const ALL_LINKS = NAV.flatMap(g => g.links)

// Bottom badge menu — system and owner-control surfaces.
const BOTTOM_MENU: { to?: string; icon: typeof Settings; label: string; soon?: boolean }[] = [
  { to: '/settings', icon: Settings, label: 'Setting' },
  { to: '/models', icon: Cpu, label: 'Models' },
  { to: '/storage', icon: HardDrive, label: 'Storage' },
  { icon: FileText, label: 'Document', soon: true },
  { to: '/integrations', icon: KeyRound, label: 'Integrations' },
  { to: '/mcp', icon: Workflow, label: 'MCP' },
  { to: '/developer', icon: Code2, label: 'Developer' },
]

// Mobile bottom tabs (by path so it survives nav reordering)
const TAB_PATHS = ['/dashboard', '/inbox', '/chat', '/office', '/task']
const TAB_LINKS = TAB_PATHS.map(p => ALL_LINKS.find(l => l.to === p)!).filter(Boolean)

function navClass(isActive: boolean, collapsed = false) {
  return `flex items-center rounded-md py-2 text-sm transition-colors ${collapsed ? 'justify-center px-0' : 'gap-3 px-3'} ${
    isActive ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-overlay/5 hover:text-text'}`
}

// ── Collapsible nav section ──────────────────────────────────────────────────
function NavSection({ group, links, collapsed, onNavigate, open, onToggle }: {
  group: string
  links: { to: string; icon: typeof Zap; label: string }[]
  collapsed: boolean
  onNavigate?: () => void
  open: boolean
  onToggle: () => void
}) {
  const recents = useRecentProjects()
  const [projectsOpen, setProjectsOpen] = useState(() => { try { return localStorage.getItem('tobi.sidebar.projects') !== '0' } catch { return true } })
  useEffect(() => { try { localStorage.setItem('tobi.sidebar.projects', projectsOpen ? '1' : '0') } catch { /* ignore */ } }, [projectsOpen])
  if (collapsed) {
    return (
      <div>
        <div className="mx-2 my-2 border-t border-border/60" />
        <div className="space-y-0.5">
          {links.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} onClick={onNavigate} title={label}
              className={({ isActive }) => navClass(isActive, true)}>
              <Icon size={16} className="shrink-0" />
            </NavLink>
          ))}
        </div>
      </div>
    )
  }
  return (
    <div>
      <button onClick={onToggle}
        className="group flex w-full items-center justify-between rounded-md px-3 py-1 text-[10px] font-semibold tracking-widest text-muted transition-colors hover:text-text">
        <span>{group.toUpperCase()}</span>
        <ChevronDown size={12} className={`opacity-50 transition-transform duration-200 group-hover:opacity-100 ${open ? '' : '-rotate-90'}`} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.18 }} className="overflow-hidden">
            <div className="mt-0.5 space-y-0.5">
              {links.map(({ to, icon: Icon, label }) => {
                const showToggle = to === '/projects' && recents.length > 0
                return (
                  <div key={to}>
                    <div className="relative">
                      <NavLink to={to} onClick={onNavigate}
                        className={({ isActive }) => `relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${showToggle ? 'pr-9' : ''} ${
                          isActive ? 'text-accent' : 'text-muted hover:bg-overlay/5 hover:text-text'}`}>
                        {({ isActive }) => (
                          <>
                            {/* Sliding active pill — one shared layoutId per sidebar instance */}
                            {isActive && (
                              <motion.span layoutId="navActive" transition={SPRING.snappy}
                                className="absolute inset-0 z-0 rounded-md bg-accent/15 ring-1 ring-accent/20" />
                            )}
                            <motion.span whileHover={{ scale: 1.18 }} transition={SPRING.pop} className="relative z-10 shrink-0">
                              <Icon size={16} />
                            </motion.span>
                            <span className="relative z-10">{label}</span>
                          </>
                        )}
                      </NavLink>
                      {/* Projects expands to recently-opened workspaces — toggle to collapse */}
                      {showToggle && (
                        <button
                          onClick={() => setProjectsOpen(o => !o)}
                          aria-label={projectsOpen ? 'Collapse projects' : 'Expand projects'}
                          aria-expanded={projectsOpen} title="Recent projects"
                          className="absolute right-1 top-1/2 z-20 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-muted transition-colors hover:bg-overlay/10 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
                          <ChevronDown size={14} className={`transition-transform duration-200 ${projectsOpen ? '' : '-rotate-90'}`} />
                        </button>
                      )}
                    </div>
                    {to === '/projects' && (
                      <AnimatePresence initial={false}>
                        {projectsOpen && recents.length > 0 && (
                          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.18 }} className="overflow-hidden">
                            <ProjectRecents items={recents} onNavigate={onNavigate} />
                          </motion.div>
                        )}
                      </AnimatePresence>
                    )}
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Sidebar: recently-opened project workspaces under the Projects entry ─────
export type RecentProject = {
  id: number; name: string
  icon_type?: 'emoji' | 'icon' | 'custom'
  icon_value?: string | null
  emoji_icon?: string
  accent_color?: string | null
}
const RECENTS_KEY = 'tobi.projects.recents.v1'

export function pushRecentProject(p: RecentProject) {
  try {
    const list = (JSON.parse(localStorage.getItem(RECENTS_KEY) || '[]') as RecentProject[])
      .filter(x => x.id !== p.id)
    list.unshift(p)
    localStorage.setItem(RECENTS_KEY, JSON.stringify(list.slice(0, 5)))
    window.dispatchEvent(new Event('tobi:recent-projects'))
  } catch { /* ignore */ }
}

function useRecentProjects(): RecentProject[] {
  const [items, setItems] = useState<RecentProject[]>([])
  useEffect(() => {
    const load = async () => {
      let recents: RecentProject[] = []
      try {
        recents = JSON.parse(localStorage.getItem(RECENTS_KEY) || '[]') as RecentProject[]
        // Migrate old entries: {icon: "🚀"} → {emoji_icon: "🚀", icon_type: "emoji"}
        for (const r of recents) {
          if ((r as Record<string, unknown>).icon && !r.emoji_icon && !r.icon_type) {
            r.emoji_icon = (r as Record<string, unknown>).icon as string
            r.icon_type = 'emoji'
          }
        }
      } catch { /* ignore */ }

      // Fetch live project data so icons are always correct (not stale localStorage),
      // and sort the list to MATCH the All Projects page order (the API returns the
      // owner's drag-reordered sort_order) instead of recently-opened order.
      try {
        const resp = await pmListProjects({ size: 'all' })
        const byId = new Map<number, PMProject>()
        const orderOf = new Map<number, number>()
        resp.items.forEach((p, i) => { byId.set(p.id, p); orderOf.set(p.id, i) })
        recents = recents.map(r => {
          const live = byId.get(r.id)
          if (live) return {
            id: live.id, name: live.name,
            icon_type: live.icon_type, icon_value: live.icon_value,
            emoji_icon: live.emoji_icon, accent_color: live.accent_color,
          }
          return null  // project was deleted — filter out below
        }).filter(Boolean) as RecentProject[]
        recents.sort((a, b) => (orderOf.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (orderOf.get(b.id) ?? Number.MAX_SAFE_INTEGER))
      } catch { /* API unavailable — use localStorage as-is */ }

      setItems(recents)
    }
    load()
    const handler = () => { load() }
    window.addEventListener('tobi:recent-projects', handler)
    return () => window.removeEventListener('tobi:recent-projects', handler)
  }, [])
  return items
}

function ProjectRecents({ items, onNavigate }: { items: RecentProject[]; onNavigate?: () => void }) {
  const loc = useLocation()
  if (!items.length) return null
  return (
    <div className="ml-6 space-y-0.5 border-l border-border/50 pl-2">
      {items.map(p => {
        const active = loc.pathname.startsWith(`/projects/${p.id}`)
        return (
          <NavLink key={p.id} to={`/projects/${p.id}/overview`} onClick={onNavigate}
            className={`flex items-center gap-2 rounded-md px-2 py-1 text-[12px] transition-colors ${
              active ? 'bg-accent/10 text-accent' : 'text-muted hover:bg-overlay/5 hover:text-text'}`}>
            <span className="flex h-4 w-4 shrink-0 items-center justify-center">
              <ProjectIcon project={p} size={15} />
            </span>
            <span className="truncate">{p.name}</span>
          </NavLink>
        )
      })}
    </div>
  )
}

// ── Bottom status badge → opens the system menu ──────────────────────────────
function BottomMenu({ collapsed, evo, onNavigate }: {
  collapsed: boolean; evo: EvolutionReport | null; onNavigate?: () => void
}) {
  const [open, setOpen] = useState(false)
  const tier = evo ? evo.tiers[evo.current_tier] : undefined
  const tierName = tier?.name ?? '—'
  const tierPct = tier?.progress_pct ?? 0
  const overall = evo?.jarvis_pct ?? 0
  const emblemTier = evo?.current_tier ?? 0
  const emblemKey = tier?.color_key ?? 'gray'

  return (
    <div className="relative shrink-0 pt-2">
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-[95]" onClick={() => setOpen(false)} />
            <motion.div initial={{ opacity: 0, y: 6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 6, scale: 0.98 }} transition={{ type: 'spring', stiffness: 380, damping: 28 }}
              className={`absolute z-[96] w-52 overflow-hidden rounded-xl border border-border bg-surface/95 shadow-2xl ring-1 ring-accent/10 backdrop-blur-xl ${
                collapsed ? 'bottom-0 left-full ml-2' : 'bottom-full left-0 mb-2'}`}>
              {BOTTOM_MENU.map(item => item.soon ? (
                <div key={item.label} className="flex items-center justify-between px-3 py-2 text-xs text-muted/60">
                  <span className="flex items-center gap-2"><item.icon size={15} /> {item.label}</span>
                  <span className="rounded-full bg-bg px-1.5 py-0.5 text-[9px] font-semibold tracking-wide text-muted">SOON</span>
                </div>
              ) : (
                <NavLink key={item.label} to={item.to!} onClick={() => { setOpen(false); onNavigate?.() }}
                  className={({ isActive }) => `flex items-center gap-2 px-3 py-2 text-xs ${
                    isActive ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-overlay/5 hover:text-text'}`}>
                  <item.icon size={15} /> {item.label}
                </NavLink>
              ))}
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <button onClick={() => setOpen(o => !o)} title={`${tierName} · Tier ${tierPct}% · Overall ${overall}%`}
        className={`flex w-full items-center rounded-lg border bg-bg/40 transition-colors hover:border-accent/40 ${
          open ? 'border-accent/40' : 'border-border'} ${collapsed ? 'justify-center p-2' : 'gap-2 px-2.5 py-2'}`}>
        {collapsed ? (
          <TierEmblem tier={emblemTier} colorKey={emblemKey} size={28} state="current" />
        ) : (
          <>
            <TierEmblem tier={emblemTier} colorKey={emblemKey} size={34} state="current" />
            <div className="min-w-0 flex-1 text-left">
              <div className="flex items-center gap-1.5">
                <span className="truncate text-[11px] font-bold tracking-wide text-heading">{tierName}</span>
                <span className="shrink-0 text-[9px] text-muted">{APP_VERSION}</span>
              </div>
              <div className="mt-0.5 text-[9px] text-muted">Tier {tierPct}% · Overall {overall}%</div>
              <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-overlay/10">
                <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${overall}%` }} />
              </div>
            </div>
            <ChevronUp size={14} className={`shrink-0 text-muted transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
          </>
        )}
      </button>
    </div>
  )
}

function SidebarContent({ onNavigate, collapsed = false, onToggleCollapse, openSections, toggleSection, evo, idScope = 'sidebar' }: {
  onNavigate?: () => void
  collapsed?: boolean
  onToggleCollapse?: () => void
  openSections: Record<string, boolean>
  toggleSection: (group: string) => void
  evo: EvolutionReport | null
  idScope?: string
}) {
  return (
    <div className="flex h-full flex-col">
      {/* Header — logo + collapse/expand toggle on top */}
      <div className={`flex shrink-0 items-center py-1 ${collapsed ? 'flex-col gap-2' : 'justify-between'}`}>
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'gap-2 px-1'}`}>
          <Zap size={18} className="shrink-0 text-accent" />
          {!collapsed && (
            <div>
              <div className="text-sm font-bold tracking-widest text-heading">TOBI</div>
              <div className="text-[10px] tracking-wider text-muted">MISSION CONTROL</div>
            </div>
          )}
        </div>
        {onToggleCollapse && (
          <button onClick={onToggleCollapse} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="rounded-md p-1.5 text-muted transition-colors hover:bg-overlay/5 hover:text-text">
            {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
          </button>
        )}
      </div>

      {/* Sections (scroll) — LayoutGroup namespaces the sliding nav-active pill
          per instance so the desktop + mobile sidebars never share a layoutId. */}
      <LayoutGroup id={idScope}>
        <div className="scroll-subtle mt-3 min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden">
          {NAV.map(g => (
            <NavSection key={g.group} group={g.group} links={g.links} collapsed={collapsed}
              onNavigate={onNavigate} open={openSections[g.group] ?? true} onToggle={() => toggleSection(g.group)} />
          ))}
        </div>
      </LayoutGroup>

      {/* Bottom status badge + system menu */}
      <BottomMenu collapsed={collapsed} evo={evo} onNavigate={onNavigate} />
    </div>
  )
}

function ThemeQuickSwitch() {
  const { theme, set } = useTheme()
  const [open, setOpen] = useState(false)
  // Guarded lookup: stored values are migrated at load, but never crash the header.
  const current = THEME_DEFS[theme]
  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)} className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1.5 text-xs text-muted hover:text-text" title="Theme">
        <Palette size={14} /> <span className="hidden sm:inline">{current?.label ?? 'Theme'}</span>
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-[90]" onClick={() => setOpen(false)} />
            <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
              className="tv2-popover scroll-subtle absolute right-0 z-[91] mt-2 max-h-[70vh] w-52 overflow-y-auto border border-border bg-surface/95 ring-1 ring-accent/10 backdrop-blur-xl">
              {THEME_GROUPS.map((g, gi) => (
                <div key={g.id} className={gi > 0 ? 'border-t border-border/60' : ''}>
                  <div className="px-3 pb-0.5 pt-2 text-[9px] font-semibold uppercase tracking-wider text-muted/70">{g.label}</div>
                  {g.themes.map(t => {
                    const def = THEME_DEFS[t]
                    const Icon = def.icon
                    return (
                      <button key={t} onClick={() => { set({ theme: t }); setOpen(false) }}
                        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${t === theme ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-overlay/5 hover:text-text'}`}>
                        <Icon size={13} className={t === theme ? 'text-accent' : 'text-muted'} />
                        {def.label}
                      </button>
                    )
                  })}
                </div>
              ))}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

function BellInbox() {
  const { notes, clear } = useToast()
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)} className="relative rounded-md p-1.5 text-muted hover:text-text" title="Notifications">
        <Bell size={16} />
        {notes.length > 0 && <span className="absolute -right-0.5 -top-0.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-accent px-1 text-[9px] font-bold text-bg">{notes.length}</span>}
      </button>
      {/* Rendered in a portal at <body> so the panel escapes the header's stacking
          context entirely — it can never be overlapped by page content again. */}
      {createPortal(
        <AnimatePresence>
          {open && (
            <>
              <div className="fixed inset-0 z-[180]" onClick={() => setOpen(false)} />
              <motion.div initial={{ opacity: 0, y: -8, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, scale: 0.97 }}
                transition={{ type: 'spring', stiffness: 380, damping: 28 }}
                className="fixed right-3 top-[52px] z-[181] flex max-h-[75vh] w-80 flex-col overflow-hidden rounded-xl border border-accent/25 bg-surface shadow-2xl shadow-accent/20 ring-1 ring-accent/10">
                <div className="flex shrink-0 items-center justify-between border-b border-border bg-surface px-3 py-2">
                  <span className="text-xs font-semibold text-heading">Notifications</span>
                  {notes.length > 0 && <button onClick={clear} className="text-[11px] text-muted hover:text-text">Clear</button>}
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto bg-surface">
                  {notes.length === 0 ? <div className="px-3 py-6 text-center text-xs text-muted">Nothing yet</div> :
                    notes.map(n => (
                      <div key={n.id} className="border-b border-border/50 px-3 py-2">
                        <div className={`text-xs font-medium ${n.kind === 'error' ? 'text-danger' : n.kind === 'success' ? 'text-success' : 'text-text'}`}>{n.title}</div>
                        {n.detail && <div className="mt-0.5 text-[11px] text-muted">{n.detail}</div>}
                        <div className="mt-0.5 text-[10px] text-muted">{new Date(n.ts).toLocaleTimeString('en-GB')}</div>
                      </div>
                    ))}
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </div>
  )
}

function Stat({ value, label, tone }: { value: string; label: string; tone: string }) {
  return (
    <span className="flex items-center gap-1 rounded-md border border-border/60 bg-bg/40 px-2 py-1 text-[11px]">
      <span className={`font-semibold tabular-nums ${tone}`}>{value}</span>
      <span className="text-muted">{label}</span>
    </span>
  )
}

function NewTabButton({ openTab, openRoutes }: { openTab: (r: string) => void; openRoutes: string[] }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { if (query) setQuery(''); else setOpen(false) } }
    document.addEventListener('mousedown', onDoc); document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open, query])

  // Focus search on open, reset on close
  useEffect(() => { if (open) setTimeout(() => searchRef.current?.focus(), 50); else setQuery('') }, [open])

  const filtered = query.trim()
    ? WORKSPACE_ROUTES.filter(r => r.label.toLowerCase().includes(query.toLowerCase()))
    : WORKSPACE_ROUTES

  const pick = (route: string) => { openTab(route); setOpen(false) }

  return (
    <motion.div className="relative mb-0.5 ml-0.5 shrink-0" ref={ref}
      initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.7 }} transition={SPRING.pop}>
      <motion.button
        onClick={() => setOpen(o => !o)}
        whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.88 }}
        transition={SPRING.pop}
        title="Open new tab" aria-label="Open new tab" aria-haspopup="menu" aria-expanded={open}
        className={`flex h-7 w-7 items-center justify-center rounded-full text-muted transition-colors duration-200 hover:bg-overlay/[0.08] hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${open ? 'bg-overlay/[0.08] text-text' : ''}`}>
        <Plus size={15} />
      </motion.button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: DUR.sm, ease: EASE.out }}
            className="absolute left-0 top-full z-50 mt-2 w-64 overflow-hidden rounded-2xl border border-border bg-surface/95 p-1.5 shadow-[0_10px_44px_-10px_rgba(0,0,0,0.55)] ring-1 ring-overlay/[0.04] backdrop-blur-xl">
            {/* Search input */}
            <div className="mb-1 flex items-center gap-2 rounded-lg border border-border bg-bg/60 px-2.5 py-1.5">
              <Search size={13} className="shrink-0 text-muted/70" />
              <input ref={searchRef} value={query} onChange={e => setQuery(e.target.value)}
                placeholder="Search pages…"
                className="w-full bg-transparent text-xs text-text placeholder:text-muted/60 focus:outline-none" />
              {query && <button onClick={() => setQuery('')} className="shrink-0 text-muted hover:text-text"><X size={12} /></button>}
            </div>
            <div className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">{query ? `${filtered.length} match${filtered.length === 1 ? '' : 'es'}` : 'Open in new tab'}</div>
            <div className="scroll-subtle max-h-[min(60vh,360px)] overflow-y-auto">
              {filtered.length === 0 ? (
                <div className="px-2.5 py-4 text-center text-xs text-muted/60">No pages match "{query}"</div>
              ) : (
                filtered.map(r => {
                  const isOpen = openRoutes.includes(r.route)
                  const Icon = r.Icon
                  return (
                    <button key={r.route} onClick={() => pick(r.route)}
                      className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-xs text-text transition-colors duration-150 hover:bg-bg/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
                      <Icon size={15} className={isOpen ? 'shrink-0 text-accent' : 'shrink-0 text-muted'} />
                      <span className="flex-1 truncate font-medium">{r.label}</span>
                      {isOpen && <span className="rounded-full bg-accent/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-accent">Open</span>}
                    </button>
                  )
                })
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function WorkspaceTabsBar() {
  const { tabs, activeId, tabLabels, tabIcons, focusTab, closeTab, reorderTabs, openTab } = useWorkspaceTabs()
  const [dragId, setDragId] = useState<string | null>(null)

  return (
    <nav aria-label="Workspace tabs" className="min-w-0 flex-1">
      {/* The tablist never scrolls/clips, so the + button's dropdown can escape
          into the content area. Tabs flex-grow (few tabs = wide / full titles;
          many or long titles = shrink to a floor + truncate, Chrome-style). */}
      <div role="tablist" aria-label="Open pages" className="flex min-w-0 items-end gap-1 px-2">
        <LayoutGroup id="wsTabs">
          <AnimatePresence initial={false}>
            {tabs.map((tab, i) => {
              const base = getWorkspaceRouteMeta(tab.route)
              const meta = { ...base, label: tabLabels[tab.id] ?? base.label }
              const iconData = tabIcons[tab.id]
              const Icon = meta.Icon
              const active = tab.id === activeId
              const showDivider = !active && i < tabs.length - 1 && tabs[i + 1].id !== activeId
              return (
                <motion.div
                  key={tab.id} layout role="tab" aria-selected={active}
                  initial={{ opacity: 0, scale: 0.92, y: 4 }} animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.92, y: 4 }}
                  transition={SPRING.snappy}
                  draggable
                  onDragStart={() => setDragId(tab.id)}
                  onDragEnd={() => setDragId(null)}
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => { e.preventDefault(); if (dragId) reorderTabs(dragId, tab.id); setDragId(null) }}
                  className={`group relative -mb-px flex h-9 min-w-[120px] max-w-[240px] flex-1 items-center gap-1.5 rounded-t-[8px] pl-3 pr-1.5 transition-colors duration-200 active:translate-y-px ${
                    active
                      ? 'chrome-tab bg-bg text-text shadow-[0_1px_0_rgb(255_255_255/0.06)_inset]'
                      : 'text-muted hover:bg-black/[0.06] hover:text-text'
                  } ${dragId === tab.id ? 'opacity-60' : ''}`}>
                  <button onClick={() => focusTab(tab.id)} title={meta.label}
                    className="relative z-10 flex min-w-0 flex-1 items-center gap-1.5 py-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 rounded-t-[8px]">
                    {iconData
                      ? <span className={`flex shrink-0 items-center justify-center transition-opacity duration-200 ${active ? '' : 'opacity-80 group-hover:opacity-100'}`}><ProjectIcon project={iconData} size={14} /></span>
                      : <Icon size={13} className={`shrink-0 transition-colors duration-200 ${active ? 'text-accent' : 'text-muted opacity-80 group-hover:opacity-100'}`} />}
                    <span className={`truncate text-xs font-medium transition-colors duration-200 ${active ? 'text-text' : 'text-muted group-hover:text-text'}`}>
                      {meta.label}
                    </span>
                  </button>
                  {tabs.length > 1 && (
                    <button onClick={() => closeTab(tab.id)} title={`Close ${meta.label}`} aria-label={`Close ${meta.label}`}
                      className={`relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-muted transition-all duration-200 hover:bg-overlay/15 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
                        active ? 'opacity-70' : 'opacity-0 group-hover:opacity-100'
                      }`}>
                      <X size={11} />
                    </button>
                  )}
                  {/* Subtle divider between adjacent inactive tabs — fades on hover,
                      and never shows next to the active tab or its curved feet. */}
                  <span aria-hidden
                    className={`pointer-events-none absolute right-[-2px] top-1/2 h-5 w-px -translate-y-1/2 bg-border/60 transition-opacity duration-200 group-hover:opacity-0 ${showDivider ? 'opacity-100' : 'opacity-0'}`} />
                </motion.div>
              )
            })}
          </AnimatePresence>
          <AnimatePresence>
            {tabs.length < MAX_WORKSPACE_TABS && (
              <NewTabButton key="newtab" openTab={openTab} openRoutes={tabs.map(t => t.route)} />
            )}
          </AnimatePresence>
        </LayoutGroup>
      </div>
    </nav>
  )
}

function StatusIndicator({ stats }: { stats: OfficeStats | null }) {
  const [open, setOpen] = useState(false)
  const s = stats?.stats

  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)} title="Mission status"
        className={`flex h-8 items-center gap-1.5 rounded-lg border px-2 text-xs transition-colors ${open ? 'border-accent/45 bg-accent/10 text-accent' : 'border-border bg-bg/35 text-muted hover:border-accent/35 hover:text-text'}`}>
        <Circle size={8} className="fill-success text-success" />
        <span className="hidden font-medium sm:inline">Live</span>
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-[85]" onClick={() => setOpen(false)} />
            <motion.div initial={{ opacity: 0, y: -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.98 }}
              transition={{ duration: 0.14 }}
              className="absolute right-0 z-[86] mt-2 w-72 rounded-xl border border-border bg-surface/95 p-3 shadow-2xl ring-1 ring-accent/10 backdrop-blur-xl">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold text-heading"><Activity size={14} className="text-accent" /> TOBI online</div>
                  <div className="mt-0.5 text-[11px] text-muted">Mission telemetry is still available here.</div>
                </div>
                <span className="rounded-full border border-success/35 bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success">Running</span>
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                <Stat value={String(s?.missions_running ?? 0)} label="running" tone="text-accent" />
                <Stat value={(s?.tokens_total ?? 0).toLocaleString()} label="tokens" tone="text-warning" />
                <Stat value={String(s?.agents_active ?? 0)} label="agents" tone="text-success" />
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

function TopBar({ onMenu, stats, onHide }: { onMenu: () => void; stats: OfficeStats | null; onHide: () => void }) {
  return (
    <header className="relative z-40 flex h-11 shrink-0 items-stretch justify-between bg-strip">
      <div className="flex min-w-0 flex-1 items-end">
        <button onClick={onMenu} aria-label="Open menu"
          className="self-center shrink-0 rounded-lg p-1.5 text-muted transition-colors hover:bg-overlay/[0.06] hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 md:hidden">
          <Menu size={18} />
        </button>
        <WorkspaceTabsBar />
      </div>
      <div className="flex shrink-0 items-center gap-1.5 pl-2 pr-2.5">
        <StatusIndicator stats={stats} />
        <ClockCalendar />
        <ThemeQuickSwitch />
        <BellInbox />
        <button onClick={onHide} title="Hide header" aria-label="Hide header"
          className="rounded-lg p-1.5 text-muted transition-colors hover:bg-overlay/[0.06] hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
          <ChevronUp size={15} />
        </button>
      </div>
    </header>
  )
}

const SB_MIN = 176; const SB_MAX = 320; const SB_DEFAULT = 224

export default function AppShell({ children }: { children: ReactNode }) {
  const [drawer, setDrawer] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('tobi.sidebar') === '1' } catch { return false }
  })
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem('tobi.sidebar.sections') || '{}') } catch { return {} }
  })
  const [stats, setStats] = useState<OfficeStats | null>(null)
  const [evo, setEvo] = useState<EvolutionReport | null>(null)
  // header collapse — hide fully, floating chip restores (persisted)
  const [headerHidden, setHeaderHidden] = useState(() => {
    try { return localStorage.getItem('tobi.header.hidden') === '1' } catch { return false }
  })
  useEffect(() => { try { localStorage.setItem('tobi.header.hidden', headerHidden ? '1' : '0') } catch { /* ignore */ } }, [headerHidden])
  // sidebar width — drag the right edge to resize (persisted)
  const [sbWidth, setSbWidth] = useState(() => {
    try { const v = parseInt(localStorage.getItem('tobi.sidebar.w') || '', 10); return Number.isFinite(v) ? Math.min(SB_MAX, Math.max(SB_MIN, v)) : SB_DEFAULT } catch { return SB_DEFAULT }
  })
  const [dragging, setDragging] = useState(false)
  useEffect(() => {
    if (!dragging) return
    const onMove = (e: MouseEvent) => setSbWidth(Math.min(SB_MAX, Math.max(SB_MIN, e.clientX)))
    const onUp = () => setDragging(false)
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.body.style.userSelect = 'none'; document.body.style.cursor = 'col-resize'
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = ''; document.body.style.cursor = ''
    }
  }, [dragging])
  useEffect(() => { if (!dragging) try { localStorage.setItem('tobi.sidebar.w', String(sbWidth)) } catch { /* ignore */ } }, [dragging, sbWidth])
  const loc = useLocation()
  useEffect(() => { setDrawer(false) }, [loc.pathname])
  useEffect(() => { try { localStorage.setItem('tobi.sidebar', collapsed ? '1' : '0') } catch { /* ignore */ } }, [collapsed])

  const toggleSection = (group: string) => setOpenSections(prev => {
    const next = { ...prev, [group]: !(prev[group] ?? true) }
    try { localStorage.setItem('tobi.sidebar.sections', JSON.stringify(next)) } catch { /* ignore */ }
    return next
  })

  useEffect(() => {
    const load = () => getOfficeStats().then(setStats).catch(() => {})
    load(); const id = setInterval(load, 15000); return () => clearInterval(id)
  }, [])
  useEffect(() => {
    const load = () => getEvolution().then(setEvo).catch(() => {})
    load(); const id = setInterval(load, 60000); return () => clearInterval(id)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-bg text-text">
      {/* desktop sidebar — drag the right edge to resize */}
      <aside style={{ width: collapsed ? 64 : sbWidth }}
        className={`relative hidden shrink-0 flex-col border-r border-border bg-surface px-3 py-4 md:flex ${dragging ? '' : 'transition-[width] duration-200'}`}>
        <SidebarContent collapsed={collapsed} onToggleCollapse={() => setCollapsed(c => !c)}
          openSections={openSections} toggleSection={toggleSection} evo={evo} idScope="desktop" />
        {!collapsed && (
          <div onMouseDown={e => { e.preventDefault(); setDragging(true) }} title="Drag to resize"
            className={`absolute inset-y-0 -right-0.5 z-10 w-1.5 cursor-col-resize transition-colors ${dragging ? 'bg-accent/50' : 'hover:bg-accent/30'}`} />
        )}
      </aside>

      {/* mobile drawer */}
      <AnimatePresence>
        {drawer && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[120] bg-black/60 md:hidden" onClick={() => setDrawer(false)} />
            <motion.aside initial={{ x: -260 }} animate={{ x: 0 }} exit={{ x: -260 }} transition={{ type: 'spring', stiffness: 360, damping: 32 }}
              className="fixed left-0 top-0 z-[121] flex h-full w-60 flex-col border-r border-border bg-surface px-3 py-4 md:hidden">
              <button onClick={() => setDrawer(false)} className="absolute right-2 top-2 z-10 text-muted hover:text-text"><X size={16} /></button>
              <SidebarContent onNavigate={() => setDrawer(false)} openSections={openSections} toggleSection={toggleSection} evo={evo} idScope="mobile" />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <div className="relative flex min-w-0 flex-1 flex-col">
        {!headerHidden && <TopBar onMenu={() => setDrawer(true)} stats={stats} onHide={() => setHeaderHidden(true)} />}
        {/* floating restore chip — the only trace of the hidden header */}
        {headerHidden && (
          <button onClick={() => setHeaderHidden(false)} title="Show header"
            className="absolute right-3 top-2 z-50 flex h-6 w-8 items-center justify-center rounded-full border border-border bg-surface/80 text-muted shadow-lg backdrop-blur transition-colors hover:border-accent/50 hover:text-accent">
            <ChevronDown size={13} />
          </button>
        )}
        <main className="relative flex-1 overflow-hidden">
          {/* HUD panel-boot per route (slide-up + fade + one-shot scanline sweep).
              Keyed by path with no AnimatePresence exit gating — the incoming page
              always mounts immediately, so navigation can never leave a blank view. */}
          {children}
        </main>
      </div>

      {/* mobile bottom tabs */}
      <nav className="fixed bottom-0 left-0 right-0 z-[110] flex h-14 items-center justify-around border-t border-border bg-surface/95 backdrop-blur md:hidden">
        {TAB_LINKS.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} className={({ isActive }) => `flex flex-col items-center gap-0.5 text-[10px] ${isActive ? 'text-accent' : 'text-muted'}`}>
            <Icon size={18} /> {label}
          </NavLink>
        ))}
      </nav>

      <CommandPalette />
    </div>
  )
}
