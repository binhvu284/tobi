import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Project } from '../api.office'
import type { TaskCreatePayload, TaskPriority, TaskStatus, TaskAgent, OwnerInputChecklistItem } from '../api.tasks'

type Props = {
  open: boolean
  projects: Project[]
  onClose: () => void
  onCreate: (payload: TaskCreatePayload) => Promise<void>
}

const initialChecklist = (): OwnerInputChecklistItem[] => [
  {
    item_key: 'context',
    label: 'Owner context',
    input_type: 'text',
    required: true,
    placeholder: 'Provide context required for execution',
    value_text: '',
    status: 'pending',
  },
]

export default function TaskCreateModal({ open, projects, onClose, onCreate }: Props) {
  const [title, setTitle] = useState('')
  const [objective, setObjective] = useState('')
  const [successCriteria, setSuccessCriteria] = useState('')
  const [priority, setPriority] = useState<TaskPriority>('P2')
  const [status, setStatus] = useState<TaskStatus>('planned')
  const [agent, setAgent] = useState<TaskAgent>('tobi')
  const [projectId, setProjectId] = useState<number | undefined>()
  const [dueAt, setDueAt] = useState('')
  const [checklistEnabled, setChecklistEnabled] = useState(false)
  const [checklist, setChecklist] = useState<OwnerInputChecklistItem[]>(initialChecklist())
  const [loading, setLoading] = useState(false)

  const projectOptions = useMemo(() => projects.map((p) => ({ id: p.id, label: p.name })), [projects])

  const submit = async () => {
    if (!title.trim()) return
    setLoading(true)
    try {
      await onCreate({
        title: title.trim(),
        objective: objective.trim() || title.trim(),
        success_criteria: successCriteria.trim(),
        priority,
        status,
        agent,
        owner: 'owner',
        project_id: projectId,
        due_at: dueAt || undefined,
        checklist: checklistEnabled ? checklist : [],
      })
      setTitle('')
      setObjective('')
      setSuccessCriteria('')
      setPriority('P2')
      setStatus('planned')
      setAgent('tobi')
      setProjectId(undefined)
      setDueAt('')
      setChecklistEnabled(false)
      setChecklist(initialChecklist())
      onClose()
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/60"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.97 }}
            className="fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-surface p-5"
          >
            <h3 className="mb-3 text-sm font-semibold text-heading">Create Task</h3>

            <div className="grid gap-2 md:grid-cols-2">
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Task title" className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text md:col-span-2" />
              <textarea value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="Objective" rows={3} className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text" />
              <textarea value={successCriteria} onChange={(e) => setSuccessCriteria(e.target.value)} placeholder="Success criteria" rows={3} className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text" />

              <select value={priority} onChange={(e) => setPriority(e.target.value as TaskPriority)} className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text">
                <option value="P0">P0</option><option value="P1">P1</option><option value="P2">P2</option><option value="P3">P3</option>
              </select>
              <select value={status} onChange={(e) => setStatus(e.target.value as TaskStatus)} className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text">
                <option value="planned">planned</option>
                <option value="in_progress">in_progress</option>
                <option value="paused">paused</option>
                <option value="blocked">blocked</option>
                <option value="needs_owner_input">needs_owner_input</option>
                <option value="done">done</option>
                <option value="cancelled">cancelled</option>
              </select>

              <select value={agent} onChange={(e) => setAgent(e.target.value as TaskAgent)} className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text">
                <option value="tobi">tobi</option>
                <option value="research">research</option>
                <option value="coder">coder</option>
                <option value="ceo">ceo</option>
              </select>

              <select value={projectId ?? ''} onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : undefined)} className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text">
                <option value="">No project</option>
                {projectOptions.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>

              <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text md:col-span-2" />
            </div>

            <label className="mt-3 flex items-center gap-2 text-xs text-muted">
              <input type="checkbox" checked={checklistEnabled} onChange={(e) => setChecklistEnabled(e.target.checked)} />
              Add owner input checklist requirement
            </label>

            {checklistEnabled && (
              <div className="mt-2 space-y-2 rounded border border-border bg-bg p-3">
                {checklist.map((item, idx) => (
                  <div key={item.item_key} className="grid gap-2 md:grid-cols-3">
                    <input
                      value={item.label}
                      onChange={(e) => {
                        const next = [...checklist]
                        next[idx] = { ...item, label: e.target.value }
                        setChecklist(next)
                      }}
                      placeholder="Label"
                      className="rounded border border-border bg-surface px-2 py-1 text-xs text-text"
                    />
                    <select
                      value={item.input_type}
                      onChange={(e) => {
                        const next = [...checklist]
                        next[idx] = { ...item, input_type: e.target.value }
                        setChecklist(next)
                      }}
                      className="rounded border border-border bg-surface px-2 py-1 text-xs text-text"
                    >
                      <option value="text">text</option>
                      <option value="file">file</option>
                    </select>
                    <input
                      value={item.placeholder || ''}
                      onChange={(e) => {
                        const next = [...checklist]
                        next[idx] = { ...item, placeholder: e.target.value }
                        setChecklist(next)
                      }}
                      placeholder="Placeholder"
                      className="rounded border border-border bg-surface px-2 py-1 text-xs text-text"
                    />
                  </div>
                ))}
              </div>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <button onClick={onClose} className="rounded border border-border px-3 py-1.5 text-xs text-muted">Cancel</button>
              <button onClick={submit} className="rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent">
                {loading ? 'Creating...' : 'Create task'}
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
