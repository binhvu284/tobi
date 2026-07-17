// Presentational chips extracted from pages/Chat.tsx.
import { Link } from 'react-router-dom'
import { Loader2, Check, X, Youtube, Wrench, Briefcase, FileText, Search, CheckCircle2 } from 'lucide-react'
import type { ReaderChip, ChatModeId, ContextChip, ChatArtifactEvent } from '../../api'

/** Subtle YouTube reader chips — 'detected' before Send, then reading/ready/unavailable. */
export function ReaderChips({ chips, draftIds }: { chips: ReaderChip[]; draftIds: string[] }) {
  const show: ReaderChip[] = chips.length
    ? chips
    : draftIds.map(id => ({ url: `https://youtu.be/${id}`, state: 'detected' }))
  if (!show.length) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-3 pt-2.5">
      {show.map((c, i) => {
        const reading = c.state === 'reading'
        const ok = c.state === 'transcript ready' || c.state === 'ready'
        const bad = c.state === 'unavailable'
        const tone = bad ? 'border-danger/40 text-danger' : ok ? 'border-success/40 text-success' : 'border-border text-muted'
        const label = reading ? 'reading…' : ok ? 'transcript ready' : bad ? 'no transcript' : 'detected'
        return (
          <span key={c.url + i} title={c.title || c.url}
            className={`inline-flex items-center gap-1.5 rounded-lg border bg-bg/50 py-1 pl-1.5 pr-2 text-[11px] ${tone}`}>
            {reading ? <Loader2 size={12} className="animate-spin" />
              : ok ? <Check size={12} />
              : bad ? <X size={12} />
              : <Youtube size={12} className="text-danger" />}
            <span className="font-medium">YouTube</span>
            <span className="opacity-70">· {label}</span>
          </span>
        )
      })}
    </div>
  )
}

/** #16: per-turn chips above the reply — mode, auto project context [D20], artifacts [D21]. */
export function TurnChips({ mode, context, artifacts, onOpenArtifact }: {
  mode?: ChatModeId
  context?: { projects?: ContextChip[]; resources?: { name?: string }[] }
  artifacts?: ChatArtifactEvent[]
  onOpenArtifact?: (id: number) => void
}) {
  const projects = context?.projects || []
  const resources = context?.resources || []
  const arts = artifacts || []
  if (mode !== 'agent' && !projects.length && !arts.length) return null
  return (
    <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
      {mode === 'agent' && (
        <span className="inline-flex items-center gap-1 rounded-full border border-purple/35 bg-purple/10 px-2 py-0.5 text-[10px] font-medium text-purple"><Wrench size={10} /> Agent</span>
      )}
      {projects.map(p => (
        <Link key={p.id} to={`/projects/${p.id}`} title="Auto-detected project context"
          className="inline-flex items-center gap-1 rounded-full border border-accent/35 bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent hover:bg-accent/20">
          <Briefcase size={10} /> {p.name}
        </Link>
      ))}
      {resources.length > 0 && (
        <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[10px] text-muted"><FileText size={10} /> {resources.length} resource{resources.length > 1 ? 's' : ''}</span>
      )}
      {projects.length > 0 && (
        <span className="text-[10px] text-muted/60">context auto</span>
      )}
      {arts.map(a => (
        <button key={a.id} title={`Open ${a.title}`} onClick={() => onOpenArtifact?.(a.id)}
          className="inline-flex items-center gap-1 rounded-full border border-success/35 bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success hover:bg-success/20">
          {a.kind === 'research_report' ? <Search size={10} /> : <CheckCircle2 size={10} />}
          {a.kind === 'research_report' ? 'Research report' : 'Task result'}
        </button>
      ))}
    </div>
  )
}
