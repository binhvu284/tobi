import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CheckCircle2, Circle, Clock, AlertTriangle, Target, HardDrive, Bot, User,
  Pencil, Save, X, Calendar, Timer, Activity as ActivityIcon, FileStack,
} from 'lucide-react'
import { type PMOverview, pmPatchProject, pmPostActivity } from '../../api.pm'
import type { TaskItem } from '../../api.tasks'
import { useToast } from '../../context/ToastProvider'
import { Bar, fmtAgo, fmtBytes, fmtDate, fmtMinutes, TASK_STATUS_COLORS, PRIORITY_COLORS } from './shared'

/** Overview (#12 D11–D15): asymmetric bento — big description, metric tiles,
 * scrollable active tasks, resources usage, goals summary, recent activity. */
export default function OverviewTab({ ov, onChanged, onOpenTask }: {
  ov: PMOverview
  onChanged: () => void
  onOpenTask: (t: TaskItem) => void
}) {
  const { project, metrics: m } = ov
  const navigate = useNavigate()

  const tiles = [
    { label: 'Tasks done', value: `${m.task_done}/${m.task_total}`, icon: CheckCircle2, tone: 'text-success' },
    { label: 'Progress', value: `${Math.round(m.progress_pct)}%`, icon: ActivityIcon, tone: 'text-accent' },
    { label: 'Active', value: String(m.task_active), icon: Circle, tone: 'text-accent' },
    { label: 'Overdue', value: String(m.task_overdue), icon: AlertTriangle, tone: m.task_overdue ? 'text-danger' : 'text-muted' },
    { label: 'Deadline', value: m.deadline_days == null ? '—' : m.deadline_days < 0 ? `${-m.deadline_days}d over` : `${m.deadline_days}d left`, icon: Calendar, tone: m.deadline_days != null && m.deadline_days < 0 ? 'text-danger' : 'text-muted' },
    { label: 'Goals', value: m.goals_count ? `${m.goals_completed}/${m.goals_count} · ${Math.round(m.goals_avg_pct)}%` : '—', icon: Target, tone: 'text-accent' },
    { label: 'Estimate', value: m.estimate_total_min ? `${fmtMinutes(m.estimate_done_min)}/${fmtMinutes(m.estimate_total_min)}` : '—', icon: Timer, tone: 'text-muted' },
    { label: 'Resources', value: `${m.resources_count} · ${fmtBytes(m.resources_bytes)}`, icon: HardDrive, tone: 'text-muted' },
  ]

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-5">
      {/* Row 1: big description + metric tile grid */}
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <DescriptionCard projectId={project.id} description={project.description} onChanged={onChanged} />
        </div>
        <div className="grid grid-cols-2 gap-2.5 self-start sm:grid-cols-4 lg:col-span-2 lg:grid-cols-2">
          {tiles.map(t => (
            <div key={t.label} className="rounded-xl border border-border bg-panel px-3 py-2.5">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted">
                <t.icon size={11} className={t.tone} /> {t.label}
              </div>
              <div className="mt-1 truncate text-base font-bold text-heading">{t.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Row 2: active tasks (scrollable) + right stack (resources, goals) */}
      <div className="grid gap-4 lg:grid-cols-5">
        <section className="rounded-xl border border-border bg-panel lg:col-span-3">
          <header className="flex items-center justify-between border-b border-border/60 px-4 py-2.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">Active tasks</span>
            <button onClick={() => navigate(`/projects/${project.id}/tasks`)} className="text-[11px] text-accent hover:underline">
              Open Tasks →
            </button>
          </header>
          <div className="max-h-72 overflow-y-auto">
            {ov.active_tasks.length === 0 ? (
              <div className="flex flex-col items-center gap-1.5 py-8 text-muted">
                <CheckCircle2 size={22} className="text-muted/40" />
                <span className="text-xs">Nothing unfinished — all clear.</span>
              </div>
            ) : ov.active_tasks.map(t => (
              <button key={t.id} onClick={() => onOpenTask(t)}
                className="flex w-full items-center gap-2.5 border-b border-border/40 px-4 py-2 text-left transition-colors last:border-0 hover:bg-overlay/3">
                <Circle size={13} className="shrink-0 text-muted" />
                <span className="min-w-0 flex-1 truncate text-sm text-text">{t.title}</span>
                <span className={`shrink-0 text-[11px] ${PRIORITY_COLORS[t.priority] ?? 'text-muted'}`}>{t.priority}</span>
                <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] ${TASK_STATUS_COLORS[t.status] ?? 'bg-muted/10 text-muted'}`}>
                  {t.status.replace('_', ' ')}
                </span>
                {t.due_at && (
                  <span className={`flex shrink-0 items-center gap-1 text-[11px] ${t.is_overdue ? 'text-danger' : 'text-muted'}`}>
                    <Clock size={10} />{fmtDate(t.due_at)}
                  </span>
                )}
              </button>
            ))}
          </div>
        </section>

        <div className="space-y-4 lg:col-span-2">
          {/* Resources usage */}
          <section className="rounded-xl border border-border bg-panel p-4">
            <header className="mb-2 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
                <FileStack size={12} /> Resources
              </span>
              <button onClick={() => navigate(`/projects/${project.id}/resources`)} className="text-[11px] text-accent hover:underline">
                Open →
              </button>
            </header>
            <div className="text-xl font-bold text-heading">{fmtBytes(m.resources_bytes)}</div>
            <div className="text-[11px] text-muted">{m.resources_count} item{m.resources_count === 1 ? '' : 's'} stored</div>
            {Object.keys(m.resources_by_type || {}).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {Object.entries(m.resources_by_type).map(([k, v]) => (
                  <span key={k} className="rounded bg-overlay/5 px-1.5 py-0.5 text-[10px] text-muted">{k} · {v}</span>
                ))}
              </div>
            )}
          </section>

          {/* Goals summary */}
          <section className="rounded-xl border border-border bg-panel p-4">
            <header className="mb-2 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
                <Target size={12} /> Goals
              </span>
              <button onClick={() => navigate(`/projects/${project.id}/goals`)} className="text-[11px] text-accent hover:underline">
                Open →
              </button>
            </header>
            {ov.goals.length === 0 ? (
              <div className="py-2 text-xs text-muted">No goals yet.</div>
            ) : ov.goals.slice(0, 4).map(g => (
              <div key={g.id} className="mb-2 last:mb-0">
                <div className="mb-1 flex justify-between text-[12px]">
                  <span className="truncate font-medium text-text">{g.title}</span>
                  <span className="ml-2 shrink-0 text-accent">{g.progress_pct}%</span>
                </div>
                <Bar pct={g.progress_pct} />
              </div>
            ))}
          </section>
        </div>
      </div>

      {/* Row 3: recent activity */}
      <section className="rounded-xl border border-border bg-panel p-4">
        <header className="mb-2 flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
            <ActivityIcon size={12} /> Recent activity
          </span>
          <button onClick={() => navigate(`/projects/${project.id}/activity`)} className="text-[11px] text-accent hover:underline">
            All activity →
          </button>
        </header>
        {ov.activity.length === 0 ? (
          <div className="py-2 text-xs text-muted">No activity yet.</div>
        ) : (
          <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
            {ov.activity.slice(0, 8).map(a => (
              <div key={a.id} className="flex items-start gap-2 text-[12px]">
                <span className={`mt-0.5 rounded-full p-1 ${a.actor === 'tobi' ? 'bg-accent/15 text-accent' : 'bg-overlay/8 text-muted'}`}>
                  {a.actor === 'tobi' ? <Bot size={10} /> : <User size={10} />}
                </span>
                <div className="min-w-0 flex-1">
                  <span className="text-text">{a.summary}</span>
                  <span className="ml-2 text-muted">{fmtAgo(a.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

/** Plain-text description both the owner and TOBI write (#12 D13/D14) — owner edits
 * inline here; TOBI writes through its act tool (edits show attributed in Activity). */
function DescriptionCard({ projectId, description, onChanged }: {
  projectId: number; description: string | null; onChanged: () => void
}) {
  const { toast } = useToast()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(description || '')
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (!editing) setDraft(description || '') }, [description, editing])

  async function save() {
    setSaving(true)
    try {
      await pmPatchProject(projectId, { description: draft })
      try { await pmPostActivity(projectId, { actor: 'user', action_type: 'project.description', summary: 'Description updated' }) } catch { /* non-fatal */ }
      setEditing(false); onChanged()
    } catch (e) {
      toast({ kind: 'error', title: 'Save failed', detail: (e as Error).message })
    } finally { setSaving(false) }
  }

  return (
    <section className="flex h-full flex-col rounded-xl border border-border bg-panel p-4">
      <header className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">Description</span>
        {editing ? (
          <div className="flex items-center gap-1.5">
            <button onClick={save} disabled={saving} className="flex items-center gap-1 rounded bg-accent/15 px-2 py-1 text-[11px] font-medium text-accent hover:bg-accent/25 disabled:opacity-50">
              <Save size={11} /> Save
            </button>
            <button onClick={() => setEditing(false)} className="rounded p-1 text-muted hover:text-text"><X size={13} /></button>
          </div>
        ) : (
          <button onClick={() => setEditing(true)} className="flex items-center gap-1 text-[11px] text-muted transition-colors hover:text-accent">
            <Pencil size={11} /> Edit
          </button>
        )}
      </header>
      {editing ? (
        <textarea autoFocus value={draft} onChange={e => setDraft(e.target.value)} rows={8}
          placeholder="What is this project about? Both you and TOBI can write here."
          className="min-h-[10rem] w-full flex-1 resize-none rounded-lg border border-border bg-surface px-3 py-2 text-sm leading-relaxed text-text outline-none focus:border-accent" />
      ) : description ? (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-text">{description}</p>
      ) : (
        <button onClick={() => setEditing(true)} className="flex flex-1 flex-col items-start justify-center gap-1 rounded-lg border border-dashed border-border/70 px-4 py-6 text-left text-muted transition-colors hover:border-accent/40 hover:text-text">
          <span className="text-sm">No description yet.</span>
          <span className="text-[11px]">Write one — or ask TOBI: “draft a description for this project”.</span>
        </button>
      )}
    </section>
  )
}
