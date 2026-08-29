import type { GraphCommunity } from '../../api.graph'
import { domainColor, orderDomains } from './layouts'

/* What the colours and lines mean. Domains come from the graph itself rather than a hardcoded
 * list — the old list advertised Notion, GitHub, Drive and Local, none of which have a single
 * node, and left out `resource`, which has 28. */

const DOMAIN_LABEL: Record<string, string> = {
  memory: 'Memories', task: 'Tasks', project: 'Projects', resource: 'Resources',
  manual: 'Notes', local: 'Local', notion: 'Notion', github: 'GitHub', gdrive: 'Drive',
}
const EDGES: { label: string; meaning: string; color: string }[] = [
  { label: 'reference', meaning: 'one thing mentions the other', color: '#58a6ff' },
  { label: 'semantic', meaning: 'they mean similar things', color: '#a78bfa' },
  { label: 'manual', meaning: 'you linked them by hand', color: '#f472b6' },
]

export default function GraphLegend({ communities, domainCounts }: {
  communities: GraphCommunity[]
  domainCounts: Record<string, number>
}) {
  const domains = orderDomains(Object.keys(domainCounts), d => domainCounts[d] || 0)
  const label = (d: string) => DOMAIN_LABEL[d] || d.charAt(0).toUpperCase() + d.slice(1)

  return (
    <div className="pointer-events-none absolute bottom-4 left-4 z-10 max-h-[46vh] w-60 select-none overflow-hidden rounded-2xl border border-accent/15 bg-[#07101d]/78 p-3 text-[11px] shadow-[0_18px_70px_rgb(0_0_0/0.25),0_0_32px_rgb(var(--accent)/0.07)] backdrop-blur-xl">
      {domains.length > 0 && (
        <>
          <div className="mb-1.5 font-semibold uppercase tracking-[0.16em] text-muted">Kinds of thing</div>
          <div className="mb-2.5 space-y-1">
            {domains.map(d => (
              <div key={d} className="flex items-center gap-1.5 text-text">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: domainColor(d), boxShadow: `0 0 6px ${domainColor(d)}` }} />
                <span className="flex-1 truncate">{label(d)}</span>
                <span className="shrink-0 text-muted">{domainCounts[d]}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {communities.length > 0 && (
        <>
          <div className="mb-1.5 font-semibold uppercase tracking-[0.16em] text-muted">
            Groups · {communities.length}
          </div>
          <div className="max-h-[18vh] space-y-1 overflow-y-auto pr-1">
            {communities.map(c => (
              <div key={c.cid} className="flex items-center gap-1.5 rounded-md px-1 py-0.5 text-text">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: c.color, boxShadow: `0 0 6px ${c.color}` }} />
                <span className="flex-1 truncate" title={c.label}>{c.label}</span>
                <span className="shrink-0 text-muted">{c.count}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="mb-1.5 mt-2.5 font-semibold uppercase tracking-[0.16em] text-muted">Links</div>
      <div className="space-y-1">
        {EDGES.map(e => (
          <div key={e.label} className="flex items-center gap-1.5 text-text">
            <span className="h-0.5 w-4 shrink-0 rounded" style={{ background: e.color }} />
            <span className="truncate" title={e.meaning}>{e.meaning}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
