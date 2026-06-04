import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard, Network, Zap, Building2, Kanban, HeartPulse, Terminal, Settings,
  Menu, X, Bell, Command, Palette, Circle, FolderKanban, TrendingUp,
} from 'lucide-react'
import { useTheme, THEMES, THEME_META } from '../context/ThemeProvider'
import { useToast } from '../context/ToastProvider'
import { getOfficeStats, type OfficeStats } from '../api'
import CommandPalette from './CommandPalette'

const NAV = [
  { group: 'MAIN', links: [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/architecture', icon: Network, label: 'Architecture' },
    { to: '/ability', icon: Zap, label: 'Ability' },
    { to: '/evolution', icon: TrendingUp, label: 'Evolution' },
  ] },
  { group: 'OPS', links: [
    { to: '/office', icon: Building2, label: 'Office' },
    { to: '/projects', icon: FolderKanban, label: 'Projects' },
    { to: '/task', icon: Kanban, label: 'Task' },
    { to: '/control', icon: Terminal, label: 'Control Room' },
    { to: '/health', icon: HeartPulse, label: 'Health' },
  ] },
]
const ALL_LINKS = NAV.flatMap(g => g.links)
// Mobile tabs: Dashboard, Evolution, Office, Task, Health
const TAB_LINKS = [ALL_LINKS[0], ALL_LINKS[3], ALL_LINKS[4], ALL_LINKS[6], ALL_LINKS[8]]

function navClass(isActive: boolean) {
  return `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
    isActive ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-white/5 hover:text-text'}`
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      <div className="flex items-center gap-2 px-2 py-1">
        <Zap size={18} className="text-accent" />
        <div>
          <div className="text-sm font-bold tracking-widest text-heading">TOBI</div>
          <div className="text-[10px] tracking-wider text-muted">MISSION CONTROL</div>
        </div>
      </div>
      <div className="mt-4 flex-1 space-y-4">
        {NAV.map(g => (
          <div key={g.group}>
            <div className="px-3 pb-1 text-[10px] font-semibold tracking-widest text-muted">{g.group}</div>
            <div className="space-y-0.5">
              {g.links.map(({ to, icon: Icon, label }) => (
                <NavLink key={to} to={to} onClick={onNavigate} className={({ isActive }) => navClass(isActive)}>
                  <Icon size={16} /> <span>{label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
        <div>
          <div className="px-3 pb-1 text-[10px] font-semibold tracking-widest text-muted">SYSTEM</div>
          <NavLink to="/settings" onClick={onNavigate} className={({ isActive }) => navClass(isActive)}>
            <Settings size={16} /> <span>Settings</span>
          </NavLink>
        </div>
      </div>
    </>
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
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
              className="absolute right-0 z-50 mt-1 w-44 overflow-hidden rounded-lg border border-border bg-surface shadow-xl">
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
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
              className="absolute right-0 z-50 mt-1 max-h-96 w-80 overflow-y-auto rounded-lg border border-border bg-surface shadow-xl">
              <div className="flex items-center justify-between border-b border-border px-3 py-2">
                <span className="text-xs font-semibold text-heading">Notifications</span>
                {notes.length > 0 && <button onClick={clear} className="text-[11px] text-muted hover:text-text">Clear</button>}
              </div>
              {notes.length === 0 ? <div className="px-3 py-6 text-center text-xs text-muted">Nothing yet</div> :
                notes.map(n => (
                  <div key={n.id} className="border-b border-border/50 px-3 py-2">
                    <div className={`text-xs font-medium ${n.kind === 'error' ? 'text-danger' : n.kind === 'success' ? 'text-success' : 'text-text'}`}>{n.title}</div>
                    {n.detail && <div className="mt-0.5 text-[11px] text-muted">{n.detail}</div>}
                    <div className="mt-0.5 text-[10px] text-muted">{new Date(n.ts).toLocaleTimeString('en-GB')}</div>
                  </div>
                ))}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

function TopBar({ onMenu, stats }: { onMenu: () => void; stats: OfficeStats | null }) {
  const s = stats?.stats
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-surface/60 px-3 backdrop-blur">
      <div className="flex items-center gap-3">
        <button onClick={onMenu} className="rounded-md p-1.5 text-muted hover:text-text md:hidden"><Menu size={18} /></button>
        <div className="flex items-center gap-2 text-xs">
          <Circle size={8} className="fill-success text-success" />
          <span className="font-semibold text-heading">Tobi</span>
          <span className="hidden text-muted sm:inline">online</span>
        </div>
        <div className="hidden items-center gap-3 text-[11px] text-muted sm:flex">
          <span className="text-accent">{s?.missions_running ?? 0}</span> running
          <span className="text-warning">{(s?.tokens_total ?? 0).toLocaleString()}</span> tok
          <span className="text-success">{s?.agents_active ?? 0}</span> agents
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
          className="hidden items-center gap-1.5 rounded-md border border-border px-2 py-1.5 text-xs text-muted hover:text-text sm:flex">
          <Command size={13} /> <span>K</span>
        </button>
        <ThemeQuickSwitch />
        <BellInbox />
      </div>
    </header>
  )
}

export default function AppShell({ children }: { children: ReactNode }) {
  const [drawer, setDrawer] = useState(false)
  const [stats, setStats] = useState<OfficeStats | null>(null)
  const loc = useLocation()
  useEffect(() => { setDrawer(false) }, [loc.pathname])
  useEffect(() => {
    const load = () => getOfficeStats().then(setStats).catch(() => {})
    load(); const id = setInterval(load, 15000); return () => clearInterval(id)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-bg text-text">
      {/* desktop sidebar */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-surface px-3 py-4 md:flex">
        <SidebarContent />
        <div className="pt-3 text-[10px] text-muted">v3.0 · Mission Control</div>
      </aside>

      {/* mobile drawer */}
      <AnimatePresence>
        {drawer && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[120] bg-black/60 md:hidden" onClick={() => setDrawer(false)} />
            <motion.aside initial={{ x: -260 }} animate={{ x: 0 }} exit={{ x: -260 }} transition={{ type: 'spring', stiffness: 360, damping: 32 }}
              className="fixed left-0 top-0 z-[121] flex h-full w-60 flex-col border-r border-border bg-surface px-3 py-4 md:hidden">
              <button onClick={() => setDrawer(false)} className="absolute right-2 top-2 text-muted hover:text-text"><X size={16} /></button>
              <SidebarContent onNavigate={() => setDrawer(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenu={() => setDrawer(true)} stats={stats} />
        <main className="relative flex-1 overflow-y-auto pb-16 md:pb-0">
          <AnimatePresence mode="wait">
            <motion.div key={loc.pathname} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.16, ease: 'easeOut' }} className="h-full">
              {children}
            </motion.div>
          </AnimatePresence>
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
