import { Link } from 'react-router-dom'
import { ArrowRight, Share2 } from 'lucide-react'
import GraphSigil from './graph/GraphSigil'
import { useGraphSnapshot } from './graph/graphSnapshot'

/* The first thing on the Dashboard, and the first place the graph asset is used for real.
 *
 * Everything here — the avatar, the three counts, the three demo sizes — reads the one shared
 * graph snapshot. Sync the graph, add a memory, draw a link by hand, and this card changes on
 * its own; nothing exports an image or caches a picture. The row of small sigils is the proof
 * that the asset is size-independent rather than a screenshot of the Graph page. */

const GREETINGS: [number, string][] = [[5, 'Good morning'], [12, 'Good afternoon'], [18, 'Good evening'], [22, 'Still up']]

function greeting(): string {
  const hour = new Date().getHours()
  let text = 'Good evening'
  for (const [from, label] of GREETINGS) if (hour >= from) text = label
  if (hour < 5) text = 'Still up'
  return text
}

export default function WelcomeCard() {
  const { data, loading, fetchedAt, error } = useGraphSnapshot()
  const groups = new Set(data.nodes.map(n => n.community ?? -1)).size
  const waiting = !fetchedAt && loading
  const stat = (value: number) => (waiting ? '—' : value.toLocaleString())

  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-surface p-5">
      <div className="pointer-events-none absolute -left-24 -top-24 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-28 right-0 h-64 w-64 rounded-full bg-purple/10 blur-3xl" />

      <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center">
        {/* TOBI — the avatar is the live graph, not an illustration of it */}
        <div className="relative shrink-0 self-center">
          <div className="absolute inset-0 -m-3 rounded-full border border-accent/15" />
          <div className="absolute inset-0 -m-6 rounded-full border border-accent/[0.07]" />
          <GraphSigil size={132} layout="orbit" shape="circle" />
          <span className="absolute bottom-2 right-2 h-3 w-3 rounded-full border-2 border-surface bg-success shadow-[0_0_10px_rgb(var(--success))]" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-bold text-heading">{greeting()} — TOBI is awake</h2>
            <span className="inline-flex items-center gap-1 rounded-full border border-success/35 bg-success/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-success">
              <span className="h-1.5 w-1.5 rounded-full bg-success" /> live
            </span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {error
              ? 'The second brain is not answering right now — the rest of the dashboard is unaffected.'
              : 'That circle is his second brain, drawn from the real graph. It redraws itself whenever the graph grows.'}
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            {[
              { label: 'Nodes', value: stat(data.nodes.length) },
              { label: 'Links', value: stat(data.edges.length) },
              { label: 'Groups', value: stat(groups) },
            ].map(item => (
              <div key={item.label} className="rounded-lg border border-border bg-bg px-3 py-1.5">
                <div className="text-[10px] uppercase tracking-wider text-muted">{item.label}</div>
                <div className="font-mono text-sm font-semibold text-heading">{item.value}</div>
              </div>
            ))}

            <Link to="/graph"
              className="flex items-center gap-1.5 self-stretch rounded-lg border border-accent/40 bg-accent/10 px-3 text-xs font-semibold text-accent transition-colors hover:bg-accent/20">
              <Share2 size={13} /> Open the graph <ArrowRight size={13} />
            </Link>
          </div>
        </div>

        {/* the same asset, three sizes — it thins itself out to stay readable as it shrinks */}
        <div className="hidden shrink-0 flex-col items-center gap-2 border-l border-border pl-5 lg:flex">
          <div className="flex items-end gap-3">
            <GraphSigil size={28} layout="orbit" shape="circle" showEdges={false} label="TOBI graph at 28 pixels" />
            <GraphSigil size={44} layout="orbit" shape="circle" label="TOBI graph at 44 pixels" />
            <GraphSigil size={72} layout="clusters" shape="rounded" label="TOBI graph clusters at 72 pixels" />
          </div>
          <div className="text-center text-[10px] leading-tight text-muted">
            one asset<br />any size
          </div>
        </div>
      </div>
    </div>
  )
}
