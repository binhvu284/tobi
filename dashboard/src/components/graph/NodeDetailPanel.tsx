import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, ExternalLink, Trash2, Pencil, Check, Unlink, Crosshair } from 'lucide-react'
import { getGraphNode, updateGraphNode, deleteGraphNode, deleteGraphEdge, type GraphNode, type GraphData } from '../../api.graph'
import { useToast } from '../../context/ToastProvider'

const DOMAIN_LABEL: Record<string, string> = {
  memory: 'Memory', task: 'Task', project: 'Project', notion: 'Notion',
  github: 'GitHub', gdrive: 'Drive', local: 'Local', manual: 'Note',
}

type Detail = GraphNode & { connections: GraphData }

export default function NodeDetailPanel({
  nodeId, onClose, onChanged, onFocusNode,
}: {
  nodeId: number | null
  onClose: () => void
  onChanged: () => void
  onFocusNode: (id: number) => void
}) {
  const { toast } = useToast()
  const [node, setNode] = useState<Detail | null>(null)
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({ title: '', summary: '', category: '' })

  useEffect(() => {
    if (nodeId == null) { setNode(null); return }
    setLoading(true); setEditing(false)
    getGraphNode(nodeId)
      .then(n => { setNode(n); setDraft({ title: n.title || '', summary: n.summary || '', category: n.category || '' }) })
      .catch(() => toast({ kind: 'error', title: 'Could not load node' }))
      .finally(() => setLoading(false))
  }, [nodeId, toast])

  const editable = node?.domain === 'manual'

  const save = async () => {
    if (!node) return
    try {
      const updated = await updateGraphNode(node.id, draft)
      setNode({ ...node, ...updated }); setEditing(false); onChanged()
      toast({ kind: 'success', title: 'Saved' })
    } catch (e) { toast({ kind: 'error', title: 'Save failed', detail: (e as Error).message }) }
  }

  const remove = async () => {
    if (!node) return
    try { await deleteGraphNode(node.id); onChanged(); onClose(); toast({ kind: 'success', title: 'Node deleted' }) }
    catch (e) { toast({ kind: 'error', title: 'Delete failed', detail: (e as Error).message }) }
  }

  const unlink = async (edgeId: number) => {
    try {
      await deleteGraphEdge(edgeId)
      if (node) setNode({ ...node, connections: { ...node.connections, edges: node.connections.edges.filter(e => e.id !== edgeId) } })
      onChanged()
    } catch (e) { toast({ kind: 'error', title: 'Unlink failed', detail: (e as Error).message }) }
  }

  const titleById = (id: number) =>
    node?.connections.nodes.find(n => n.id === id)?.title || `#${id}`

  return (
    <AnimatePresence>
      {nodeId != null && (
        <motion.aside
          initial={{ x: 360, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 360, opacity: 0 }}
          transition={{ type: 'spring', stiffness: 320, damping: 32 }}
          className="absolute right-0 top-0 z-20 flex h-full w-[340px] max-w-[88vw] flex-col border-l border-border bg-surface/95 backdrop-blur">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <span className="rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: node?.color || '#58a6ff', borderColor: (node?.color || '#58a6ff') + '55', background: (node?.color || '#58a6ff') + '14' }}>
              {DOMAIN_LABEL[node?.domain || ''] || node?.domain || 'Node'}
            </span>
            <button onClick={onClose} className="text-muted hover:text-text"><X size={16} /></button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {loading && <div className="text-sm text-muted">Loading…</div>}
            {node && !loading && (
              <>
                {editing ? (
                  <input value={draft.title} onChange={e => setDraft(d => ({ ...d, title: e.target.value }))}
                    className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-heading outline-none focus:border-accent/50" />
                ) : (
                  <h2 className="text-base font-bold leading-snug text-heading">{node.title}</h2>
                )}

                {node.category && !editing && (
                  <div className="text-xs text-muted">Category · <span className="text-text">{node.category}</span></div>
                )}
                {editing && (
                  <input value={draft.category} onChange={e => setDraft(d => ({ ...d, category: e.target.value }))}
                    placeholder="category"
                    className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-xs text-text outline-none focus:border-accent/50" />
                )}

                {editing ? (
                  <textarea value={draft.summary} onChange={e => setDraft(d => ({ ...d, summary: e.target.value }))}
                    rows={5}
                    className="w-full resize-none rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent/50" />
                ) : node.summary ? (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-text">{node.summary}</p>
                ) : null}

                {node.source_url && (
                  <a href={node.source_url} target="_blank" rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline">
                    <ExternalLink size={12} /> Open source
                  </a>
                )}

                <div>
                  <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
                    Connections · {node.connections.edges.length}
                  </div>
                  <ul className="space-y-1">
                    {node.connections.edges.map(e => {
                      const otherId = e.source === node.id ? e.target : e.source
                      return (
                        <li key={e.id} className="group flex items-center justify-between gap-2 rounded-md border border-border/60 bg-bg/40 px-2 py-1.5">
                          <button onClick={() => onFocusNode(otherId)}
                            className="flex min-w-0 items-center gap-1.5 text-left text-xs text-text hover:text-accent">
                            <Crosshair size={11} className="shrink-0 opacity-60" />
                            <span className="truncate">{titleById(otherId)}</span>
                            <span className="shrink-0 text-[9px] uppercase text-muted">{e.type}</span>
                          </button>
                          <button onClick={() => unlink(e.id)} title="Remove link"
                            className="text-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100">
                            <Unlink size={12} />
                          </button>
                        </li>
                      )
                    })}
                    {node.connections.edges.length === 0 && <li className="text-xs text-muted">No connections yet.</li>}
                  </ul>
                </div>
              </>
            )}
          </div>

          {node && !loading && (
            <div className="flex items-center gap-2 border-t border-border p-3">
              {editable && (editing ? (
                <button onClick={save} className="flex items-center gap-1.5 rounded-lg border border-success/40 bg-success/15 px-3 py-1.5 text-xs font-semibold text-success hover:bg-success/25">
                  <Check size={13} /> Save
                </button>
              ) : (
                <button onClick={() => setEditing(true)} className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-text hover:border-accent/50">
                  <Pencil size={13} /> Edit
                </button>
              ))}
              {editable && (
                <button onClick={remove} className="ml-auto flex items-center gap-1.5 rounded-lg border border-danger/40 px-3 py-1.5 text-xs text-danger hover:bg-danger/10">
                  <Trash2 size={13} /> Delete
                </button>
              )}
              {!editable && <span className="ml-auto text-[10px] text-muted">Mirrored · read-only</span>}
            </div>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  )
}
