import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ThemeProvider } from './context/ThemeProvider'
import { ToastProvider } from './context/ToastProvider'
import AppShell from './components/AppShell'
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
import Integrations from './pages/Integrations'
import Mcp from './pages/Mcp'
import Brain from './pages/Brain'
import Chat from './pages/Chat'
import Inbox from './pages/Inbox'
// Graph carries the heavy force-graph canvas lib — lazy-load so it stays out of the main bundle.
const Graph = lazy(() => import('./pages/Graph'))
// Office embeds the Phaser game engine (~1.2MB) — lazy-load so it stays out of the main bundle.
const Office = lazy(() => import('./pages/Office'))

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ToastProvider>
          <AppShell>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/inbox" element={<Inbox />} />
              <Route path="/brain" element={<Brain />} />
              <Route path="/chat" element={<Chat />} />
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
              <Route path="/control" element={<ControlRoom />} />
              <Route path="/integrations" element={<Integrations />} />
              <Route path="/mcp" element={<Mcp />} />
              <Route path="/health" element={<Health />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </AppShell>
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
