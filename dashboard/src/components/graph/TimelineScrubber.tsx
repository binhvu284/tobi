import { useMemo, useState } from 'react'
import { Clock, Play, Pause } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { TimelineEvent } from '../../api.graph'

/* Replays graph growth: a slider over node-creation timestamps. Emits `date_to`
 * (ISO) so the graph filters to nodes that existed at the scrubbed moment. At max,
 * emits undefined = show everything. */

export default function TimelineScrubber({ events, onScrub }: {
  events: TimelineEvent[]
  onScrub: (dateTo: string | undefined) => void
}) {
  const stamps = useMemo(() => events.map(e => e.ts).filter(Boolean).sort(), [events])
  const [idx, setIdx] = useState(stamps.length)
  const [playing, setPlaying] = useState(false)
  const raf = useRef<ReturnType<typeof setInterval> | null>(null)

  // keep the handle at "now" when the dataset grows
  useEffect(() => { setIdx(stamps.length) }, [stamps.length])

  useEffect(() => {
    if (!playing) { if (raf.current) { clearInterval(raf.current); raf.current = null } return }
    raf.current = setInterval(() => {
      setIdx(i => {
        if (i >= stamps.length) { setPlaying(false); return stamps.length }
        const next = i + 1
        onScrub(next >= stamps.length ? undefined : stamps[next])
        return next
      })
    }, 220)
    return () => { if (raf.current) clearInterval(raf.current) }
  }, [playing, stamps, onScrub])

  if (stamps.length < 2) return null

  const atNow = idx >= stamps.length
  const label = atNow ? 'now' : new Date(stamps[Math.max(0, idx)]).toLocaleDateString()

  return (
    <div className="absolute bottom-4 left-1/2 z-10 flex w-[min(620px,80vw)] -translate-x-1/2 items-center gap-3 rounded-2xl border border-accent/15 bg-[#07101d]/82 px-3 py-2 shadow-[0_18px_70px_rgb(0_0_0/0.24),0_0_32px_rgb(var(--accent)/0.07)] backdrop-blur-xl">
      <button onClick={() => { setPlaying(p => !p); if (idx >= stamps.length) { setIdx(0); onScrub(stamps[0]) } }}
        className="flex h-7 w-7 items-center justify-center rounded-lg border border-accent/35 bg-accent/10 text-accent hover:text-heading" title={playing ? 'Pause' : 'Replay growth'}>
        {playing ? <Pause size={15} /> : <Play size={15} />}
      </button>
      <Clock size={13} className="text-muted" />
      <input type="range" min={0} max={stamps.length} value={idx}
        onChange={e => {
          const v = Number(e.target.value); setIdx(v); setPlaying(false)
          onScrub(v >= stamps.length ? undefined : stamps[v])
        }}
        className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-border accent-accent" />
      <span className="w-20 shrink-0 text-right text-[11px] tabular-nums text-muted">{label}</span>
    </div>
  )
}
