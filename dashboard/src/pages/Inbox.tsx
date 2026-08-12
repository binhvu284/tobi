import { useEffect, useState } from 'react'
import { softFail } from '../lib/report'
import { motion } from 'framer-motion'
import { Inbox as InboxIcon, CheckCircle2, Bell, ListTodo, Trash2 } from 'lucide-react'
import { getStatus } from '../api.core'
import type { Todo } from '../api.office'
import { markDone } from '../api.tasks'
import { useToast } from '../context/ToastProvider'

const PRIORITY_META: Record<number, { label: string; cls: string }> = {
  0: { label: 'P0', cls: 'bg-danger/20 text-danger' },
  1: { label: 'P1', cls: 'bg-warning/20 text-warning' },
  2: { label: 'P2', cls: 'bg-accent/15 text-accent' },
  3: { label: 'P3', cls: 'bg-muted/20 text-muted' },
}

export default function Inbox() {
  const [todos, setTodos] = useState<Todo[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<number | null>(null)
  const { notes, clear } = useToast()

  const load = () => {
    setLoading(true)
    getStatus()
      .then((s: { human_todos?: Todo[] }) => setTodos(s.human_todos || []))
      .catch(softFail('your inbox'))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  async function done(id: number) {
    setBusy(id)
    try {
      await markDone(id)
      setTodos(prev => prev.filter(t => t.id !== id))
    } finally {
      setBusy(null)
    }
  }

  const total = todos.length + notes.length

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 md:p-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent">
          <InboxIcon size={20} />
        </span>
        <div>
          <h1 className="text-xl font-bold text-heading">Inbox</h1>
          <p className="text-xs text-muted">
            {total === 0 ? 'Nothing needs you right now.' : `${total} item${total === 1 ? '' : 's'} waiting`}
          </p>
        </div>
      </div>

      {/* Owner Todos */}
      <section className="overflow-hidden rounded-xl border border-border bg-surface">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-heading">
            <ListTodo size={15} className="text-accent" /> Owner Todos
          </div>
          <span className="rounded-full bg-bg px-2 py-0.5 text-[11px] text-muted">{todos.length}</span>
        </div>
        <div className="divide-y divide-border/60">
          {loading ? (
            <div className="px-5 py-8 text-center text-sm text-muted">Loading…</div>
          ) : todos.length === 0 ? (
            <div className="px-5 py-8 text-center text-sm text-muted">
              <CheckCircle2 size={16} className="mr-1 inline text-success" /> All clear!
            </div>
          ) : (
            todos.map(t => {
              const p = PRIORITY_META[t.priority] ?? PRIORITY_META[3]
              return (
                <motion.div key={t.id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-3 px-5 py-3">
                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${p.cls}`}>{p.label}</span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-text">{t.title}</div>
                    {t.project_name && <div className="truncate text-[11px] text-muted">{t.project_name}</div>}
                  </div>
                  <button onClick={() => done(t.id)} disabled={busy === t.id}
                    className="flex shrink-0 items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted transition-colors hover:border-success/40 hover:text-success disabled:opacity-50">
                    <CheckCircle2 size={13} /> {busy === t.id ? '…' : 'Done'}
                  </button>
                </motion.div>
              )
            })
          )}
        </div>
      </section>

      {/* Notifications */}
      <section className="overflow-hidden rounded-xl border border-border bg-surface">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-heading">
            <Bell size={15} className="text-accent" /> Notifications
          </div>
          {notes.length > 0 && (
            <button onClick={clear} className="flex items-center gap-1 text-[11px] text-muted hover:text-text">
              <Trash2 size={12} /> Clear
            </button>
          )}
        </div>
        <div className="divide-y divide-border/60">
          {notes.length === 0 ? (
            <div className="px-5 py-8 text-center text-sm text-muted">No notifications</div>
          ) : (
            notes.map(n => (
              <div key={n.id} className="px-5 py-3">
                <div className={`text-sm font-medium ${n.kind === 'error' ? 'text-danger' : n.kind === 'success' ? 'text-success' : 'text-text'}`}>
                  {n.title}
                </div>
                {n.detail && <div className="mt-0.5 text-[12px] text-muted">{n.detail}</div>}
                <div className="mt-1 text-[10px] text-muted">{new Date(n.ts).toLocaleString('en-GB')}</div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  )
}
