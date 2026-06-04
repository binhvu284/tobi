type StatCardProps = {
  label: string
  value: string | number
  color?: 'accent' | 'success' | 'warning' | 'danger' | 'muted'
  icon?: string
  sub?: string
}

const colorMap = {
  accent: 'text-accent',
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
  muted: 'text-muted',
}

export default function StatCard({ label, value, color = 'accent', icon, sub }: StatCardProps) {
  return (
    <div className="bg-surface border border-border rounded-lg p-5">
      <div className="text-muted text-xs uppercase tracking-widest mb-2 flex items-center gap-1.5">
        {icon && <span>{icon}</span>}
        {label}
      </div>
      <div className={`text-3xl font-bold ${colorMap[color]}`}>{value}</div>
      {sub && <div className="text-muted text-xs mt-1">{sub}</div>}
    </div>
  )
}
