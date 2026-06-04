import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ThemeProvider } from './context/ThemeProvider'
import { ToastProvider } from './context/ToastProvider'
import AppShell from './components/AppShell'
import Dashboard from './pages/Dashboard'
import Architecture from './pages/Architecture'
import Ability from './pages/Ability'
import Evolution from './pages/Evolution'
import Office from './pages/Office'
import Health from './pages/Health'
import Task from './pages/Task'
import Projects from './pages/Projects'
import ControlRoom from './pages/ControlRoom'
import Settings from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ToastProvider>
          <AppShell>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/architecture" element={<Architecture />} />
              <Route path="/ability" element={<Ability />} />
              <Route path="/evolution" element={<Evolution />} />
              <Route path="/office" element={<Office />} />
              <Route path="/task" element={<Task />} />
              <Route path="/projects" element={<Projects />} />
              <Route path="/control" element={<ControlRoom />} />
              <Route path="/health" element={<Health />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </AppShell>
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
