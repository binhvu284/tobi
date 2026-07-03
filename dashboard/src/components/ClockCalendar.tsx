import { useState, useEffect, useRef } from 'react'
import { Clock, Calendar } from 'lucide-react'
import { createPortal } from 'react-dom'
import { getOwnerSettings } from '../api'

function useTimezone() {
  const [tz, setTz] = useState('Asia/Ho_Chi_Minh')
  useEffect(() => {
    getOwnerSettings().then(s => { if (s.timezone) setTz(s.timezone) }).catch(() => {})
  }, [])
  return tz
}

function useTick(tz: string) {
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

type PopoverProps = { anchor: DOMRect; children: React.ReactNode; onClose: () => void }

function Popover({ anchor, children }: Omit<PopoverProps, 'onClose'>) {
  const top = anchor.bottom + 8
  const right = window.innerWidth - anchor.right

  return createPortal(
    <div
      className="fixed z-[9999] min-w-[180px] rounded-xl border border-border bg-surface shadow-lg"
      style={{ top, right }}
    >
      {children}
    </div>,
    document.body,
  )
}

function ClockPopover({ anchor, tz }: { anchor: DOMRect; tz: string }) {
  const now = useTick(tz)
  const local = toLocal(now, tz)
  const hh = local.getHours().toString().padStart(2, '0')
  const mm = local.getMinutes().toString().padStart(2, '0')
  const ss = local.getSeconds().toString().padStart(2, '0')
  const dateStr = local.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })

  return (
    <Popover anchor={anchor}>
      <div className="p-3 text-center">
        <div className="font-mono text-2xl font-bold text-heading">
          {hh}:{mm}<span className="text-base text-muted">:{ss}</span>
        </div>
        <div className="mt-1 text-[11px] text-muted">{dateStr}</div>
        <div className="mt-0.5 text-[10px] text-muted/60">{tz}</div>
      </div>
    </Popover>
  )
}

function CalendarPopover({ anchor, tz }: { anchor: DOMRect; tz: string }) {
  const now = useTick(tz)
  const local = toLocal(now, tz)
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

  return (
    <Popover anchor={anchor}>
      <div className="p-3">
        <div className="mb-2 text-center text-xs font-semibold text-heading">{monthName}</div>
        <div className="grid grid-cols-7 gap-0.5 text-center text-[10px]">
          {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map(d => (
            <div key={d} className="py-0.5 font-medium text-muted">{d}</div>
          ))}
          {cells.map((d, i) => (
            <div
              key={i}
              className={`rounded py-0.5 ${
                d === today
                  ? 'bg-accent text-white font-bold'
                  : d
                  ? 'text-text hover:bg-surface-raised'
                  : ''
              }`}
            >
              {d ?? ''}
            </div>
          ))}
        </div>
      </div>
    </Popover>
  )
}

type Widget = 'clock' | 'calendar' | null

export default function ClockCalendar() {
  const tz = useTimezone()
  const [open, setOpen] = useState<Widget>(null)
  const clockRef = useRef<HTMLButtonElement>(null)
  const calRef = useRef<HTMLButtonElement>(null)

  const clockRect = clockRef.current?.getBoundingClientRect()
  const calRect = calRef.current?.getBoundingClientRect()

  return (
    <>
      <button
        ref={clockRef}
        onMouseEnter={() => setOpen('clock')}
        onMouseLeave={() => setOpen(null)}
        className="rounded-md p-1.5 text-muted hover:text-text"
        aria-label="Clock"
      >
        <Clock size={15} />
      </button>
      <button
        ref={calRef}
        onMouseEnter={() => setOpen('calendar')}
        onMouseLeave={() => setOpen(null)}
        className="rounded-md p-1.5 text-muted hover:text-text"
        aria-label="Calendar"
      >
        <Calendar size={15} />
      </button>

      {open === 'clock' && clockRect && <ClockPopover anchor={clockRect} tz={tz} />}
      {open === 'calendar' && calRect && <CalendarPopover anchor={calRect} tz={tz} />}
    </>
  )
}
