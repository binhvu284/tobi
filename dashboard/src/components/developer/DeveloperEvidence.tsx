import { useEffect, useMemo, useState } from 'react'
import { Braces, FileDiff, FileText, Loader2, TestTube2 } from 'lucide-react'
import {
  getDeveloperArtifact,
  getDeveloperArtifacts,
  getDeveloperChanges,
  getDeveloperQueuePlan,
  getDeveloperScorecard,
  type DeveloperArtifact,
  type DeveloperChanges,
  type DeveloperQueuePlan,
  type DeveloperScorecard,
  type DeveloperWorkflow,
} from '../../api.developer'
import MarkdownView from '../chat/MarkdownView'

type EvidenceView = 'plan' | 'changes' | 'checks' | `artifact:${number}`

function initialView(): EvidenceView {
  const selected = new URLSearchParams(window.location.search).get('artifact')
  if (selected === 'changes' || selected === 'checks' || selected === 'plan') return selected
  const id = Number(selected)
  return Number.isFinite(id) && id > 0 ? `artifact:${id}` : 'plan'
}

export default function DeveloperEvidence({ workflow }: { workflow: DeveloperWorkflow }) {
  const [view, setView] = useState<EvidenceView>(initialView)
  const [plan, setPlan] = useState<DeveloperQueuePlan | null>(null)
  const [changes, setChanges] = useState<DeveloperChanges | null>(null)
  const [scorecard, setScorecard] = useState<DeveloperScorecard | null>(null)
  const [artifacts, setArtifacts] = useState<DeveloperArtifact[]>([])
  const [artifactContent, setArtifactContent] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    Promise.all([
      getDeveloperQueuePlan(workflow.queue_id, controller.signal).catch(() => null),
      getDeveloperChanges(workflow.id, controller.signal).catch(() => null),
      getDeveloperScorecard(workflow.id).catch(() => null),
      getDeveloperArtifacts(workflow.id, controller.signal).catch(() => ({ artifacts: [] })),
    ]).then(([nextPlan, nextChanges, nextScorecard, nextArtifacts]) => {
      if (controller.signal.aborted) return
      setPlan(nextPlan); setChanges(nextChanges); setScorecard(nextScorecard)
      setArtifacts(nextArtifacts.artifacts); setLoading(false)
    })
    return () => controller.abort()
  }, [workflow.id, workflow.queue_id])

  useEffect(() => {
    if (!view.startsWith('artifact:')) { setArtifactContent(''); return }
    const artifactId = Number(view.split(':')[1])
    const controller = new AbortController()
    setArtifactContent('')
    getDeveloperArtifact(workflow.id, artifactId, controller.signal)
      .then(result => { if (!controller.signal.aborted) setArtifactContent(result.content) })
      .catch(() => { if (!controller.signal.aborted) setArtifactContent('This retained artifact is unavailable.') })
    return () => controller.abort()
  }, [view, workflow.id])

  const content = useMemo(() => {
    if (view === 'plan') return plan?.markdown || 'The approved plan is not available.'
    if (view === 'changes') return JSON.stringify(changes || { files: [], stat: 'No changes recorded yet.' }, null, 2)
    if (view === 'checks') return JSON.stringify(scorecard || { checks: [], outcome: 'No scorecard recorded yet.' }, null, 2)
    return artifactContent || 'Loading retained evidence...'
  }, [artifactContent, changes, plan, scorecard, view])

  const options: Array<{ id: EvidenceView; label: string; icon: typeof FileText }> = [
    { id: 'plan', label: 'Plan', icon: FileText },
    { id: 'changes', label: 'Changes', icon: FileDiff },
    { id: 'checks', label: 'Checks', icon: TestTube2 },
    ...artifacts.map(item => ({
      id: `artifact:${item.id}` as EvidenceView,
      label: item.evidence_type.replace(/_/g, ' '),
      icon: Braces,
    })),
  ]

  return (
    <section className="overflow-hidden rounded-md border border-border bg-surface/30" aria-label="Developer evidence">
      <header className="flex min-h-12 flex-col gap-2 border-b border-border px-4 py-3 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-semibold uppercase text-accent">Linked Chat delivery</div>
          <h2 className="truncate text-sm font-semibold text-text">Evidence for run #{workflow.id}</h2>
        </div>
        <div className="flex max-w-full gap-1 overflow-x-auto" role="tablist" aria-label="Evidence views">
          {options.map(option => {
            const Icon = option.icon
            return <button key={option.id} type="button" role="tab" aria-selected={view === option.id}
              onClick={() => setView(option.id)} title={`Open ${option.label}`}
              className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded px-2.5 text-[11px] ${view === option.id ? 'bg-accent text-background' : 'text-muted hover:bg-overlay/5 hover:text-text'}`}>
              <Icon size={12} /><span className="capitalize">{option.label}</span>
            </button>
          })}
        </div>
      </header>
      <div className="max-h-[560px] overflow-auto p-4">
        {loading ? <div className="flex min-h-32 items-center justify-center gap-2 text-xs text-muted"><Loader2 size={14} className="animate-spin" /> Loading evidence</div>
          : view === 'plan' ? <MarkdownView content={content} />
          : <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-text">{content}</pre>}
      </div>
    </section>
  )
}
