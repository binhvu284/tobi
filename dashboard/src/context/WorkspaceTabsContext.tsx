import { createContext, useContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Inbox, MessagesSquare, History, Brain, Share2, Network, Zap,
  TrendingUp, HeartPulse, Building2, FolderKanban, Kanban, Settings, Cpu,
  HardDrive, KeyRound, Workflow, SlidersHorizontal, Newspaper, type LucideIcon,
} from 'lucide-react'
import { useToast } from './ToastProvider'

export const MAX_WORKSPACE_TABS = 5

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
const ICONS_KEY = 'tobi.workspace.tabIcons.v1'

export type TabIconData = {
  icon_type?: 'emoji' | 'icon' | 'custom'
  icon_value?: string | null
  emoji_icon?: string
  accent_color?: string | null
}

type WorkspaceTabsContextValue = {
  tabs: WorkspaceTab[]
  activeId: string
  tabLabels: Record<string, string>
  tabIcons: Record<string, TabIconData>
  focusTab: (id: string) => void
  closeTab: (id: string) => void
  reorderTabs: (fromId: string, toId: string) => void
  openTab: (route: string) => void
  setTabLabel: (id: string, label: string) => void
  setTabIcon: (id: string, icon: TabIconData) => void
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

// Chat sessions (/chat/123) each get their own workspace tab keyed chat:{id},
// so the owner can have multiple conversations open side-by-side.
const CHAT_SESSION_RE = /^\/chat\/(\d+)(?:\/.*)?$/

export function chatTabKey(route: string): string | null {
  const m = CHAT_SESSION_RE.exec(normalizeWorkspaceRoute(route))
  return m ? `chat:${m[1]}` : null
}

function tabKeyFor(route: string): string {
  return projectTabKey(route) ?? chatTabKey(route) ?? normalizeWorkspaceRoute(route)
}

function isTabbable(route: string): boolean {
  const clean = normalizeWorkspaceRoute(route)
  return ROUTE_META.has(clean) || PROJECT_ROUTE_RE.test(clean) || CHAT_SESSION_RE.test(clean)
}

export function getWorkspaceRouteMeta(route: string): WorkspaceRouteMeta {
  const clean = normalizeWorkspaceRoute(route)
  const pkey = projectTabKey(clean)
  if (pkey) return { route: pkey, label: `Project ${pkey.split('/')[2]}`, Icon: FolderKanban }
  const ckey = chatTabKey(clean)
  if (ckey) return { route: ckey, label: 'Chat', Icon: MessagesSquare }
  return ROUTE_META.get(clean) ?? WORKSPACE_ROUTES[0]
}

function loadLabels(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(LABELS_KEY) || '{}') } catch { return {} }
}
function loadIcons(): Record<string, TabIconData> {
  try {
    const raw = JSON.parse(localStorage.getItem(ICONS_KEY) || '{}')
    // Migrate old format: string emoji → { emoji_icon: str, icon_type: 'emoji' }
    const out: Record<string, TabIconData> = {}
    for (const [k, v] of Object.entries(raw)) {
      if (typeof v === 'string') out[k] = { icon_type: 'emoji', emoji_icon: v }
      else out[k] = v as TabIconData
    }
    return out
  } catch { return {} }
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
  const [tabIcons, setTabIcons] = useState<Record<string, TabIconData>>(loadIcons)

  // Refs mirror the latest state so callbacks read current values without
  // needing them in dependency arrays — keeps callback identities stable.
  const tabsRef = useRef(tabs)
  tabsRef.current = tabs
  const activeIdRef = useRef(activeId)
  activeIdRef.current = activeId

  // Route → tab sync.  Only depends on the route, NOT on tabs/activeId,
  // so it doesn't re-run when our own setState changes those.
  useEffect(() => {
    if (loc.pathname === '/') {
      navigate('/dashboard', { replace: true })
      return
    }
    const route = normalizeWorkspaceRoute(loc.pathname)
    if (!isTabbable(route)) return
    const key = tabKeyFor(route)
    const existing = tabsRef.current.find(t => t.id === key)
    if (existing) {
      if (existing.route !== route) {
        setTabs(prev => prev.map(t => (t.id === key ? { ...t, route } : t)))
      }
      if (key !== activeIdRef.current) setActiveId(key)
      return
    }
    if (key === activeIdRef.current) return
    setTabs(prev => prev.map(t => (t.id === activeIdRef.current ? makeTab(route) : t)))
    setActiveId(key)
  }, [loc.pathname, navigate])

  // Persist state to localStorage (single effect, not inside setState updaters).
  useEffect(() => {
    try {
      localStorage.setItem(TABS_KEY, JSON.stringify(tabs))
      localStorage.setItem(ACTIVE_KEY, activeId)
    } catch { /* ignore */ }
  }, [activeId, tabs])

  useEffect(() => {
    try { localStorage.setItem(LABELS_KEY, JSON.stringify(tabLabels)) } catch { /* ignore */ }
  }, [tabLabels])

  useEffect(() => {
    try { localStorage.setItem(ICONS_KEY, JSON.stringify(tabIcons)) } catch { /* ignore */ }
  }, [tabIcons])

  // Stable callbacks — identities never change across re-renders.
  const openTab = useCallback((route: string) => {
    const clean = normalizeWorkspaceRoute(route)
    if (!isTabbable(clean)) return
    const key = tabKeyFor(clean)
    const existing = tabsRef.current.find(t => t.id === key)
    if (existing) {
      setActiveId(existing.id)
      navigate(clean)
      return
    }
    if (tabsRef.current.length >= MAX_WORKSPACE_TABS) {
      toast({ kind: 'info', title: `${MAX_WORKSPACE_TABS} tabs maximum`, detail: 'Close a tab before opening another page.' })
      return
    }
    setTabs(prev => [...prev, makeTab(clean)])
    setActiveId(key)
    navigate(clean)
  }, [navigate, toast])

  const focusTab = useCallback((id: string) => {
    const tab = tabsRef.current.find(t => t.id === id)
    if (!tab) return
    setActiveId(id)
    navigate(tab.route)
  }, [navigate])

  const closeTab = useCallback((id: string) => {
    const cur = tabsRef.current
    if (cur.length <= 1) {
      toast({ kind: 'info', title: 'Keep one tab open', detail: 'Mission Control needs one active workspace tab.' })
      return
    }
    const idx = cur.findIndex(t => t.id === id)
    if (idx < 0) return
    const nextTabs = cur.filter(t => t.id !== id)
    setTabs(nextTabs)
    if (activeIdRef.current === id) {
      const next = nextTabs[Math.max(0, Math.min(idx, nextTabs.length - 1))]
      setActiveId(next.id)
      navigate(next.route)
    }
  }, [navigate, toast])

  const reorderTabs = useCallback((fromId: string, toId: string) => {
    if (fromId === toId) return
    const cur = tabsRef.current
    const from = cur.findIndex(t => t.id === fromId)
    const to = cur.findIndex(t => t.id === toId)
    if (from < 0 || to < 0) return
    const next = [...cur]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    setTabs(next)
  }, [])

  const setTabLabel = useCallback((id: string, label: string) => {
    setTabLabels(prev => prev[id] === label ? prev : { ...prev, [id]: label })
  }, [])

  const setTabIcon = useCallback((id: string, icon: TabIconData) => {
    setTabIcons(prev => {
      const cur = prev[id]
      if (cur && cur.icon_type === icon.icon_type && cur.icon_value === icon.icon_value && cur.emoji_icon === icon.emoji_icon)
        return prev
      return { ...prev, [id]: icon }
    })
  }, [])

  const value = useMemo<WorkspaceTabsContextValue>(() => ({
    tabs, activeId, tabLabels, tabIcons,
    openTab, focusTab, closeTab, reorderTabs, setTabLabel, setTabIcon,
  }), [tabs, activeId, tabLabels, tabIcons, openTab, focusTab, closeTab, reorderTabs, setTabLabel, setTabIcon])

  return <WorkspaceTabsContext.Provider value={value}>{children}</WorkspaceTabsContext.Provider>
}

export function useWorkspaceTabs() {
  const ctx = useContext(WorkspaceTabsContext)
  if (!ctx) throw new Error('useWorkspaceTabs must be used within WorkspaceTabsProvider')
  return ctx
}
