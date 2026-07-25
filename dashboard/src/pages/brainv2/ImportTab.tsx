// Extracted from BrainV2.tsx (pre-#21 refactor) — verbatim move.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Brain as BrainIcon, Lock, Unlock, RefreshCw, Upload, Sparkles, ArrowLeft,
  ThumbsUp, ThumbsDown, XCircle, Trash2, Archive, CheckCircle2, ChevronDown,
  ChevronRight, Loader2, ShieldAlert, Search, Database, GitMerge, Eye, Play,
  X, Filter, CheckSquare, Square, Plus, CalendarClock, TrendingUp, ArrowDownAZ, Eraser, Pencil,
} from 'lucide-react'
import {
  type V2Memory, type V2Stats, type V2JobStatus, type V2Candidate,
  type V2MigrationStatus, type V2MigrationItem, type V2RecallItem,
  type V2Influence, type V2CleanupProposal,
  v2Stats, v2Profile, v2Memories, v2SetStatus, v2EditMemory, v2Feedback, v2Influence,
  v2Purge, v2Recall, v2Remember, v2ImportCreate, v2ImportCandidates, v2ImportCommand, v2ImportStatus,
  v2ImportDecide, v2MigrationCreate, v2MigrationItems, v2MigrationCommand,
  v2MigrationDecide, v2CleanupPreview, v2CleanupApply,
} from '../../api.brainV2'
import { useToast } from '../../context/ToastProvider'
import { Badge, errMsg } from './parts'


// ── import wizard tab ─────────────────────────────────────────────────────────
export function ImportTab() {
  const { toast } = useToast()
  const [filename, setFilename] = useState('notes.md')
  const [content, setContent] = useState('')
  const [job, setJob] = useState<V2JobStatus | null>(null)
  const [cands, setCands] = useState<V2Candidate[]>([])
  const [busy, setBusy] = useState(false)
  const [hideTrash, setHideTrash] = useState(true)   // auto-filter rejected/trash by default
  const [dragOver, setDragOver] = useState(false)

  const refresh = useCallback(async (id: number) => {
    setCands(await v2ImportCandidates(id))
  }, [])

  // Read a .md/.txt/.json file (from the picker or a drag-drop) into the import box.
  const loadFile = useCallback((f: File | null | undefined) => {
    if (!f) return
    if (f.size > 10 * 1024 * 1024) { toast({ kind: 'error', title: 'File too large (max 10 MiB)' }); return }
    if (!/\.(md|markdown|txt|json)$/i.test(f.name) && !/^(text\/|application\/json)/.test(f.type)) {
      toast({ kind: 'error', title: 'Unsupported file — use .md, .txt, or .json' }); return
    }
    setFilename(f.name)
    const reader = new FileReader()
    reader.onload = () => setContent(String(reader.result || ''))
    reader.onerror = () => toast({ kind: 'error', title: 'Could not read the file' })
    reader.readAsText(f)
  }, [toast])

  const onFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    loadFile(e.target.files?.[0]); e.target.value = ''  // allow re-picking the same file
  }, [loadFile])
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false); loadFile(e.dataTransfer.files?.[0])
  }, [loadFile])

  // #20 review P1: the dry-run runs on a server-side background worker, so we
  // poll for live progress instead of blocking on the whole run. The active job
  // id is stashed so a reload / navigate-away re-attaches (browser-level resume).
  const pollRef = useRef<number | null>(null)
  const stopPoll = useCallback(() => {
    if (pollRef.current != null) { window.clearTimeout(pollRef.current); pollRef.current = null }
  }, [])
  const watch = useCallback((id: number) => {
    let idle = 0
    const tick = async () => {
      try {
        const st = await v2ImportStatus(id)
        setJob(st)
        if (st.status !== 'dry_run') {          // ready / committed / cancelled / failed
          stopPoll(); setBusy(false); await refresh(id)
          localStorage.removeItem('brainImportJob')
          toast({ kind: st.status === 'failed' ? 'error' : 'success',
                  title: st.status === 'failed' ? (st.error || 'Import failed')
                                                : 'Dry-run complete — review the candidates below' })
          return
        }
        idle = st.running ? 0 : idle + 1           // worker stopped but still dry_run (e.g. vault locked)
        if (idle >= 2) {
          stopPoll(); setBusy(false); await refresh(id)
          toast({ kind: 'info', title: 'Import paused — unlock the vault or press Resume' })
          return
        }
        pollRef.current = window.setTimeout(tick, 1000)
      } catch (e) { stopPoll(); setBusy(false); toast({ kind: 'error', title: errMsg(e) }) }
    }
    tick()
  }, [refresh, stopPoll, toast])

  const start = useCallback(async () => {
    setBusy(true)
    try {
      const j = await v2ImportCreate(filename, content)
      const st = await v2ImportCommand(j.id, 'run')   // returns immediately; worker runs server-side
      setJob(st)
      localStorage.setItem('brainImportJob', String(j.id))
      watch(j.id)
    } catch (e) { setBusy(false); toast({ kind: 'error', title: errMsg(e) }) }
  }, [filename, content, watch, toast])

  // Re-attach to an in-progress import after a reload / tab switch.
  useEffect(() => {
    const saved = localStorage.getItem('brainImportJob')
    if (!saved) return
    const id = Number(saved)
    v2ImportStatus(id).then(st => {
      if (st.status === 'dry_run') { setJob(st); setBusy(true); watch(id) }
      else localStorage.removeItem('brainImportJob')
    }).catch(() => localStorage.removeItem('brainImportJob'))
    return stopPoll
  }, [watch, stopPoll])

  const cmd = useCallback(async (command: 'commit' | 'cancel') => {
    if (!job) return
    stopPoll()
    setBusy(true)
    try {
      const st = await v2ImportCommand(job.id, command)
      setJob(st)
      await refresh(job.id)
      localStorage.removeItem('brainImportJob')
      toast({ kind: 'success', title: command === 'commit' ? `Committed — ${st.applied ?? 0} applied` : 'Import cancelled' })
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [job, refresh, stopPoll, toast])

  const decide = useCallback(async (approve: boolean, payload: { ids?: number[]; outcome?: string }) => {
    if (!job) return
    try { await v2ImportDecide(job.id, approve, payload); await refresh(job.id) }
    catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
  }, [job, refresh, toast])

  // Trash = a candidate the quality gate proposes to reject; auto-filtered from import.
  const isTrash = (c: V2Candidate) => !c.error && c.proposed_outcome === 'rejected'
  const goodCands = useMemo(() => cands.filter(c => !c.error && !isTrash(c)), [cands])
  const trashCount = useMemo(() => cands.filter(isTrash).length, [cands])
  const visibleCands = useMemo(() => hideTrash ? cands.filter(c => !isTrash(c)) : cands, [cands, hideTrash])

  return (
    <div className="space-y-3">
      {!job && (
        <div
          onDrop={onDrop}
          onDragOver={e => { e.preventDefault(); if (!dragOver) setDragOver(true) }}
          onDragEnter={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={e => { if (e.currentTarget === e.target) setDragOver(false) }}
          className={`relative space-y-2 rounded-xl border p-3.5 transition-colors ${dragOver ? 'border-accent bg-accent/10 ring-2 ring-accent/30' : 'border-border bg-surface/40'}`}
        >
          <p className="text-xs text-muted"><span className="text-text">Drag a .md file here</span> — or pick one, or paste MD / TXT / JSON (≤10 MiB). Every item runs through the V2 quality gate: <span className="text-text">trash is filtered out automatically</span>, and nothing is saved until you commit.</p>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20">
              <input type="file" accept=".md,.markdown,.txt,.json,text/markdown,text/plain" onChange={onFile} className="hidden" />
              <Upload size={13} /> Choose .md file
            </label>
            <input value={filename} onChange={e => setFilename(e.target.value)}
              className="min-w-[140px] flex-1 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs text-text" placeholder="filename.md" />
          </div>
          <textarea value={content} onChange={e => setContent(e.target.value)} rows={8}
            className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs text-text" placeholder="…or paste the content to import here" />
          <button disabled={busy || !content.trim()} onClick={start}
            className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20 disabled:opacity-50">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Dry-run import
          </button>
          {dragOver && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-bg/70 backdrop-blur-sm">
              <span className="flex items-center gap-2 text-sm font-medium text-accent"><Upload size={16} /> Drop the .md file to load it</span>
            </div>
          )}
        </div>
      )}
      {job && (
        <>
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-surface/40 p-3">
            <Badge tone={job.status === 'committed' ? 'success' : job.status === 'ready' ? 'accent' : 'muted'}>{job.status}</Badge>
            <span className="text-xs text-muted">{job.filename} · {Object.entries(job.candidates_by_outcome).map(([k, v]) => `${k} ${v}`).join(' · ') || 'no candidates'}
              {job.extraction_errors > 0 && ` · ${job.extraction_errors} extraction errors`}</span>
            <div className="ml-auto flex gap-1.5">
              {job.status === 'ready' && (
                <>
                  <button disabled={busy || goodCands.length === 0} onClick={() => decide(true, { ids: goodCands.map(c => c.id) })}
                    title="Approve every candidate that passed the quality gate (excludes trash)"
                    className="rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-success disabled:opacity-40">Approve good ({goodCands.length})</button>
                  <button disabled={busy} onClick={() => cmd('commit')}
                    className="rounded-lg border border-success/40 bg-success/10 px-2 py-1 text-[11px] font-medium text-success">Commit approved</button>
                  <button disabled={busy} onClick={() => cmd('cancel')}
                    className="rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-danger">Cancel</button>
                </>
              )}
              <button onClick={() => { setJob(null); setCands([]); setContent('') }}
                className="rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-text">New import</button>
            </div>
          </div>
          {job.status === 'dry_run' && (
            <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-surface/40 p-3">
              <div className="flex items-center gap-2 text-xs text-muted">
                {job.running
                  ? <><Loader2 size={13} className="animate-spin text-accent" /> Extracting memories — chunk {job.next_chunk} / {job.total_chunks}</>
                  : <>Paused at chunk {job.next_chunk} / {job.total_chunks}</>}
                <span className="ml-auto font-mono text-text">{Math.round((job.progress || 0) * 100)}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-border/40">
                <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} />
              </div>
              {!job.running && (
                <button onClick={() => { setBusy(true); v2ImportCommand(job.id, 'resume').then(st => { setJob(st); watch(job.id) }).catch(e => { setBusy(false); toast({ kind: 'error', title: errMsg(e) }) }) }}
                  className="self-start rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-text">Resume</button>
              )}
            </div>
          )}
          {trashCount > 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-border bg-surface/30 px-3 py-1.5 text-[11px] text-muted">
              <Filter size={12} /> {trashCount} low-value {trashCount === 1 ? 'item' : 'items'} auto-filtered (won't be imported).
              <button onClick={() => setHideTrash(h => !h)} className="ml-auto flex items-center gap-1 text-muted hover:text-text">
                <Eye size={12} /> {hideTrash ? 'Show filtered' : 'Hide filtered'}
              </button>
            </div>
          )}
          <div className="space-y-1.5">
            {visibleCands.map(c => (
              <div key={c.id} className="flex items-start gap-2 rounded-xl border border-border bg-surface/40 px-3 py-2">
                <div className="min-w-0 flex-1">
                  {c.error
                    ? <p className="text-xs text-danger">extraction error: {c.error}</p>
                    : <p className="truncate text-xs text-text">{c.sensitive && <ShieldAlert size={11} className="mr-1 inline text-warning" />}{String(c.candidate?.distilled_text ?? '')}</p>}
                  <div className="mt-1 flex gap-1.5">
                    {c.proposed_outcome && <Badge tone={c.proposed_outcome === 'active' ? 'success' : c.proposed_outcome === 'rejected' ? 'danger' : 'warning'}>{c.proposed_outcome}</Badge>}
                    {c.applied_memory_id && <Badge tone="accent">applied #{c.applied_memory_id}</Badge>}
                  </div>
                </div>
                {!c.error && job.status === 'ready' && (
                  <div className="flex shrink-0 gap-1">
                    <button onClick={() => decide(true, { ids: [c.id] })}
                      className={`rounded-lg border px-2 py-1 text-[11px] ${c.approved === true ? 'border-success/50 bg-success/15 text-success' : 'border-border text-muted hover:text-success'}`}>✓</button>
                    <button onClick={() => decide(false, { ids: [c.id] })}
                      className={`rounded-lg border px-2 py-1 text-[11px] ${c.approved === false ? 'border-danger/50 bg-danger/15 text-danger' : 'border-border text-muted hover:text-danger'}`}>✗</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
