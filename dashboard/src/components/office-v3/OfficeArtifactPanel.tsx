import { useState } from 'react'
import { FileOutput, FileText, Plus, Save, ScrollText, Trash2 } from 'lucide-react'
import type { OfficeArtifact, OfficeArtifactKind } from '../../api.office'

const kindIcon = (kind: OfficeArtifactKind) => kind === 'report' ? ScrollText : kind === 'plan' ? FileOutput : FileText

export default function OfficeArtifactPanel({ artifacts, selected, onSelect, onPropose }:
  { artifacts: OfficeArtifact[]; selected: OfficeArtifact | null; onSelect: (artifact: OfficeArtifact) => void; onPropose: (action: string, args: Record<string, unknown>) => void }) {
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<OfficeArtifactKind>('report')
  const [content, setContent] = useState('')

  const proposeCreate = () => {
    if (!title.trim() || !content.trim()) return
    onPropose('office_create_artifact', { title: title.trim(), kind, content: content.trim(), source_type: 'manual' })
    setCreating(false); setTitle(''); setContent('')
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div><div className="text-[10px] font-semibold uppercase text-muted">Local outputs</div><div className="text-sm font-semibold text-heading">Office artifacts</div></div>
        <button onClick={() => setCreating(v => !v)} title="New artifact" className="flex h-8 w-8 items-center justify-center border border-border text-muted hover:border-accent hover:text-accent"><Plus size={15} /></button>
      </div>
      {creating && (
        <div className="space-y-2 border-b border-border bg-overlay/5 p-3">
          <div className="flex gap-2">
            <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Artifact title" className="min-w-0 flex-1 border border-border bg-bg px-2.5 py-2 text-xs text-text outline-none focus:border-accent" />
            <select value={kind} onChange={e => setKind(e.target.value as OfficeArtifactKind)} className="border border-border bg-bg px-2 text-xs text-text outline-none">
              {['report','plan','summary','next_actions','mission_note'].map(k => <option key={k} value={k}>{k.replace('_',' ')}</option>)}
            </select>
          </div>
          <textarea value={content} onChange={e => setContent(e.target.value)} rows={7} placeholder="Sensitive local content" className="w-full resize-none border border-border bg-bg px-2.5 py-2 text-xs leading-relaxed text-text outline-none focus:border-accent" />
          <button onClick={proposeCreate} disabled={!title.trim() || !content.trim()} className="flex h-8 w-full items-center justify-center gap-1.5 bg-accent text-xs font-semibold text-bg disabled:opacity-40"><Save size={12} /> Review and save</button>
        </div>
      )}
      <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[180px_minmax(0,1fr)]">
        <div className="min-h-0 overflow-y-auto border-r border-border">
          {artifacts.length === 0 && <div className="p-5 text-center text-xs text-muted">Mission reports and plans will appear here.</div>}
          {artifacts.map(artifact => {
            const Icon = kindIcon(artifact.kind)
            return (
              <button key={artifact.id} onClick={() => onSelect(artifact)} className={`w-full border-b border-border px-3 py-3 text-left ${selected?.id === artifact.id ? 'bg-accent/8' : 'hover:bg-overlay/5'}`}>
                <span className="flex items-center gap-2"><Icon size={13} className="text-accent" /><span className="truncate text-[11px] font-semibold text-heading">{artifact.title}</span></span>
                <span className="mt-1 block text-[9px] uppercase text-muted">{artifact.kind.replace('_',' ')}</span>
              </button>
            )
          })}
        </div>
        <div className="min-h-0 overflow-y-auto p-4">
          {!selected ? (
            <div className="flex h-full min-h-48 flex-col items-center justify-center text-center text-muted"><FileOutput size={22} /><p className="mt-2 max-w-56 text-xs">Select an artifact to inspect its latest local version.</p></div>
          ) : (
            <>
              <div className="flex items-start justify-between gap-3">
                <div><div className="text-[9px] uppercase text-warning">Sensitive · local only</div><h3 className="mt-1 text-base font-semibold text-heading">{selected.title}</h3></div>
                <button onClick={() => onPropose('office_delete_artifact', { artifact_id: selected.id })} title="Delete artifact" className="flex h-8 w-8 items-center justify-center border border-danger/35 text-danger hover:bg-danger/10"><Trash2 size={13} /></button>
              </div>
              <div className="mt-4 whitespace-pre-wrap text-[12px] leading-6 text-text/85">{selected.content || selected.preview}</div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
