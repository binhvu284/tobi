import type { TaskItem, TaskStatus } from '../api.tasks'
import TaskCard from './TaskCard'

type Props = {
  title: string
  status: TaskStatus
  tasks: TaskItem[]
  onOpen: (task: TaskItem) => void
  onMove: (taskId: number, to: TaskStatus) => void
  onDragStart: (taskId: number) => void
  onDragEnd: () => void
  onDragOverStatus: (status: TaskStatus | null) => void
  onDropToStatus: (status: TaskStatus) => void
  isDropTarget: boolean
}

export default function KanbanColumn({ title, status, tasks, onOpen, onMove, onDragStart, onDragEnd, onDragOverStatus, onDropToStatus, isDropTarget }: Props) {
  return (
    <section
      onDragOver={(e) => {
        e.preventDefault()
        onDragOverStatus(status)
      }}
      onDragLeave={() => onDragOverStatus(null)}
      onDrop={() => {
        onDropToStatus(status)
        onDragOverStatus(null)
      }}
      className={`min-w-[280px] flex-1 rounded-lg border bg-bg/60 p-3 transition-colors ${
        isDropTarget ? 'border-accent/60 bg-accent/5' : 'border-border'
      }`}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">{title}</h3>
        <span className="rounded bg-surface px-2 py-0.5 text-xs text-text">{tasks.length}</span>
      </div>

      <div className="space-y-2">
        {tasks.map((task) => (
          <TaskCard
            key={task.id}
            task={task}
            onOpen={() => onOpen(task)}
            onMove={onMove}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
          />
        ))}
        {tasks.length === 0 && (
          <div className="rounded border border-dashed border-border p-3 text-center text-xs text-muted">
            No tasks in {status}
          </div>
        )}
      </div>
    </section>
  )
}
