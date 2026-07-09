import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Network, Zap, Building2, HeartPulse, Kanban } from 'lucide-react'

const links = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/architecture', icon: Network, label: 'Architecture' },
  { to: '/ability', icon: Zap, label: 'Ability' },
  { to: '/office', icon: Building2, label: 'Office' },
  { to: '/task', icon: Kanban, label: 'Task' },
  { to: '/health', icon: HeartPulse, label: 'Health' },
]

export default function NavBar() {
  return (
    <nav className="w-56 flex-shrink-0 bg-surface border-r border-border flex flex-col">
      <div className="px-4 py-5 border-b border-border">
        <div className="text-accent font-bold text-lg tracking-widest">⚡ TOBI</div>
        <div className="text-muted text-xs mt-0.5 tracking-wider">MISSION CONTROL</div>
      </div>

      <div className="flex-1 py-3">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                isActive
                  ? 'text-accent bg-accent/10 border-r-2 border-accent'
                  : 'text-muted hover:text-text hover:bg-overlay/5'
              }`
            }
          >
            <Icon size={16} />
            <span>{label}</span>
          </NavLink>
        ))}
      </div>

      <div className="px-4 py-3 border-t border-border">
        <div className="text-muted text-xs">v2.0 · Mission Control</div>
      </div>
    </nav>
  )
}
