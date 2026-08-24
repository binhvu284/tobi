// Morpheus workspace tabs.
//
// Same mechanism as TOBI's WorkspaceTabsContext (src/context/WorkspaceTabsContext.tsx): a
// browser-style tab strip whose tabs are routes, persisted across reloads, with every open tab
// staying mounted so switching back does not refetch or lose scroll. Morpheus keeps its own
// provider rather than reusing TOBI's because its routes, its storage keys, and its tab budget
// are its own -- opening a Morpheus object must never displace a TOBI tab.
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode,
} from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Home, MessagesSquare, ScanSearch, Cpu, ShieldCheck, Fingerprint, Sparkles, type LucideIcon,
} from 'lucide-react'

export const MAX_MORPHEUS_TABS = 5

export type MorpheusTab = { id: string; route: string; stateKey: string; openedAt: number }
export type MorpheusRouteMeta = { route: string; label: string; Icon: LucideIcon }

export const MORPHEUS_ROUTES: MorpheusRouteMeta[] = [
  { route: '/morpheus', label: 'Home', Icon: Home },
  { route: '/morpheus/chat', label: 'Chat', Icon: MessagesSquare },
  { route: '/morpheus/osint', label: 'OSINT', Icon: ScanSearch },
  { route: '/morpheus/agents', label: 'Agents', Icon: Sparkles },
  { route: '/morpheus/models', label: 'Models', Icon: Cpu },
  { route: '/morpheus/access', label: 'Access Log', Icon: Fingerprint },
  { route: '/morpheus/security', label: 'Security', Icon: ShieldCheck },
]

const ROUTE_META = new Map(MORPHEUS_ROUTES.map(r => [r.route, r]))
const TABS_KEY = 'morpheus.tabs.v1'
const ACTIVE_KEY = 'morpheus.activeTab.v1'

/** An OSINT object (/morpheus/osint/acme-robotics.com) gets its own tab, like TOBI chat sessions. */
const OBJECT_RE = /^\/morpheus\/osint\/([^/]+)$/

export function normalizeRoute(path: string) {
  if (!path || path === '/morpheus/') return '/morpheus'
  const clean = path.split('?')[0].split('#')[0]
  return clean.endsWith('/') && clean.length > 1 ? clean.slice(0, -1) : clean
}

function tabKeyFor(route: string) {
  const clean = normalizeRoute(route)
  const m = OBJECT_RE.exec(clean)
  return m ? `object:${m[1]}` : clean
}

function isTabbable(route: string) {
  const clean = normalizeRoute(route)
  return ROUTE_META.has(clean) || OBJECT_RE.test(clean)
}

export function getMorpheusRouteMeta(route: string): MorpheusRouteMeta {
  const clean = normalizeRoute(route)
  const m = OBJECT_RE.exec(clean)
  if (m) return { route: clean, label: decodeURIComponent(m[1]), Icon: ScanSearch }
  return ROUTE_META.get(clean) ?? MORPHEUS_ROUTES[0]
}

function makeTab(route: string): MorpheusTab {
  const clean = normalizeRoute(route)
  const key = tabKeyFor(clean)
  return { id: key, route: clean, stateKey: `morpheus-tab:${key}`, openedAt: Date.now() }
}

function loadInitial(currentPath: string) {
  const current = normalizeRoute(currentPath)
  const currentKey = tabKeyFor(current)
  try {
    const stored = JSON.parse(localStorage.getItem(TABS_KEY) || '[]') as MorpheusTab[]
    const tabs = stored
      .map(t => makeTab(t.route))
      .filter((t, i, arr) => isTabbable(t.route) && arr.findIndex(x => x.id === t.id) === i)
      .slice(0, MAX_MORPHEUS_TABS)
    if (tabs.some(t => t.id === currentKey)) return { tabs, activeId: currentKey }
    if (isTabbable(current) && tabs.length < MAX_MORPHEUS_TABS) {
      return { tabs: [...tabs, makeTab(current)], activeId: currentKey }
    }
    const stashed = localStorage.getItem(ACTIVE_KEY) || ''
    if (tabs.length) return { tabs, activeId: tabs.some(t => t.id === stashed) ? stashed : tabs[0].id }
    return { tabs: [makeTab('/morpheus')], activeId: '/morpheus' }
  } catch {
    return { tabs: [makeTab(current)], activeId: currentKey }
  }
}

type Ctx = {
  tabs: MorpheusTab[]
  activeId: string
  openTab: (route: string) => void
  focusTab: (id: string) => void
  closeTab: (id: string) => void
  reorderTabs: (fromId: string, toId: string) => void
  /** Set when the tab budget is full, so the strip can say so instead of failing silently. */
  notice: string
  clearNotice: () => void
}

const MorpheusTabsContext = createContext<Ctx | null>(null)

export function MorpheusTabsProvider({ children }: { children: ReactNode }) {
  const loc = useLocation()
  const navigate = useNavigate()
  const initial = useMemo(() => loadInitial(loc.pathname), [])
  const [tabs, setTabs] = useState<MorpheusTab[]>(initial.tabs)
  const [activeId, setActiveId] = useState(initial.activeId)
  const [notice, setNotice] = useState('')

  const tabsRef = useRef(tabs); tabsRef.current = tabs
  const activeRef = useRef(activeId); activeRef.current = activeId

  // Route -> tab sync. Depends only on the path so our own setState does not re-enter it.
  useEffect(() => {
    const route = normalizeRoute(loc.pathname)
    if (!isTabbable(route)) return
    const key = tabKeyFor(route)
    const existing = tabsRef.current.find(t => t.id === key)
    if (existing) {
      if (existing.route !== route) setTabs(p => p.map(t => (t.id === key ? { ...t, route } : t)))
      if (key !== activeRef.current) setActiveId(key)
      return
    }
    if (key === activeRef.current) return
    // Navigating to an untabbed route replaces the active tab rather than growing the strip.
    //
    // The guard matters: if activeId has drifted to a tab that no longer exists, the map below
    // replaces nothing, activeId is then set to a key with no matching tab, and every pane
    // renders hidden -- a completely blank app with the shell still drawn around it.
    setTabs(prev => {
      if (prev.some(t => t.id === activeRef.current)) {
        return prev.map(t => (t.id === activeRef.current ? makeTab(route) : t))
      }
      return prev.length < MAX_MORPHEUS_TABS
        ? [...prev, makeTab(route)]
        : [...prev.slice(0, -1), makeTab(route)]
    })
    setActiveId(key)
  }, [loc.pathname])

  useEffect(() => {
    try {
      localStorage.setItem(TABS_KEY, JSON.stringify(tabs))
      localStorage.setItem(ACTIVE_KEY, activeId)
    } catch { /* storage disabled; tabs simply do not persist */ }
  }, [tabs, activeId])

  const openTab = useCallback((route: string) => {
    const clean = normalizeRoute(route)
    if (!isTabbable(clean)) return
    const key = tabKeyFor(clean)
    const existing = tabsRef.current.find(t => t.id === key)
    if (existing) { setActiveId(key); navigate(clean); return }
    if (tabsRef.current.length >= MAX_MORPHEUS_TABS) {
      setNotice(`${MAX_MORPHEUS_TABS} tabs maximum. Close one to open another.`)
      return
    }
    setTabs(p => [...p, makeTab(clean)])
    setActiveId(key)
    navigate(clean)
  }, [navigate])

  const focusTab = useCallback((id: string) => {
    const tab = tabsRef.current.find(t => t.id === id)
    if (!tab) return
    setActiveId(id)
    navigate(tab.route)
  }, [navigate])

  const closeTab = useCallback((id: string) => {
    const cur = tabsRef.current
    if (cur.length <= 1) { setNotice('Keep one tab open.'); return }
    const idx = cur.findIndex(t => t.id === id)
    if (idx < 0) return
    const next = cur.filter(t => t.id !== id)
    setTabs(next)
    if (activeRef.current === id) {
      const focus = next[Math.max(0, Math.min(idx, next.length - 1))]
      setActiveId(focus.id)
      navigate(focus.route)
    }
  }, [navigate])

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

  const clearNotice = useCallback(() => setNotice(''), [])

  const value = useMemo<Ctx>(() => ({
    tabs, activeId, openTab, focusTab, closeTab, reorderTabs, notice, clearNotice,
  }), [tabs, activeId, openTab, focusTab, closeTab, reorderTabs, notice, clearNotice])

  return <MorpheusTabsContext.Provider value={value}>{children}</MorpheusTabsContext.Provider>
}

export function useMorpheusTabs() {
  const ctx = useContext(MorpheusTabsContext)
  if (!ctx) throw new Error('useMorpheusTabs must be used within MorpheusTabsProvider')
  return ctx
}
