// 3-dot resource card menus (grid + list), extracted from ResourcesTab.tsx.
import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MoreVertical, Copy, Pencil, Trash2 } from 'lucide-react'
import { type PMResource } from '../../api'
import { useToast } from '../../context/ToastProvider'

export function CardMenu({ resource, onRename, onDelete }: {
  resource: PMResource; onRename: () => void; onDelete: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const { toast } = useToast()

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const copyLink = () => {
    navigator.clipboard?.writeText(resource.url || '').then(() => toast({ kind: 'success', title: 'Link copied' })).catch(() => {})
    setOpen(false)
  }

  return (
    <div className="absolute right-2 top-2 z-30" ref={ref}>
      <button onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        className="rounded-md bg-black/50 p-1 text-white/70 backdrop-blur-sm transition-colors hover:bg-black/70 hover:text-white">
        <MoreVertical size={14} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, scale: 0.95, y: -4 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full mt-1 w-40 overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-2xl backdrop-blur-xl">
            <button onClick={e => { e.stopPropagation(); copyLink() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-text hover:bg-bg/60">
              <Copy size={13} className="text-muted" /> Copy link
            </button>
            <button onClick={e => { e.stopPropagation(); setOpen(false); onRename() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-text hover:bg-bg/60">
              <Pencil size={13} className="text-muted" /> Rename
            </button>
            <button onClick={e => { e.stopPropagation(); setOpen(false); onDelete() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-danger hover:bg-danger/10">
              <Trash2 size={13} /> Delete
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function ListCardMenu({ resource, onRename, onDelete }: {
  resource: PMResource; onRename: () => void; onDelete: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const { toast } = useToast()

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const copyLink = () => {
    navigator.clipboard?.writeText(resource.url || '').then(() => toast({ kind: 'success', title: 'Link copied' })).catch(() => {})
    setOpen(false)
  }

  return (
    <div className="relative shrink-0" ref={ref}>
      <button onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        className="text-muted opacity-0 transition-opacity hover:text-text group-hover:opacity-100">
        <MoreVertical size={14} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, scale: 0.95, y: -4 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full z-50 mt-1 w-40 overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-2xl backdrop-blur-xl">
            <button onClick={e => { e.stopPropagation(); copyLink() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-text hover:bg-bg/60">
              <Copy size={13} className="text-muted" /> Copy link
            </button>
            <button onClick={e => { e.stopPropagation(); setOpen(false); onRename() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-text hover:bg-bg/60">
              <Pencil size={13} className="text-muted" /> Rename
            </button>
            <button onClick={e => { e.stopPropagation(); setOpen(false); onDelete() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-danger hover:bg-danger/10">
              <Trash2 size={13} /> Delete
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
