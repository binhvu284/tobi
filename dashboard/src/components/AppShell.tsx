import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence, LayoutGroup } from 'framer-motion'
import {
  LayoutDashboard, Network, Zap, Building2, Kanban, HeartPulse, Settings,
  Menu, X, Bell, Command, Palette, Circle, FolderKanban, TrendingUp,
  ChevronsLeft, ChevronsRight, ChevronUp, ChevronDown, Brain, MessagesSquare,
  Share2, KeyRound, Inbox, FileText, Code2, Workflow, History, Cpu,
} from 'lucide-react'
import { useTheme, THEMES, THEME_META } from '../context/ThemeProvider'
import { useToast } from '../context/ToastProvider'
import { getOfficeStats, getEvolution, type OfficeStats, type EvolutionReport } from '../api'
import CommandPalette from './CommandPalette'
import ErrorBoundary from './ErrorBoundary'
import TierEmblem from './TierEmblem'
import PageBoot from './motion/PageBoot'
import ClockCalendar from './ClockCalendar'
import { SPRING } from '../lib/motion'

const APP_VERSION = 'v3.0'

const NAV = [
  { group: 'Main', links: [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/inbox', icon: Inbox, label: 'Inbox' },
    { to: '/chat', icon: MessagesSquare, label: 'Chat' },
    { to: '/actions', icon: History, label: 'Actions' },
  ] },
  { group: 'Persona', links: [
    { to: '/brain', icon: Brain, label: 'Brain' },
    { to: '/graph', icon: Share2, label: 'Graph' },
    { to: '/architecture', icon: Network, label: 'Architecture' },
    { to: '/ability', icon: Zap, label: 'Ability' },
    { to: '/evolution', icon: TrendingUp, label: 'Evolution' },
    { to: '/health', icon: HeartPulse, label: 'Health' },
  ] },
  { group: 'Operation', links: [
    { to: '/office', icon: Building2, label: 'Office' },
    { to: '/projects', icon: FolderKanban, label: 'Projects' },
    { to: '/task', icon: Kanban, label: 'Tasks' },
  ] },
]
const ALL_LINKS = NAV.flatMap(g => g.links)

// Bottom badge menu — Setting + Integrations route; Document/Developer are coming soon.
const BOTTOM_MENU: { to?: string; icon: typeof Settings; label: string; soon?: boolean }[] = [
  { to: '/settings', icon: Settings, label: 'Setting' },
  { to: '/models', icon: Cpu, label: 'Models' },
  { icon: FileText, label: 'Document', soon: true },
  { to: '/integrations', icon: KeyRound, label: 'Integrations' },
  { to: '/mcp', icon: Workflow, label: 'MCP' },
  { icon: Code2, label: 'Developer', soon: true },
]

// Mobile bottom tabs (by path so it survives nav reordering)
const TAB_PATHS = ['/dashboard', '/inbox', '/chat', '/office', '/task']
const TAB_LINKS = TAB_PATHS.map(p => ALL_LINKS.find(l => l.to === p)!).filter(Boolean)

function navClass(isActive: boolean, collapsed = false) {
  return `flex items-center rounded-md py-2 text-sm transition-colors ${collapsed ? 'justify-center px-0' : 'gap-3 px-3'} ${
    isActive ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-white/5 hover:text-text'}`
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
              {links.map(({ to, icon: Icon, label }) => (
                <NavLink key={to} to={to} onClick={onNavigate}
                  className={({ isActive }) => `relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                    isActive ? 'text-accent' : 'text-muted hover:bg-white/5 hover:text-text'}`}>
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
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
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
                    isActive ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-white/5 hover:text-text'}`}>
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
              <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-white/10">
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
            className="rounded-md p-1.5 text-muted transition-colors hover:bg-white/5 hover:text-text">
            {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
          </button>
        )}
      </div>

      {/* Sections (scroll) — LayoutGroup namespaces the sliding nav-active pill
          per instance so the desktop + mobile sidebars never share a layoutId. */}
      <LayoutGroup id={idScope}>
        <div className="mt-3 min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden">
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
  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)} className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1.5 text-xs text-muted hover:text-text" title="Theme">
        <Palette size={14} /> <span className="hidden sm:inline">{THEME_META[theme].label}</span>
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-[90]" onClick={() => setOpen(false)} />
            <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
              className="absolute right-0 z-[91] mt-2 w-44 overflow-hidden rounded-xl border border-border bg-surface/95 shadow-2xl ring-1 ring-accent/10 backdrop-blur-xl">
              {THEMES.map(t => (
                <button key={t} onClick={() => { set({ theme: t }); setOpen(false) }}
                  className={`block w-full px-3 py-2 text-left text-xs ${t === theme ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-white/5 hover:text-text'}`}>
                  {THEME_META[t].label}
                </button>
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

function TopBar({ onMenu, stats }: { onMenu: () => void; stats: OfficeStats | null }) {
  const s = stats?.stats
  return (
    <header className="relative z-40 flex h-12 shrink-0 items-center justify-between border-b border-border bg-surface/60 px-3 backdrop-blur">
      <div className="flex items-center gap-3">
        <button onClick={onMenu} className="rounded-md p-1.5 text-muted hover:text-text md:hidden"><Menu size={18} /></button>
        <div className="flex items-center gap-2 text-xs">
          <Circle size={8} className="fill-success text-success" />
          <span className="font-semibold text-heading">Tobi</span>
          <span className="hidden text-muted sm:inline">online</span>
        </div>
        <div className="hidden h-4 w-px bg-border sm:block" />
        <div className="hidden items-center gap-1.5 sm:flex">
          <Stat value={String(s?.missions_running ?? 0)} label="running" tone="text-accent" />
          <Stat value={(s?.tokens_total ?? 0).toLocaleString()} label="tok" tone="text-warning" />
          <Stat value={String(s?.agents_active ?? 0)} label="agents" tone="text-success" />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
          className="hidden items-center gap-1.5 rounded-md border border-border px-2 py-1.5 text-xs text-muted hover:text-text sm:flex">
          <Command size={13} /> <span>K</span>
        </button>
        <ClockCalendar />
        <div className="hidden h-4 w-px bg-border sm:block" />
        <ThemeQuickSwitch />
        <BellInbox />
      </div>
    </header>
  )
}

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
      {/* desktop sidebar */}
      <aside className={`hidden shrink-0 flex-col border-r border-border bg-surface px-3 py-4 transition-[width] duration-200 md:flex ${collapsed ? 'w-16' : 'w-56'}`}>
        <SidebarContent collapsed={collapsed} onToggleCollapse={() => setCollapsed(c => !c)}
          openSections={openSections} toggleSection={toggleSection} evo={evo} idScope="desktop" />
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

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenu={() => setDrawer(true)} stats={stats} />
        <main className="relative flex-1 overflow-y-auto pb-16 md:pb-0">
          {/* HUD panel-boot per route (slide-up + fade + one-shot scanline sweep).
              Keyed by path with no AnimatePresence exit gating — the incoming page
              always mounts immediately, so navigation can never leave a blank view. */}
          <PageBoot key={loc.pathname}>
            <ErrorBoundary key={loc.pathname}>
              {children}
            </ErrorBoundary>
          </PageBoot>
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
