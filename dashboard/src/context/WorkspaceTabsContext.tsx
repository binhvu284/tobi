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
const LABELS_KEY = 'tobi.workspace.tabLabels.v1'

type WorkspaceTabsContextValue = {
  tabs: WorkspaceTab[]
  activeId: string
  tabLabels: Record<string, string>
  focusTab: (id: string) => void
  closeTab: (id: string) => void
  reorderTabs: (fromId: string, toId: string) => void
  openTab: (route: string) => void
  setTabLabel: (id: string, label: string) => void
}

const WorkspaceTabsContext = createContext<WorkspaceTabsContextValue | null>(null)

export function normalizeWorkspaceRoute(path: string) {
  if (!path || path === '/') return '/dashboard'
  const clean = path.split('?')[0].split('#')[0]
  return clean.endsWith('/') && clean.length > 1 ? clean.slice(0, -1) : clean
}

// Project v2 (#12): a project workspace (/projects/8/tasks) is a dynamic tabbable route.
// All inner tabs of one project share ONE workspace tab keyed /projects/{id}, so moving
// between Overview/Tasks/… updates the tab's route rather than spawning new tabs.
const PROJECT_ROUTE_RE = /^\/projects\/(\d+)(?:\/.*)?$/

export function projectTabKey(route: string): string | null {
  const m = PROJECT_ROUTE_RE.exec(normalizeWorkspaceRoute(route))
  return m ? `/projects/${m[1]}` : null
}

function tabKeyFor(route: string): string {
  return projectTabKey(route) ?? normalizeWorkspaceRoute(route)
}

function isTabbable(route: string): boolean {
  const clean = normalizeWorkspaceRoute(route)
  return ROUTE_META.has(clean) || PROJECT_ROUTE_RE.test(clean)
}

export function getWorkspaceRouteMeta(route: string): WorkspaceRouteMeta {
  const clean = normalizeWorkspaceRoute(route)
  const key = projectTabKey(clean)
  if (key) return { route: key, label: `Project ${key.split('/')[2]}`, Icon: FolderKanban }
  return ROUTE_META.get(clean) ?? WORKSPACE_ROUTES[0]
}

function loadLabels(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(LABELS_KEY) || '{}') } catch { return {} }
}

function makeTab(route: string): WorkspaceTab {
  const clean = normalizeWorkspaceRoute(route)
  const key = tabKeyFor(clean)
  return { id: key, route: clean, stateKey: `mc-tab:${key}`, openedAt: Date.now() }
}

function loadInitialTabs(currentPath: string) {
  const current = normalizeWorkspaceRoute(currentPath)
  const currentKey = tabKeyFor(current)
  try {
    const stored = JSON.parse(localStorage.getItem(TABS_KEY) || '[]') as WorkspaceTab[]
    const tabs = stored
      .map(t => makeTab(t.route))
      .filter((t, i, arr) => isTabbable(t.route) && arr.findIndex(x => x.id === t.id) === i)
      .slice(0, MAX_WORKSPACE_TABS)
    const activeStored = localStorage.getItem(ACTIVE_KEY) || ''
    const active = tabs.some(t => t.id === activeStored) ? activeStored : currentKey
    if (tabs.length && tabs.some(t => t.id === currentKey)) return { tabs, activeId: currentKey }
    if (tabs.length && tabs.some(t => t.id === active)) return { tabs, activeId: active }
    if (isTabbable(current) && tabs.length < MAX_WORKSPACE_TABS) return { tabs: [...tabs, makeTab(current)], activeId: currentKey }
    return { tabs: tabs.length ? tabs : [makeTab('/dashboard')], activeId: tabs[0]?.id ?? '/dashboard' }
  } catch {
    return { tabs: [makeTab(current)], activeId: currentKey }
  }
}

export function WorkspaceTabsProvider({ children }: { children: ReactNode }) {
  const loc = useLocation()
  const navigate = useNavigate()
  const { toast } = useToast()
  const initial = useMemo(() => loadInitialTabs(loc.pathname), [])
  const [tabs, setTabs] = useState<WorkspaceTab[]>(initial.tabs)
  const [activeId, setActiveId] = useState(initial.activeId)
  const [tabLabels, setTabLabels] = useState<Record<string, string>>(loadLabels)

  useEffect(() => {
    if (loc.pathname === '/') {
      navigate('/dashboard', { replace: true })
      return
    }
    const route = normalizeWorkspaceRoute(loc.pathname)
    if (!isTabbable(route)) return
    const key = tabKeyFor(route)
    const existing = tabs.find(t => t.id === key)
    if (existing) {
      // Same workspace tab — but a project's inner tab may have changed (…/overview → …/tasks):
      // keep the tab, update its stored route so focus/restore lands on the right inner tab.
      if (existing.route !== route) {
        setTabs(prev => prev.map(t => (t.id === key ? { ...t, route } : t)))
      }
      if (key !== activeId) setActiveId(key)
      return
    }
    if (key === activeId) return
    // No tab for this route: navigate the active tab in place instead of spawning a new one.
    setTabs(prev => prev.map(t => (t.id === activeId ? makeTab(route) : t)))
    setActiveId(key)
  }, [activeId, loc.pathname, navigate, tabs])

  useEffect(() => {
    try {
      localStorage.setItem(TABS_KEY, JSON.stringify(tabs))
      localStorage.setItem(ACTIVE_KEY, activeId)
    } catch { /* ignore */ }
  }, [activeId, tabs])

  const value = useMemo<WorkspaceTabsContextValue>(() => ({
    tabs,
    activeId,
    tabLabels,
    openTab: (route) => {
      const clean = normalizeWorkspaceRoute(route)
      if (!isTabbable(clean)) return
      const key = tabKeyFor(clean)
      const existing = tabs.find(t => t.id === key)
      if (existing) {
        setActiveId(existing.id)
        navigate(clean)
        return
      }
      if (tabs.length >= MAX_WORKSPACE_TABS) {
        toast({ kind: 'info', title: `${MAX_WORKSPACE_TABS} tabs maximum`, detail: 'Close a tab before opening another page.' })
        return
      }
      setTabs(prev => [...prev, makeTab(clean)])
      setActiveId(key)
      navigate(clean)
    },
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
    setTabLabel: (id, label) => {
      setTabLabels(prev => {
        if (prev[id] === label) return prev
        const next = { ...prev, [id]: label }
        // keep only labels for known tabs + a small tail, so the map can't grow unbounded
        try { localStorage.setItem(LABELS_KEY, JSON.stringify(next)) } catch { /* ignore */ }
        return next
      })
    },
  }), [activeId, navigate, tabLabels, tabs, toast])

  return <WorkspaceTabsContext.Provider value={value}>{children}</WorkspaceTabsContext.Provider>
}

export function useWorkspaceTabs() {
  const ctx = useContext(WorkspaceTabsContext)
  if (!ctx) throw new Error('useWorkspaceTabs must be used within WorkspaceTabsProvider')
  return ctx
}
