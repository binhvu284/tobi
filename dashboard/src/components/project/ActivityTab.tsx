import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Bot, User, Activity as ActivityIcon, ChevronDown, ChevronUp } from 'lucide-react'
import { pmListActivity, type PMActivity } from '../../api.pm'
import { fmtAgo } from './shared'

/** Activity — who did what (owner vs TOBI), with expandable diffs. */
export default function ActivityTab({ projectId }: { projectId: number }) {
  const [items, setItems] = useState<PMActivity[]>([])
  const [filter, setFilter] = useState<'all' | 'user' | 'tobi'>('all')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    pmListActivity(projectId, filter === 'all' ? undefined : filter)
      .then(r => setItems(r.items)).catch(() => {})
  }, [projectId, filter])

  return (
    <div className="mx-auto max-w-3xl space-y-3 p-5">
      <div className="flex gap-2">
        {(['all', 'user', 'tobi'] as const).map(a => (
          <button key={a} onClick={() => setFilter(a)}
            className={`rounded-full border px-3 py-1 text-[11px] transition-colors ${filter === a ? 'border-accent/30 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
            {a === 'all' ? 'All' : a === 'user' ? 'Me' : 'TOBI'}
          </button>
        ))}
      </div>
      {items.length === 0
        ? <div className="py-8 text-center text-muted"><ActivityIcon size={32} className="mx-auto mb-2 text-muted/40" /><div className="text-sm">No activity yet</div></div>
        : items.map(a => (
          <div key={a.id} className="overflow-hidden rounded-lg border border-border bg-panel">
            <div className="flex cursor-pointer items-start gap-3 px-3 py-2.5 hover:bg-overlay/2"
              onClick={() => setExpandedId(expandedId === a.id ? null : a.id)}>
              <span className={`mt-0.5 rounded-full p-1.5 ${a.actor === 'tobi' ? 'bg-accent/15 text-accent' : 'bg-overlay/8 text-muted'}`}>
                {a.actor === 'tobi' ? <Bot size={11} /> : <User size={11} />}
              </span>
              <div className="min-w-0 flex-1">
                <span className="text-sm text-text">{a.summary}</span>
                <div className="mt-0.5 text-[11px] text-muted">{fmtAgo(a.created_at)}</div>
              </div>
              {a.diff && <span className="text-muted">{expandedId === a.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</span>}
            </div>
            <AnimatePresence>
              {expandedId === a.id && a.diff && (
                <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
                  className="overflow-hidden border-t border-border/40">
                  <pre className="p-3 font-mono text-[11px] text-muted">{JSON.stringify(a.diff, null, 2)}</pre>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))
      }
    </div>
  )
}
