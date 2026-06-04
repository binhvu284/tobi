import { useMemo, useState } from 'react'
import { X } from 'lucide-react'
import type { TaskAgent, TaskItem, TaskPriority, TaskStatus } from '../api'
import TaskCommandBox from './TaskCommandBox'
import OwnerInputChecklist from './OwnerInputChecklist'

type Props = {
  task: TaskItem | null
  onClose: () => void
  onPatch: (taskId: number, patch: { status?: TaskStatus; priority?: TaskPriority; agent?: TaskAgent; due_at?: string | null; confirmed?: boolean }) => Promise<void>
  onDelete: (taskId: number) => Promise<void>
  onRequestConfirm: (taskId: number, patch: { status?: TaskStatus; priority?: TaskPriority; agent?: TaskAgent }, title: string, detail: string) => void
  onAddNote: (taskId: number, note: string) => Promise<void>
  onSubmitChecklist: (taskId: number, items: TaskItem['checklist']) => Promise<void>
  onEvaluateChecklist: (taskId: number) => Promise<void>
  onSendCommand: (taskId: number, command: string) => Promise<void>
}

export default function TaskDetailPanel({
  task,
  onClose,
  onPatch,
  onDelete,
  onRequestConfirm,
  onAddNote,
  onSubmitChecklist,
  onEvaluateChecklist,
  onSendCommand,
}: Props) {
  const [note, setNote] = useState('')

  const dueInput = useMemo(() => {
    if (!task?.due_at) return ''
    const d = new Date(task.due_at)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
  }, [task?.due_at])

  const handleStatusChange = async (status: TaskStatus) => {
    if (!task) return
    if (status === 'done' || status === 'cancelled') {
      onRequestConfirm(task.id, { status }, 'High-risk transition', `Changing status to ${status} requires confirmation.`)
      return
    }
    await onPatch(task.id, { status })
  }

  const handlePriorityChange = async (priority: TaskPriority) => {
    if (!task) return
    if (priority === 'P0' && task.priority !== 'P0') {
      onRequestConfirm(task.id, { priority }, 'Escalate to P0', 'Raising priority to P0 requires confirmation.')
      return
    }
    await onPatch(task.id, { priority })
  }

  const handleAgentChange = async (agent: TaskAgent) => {
    if (!task) return
    if (agent !== task.agent) {
      onRequestConfirm(task.id, { agent }, 'Reassign agent', 'Changing task owner agent requires confirmation.')
      return
    }
    await onPatch(task.id, { agent })
  }

  if (!task) return null

  return (
    <aside className="w-[420px] flex-shrink-0 space-y-3 rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-heading">{task.title}</h3>
          <p className="mt-0.5 text-xs text-muted">{task.objective}</p>
        </div>
        <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        <select value={task.status} onChange={(e) => { void handleStatusChange(e.target.value as TaskStatus) }} className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text">
          <option value="planned">planned</option>
          <option value="in_progress">in_progress</option>
          <option value="paused">paused</option>
          <option value="blocked">blocked</option>
          <option value="needs_owner_input">needs_owner_input</option>
          <option value="done">done</option>
          <option value="cancelled">cancelled</option>
        </select>
        <select value={task.priority} onChange={(e) => { void handlePriorityChange(e.target.value as TaskPriority) }} className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text">
          <option value="P0">P0</option><option value="P1">P1</option><option value="P2">P2</option><option value="P3">P3</option>
        </select>
        <select value={task.agent} onChange={(e) => { void handleAgentChange(e.target.value as TaskAgent) }} className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text">
          <option value="tobi">tobi</option><option value="research">research</option><option value="coder">coder</option><option value="ceo">ceo</option>
        </select>
        <input
          type="datetime-local"
          defaultValue={dueInput}
          onBlur={(e) => onPatch(task.id, { due_at: e.target.value || null })}
          className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text"
        />
      </div>

      <div className="rounded border border-border bg-bg p-3">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">Success Criteria</p>
        <p className="text-xs text-text">{task.success_criteria || 'No criteria set.'}</p>
      </div>

      <TaskCommandBox onSend={(command) => onSendCommand(task.id, command)} />

      {task.status === 'needs_owner_input' && (
        <OwnerInputChecklist
          items={task.checklist}
          onSubmit={(items) => onSubmitChecklist(task.id, items)}
          onEvaluate={() => onEvaluateChecklist(task.id)}
        />
      )}

      <div className="rounded border border-border bg-bg p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Owner Note</p>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          placeholder="Add context or instruction"
          className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-text"
        />
        <div className="mt-2 flex justify-end">
          <button
            onClick={async () => {
              const value = note.trim()
              if (!value) return
              await onAddNote(task.id, value)
              setNote('')
            }}
            className="rounded border border-accent/40 bg-accent/10 px-3 py-1 text-xs text-accent"
          >
            Add note
          </button>
        </div>
      </div>

      <div className="rounded border border-border bg-bg p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Activity</p>
        <div className="max-h-48 space-y-1 overflow-y-auto text-xs">
          {(task.activity || []).length === 0 ? (
            <p className="text-muted">No activity yet.</p>
          ) : (
            task.activity?.map((a) => (
              <div key={a.id} className="rounded border border-border bg-surface px-2 py-1">
                <p className="text-text">{a.message}</p>
                <p className="text-[10px] text-muted">{a.author} · {new Date(a.created_at).toLocaleString('en-GB')}</p>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button onClick={() => onRequestConfirm(task.id, { status: 'cancelled' }, 'Cancel task', 'Cancelling this task requires confirmation.')} className="rounded border border-warning/40 bg-warning/10 px-3 py-1.5 text-xs text-warning">
          Cancel task
        </button>
        <button onClick={() => onDelete(task.id)} className="rounded border border-danger/40 bg-danger/10 px-3 py-1.5 text-xs text-danger">
          Delete
        </button>
      </div>
    </aside>
  )
}
