import type { TaskAgent, TaskPriority, TaskStatus } from '../api'

type Props = {
  q: string
  onQ: (value: string) => void
  status: TaskStatus | 'all'
  onStatus: (value: TaskStatus | 'all') => void
  priority: TaskPriority | 'all'
  onPriority: (value: TaskPriority | 'all') => void
  agent: TaskAgent | 'all'
  onAgent: (value: TaskAgent | 'all') => void
  owner: string | 'all'
  onOwner: (value: string | 'all') => void
  projectId: string | 'all'
  onProjectId: (value: string | 'all') => void
  projectOptions: Array<{ id: number; name: string }>
  overdueOnly: boolean
  onOverdueOnly: (value: boolean) => void
}

export default function TaskFilters({
  q,
  onQ,
  status,
  onStatus,
  priority,
  onPriority,
  agent,
  onAgent,
  owner,
  onOwner,
  projectId,
  onProjectId,
  projectOptions,
  overdueOnly,
  onOverdueOnly,
}: Props) {
  return (
    <div className="grid gap-2 rounded-lg border border-border bg-surface p-3 lg:grid-cols-8">
      <input
        value={q}
        onChange={(e) => onQ(e.target.value)}
        placeholder="Search tasks..."
        className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text outline-none focus:border-accent lg:col-span-2"
      />

      <select
        value={status}
        onChange={(e) => onStatus(e.target.value as TaskStatus | 'all')}
        className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text"
      >
        <option value="all">All status</option>
        <option value="planned">Planned</option>
        <option value="in_progress">In progress</option>
        <option value="paused">Paused</option>
        <option value="blocked">Blocked</option>
        <option value="needs_owner_input">Needs owner input</option>
        <option value="done">Done</option>
        <option value="cancelled">Cancelled</option>
      </select>

      <select
        value={priority}
        onChange={(e) => onPriority(e.target.value as TaskPriority | 'all')}
        className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text"
      >
        <option value="all">All priority</option>
        <option value="P0">P0</option>
        <option value="P1">P1</option>
        <option value="P2">P2</option>
        <option value="P3">P3</option>
      </select>

      <select
        value={agent}
        onChange={(e) => onAgent(e.target.value as TaskAgent | 'all')}
        className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text"
      >
        <option value="all">All agents</option>
        <option value="tobi">tobi</option>
        <option value="research">research</option>
        <option value="coder">coder</option>
        <option value="ceo">ceo</option>
      </select>

      <select
        value={owner}
        onChange={(e) => onOwner(e.target.value as string | 'all')}
        className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text"
      >
        <option value="all">All owners</option>
        <option value="owner">owner</option>
      </select>

      <select
        value={projectId}
        onChange={(e) => onProjectId(e.target.value as string | 'all')}
        className="rounded border border-border bg-bg px-2 py-1.5 text-xs text-text"
      >
        <option value="all">All projects</option>
        {projectOptions.map((p) => (
          <option key={p.id} value={String(p.id)}>{p.name}</option>
        ))}
      </select>

      <label className="flex items-center gap-2 rounded border border-border bg-bg px-2 py-1.5 text-xs text-text">
        <input type="checkbox" checked={overdueOnly} onChange={(e) => onOverdueOnly(e.target.checked)} />
        Overdue only
      </label>
    </div>
  )
}
