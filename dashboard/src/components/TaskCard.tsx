import { AlertCircle, CalendarClock, PauseCircle, UserCircle2 } from 'lucide-react'
import type { TaskItem } from '../api.tasks'

type Props = {
  task: TaskItem
  onOpen: () => void
  onMove: (taskId: number, to: TaskItem['status']) => void
  onDragStart: (taskId: number) => void
  onDragEnd: () => void
}

const priorityCls: Record<string, string> = {
  P0: 'bg-danger/20 text-danger border-danger/40',
  P1: 'bg-warning/20 text-warning border-warning/40',
  P2: 'bg-accent/20 text-accent border-accent/40',
  P3: 'bg-muted/20 text-muted border-border',
}

const statusCls: Record<TaskItem['status'], string> = {
  planned: 'bg-accent/20 text-accent border-accent/40',
  in_progress: 'bg-success/20 text-success border-success/40',
  paused: 'bg-warning/20 text-warning border-warning/40',
  blocked: 'bg-danger/20 text-danger border-danger/40',
  needs_owner_input: 'bg-purple/20 text-purple border-purple/40',
  done: 'bg-success/25 text-success border-success/50',
  cancelled: 'bg-muted/20 text-muted border-border',
}

const quickNext: Record<TaskItem['status'], TaskItem['status'] | null> = {
  planned: 'in_progress',
  in_progress: 'needs_owner_input',
  paused: 'in_progress',
  blocked: 'in_progress',
  needs_owner_input: 'in_progress',
  done: null,
  cancelled: null,
}

export default function TaskCard({ task, onOpen, onMove, onDragStart, onDragEnd }: Props) {
  const next = quickNext[task.status]
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onOpen()
      }}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', String(task.id))
        onDragStart(task.id)
      }}
      onDragEnd={onDragEnd}
      className="w-full rounded-lg border border-border bg-surface p-3 text-left transition-colors hover:border-overlay/20"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-heading">{task.title}</p>
          <p className="mt-0.5 line-clamp-2 text-xs text-muted">{task.objective}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusCls[task.status]}`}>
            {task.status.replace(/_/g, ' ')}
          </span>
          <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${priorityCls[task.priority] || priorityCls.P2}`}>
            {task.priority}
          </span>
        </div>
      </div>

      <div className="mb-2 flex flex-wrap gap-1.5 text-[11px]">
        <span className="rounded bg-bg px-1.5 py-0.5 text-muted">{task.agent}</span>
        <span className="rounded bg-bg px-1.5 py-0.5 text-muted">{task.owner}</span>
        {task.project_name && <span className="rounded bg-bg px-1.5 py-0.5 text-muted">{task.project_name}</span>}
      </div>

      <div className="flex items-center justify-between text-[11px] text-muted">
        <div className="flex items-center gap-2">
          {task.due_at ? (
            <span className={`inline-flex items-center gap-1 ${task.is_overdue ? 'text-danger' : ''}`}>
              <CalendarClock size={12} /> {new Date(task.due_at).toLocaleDateString('en-GB')}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1"><UserCircle2 size={12} /> no due date</span>
          )}
          {task.status === 'paused' && <PauseCircle size={12} className="text-warning" />}
          {task.status === 'blocked' && <AlertCircle size={12} className="text-danger" />}
        </div>

        {next && (
          <span
            role="button"
            onClick={(e) => {
              e.stopPropagation()
              onMove(task.id, next)
            }}
            className="rounded border border-border px-1.5 py-0.5 hover:border-overlay/20"
          >
            Move to {next}
          </span>
        )}
      </div>
    </div>
  )
}
