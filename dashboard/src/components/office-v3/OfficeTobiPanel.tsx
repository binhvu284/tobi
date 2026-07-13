import { FormEvent, useMemo, useState } from 'react'
import { Bot, Check, Loader2, Send, ShieldAlert, Sparkles, X } from 'lucide-react'
import { askOfficeTobi, confirmConductorAction, type PendingAction } from '../../api'
import type { OfficeSelection } from './types'

type Line = { role: 'user' | 'assistant'; text: string }

export default function OfficeTobiPanel({ selection, pending: externalPending, onPending, onResolved }:
  { selection: OfficeSelection; pending?: PendingAction | null; onPending: (pending: PendingAction | null) => void; onResolved: (result?: unknown) => void }) {
  const [draft, setDraft] = useState('')
  const [lines, setLines] = useState<Line[]>([{ role: 'assistant', text: 'Office channel online. Select an agent, mission, or artifact and tell me the outcome you need.' }])
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const pending = externalPending || null
  const context = useMemo(() => {
    if (!selection) return {}
    if (selection.type === 'agent') return { agent_id: selection.item.id }
    if (selection.type === 'mission') return { mission_id: selection.item.id }
    return { artifact_id: selection.item.id }
  }, [selection])
  const label = !selection ? 'Office overview'
    : selection.type === 'agent' ? `agent: ${selection.item.name}`
      : `${selection.type}: ${selection.item.title}`
  const suggestions = selection?.type === 'mission'
    ? ['Summarize this mission', 'Create a report from this mission', 'Turn the result into next actions']
    : selection?.type === 'agent'
      ? ['What is this agent doing?', 'Review this agent performance', 'Assign follow-up work']
      : selection?.type === 'artifact'
        ? ['Summarize this artifact', 'Turn this into next actions', 'Create tasks from this artifact']
        : ['What needs attention?', 'Plan a new mission', 'Summarize Office status']

  const send = async (text = draft) => {
    const message = text.trim()
    if (!message || busy) return
    setDraft(''); setBusy(true); setLines(prev => [...prev, { role: 'user', text: message }])
    try {
      const result = await askOfficeTobi(message, context)
      setLines(prev => [...prev, { role: 'assistant', text: result.reply || 'I completed the Office check.' }])
      if (result.pending_action) onPending(result.pending_action)
    } catch (error) {
      setLines(prev => [...prev, { role: 'assistant', text: `Office request failed: ${(error as Error).message}` }])
    } finally { setBusy(false) }
  }
  const submit = (event: FormEvent) => { event.preventDefault(); send() }
  const decide = async (decision: 'approve' | 'reject') => {
    if (!pending || confirming) return
    setConfirming(true)
    try {
      const result = await confirmConductorAction(pending.id, decision)
      setLines(prev => [...prev, { role: 'assistant', text: decision === 'approve'
        ? (result.ok ? `Approved and completed: ${pending.summary}` : `The action failed: ${result.error || 'unknown error'}`)
        : `Cancelled: ${pending.summary}` }])
      onPending(null); onResolved(result.result)
    } finally { setConfirming(false) }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 text-[10px] font-semibold uppercase text-accent"><Bot size={13} /> Office TOBI</div>
        <div className="mt-1 truncate text-xs text-muted">Context: {label}</div>
      </div>
      <div className="flex gap-1.5 overflow-x-auto border-b border-border px-3 py-2">
        {suggestions.map(item => <button key={item} onClick={() => send(item)} className="shrink-0 border border-border px-2 py-1 text-[10px] text-muted hover:border-accent hover:text-accent">{item}</button>)}
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {lines.map((line, index) => (
          <div key={index} className={`text-[12px] leading-relaxed ${line.role === 'user' ? 'ml-6 border-l-2 border-accent pl-2 text-text' : 'text-text/85'}`}>
            {line.role === 'assistant' && <Sparkles size={11} className="mr-1.5 inline text-accent" />}{line.text}
          </div>
        ))}
        {busy && <div className="flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> Working with selected context</div>}
        {pending && (
          <div className="border border-warning/45 bg-warning/5 p-3">
            <div className="flex items-center gap-2 text-[11px] font-semibold text-warning"><ShieldAlert size={14} /> Confirmation required</div>
            <p className="mt-1.5 text-[11px] leading-relaxed text-text">{pending.summary}</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button onClick={() => decide('reject')} disabled={confirming} className="flex h-8 items-center justify-center gap-1 border border-border text-[11px] text-muted hover:text-text"><X size={12} /> Cancel</button>
              <button onClick={() => decide('approve')} disabled={confirming} className="flex h-8 items-center justify-center gap-1 bg-warning text-[11px] font-semibold text-bg"><Check size={12} /> Confirm</button>
            </div>
          </div>
        )}
      </div>
      <form onSubmit={submit} className="flex gap-2 border-t border-border p-3">
        <input value={draft} onChange={e => setDraft(e.target.value)} placeholder="Command TOBI with selected context" className="min-w-0 flex-1 border border-border bg-bg px-3 text-xs text-text outline-none focus:border-accent" />
        <button disabled={!draft.trim() || busy} title="Send" className="flex h-9 w-9 items-center justify-center bg-accent text-bg disabled:opacity-40"><Send size={14} /></button>
      </form>
    </div>
  )
}
