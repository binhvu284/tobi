import { Activity, Bot, FileOutput, Play, ShieldCheck } from 'lucide-react'
import type { OfficeActivity } from '../../api.officev3'

const eventIcon = (type: string) => type.startsWith('artifact.') ? FileOutput : type.startsWith('mission.') ? Play : type.includes('confirm') ? ShieldCheck : Bot

export default function OfficeActivityFeed({ activity }: { activity: OfficeActivity[] }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border px-4 py-3"><div className="text-[10px] font-semibold uppercase text-muted">Office-local history</div><div className="text-sm font-semibold text-heading">Activity stream</div></div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {activity.length === 0 && <div className="flex h-full min-h-48 flex-col items-center justify-center text-muted"><Activity size={22} /><span className="mt-2 text-xs">No Office activity yet.</span></div>}
        {activity.map(item => {
          const Icon = eventIcon(item.event_type)
          return (
            <div key={item.id} className="flex gap-3 border-b border-border px-4 py-3">
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center bg-overlay/5 text-accent"><Icon size={13} /></span>
              <span className="min-w-0 flex-1"><span className="block text-[11px] text-text">{item.summary}</span><span className="mt-1 block text-[9px] uppercase text-muted">{item.actor} · {new Date(item.created_at).toLocaleString()}</span></span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
