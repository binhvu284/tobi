import type { GraphCommunity } from '../../api.graph'

/* Communities legend (graphify-style): color dot + label + count, ordered by size.
 * Falls back to the domain key when communities haven't been computed yet. */

const DOMAIN_FALLBACK: { key: string; label: string; color: string }[] = [
  { key: 'memory', label: 'Memory', color: '#a78bfa' },
  { key: 'task', label: 'Task', color: '#58a6ff' },
  { key: 'project', label: 'Project', color: '#22d3ee' },
  { key: 'notion', label: 'Notion', color: '#e5e7eb' },
  { key: 'github', label: 'GitHub', color: '#8b949e' },
  { key: 'gdrive', label: 'Drive', color: '#34d399' },
  { key: 'local', label: 'Local', color: '#f59e0b' },
  { key: 'manual', label: 'Note', color: '#f472b6' },
]
const EDGES: { label: string; color: string }[] = [
  { label: 'reference', color: '#58a6ff' },
  { label: 'semantic', color: '#a78bfa' },
  { label: 'manual', color: '#f472b6' },
]

export default function GraphLegend({ communities }: { communities: GraphCommunity[] }) {
  const hasComm = communities.length > 0
  return (
    <div className="pointer-events-none absolute bottom-4 left-4 z-10 max-h-[42vh] w-60 select-none overflow-hidden rounded-2xl border border-accent/15 bg-[#07101d]/78 p-3 text-[11px] shadow-[0_18px_70px_rgb(0_0_0/0.25),0_0_32px_rgb(var(--accent)/0.07)] backdrop-blur-xl">
      <div className="mb-2 font-semibold uppercase tracking-[0.16em] text-muted">
        {hasComm ? `Communities · ${communities.length}` : 'Nodes'}
      </div>
      <div className="max-h-[26vh] space-y-1 overflow-y-auto pr-1">
        {hasComm
          ? communities.map(c => (
              <div key={c.cid} className="flex items-center gap-1.5 rounded-md px-1 py-0.5 text-text">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: c.color, boxShadow: `0 0 6px ${c.color}` }} />
                <span className="flex-1 truncate" title={c.label}>{c.label}</span>
                <span className="shrink-0 text-muted">{c.count}</span>
              </div>
            ))
          : DOMAIN_FALLBACK.map(d => (
              <div key={d.key} className="flex items-center gap-1.5 rounded-md px-1 py-0.5 text-text">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: d.color, boxShadow: `0 0 6px ${d.color}` }} />
                {d.label}
              </div>
            ))}
      </div>
      <div className="mb-1.5 mt-2.5 font-semibold uppercase tracking-[0.16em] text-muted">Synapses</div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {EDGES.map(e => (
          <div key={e.label} className="flex items-center gap-1.5 text-text">
            <span className="h-0.5 w-4 rounded" style={{ background: e.color }} />
            {e.label}
          </div>
        ))}
      </div>
    </div>
  )
}
