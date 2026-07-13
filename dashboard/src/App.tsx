import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ThemeProvider } from './context/ThemeProvider'
import { MotionProvider } from './context/MotionProvider'
import { ToastProvider } from './context/ToastProvider'
import { WorkspaceTabsProvider, useWorkspaceTabs } from './context/WorkspaceTabsContext'
import AppShell from './components/AppShell'
import ErrorBoundary from './components/ErrorBoundary'
import PageBoot from './components/motion/PageBoot'
import PageLoader from './components/PageLoader'
import Dashboard from './pages/Dashboard'
import Architecture from './pages/Architecture'
import Ability from './pages/Ability'
import Evolution from './pages/Evolution'
import Health from './pages/Health'
import Task from './pages/Task'
import Projects from './pages/Projects'
import ControlRoom from './pages/ControlRoom'
import Settings from './pages/Settings'
import Models from './pages/Models'
import Integrations from './pages/Integrations'
import Mcp from './pages/Mcp'
import Brain from './pages/Brain'
import Chat from './pages/Chat'
import Inbox from './pages/Inbox'
import Actions from './pages/Actions'
// Graph carries the heavy force-graph canvas lib — lazy-load so it stays out of the main bundle.
const Graph = lazy(() => import('./pages/Graph'))
// Office embeds the Phaser game engine (~1.2MB) — lazy-load so it stays out of the main bundle.
const Office = lazy(() => import('./pages/OfficeV3'))
// Storage carries Recharts — lazy-load so it stays out of the main bundle.
const Storage = lazy(() => import('./pages/Storage'))
// News (Explore) carries Recharts too — lazy-load so it stays out of the main bundle.
const News = lazy(() => import('./pages/News'))
// Project v2 full-page workspace (#12) — lazy so the main bundle stays lean.
const ProjectWorkspace = lazy(() => import('./pages/ProjectWorkspace'))

function RouteSet({ location }: { location?: string }) {
  return (
    <Routes location={location}>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/inbox" element={<Inbox />} />
      <Route path="/brain" element={<Brain />} />
      <Route path="/chat" element={<Chat />} />
      <Route path="/chat/:sessionId" element={<Chat />} />
      <Route path="/actions" element={<Actions />} />
      <Route path="/graph" element={
        <Suspense fallback={<PageLoader preset="graph" />}><Graph /></Suspense>
      } />
      <Route path="/architecture" element={<Architecture />} />
      <Route path="/ability" element={<Ability />} />
      <Route path="/evolution" element={<Evolution />} />
      <Route path="/office" element={
        <Suspense fallback={<PageLoader preset="office" />}><Office /></Suspense>
      } />
      <Route path="/task" element={<Task />} />
      <Route path="/projects" element={<Projects />} />
      {/* One splat route keeps the workspace mounted across inner-tab changes */}
      <Route path="/projects/:projectId/*" element={
        <Suspense fallback={<PageLoader preset="projects" />}><ProjectWorkspace /></Suspense>
      } />
      <Route path="/control" element={<ControlRoom />} />
      <Route path="/integrations" element={<Integrations />} />
      <Route path="/mcp" element={<Mcp />} />
      <Route path="/health" element={<Health />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/models" element={<Models />} />
      <Route path="/storage" element={
        <Suspense fallback={<PageLoader />}><Storage /></Suspense>
      } />
      <Route path="/news" element={
        <Suspense fallback={<PageLoader />}><News /></Suspense>
      } />
    </Routes>
  )
}

function WorkspaceRoutePanes() {
  const { tabs, activeId } = useWorkspaceTabs()
  return (
    <div className="relative h-full">
      {tabs.map(tab => (
        <section key={tab.id} data-state-key={tab.stateKey}
          className={`absolute inset-0 overflow-y-auto pb-16 md:pb-0 ${tab.id === activeId ? 'block' : 'hidden'}`}>
          <PageBoot>
            <ErrorBoundary key={tab.id}>
              <RouteSet location={tab.route} />
            </ErrorBoundary>
          </PageBoot>
        </section>
      ))}
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <MotionProvider>
          <ToastProvider>
            <WorkspaceTabsProvider>
              <AppShell>
                <WorkspaceRoutePanes />
              </AppShell>
            </WorkspaceTabsProvider>
          </ToastProvider>
        </MotionProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
