import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Inbox, MessagesSquare, History, Brain, Share2, Network, Zap,
  TrendingUp, HeartPulse, Building2, FolderKanban, Kanban, Settings, Cpu,
  HardDrive, KeyRound, Workflow, SlidersHorizontal, Newspaper, type LucideIcon,
} from 'lucide-react'
import { useToast } from './ToastProvider'

export const MAX_WORKSPACE_TABS = 3

export type WorkspaceTab = {
  id: string
  route: string
  stateKey: string
  openedAt: number
}

export type WorkspaceRouteMeta = {
  route: string
  label: string
  Icon: LucideIcon
}

export const WORKSPACE_ROUTES: WorkspaceRouteMeta[] = [
  { route: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { route: '/inbox', label: 'Inbox', Icon: Inbox },
  { route: '/chat', label: 'Chat', Icon: MessagesSquare },
  { route: '/actions', label: 'Actions', Icon: History },
  { route: '/brain', label: 'Brain', Icon: Brain },
  { route: '/graph', label: 'Graph', Icon: Share2 },
  { route: '/architecture', label: 'Architecture', Icon: Network },
  { route: '/ability', label: 'Ability', Icon: Zap },
  { route: '/evolution', label: 'Evolution', Icon: TrendingUp },
  { route: '/health', label: 'Health', Icon: HeartPulse },
  { route: '/office', label: 'Office', Icon: Building2 },
  { route: '/projects', label: 'Projects', Icon: FolderKanban },
  { route: '/task', label: 'Tasks', Icon: Kanban },
  { route: '/news', label: 'News', Icon: Newspaper },
  { route: '/settings', label: 'Settings', Icon: Settings },
  { route: '/models', label: 'Models', Icon: Cpu },
  { route: '/storage', label: 'Storage', Icon: HardDrive },
  { route: '/integrations', label: 'Integrations', Icon: KeyRound },
  { route: '/mcp', label: 'MCP', Icon: Workflow },
  { route: '/control', label: 'Control', Icon: SlidersHorizontal },
]

const ROUTE_META = new Map(WORKSPACE_ROUTES.map(r => [r.route, r]))
const TABS_KEY = 'tobi.workspace.tabs.v2'
const ACTIVE_KEY = 'tobi.workspace.activeTab.v2'

type WorkspaceTabsContextValue = {
  tabs: WorkspaceTab[]
  activeId: string
  focusTab: (id: string) => void
  closeTab: (id: string) => void
  reorderTabs: (fromId: string, toId: string) => void
}

const WorkspaceTabsContext = createContext<WorkspaceTabsContextValue | null>(null)

export function normalizeWorkspaceRoute(path: string) {
  if (!path || path === '/') return '/dashboard'
  const clean = path.split('?')[0].split('#')[0]
  return clean.endsWith('/') && clean.length > 1 ? clean.slice(0, -1) : clean
}

export function getWorkspaceRouteMeta(route: string) {
  return ROUTE_META.get(normalizeWorkspaceRoute(route)) ?? WORKSPACE_ROUTES[0]
}

function makeTab(route: string): WorkspaceTab {
  const clean = normalizeWorkspaceRoute(route)
  return { id: clean, route: clean, stateKey: `mc-tab:${clean}`, openedAt: Date.now() }
}

function loadInitialTabs(currentPath: string) {
  const current = normalizeWorkspaceRoute(currentPath)
  try {
    const stored = JSON.parse(localStorage.getItem(TABS_KEY) || '[]') as WorkspaceTab[]
    const tabs = stored
      .map(t => makeTab(t.route))
      .filter((t, i, arr) => ROUTE_META.has(t.route) && arr.findIndex(x => x.route === t.route) === i)
      .slice(0, MAX_WORKSPACE_TABS)
    const activeStored = normalizeWorkspaceRoute(localStorage.getItem(ACTIVE_KEY) || '')
    const active = tabs.some(t => t.id === activeStored) ? activeStored : current
    if (tabs.length && tabs.some(t => t.id === current)) return { tabs, activeId: current }
    if (tabs.length && tabs.some(t => t.id === active)) return { tabs, activeId: active }
    if (ROUTE_META.has(current) && tabs.length < MAX_WORKSPACE_TABS) return { tabs: [...tabs, makeTab(current)], activeId: current }
    return { tabs: tabs.length ? tabs : [makeTab('/dashboard')], activeId: tabs[0]?.id ?? '/dashboard' }
  } catch {
    return { tabs: [makeTab(current)], activeId: current }
  }
}

export function WorkspaceTabsProvider({ children }: { children: ReactNode }) {
  const loc = useLocation()
  const navigate = useNavigate()
  const { toast } = useToast()
  const initial = useMemo(() => loadInitialTabs(loc.pathname), [])
  const [tabs, setTabs] = useState<WorkspaceTab[]>(initial.tabs)
  const [activeId, setActiveId] = useState(initial.activeId)

  useEffect(() => {
    if (loc.pathname === '/') {
      navigate('/dashboard', { replace: true })
      return
    }
    const route = normalizeWorkspaceRoute(loc.pathname)
    if (!ROUTE_META.has(route)) return
    if (tabs.some(t => t.route === route)) {
      if (activeId !== route) setActiveId(route)
      return
    }
    if (tabs.length >= MAX_WORKSPACE_TABS) {
      const fallback = tabs.find(t => t.id === activeId)?.route ?? tabs[0]?.route ?? '/dashboard'
      toast({ kind: 'info', title: 'Three tabs maximum', detail: 'Close a tab before opening another page.' })
      if (fallback !== route) navigate(fallback, { replace: true })
      return
    }
    setTabs(prev => [...prev, makeTab(route)])
    setActiveId(route)
  }, [activeId, loc.pathname, navigate, tabs, toast])

  useEffect(() => {
    try {
      localStorage.setItem(TABS_KEY, JSON.stringify(tabs))
      localStorage.setItem(ACTIVE_KEY, activeId)
    } catch { /* ignore */ }
  }, [activeId, tabs])

  const value = useMemo<WorkspaceTabsContextValue>(() => ({
    tabs,
    activeId,
    focusTab: (id) => {
      const tab = tabs.find(t => t.id === id)
      if (!tab) return
      setActiveId(id)
      navigate(tab.route)
    },
    closeTab: (id) => {
      if (tabs.length <= 1) {
        toast({ kind: 'info', title: 'Keep one tab open', detail: 'Mission Control needs one active workspace tab.' })
        return
      }
      const idx = tabs.findIndex(t => t.id === id)
      if (idx < 0) return
      const nextTabs = tabs.filter(t => t.id !== id)
      setTabs(nextTabs)
      if (activeId === id) {
        const next = nextTabs[Math.max(0, Math.min(idx, nextTabs.length - 1))]
        setActiveId(next.id)
        navigate(next.route)
      }
    },
    reorderTabs: (fromId, toId) => {
      if (fromId === toId) return
      const from = tabs.findIndex(t => t.id === fromId)
      const to = tabs.findIndex(t => t.id === toId)
      if (from < 0 || to < 0) return
      const next = [...tabs]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      setTabs(next)
    },
  }), [activeId, navigate, tabs, toast])

  return <WorkspaceTabsContext.Provider value={value}>{children}</WorkspaceTabsContext.Provider>
}

export function useWorkspaceTabs() {
  const ctx = useContext(WorkspaceTabsContext)
  if (!ctx) throw new Error('useWorkspaceTabs must be used within WorkspaceTabsProvider')
  return ctx
}
