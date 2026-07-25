import { useState, useEffect, useRef } from 'react'
import { Clock, Calendar } from 'lucide-react'
import { createPortal } from 'react-dom'
import { getOwnerSettings } from '../api.brain'

function useTimezone() {
  const [tz, setTz] = useState('Asia/Ho_Chi_Minh')
  useEffect(() => {
    getOwnerSettings().then(s => { if (s.timezone) setTz(s.timezone) }).catch(() => {})
  }, [])
  return tz
}

function useTick() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

function toLocal(date: Date, tz: string) {
  return new Date(date.toLocaleString('en-US', { timeZone: tz }))
}

// ── Combined detail popover (live clock + month grid) ────────────────────────
function DetailPopover({ anchor, local, tz }: { anchor: DOMRect; local: Date; tz: string }) {
  const top = anchor.bottom + 8
  const right = window.innerWidth - anchor.right

  const hh = local.getHours().toString().padStart(2, '0')
  const mm = local.getMinutes().toString().padStart(2, '0')
  const ss = local.getSeconds().toString().padStart(2, '0')
  const fullDate = local.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })

  const year = local.getFullYear()
  const month = local.getMonth()
  const today = local.getDate()
  const firstDay = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const monthName = local.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })

  const cells: (number | null)[] = []
  for (let i = 0; i < firstDay; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) cells.push(d)
  while (cells.length % 7 !== 0) cells.push(null)

  return createPortal(
    <div className="fixed z-[9999] w-60 overflow-hidden rounded-xl border border-border bg-surface shadow-2xl ring-1 ring-accent/10" style={{ top, right }}>
      {/* Clock */}
      <div className="border-b border-border/60 p-3 text-center">
        <div className="font-mono text-2xl font-bold tabular-nums text-heading">
          {hh}:{mm}<span className="text-base text-muted">:{ss}</span>
        </div>
        <div className="mt-1 text-[11px] text-muted">{fullDate}</div>
        <div className="mt-0.5 text-[10px] text-muted/60">{tz}</div>
      </div>
      {/* Calendar */}
      <div className="p-3">
        <div className="mb-2 text-center text-xs font-semibold text-heading">{monthName}</div>
        <div className="grid grid-cols-7 gap-0.5 text-center text-[10px]">
          {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map(d => (
            <div key={d} className="py-0.5 font-medium text-muted">{d}</div>
          ))}
          {cells.map((d, i) => (
            <div key={i}
              className={`rounded py-0.5 ${d === today ? 'bg-accent font-bold text-white' : d ? 'text-text' : ''}`}>
              {d ?? ''}
            </div>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  )
}

// ── Single compact badge: inline time + date, hover → full detail ────────────
export default function ClockCalendar() {
  const tz = useTimezone()
  const now = useTick()
  const local = toLocal(now, tz)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)
  const rect = ref.current?.getBoundingClientRect()

  const compactTime = local.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) // 14:32
  const compactDate = local.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })     // Jul 3

  return (
    <>
      <button
        ref={ref}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="hidden items-center gap-2 rounded-md border border-border px-2 py-1.5 text-xs text-muted transition-colors hover:border-accent/40 hover:text-text sm:flex"
        aria-label="Date and time"
      >
        <span className="flex items-center gap-1">
          <Clock size={13} className="shrink-0" />
          <span className="font-mono tabular-nums">{compactTime}</span>
        </span>
        <span className="h-3.5 w-px bg-border" />
        <span className="flex items-center gap-1">
          <Calendar size={13} className="shrink-0" />
          <span>{compactDate}</span>
        </span>
      </button>

      {open && rect && <DetailPopover anchor={rect} local={local} tz={tz} />}
    </>
  )
}
