import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
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
} from '../api.brainV2'
import { useToast } from '../context/ToastProvider'

type Tab = 'overview' | 'library' | 'import' | 'migration' | 'ask'

const STATUSES = ['active', 'pending', 'rejected', 'archived', 'superseded'] as const
const TYPES = ['fact', 'identity', 'preference', 'correction', 'behavior_rule',
  'workflow_standard', 'frustration_trigger', 'decision', 'project_context', 'relationship']

// One hue per memory type — drives the row bar, the type chip, and the filter tabs.
const TYPE_META: Record<string, { label: string; color: string }> = {
  fact: { label: 'Fact', color: '#9CA3AF' },
  identity: { label: 'Identity', color: '#58a6ff' },
  preference: { label: 'Preference', color: '#3fb950' },
  correction: { label: 'Correction', color: '#f85149' },
  behavior_rule: { label: 'Behavior rule', color: '#8b5cf6' },
  workflow_standard: { label: 'Workflow', color: '#d29922' },
  frustration_trigger: { label: 'Frustration', color: '#db61a2' },
  decision: { label: 'Decision', color: '#f0883e' },
  project_context: { label: 'Project', color: '#9ccc2c' },
  relationship: { label: 'Relationship', color: '#39c5cf' },
}
function typeMeta(t: string) { return TYPE_META[t] ?? { label: t, color: '#a78bfa' } }

function errMsg(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e)
  return /423|locked/i.test(m) ? 'Vault is locked — unlock it in Settings first.' : m
}

function Badge({ children, tone = 'muted' }: { children: React.ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    muted: 'border-border text-muted',
    accent: 'border-accent/40 bg-accent/10 text-accent',
    warning: 'border-warning/40 bg-warning/10 text-warning',
    danger: 'border-danger/40 bg-danger/10 text-danger',
    purple: 'border-purple/40 bg-purple/10 text-purple',
    success: 'border-success/40 bg-success/10 text-success',
  }
  return <span className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-px text-[10px] ${tones[tone] || tones.muted}`}>{children}</span>
}

function statusTone(s: string): string {
  return s === 'active' ? 'success' : s === 'pending' ? 'warning'
    : s === 'rejected' ? 'danger' : s === 'superseded' ? 'purple' : 'muted'
}

function StatTile({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface/60 px-3.5 py-2.5">
      <div className={`text-lg font-bold ${tone || 'text-heading'}`}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  )
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = value >= 0.8 ? '#3fb950' : value >= 0.6 ? '#d29922' : '#f85149'
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-muted">
      <span className="block h-1 w-10 overflow-hidden rounded-full bg-border">
        <span className="block h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </span>
      {pct}%
    </span>
  )
}

// ── sort menu (V1 pattern) ────────────────────────────────────────────────────
const SORT_OPTIONS = [
  { id: 'default', label: 'Default', desc: 'Quality first', Icon: Sparkles },
  { id: 'latest', label: 'Latest First', desc: 'Most recently updated', Icon: CalendarClock },
  { id: 'confidence', label: 'Confidence First', desc: 'High → low confidence', Icon: TrendingUp },
  { id: 'az', label: 'A → Z', desc: 'Alphabetical', Icon: ArrowDownAZ },
] as const

function SortMenu({ sortBy, setSortBy }: { sortBy: string; setSortBy: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const cur = SORT_OPTIONS.find(o => o.id === sortBy) ?? SORT_OPTIONS[0]
  const CurIcon = cur.Icon

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc); document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs transition-colors ${open ? 'border-accent/50 text-accent' : 'border-border text-muted hover:text-text'}`}>
        <CurIcon size={13} /> {cur.label}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-52 rounded-xl border border-border bg-surface p-1.5 shadow-xl">
          {SORT_OPTIONS.map(o => {
            const OIcon = o.Icon
            return (
              <button key={o.id} onClick={() => { setSortBy(o.id); setOpen(false) }}
                className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors ${o.id === sortBy ? 'bg-accent/10 text-accent' : 'text-text hover:bg-bg/60'}`}>
                <OIcon size={14} className="shrink-0" />
                <span className="min-w-0">
                  <span className="block text-xs font-medium">{o.label}</span>
                  <span className="block text-[10px] text-muted">{o.desc}</span>
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── memory row (library) ──────────────────────────────────────────────────────
function MemoryRow({ m, onChanged, selectMode = false, selected = false, onToggleSel, matchPct }: {
  m: V2Memory; onChanged: () => void
  selectMode?: boolean; selected?: boolean; onToggleSel?: () => void; matchPct?: number
}) {
  const { toast } = useToast()
  const [open, setOpen] = useState(false)
  const [influence, setInfluence] = useState<V2Influence[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmPurge, setConfirmPurge] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(m.distilled_text)
  const [editType, setEditType] = useState(m.memory_type)
  const [editImpl, setEditImpl] = useState(m.behavior_implication)
  const meta = typeMeta(m.memory_type)

  const act = useCallback(async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true)
    try { await fn(); toast({ kind: 'success', title: done }); onChanged() }
    catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [toast, onChanged])

  const startEdit = useCallback(() => {
    setEditText(m.distilled_text); setEditType(m.memory_type); setEditImpl(m.behavior_implication); setEditing(true)
  }, [m.distilled_text, m.memory_type, m.behavior_implication])
  const saveEdit = useCallback(() => {
    if (!editText.trim()) return
    void act(async () => {
      await v2EditMemory(m.id, { distilled_text: editText.trim(), memory_type: editType, behavior_implication: editImpl.trim() })
      setEditing(false)
    }, 'Saved')
  }, [editText, editType, editImpl, m.id, act])

  const loadInfluence = useCallback(async () => {
    try { setInfluence(await v2Influence(m.id)) } catch { setInfluence([]) }
  }, [m.id])

  return (
    <div className={`rounded-xl border bg-surface/40 transition-colors ${selected ? 'border-accent/60 bg-accent/5' : 'border-border'}`}>
      <button
        onClick={() => {
          if (selectMode) { onToggleSel?.(); return }
          setOpen(o => !o)
          if (!open && influence === null) void loadInfluence()
        }}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left">
        {selectMode
          ? <span className={selected ? 'shrink-0 text-accent' : 'shrink-0 text-muted'}>{selected ? <CheckSquare size={15} /> : <Square size={15} />}</span>
          : open ? <ChevronDown size={14} className="shrink-0 text-muted" /> : <ChevronRight size={14} className="shrink-0 text-muted" />}
        <span className="h-8 w-1 shrink-0 rounded-full" style={{ background: meta.color }} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs text-text">{m.sensitive && <ShieldAlert size={11} className="mr-1 inline text-warning" />}{m.distilled_text}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <Badge tone={statusTone(m.status)}>{m.status}</Badge>
            <span className="rounded px-1.5 py-0.5 text-[10px] font-medium" style={{ color: meta.color, background: `${meta.color}1a` }}>{meta.label}</span>
            {m.authority === 'hard' && <Badge tone="purple">hard rule</Badge>}
            {m.explicitness === 'inferred' && <Badge tone="warning">inferred</Badge>}
            {m.trust === 'untrusted' && <Badge tone="warning">imported</Badge>}
            <ConfidenceBar value={m.confidence} />
            <Badge>quality {Math.round(m.quality_score)}</Badge>
            {m.scope_key && <Badge tone="accent">{m.scope_type}:{m.scope_key}</Badge>}
            {typeof matchPct === 'number' && <span className="text-[10px] font-medium text-accent">{matchPct}% match</span>}
          </div>
        </div>
      </button>
      {open && !selectMode && editing && (
        <div className="space-y-2 border-t border-border px-3 py-2.5 text-xs">
          <p className="font-semibold text-muted">Edit memory</p>
          {m.redacted ? (
            <p className="text-warning">Unlock the vault to edit this sensitive memory.</p>
          ) : (
            <>
              <textarea value={editText} onChange={e => setEditText(e.target.value)} rows={3} autoFocus
                onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) saveEdit() }}
                className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs text-text" placeholder="Memory text…" />
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1 text-[10px] text-muted">Type
                  <select value={editType} onChange={e => setEditType(e.target.value)}
                    className="rounded border border-border bg-surface px-1.5 py-1 text-[11px] text-text">
                    {TYPES.map(t => <option key={t} value={t}>{typeMeta(t).label}</option>)}
                  </select>
                </label>
                <input value={editImpl} onChange={e => setEditImpl(e.target.value)} placeholder="Behavior implication (optional)"
                  className="min-w-[160px] flex-1 rounded-lg border border-border bg-surface px-2.5 py-1 text-[11px] text-text" />
              </div>
              <div className="flex gap-1.5 pt-0.5">
                <button disabled={busy || !editText.trim()} onClick={saveEdit}
                  className="flex items-center gap-1 rounded-lg border border-success/40 bg-success/10 px-2.5 py-1 text-[11px] font-medium text-success disabled:opacity-40">
                  {busy ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />} Save
                </button>
                <button disabled={busy} onClick={() => setEditing(false)}
                  className="rounded-lg border border-border px-2.5 py-1 text-[11px] text-muted hover:text-text">Cancel</button>
              </div>
            </>
          )}
        </div>
      )}
      {open && !selectMode && !editing && (
        <div className="space-y-2.5 border-t border-border px-3 py-2.5 text-xs">
          {m.behavior_implication && <p className="text-muted"><span className="text-text">Implication:</span> {m.behavior_implication}</p>}
          {m.evidence.length > 0 && (
            <div>
              <p className="mb-1 font-semibold text-muted">Evidence</p>
              {m.evidence.map(e => (
                <p key={e.id} className="text-muted">· {e.redacted ? <em>locked (sensitive)</em> : e.excerpt || <em>(reference only)</em>}
                  {e.source_ref && <span className="text-[10px]"> — {e.source_ref}</span>}</p>
              ))}
            </div>
          )}
          <div>
            <p className="mb-1 font-semibold text-muted">Influence trace</p>
            {influence === null ? <Loader2 size={12} className="animate-spin text-muted" />
              : influence.length === 0 ? <p className="text-muted">Hasn't shaped a turn yet.</p>
                : influence.slice(0, 5).map((t, i) => (
                  <p key={i} className="text-muted">· {t.surface} — "{t.query_hint}" <span className="text-[10px]">{t.at}</span></p>
                ))}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-[10px] text-muted">Feedback:</span>
            <button disabled={busy} onClick={() => act(() => v2Feedback(m.id, 'useful'), 'Marked useful')}
              className="flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-success"><ThumbsUp size={11} /> Useful</button>
            <button disabled={busy} onClick={() => act(() => v2Feedback(m.id, 'irrelevant'), 'Marked irrelevant')}
              className="flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-warning"><ThumbsDown size={11} /> Irrelevant</button>
            <button disabled={busy} onClick={() => act(() => v2Feedback(m.id, 'wrong'), 'Marked wrong')}
              className="flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-danger"><XCircle size={11} /> Wrong</button>
            <span className="mx-1 h-4 w-px bg-border" />
            <button disabled={busy} onClick={startEdit}
              className="flex items-center gap-1 rounded-lg border border-accent/40 bg-accent/10 px-2 py-1 text-[11px] font-medium text-accent hover:bg-accent/20"><Pencil size={11} /> Edit</button>
            {m.status === 'pending' && (
              <button disabled={busy} onClick={() => act(() => v2SetStatus(m.id, 'active'), 'Activated')}
                className="flex items-center gap-1 rounded-lg border border-success/40 bg-success/10 px-2 py-1 text-[11px] text-success"><CheckCircle2 size={11} /> Approve</button>
            )}
            {m.status !== 'archived' && (
              <button disabled={busy} onClick={() => act(() => v2SetStatus(m.id, 'archived'), 'Archived')}
                className="flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-text"><Archive size={11} /> Archive</button>
            )}
            {confirmPurge ? (
              <button disabled={busy} onClick={() => act(() => v2Purge(m.id), 'Purged permanently')}
                className="flex items-center gap-1 rounded-lg border border-danger/50 bg-danger/15 px-2 py-1 text-[11px] font-semibold text-danger"><Trash2 size={11} /> Confirm purge</button>
            ) : (
              <button disabled={busy} onClick={() => setConfirmPurge(true)}
                className="flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-danger"><Trash2 size={11} /> Purge</button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── import wizard tab ─────────────────────────────────────────────────────────
function ImportTab() {
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

// ── migration tab ─────────────────────────────────────────────────────────────
function MigrationTab() {
  const { toast } = useToast()
  const [run, setRun] = useState<V2MigrationStatus | null>(null)
  const [items, setItems] = useState<V2MigrationItem[]>([])
  const [group, setGroup] = useState<string>('all')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async (id: number) => {
    setItems(await v2MigrationItems(id))
  }, [])

  const start = useCallback(async () => {
    setBusy(true)
    try {
      const r = await v2MigrationCreate()
      const done = await v2MigrationCommand(r.id, 'run')
      setRun(done)
      await refresh(r.id)
      toast({ kind: 'success', title: 'Preview complete — review the grouped proposals' })
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [refresh, toast])

  const apply = useCallback(async () => {
    if (!run) return
    setBusy(true)
    try {
      const st = await v2MigrationCommand(run.id, 'apply')
      setRun(st)
      await refresh(run.id)
      toast({ kind: 'success', title: `Applied ${st.applied_now ?? st.applied} approved items — legacy rows untouched` })
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [run, refresh, toast])

  const decide = useCallback(async (approve: boolean, payload: { ids?: number[]; group?: string }) => {
    if (!run) return
    try { await v2MigrationDecide(run.id, approve, payload); await refresh(run.id) }
    catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
  }, [run, refresh, toast])

  const visible = useMemo(() => group === 'all' ? items : items.filter(i => i.group === group), [items, group])
  const approvedCount = useMemo(() => items.filter(i => i.approved === true && !i.applied_memory_id).length, [items])
  const triaging = run !== null && (run.status === 'ready' || run.status === 'applied')

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-border bg-surface/40 p-3.5">
        <p className="text-xs text-muted">Preview reclassifies every legacy memory into V2 groups. Nothing changes until you approve and apply — and legacy memories are <span className="text-text">never modified</span> either way.</p>
        {!run && (
          <button disabled={busy} onClick={start}
            className="mt-2 flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20 disabled:opacity-50">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Eye size={13} />} Run preview
          </button>
        )}
      </div>
      {run && (
        <>
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-surface/40 p-3">
            <Badge tone={run.status === 'applied' ? 'success' : 'accent'}>{run.status}</Badge>
            <span className="text-xs text-muted">{run.scanned}/{run.total_legacy} scanned · {run.applied} applied · {approvedCount} approved waiting</span>
            <div className="ml-auto flex gap-1.5">
              {triaging && (
                <button disabled={busy || approvedCount === 0} onClick={apply}
                  title={approvedCount === 0 ? 'Approve items first — ✓ a row, a group, or Approve all' : undefined}
                  className="rounded-lg border border-success/40 bg-success/10 px-2 py-1 text-[11px] font-medium text-success disabled:opacity-40">
                  Apply approved ({approvedCount})
                </button>
              )}
              <button onClick={() => { setRun(null); setItems([]) }}
                className="rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-text">Close</button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {['all', ...Object.keys(run.groups)].map(g => (
              <button key={g} onClick={() => setGroup(g)}
                className={`rounded-full border px-2.5 py-1 text-[11px] ${group === g ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
                {g}{g !== 'all' && ` (${run.groups[g]})`}
              </button>
            ))}
            {triaging && (
              <span className="ml-auto flex gap-1.5">
                <button onClick={() => decide(true, group === 'all' ? {} : { group })}
                  className="rounded-lg border border-success/40 px-2 py-1 text-[11px] text-success hover:bg-success/10">
                  Approve {group === 'all' ? 'all' : group}
                </button>
                <button onClick={() => decide(false, group === 'all' ? {} : { group })}
                  className="rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-danger">
                  Reject {group === 'all' ? 'all' : group}
                </button>
              </span>
            )}
          </div>
          <div className="space-y-1.5">
            {visible.map(i => (
              <div key={i.id} className="flex items-start gap-2 rounded-xl border border-border bg-surface/40 px-3 py-2">
                <div className="min-w-0 flex-1">
                  {i.error
                    ? <p className="text-xs text-danger">error: {i.error}</p>
                    : <p className="truncate text-xs text-text">{i.sensitive && <ShieldAlert size={11} className="mr-1 inline text-warning" />}{String(i.candidate?.distilled_text ?? '')}</p>}
                  <div className="mt-1 flex gap-1.5">
                    {i.group && <Badge tone="accent">{i.group}</Badge>}
                    {i.proposed_outcome && <Badge tone={statusTone(i.proposed_status || '')}>{i.proposed_outcome}</Badge>}
                    {i.approved !== null && <Badge tone={i.approved ? 'success' : 'danger'}>{i.approved ? 'approved' : 'rejected'}</Badge>}
                    {i.applied_memory_id && <Badge tone="purple">applied #{i.applied_memory_id}</Badge>}
                  </div>
                </div>
                {!i.error && !i.applied_memory_id && triaging && (
                  <div className="flex shrink-0 gap-1">
                    <button onClick={() => decide(true, { ids: [i.id] })}
                      className={`rounded-lg border px-2 py-1 text-[11px] ${i.approved === true ? 'border-success/50 bg-success/15 text-success' : 'border-border text-muted hover:text-success'}`}>✓</button>
                    <button onClick={() => decide(false, { ids: [i.id] })}
                      className={`rounded-lg border px-2 py-1 text-[11px] ${i.approved === false ? 'border-danger/50 bg-danger/15 text-danger' : 'border-border text-muted hover:text-danger'}`}>✗</button>
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

// ── tell tobi tab (coming soon) ───────────────────────────────────────────────
function TellTab() {
  return (
    <div className="rounded-2xl border border-dashed border-purple/30 bg-purple/5 px-6 py-12 text-center">
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-purple/30 bg-purple/10 text-purple">
        <Sparkles size={20} />
      </div>
      <h3 className="text-sm font-semibold text-heading">Tell TOBI <span className="ml-1 rounded-full bg-warning/15 px-1.5 py-0.5 text-[10px] font-medium text-warning">coming soon</span></h3>
      <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-muted">
        A conversational way to teach TOBI about you — add facts, correct what it got wrong, and set
        rules in plain language, each routed through the same quality gate. It's on the way.
      </p>
      <p className="mx-auto mt-3 max-w-md text-[11px] text-muted">
        For now: use <span className="text-text">+ Add</span> in the Library to remember something, and the
        <span className="text-text"> Semantic</span> toggle there to see what TOBI would recall.
      </p>
    </div>
  )
}

// ── page ──────────────────────────────────────────────────────────────────────
export default function BrainV2() {
  const { toast } = useToast()
  const [tab, setTab] = useState<Tab>('overview')
  const [stats, setStats] = useState<V2Stats | null>(null)
  const [profile, setProfile] = useState<{ profile: string; version: string } | null>(null)
  const [memories, setMemories] = useState<V2Memory[]>([])
  const [status, setStatus] = useState('all')
  const [mtype, setMtype] = useState('all')
  const [cleanup, setCleanup] = useState<V2CleanupProposal[] | null>(null)
  const [busy, setBusy] = useState(false)

  // library controls (V1-parity UX)
  const [query, setQuery] = useState('')
  const [semantic, setSemantic] = useState(false)
  const [recallHits, setRecallHits] = useState<V2RecallItem[] | null>(null)
  const [recallBusy, setRecallBusy] = useState(false)
  const [sortBy, setSortBy] = useState('default')
  const [showFilters, setShowFilters] = useState(false)
  const [fAuthority, setFAuthority] = useState('all')
  const [fExplicit, setFExplicit] = useState('all')
  const [fTrust, setFTrust] = useState('all')
  const [fSensitive, setFSensitive] = useState(false)
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [confirmDel, setConfirmDel] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [addText, setAddText] = useState('')
  const [addBusy, setAddBusy] = useState(false)

  const reload = useCallback(async () => {
    try {
      const [s, p, m] = await Promise.all([v2Stats(), v2Profile(), v2Memories({ limit: 500 })])
      setStats(s); setProfile(p); setMemories(m)
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
  }, [toast])

  useEffect(() => { void reload() }, [reload])

  // semantic search = live recall preview (what TOBI would actually retrieve)
  useEffect(() => {
    if (!semantic || !query.trim()) { setRecallHits(null); return }
    const t = setTimeout(async () => {
      setRecallBusy(true)
      try { setRecallHits(await v2Recall(query.trim(), 'agent')) } catch { setRecallHits([]) }
      finally { setRecallBusy(false) }
    }, 400)
    return () => clearTimeout(t)
  }, [semantic, query])

  const runCleanup = useCallback(async () => {
    setBusy(true)
    try { setCleanup((await v2CleanupPreview()).proposals) }
    catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [toast])

  const applyCleanup = useCallback(async (p: V2CleanupProposal) => {
    try {
      await v2CleanupApply([p])
      toast({ kind: 'success', title: 'Applied' })
      setCleanup(c => (c || []).filter(x => x !== p))
      void reload()
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
  }, [toast, reload])

  const total = memories.length
  const statusCounts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const m of memories) c[m.status] = (c[m.status] ?? 0) + 1
    return c
  }, [memories])
  const typeCounts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const m of memories) c[m.memory_type] = (c[m.memory_type] ?? 0) + 1
    return c
  }, [memories])

  const filtered = useMemo(() => {
    let list = memories
    if (status !== 'all') list = list.filter(m => m.status === status)
    if (mtype !== 'all') list = list.filter(m => m.memory_type === mtype)
    if (fAuthority !== 'all') list = list.filter(m => m.authority === fAuthority)
    if (fExplicit !== 'all') list = list.filter(m => m.explicitness === fExplicit)
    if (fTrust !== 'all') list = list.filter(m => m.trust === fTrust)
    if (fSensitive) list = list.filter(m => m.sensitive)
    const q = query.trim().toLowerCase()
    if (q && !semantic) {
      list = list.filter(m => m.distilled_text.toLowerCase().includes(q)
        || m.behavior_implication.toLowerCase().includes(q)
        || m.tags.some(t => t.toLowerCase().includes(q)))
    }
    return list
  }, [memories, status, mtype, fAuthority, fExplicit, fTrust, fSensitive, query, semantic])

  const sorted = useMemo(() => {
    const list = [...filtered]
    switch (sortBy) {
      case 'latest': list.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')); break
      case 'confidence': list.sort((a, b) => b.confidence - a.confidence); break
      case 'az': list.sort((a, b) => a.distilled_text.localeCompare(b.distilled_text)); break
      default: list.sort((a, b) => (b.quality_score - a.quality_score) || (b.confidence - a.confidence))
    }
    return list
  }, [filtered, sortBy])

  // what the list actually shows: semantic recall order, or the filtered+sorted set
  const display = useMemo((): { m: V2Memory; matchPct?: number }[] => {
    if (semantic && query.trim() && recallHits) {
      const byId = new Map(memories.map(m => [m.id, m]))
      return recallHits.filter(r => byId.has(r.memory_id))
        .map(r => ({ m: byId.get(r.memory_id)!, matchPct: Math.round((r.signals.semantic ?? 0) * 100) }))
    }
    return sorted.map(m => ({ m }))
  }, [semantic, query, recallHits, memories, sorted])

  const toggleSel = useCallback((id: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }, [])

  const bulk = useCallback(async (label: string, ids: number[], fn: (id: number) => Promise<unknown>) => {
    if (ids.length === 0) { toast({ kind: 'error', title: `Nothing selected is eligible to ${label.toLowerCase()}` }); return }
    setBulkBusy(true)
    let done = 0, failed = 0
    for (const id of ids) { try { await fn(id); done++ } catch { failed++ } }
    toast({ kind: failed ? 'error' : 'success', title: `${label} ${done}${failed ? ` · ${failed} failed` : ''}` })
    setSelected(new Set()); setConfirmDel(false); setBulkBusy(false)
    void reload()
  }, [toast, reload])

  const selIds = useCallback((pred: (m: V2Memory) => boolean) =>
    memories.filter(m => selected.has(m.id) && pred(m)).map(m => m.id), [memories, selected])

  const addSubmit = useCallback(async () => {
    if (!addText.trim()) return
    setAddBusy(true)
    try {
      const res = await v2Remember(addText.trim())
      const v2 = res.v2
      toast({
        kind: 'success', title: 'Remembered',
        detail: v2?.outcome ? `Quality gate: ${v2.outcome}${v2.status ? ` → ${v2.status}` : ''}` : res.action,
      })
      setAddText(''); setShowAdd(false)
      void reload()
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setAddBusy(false) }
  }, [addText, toast, reload])

  return (
    <div className="space-y-4 p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-purple/30 bg-purple/10 text-purple"><BrainIcon size={18} /></div>
          <div>
            <h1 className="flex items-center gap-2 text-lg font-bold text-heading">Brain V2 <Badge tone="purple">typed memory</Badge></h1>
            <p className="text-[11px] text-muted">Quality-gated owner memory · {total} memories
              {stats && (stats.vault_unlocked
                ? <span className="ml-1 inline-flex items-center gap-0.5 text-success"><Unlock size={10} /> vault unlocked</span>
                : <span className="ml-1 inline-flex items-center gap-0.5 text-warning"><Lock size={10} /> vault locked — sensitive memory redacted</span>)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/brain/legacy" className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"><ArrowLeft size={13} /> Legacy Brain</Link>
          <button onClick={() => { setTab('overview'); void runCleanup() }}
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"><Eraser size={13} /> Clean</button>
          <button onClick={() => { setTab('library'); setShowAdd(true) }}
            className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-2.5 py-1.5 text-xs font-medium text-accent hover:bg-accent/20"><Plus size={13} /> Add</button>
          <button onClick={() => void reload()} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"><RefreshCw size={13} /> Refresh</button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {([['overview', 'Overview', Database], ['library', 'Library', BrainIcon], ['import', 'Import', Upload],
        ['migration', 'Migration', GitMerge], ['ask', 'Tell TOBI', Sparkles]] as [Tab, string, typeof Database][]).map(([id, label, Icon]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs ${tab === id ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
            <Icon size={13} /> {label}
            {id === 'ask' && <span className="rounded-full bg-warning/15 px-1.5 text-[9px] font-medium text-warning">soon</span>}
          </button>
        ))}
      </div>

      {tab === 'overview' && stats && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <StatTile label="Active" value={stats.by_status.active ?? 0} tone="text-success" />
            <StatTile label="Pending review" value={stats.by_status.pending ?? 0} tone={stats.by_status.pending ? 'text-warning' : undefined} />
            <StatTile label="Conflicted" value={stats.conflicted} tone={stats.conflicted ? 'text-danger' : undefined} />
            <StatTile label="Sensitive" value={stats.sensitive} />
            <StatTile label="Aging (14d+)" value={stats.aging_pending} tone={stats.aging_pending ? 'text-warning' : undefined} />
            <StatTile label="Rejected" value={stats.by_status.rejected ?? 0} />
          </div>
          <div className="rounded-xl border border-purple/20 bg-purple/5 p-3.5">
            <p className="mb-1.5 text-xs font-semibold text-purple">Stable behavior profile <span className="font-normal text-muted">· v{profile?.version} · always in context (≤800 tokens)</span></p>
            <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-text">{profile?.profile || <span className="text-muted">Empty — activate memories to build the profile.</span>}</pre>
          </div>
          <div className="rounded-xl border border-border bg-surface/40 p-3.5">
            <div className="mb-1.5 flex items-center justify-between">
              <p className="text-xs font-semibold text-text">Cleanup center</p>
              <button disabled={busy} onClick={runCleanup} className="flex items-center gap-1 text-[11px] text-muted hover:text-text">
                {busy ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />} Scan for recommendations
              </button>
            </div>
            {cleanup === null ? <p className="text-xs text-muted">Recommends merges, archives, and revalidation. Nothing applies without your confirmation.</p>
              : cleanup.length === 0 ? <p className="text-xs text-success">Nothing to clean up.</p>
                : cleanup.map((p, i) => (
                  <div key={i} className="flex items-center gap-2 border-t border-border py-1.5 first:border-0">
                    <Badge tone={p.action === 'merge' ? 'accent' : p.action === 'archive' ? 'warning' : 'purple'}>{p.action}</Badge>
                    <span className="flex-1 text-xs text-muted">{p.reason} (#{p.memory_id ?? `${p.keep_id}←${p.merge_id}`})</span>
                    <button onClick={() => applyCleanup(p)} className="rounded-lg border border-border px-2 py-0.5 text-[11px] text-muted hover:text-text">Apply</button>
                  </div>
                ))}
          </div>
        </div>
      )}

      {tab === 'library' && (
        <div className="space-y-2.5">
          {/* search + controls */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex min-w-[220px] flex-1 items-center gap-2 rounded-lg border border-border bg-surface px-3">
              <Search size={15} className="text-muted" />
              <input value={query} onChange={e => setQuery(e.target.value)}
                placeholder={semantic ? 'Ask your memory…' : 'Search memories…'}
                className="w-full bg-transparent py-2 text-sm text-text outline-none placeholder:text-muted" />
              {recallBusy && <Loader2 size={14} className="animate-spin text-muted" />}
              {query && <button onClick={() => setQuery('')} className="text-muted hover:text-text"><X size={14} /></button>}
            </div>
            <button onClick={() => setSemantic(s => !s)} title="Rank by meaning using TOBI's live recall pipeline"
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs transition-colors ${semantic ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
              <Sparkles size={13} /> Semantic
            </button>
            <SortMenu sortBy={sortBy} setSortBy={setSortBy} />
            <button onClick={() => setShowFilters(f => !f)}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs transition-colors ${showFilters ? 'border-accent/50 text-accent' : 'border-border text-muted hover:text-text'}`}>
              <Filter size={13} /> Filter
            </button>
            <button onClick={() => setSelectMode(s => { if (s) { setSelected(new Set()); setConfirmDel(false) } return !s })}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs transition-colors ${selectMode ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
              <CheckSquare size={13} /> Select
            </button>
          </div>

          {showAdd && (
            <div className="space-y-2 rounded-xl border border-accent/30 bg-accent/5 p-3">
              <p className="text-xs text-muted">Tell TOBI something to remember. It runs through the V2 quality gate — strong, explicit, conflict-free facts activate immediately; everything else lands in pending for your review.</p>
              <textarea value={addText} onChange={e => setAddText(e.target.value)} rows={2} autoFocus
                onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void addSubmit() }}
                className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs text-text"
                placeholder="e.g. Weekly reports must always be in Vietnamese, delivered before Friday noon." />
              <div className="flex items-center gap-2">
                <button disabled={addBusy || !addText.trim()} onClick={() => void addSubmit()}
                  className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20 disabled:opacity-50">
                  {addBusy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Remember
                </button>
                <button onClick={() => { setShowAdd(false); setAddText('') }}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-text">Cancel</button>
              </div>
            </div>
          )}

          {showFilters && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-xs">
              <label className="flex items-center gap-1.5 text-muted">Authority
                <select value={fAuthority} onChange={e => setFAuthority(e.target.value)} className="rounded border border-border bg-bg px-1.5 py-1 text-text outline-none">
                  <option value="all">all</option><option value="hard">hard rules</option><option value="soft">soft</option>
                </select>
              </label>
              <label className="flex items-center gap-1.5 text-muted">Origin
                <select value={fExplicit} onChange={e => setFExplicit(e.target.value)} className="rounded border border-border bg-bg px-1.5 py-1 text-text outline-none">
                  <option value="all">all</option><option value="explicit">explicit</option><option value="inferred">inferred</option>
                </select>
              </label>
              <label className="flex items-center gap-1.5 text-muted">Trust
                <select value={fTrust} onChange={e => setFTrust(e.target.value)} className="rounded border border-border bg-bg px-1.5 py-1 text-text outline-none">
                  <option value="all">all</option><option value="trusted">trusted</option><option value="untrusted">imported</option>
                </select>
              </label>
              <label className="flex cursor-pointer items-center gap-1.5 text-muted">
                <input type="checkbox" checked={fSensitive} onChange={e => setFSensitive(e.target.checked)} /> sensitive only
              </label>
            </div>
          )}

          {/* status chips */}
          <div className="flex flex-wrap gap-1.5">
            {['all', ...STATUSES].map(s => (
              <button key={s} onClick={() => setStatus(s)}
                className={`rounded-full border px-2.5 py-1 text-[11px] ${status === s ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
                {s} <span className="opacity-70">{s === 'all' ? total : statusCounts[s] ?? 0}</span>
              </button>
            ))}
          </div>

          {/* type chips (colored, with counts) */}
          <div className="flex flex-wrap gap-1.5">
            <button onClick={() => setMtype('all')}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${mtype === 'all' ? 'text-text' : 'text-muted hover:text-text'}`}
              style={mtype === 'all' ? { borderColor: 'rgb(var(--muted))', background: 'rgb(var(--muted) / 0.1)' } : { borderColor: 'rgb(var(--border))' }}>
              <span className="h-2 w-2 rounded-full bg-muted" /> All types
            </button>
            {TYPES.map(t => {
              const meta = typeMeta(t)
              const active = mtype === t
              return (
                <button key={t} onClick={() => setMtype(active ? 'all' : t)}
                  className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${active ? 'text-text' : 'text-muted hover:text-text'}`}
                  style={active ? { borderColor: meta.color, background: `${meta.color}1a` } : { borderColor: 'rgb(var(--border))' }}>
                  <span className="h-2 w-2 rounded-full" style={{ background: meta.color }} />
                  {meta.label} <span className="opacity-70">{typeCounts[t] ?? 0}</span>
                </button>
              )
            })}
          </div>

          {/* bulk-select action bar */}
          {selectMode && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-accent/40 bg-accent/5 px-3 py-2 text-xs">
              <span className="font-medium text-text">{selected.size} selected</span>
              <button onClick={() => setSelected(new Set(display.map(d => d.m.id)))} className="text-muted hover:text-text">Select all ({display.length})</button>
              {selected.size > 0 && <button onClick={() => setSelected(new Set())} className="text-muted hover:text-text">Clear</button>}
              <div className="ml-auto flex flex-wrap items-center gap-1.5">
                <button disabled={bulkBusy || selected.size === 0}
                  onClick={() => bulk('Approved', selIds(m => m.status === 'pending'), id => v2SetStatus(id, 'active'))}
                  className="flex items-center gap-1 rounded-md border border-success/40 bg-success/10 px-2.5 py-1.5 text-success hover:bg-success/20 disabled:opacity-40">
                  <CheckCircle2 size={13} /> Approve
                </button>
                <button disabled={bulkBusy || selected.size === 0}
                  onClick={() => bulk('Rejected', selIds(m => m.status !== 'rejected'), id => v2SetStatus(id, 'rejected'))}
                  className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-muted hover:text-warning disabled:opacity-40">
                  <XCircle size={13} /> Reject
                </button>
                <button disabled={bulkBusy || selected.size === 0}
                  onClick={() => bulk('Archived', selIds(m => m.status !== 'archived'), id => v2SetStatus(id, 'archived'))}
                  className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-muted hover:text-text disabled:opacity-40">
                  <Archive size={13} /> Archive
                </button>
                {!confirmDel ? (
                  <button disabled={bulkBusy || selected.size === 0} onClick={() => setConfirmDel(true)}
                    className="flex items-center gap-1 rounded-md border border-danger/40 bg-danger/10 px-2.5 py-1.5 font-medium text-danger hover:bg-danger/20 disabled:opacity-40">
                    <Trash2 size={13} /> Delete
                  </button>
                ) : (
                  <>
                    <span className="text-danger">Purge {selected.size} permanently?</span>
                    <button onClick={() => setConfirmDel(false)} className="rounded-md border border-border px-2 py-1.5 text-muted hover:text-text">Cancel</button>
                    <button disabled={bulkBusy}
                      onClick={() => bulk('Purged', [...selected], id => v2Purge(id))}
                      className="flex items-center gap-1 rounded-md border border-danger/50 bg-danger/20 px-2.5 py-1.5 font-medium text-danger hover:bg-danger/30 disabled:opacity-50">
                      {bulkBusy ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />} Confirm
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

          {semantic && query.trim() && (
            <p className="text-[11px] text-muted">
              Semantic mode shows what TOBI would <span className="text-text">actually recall</span> for this query — ranked and budgeted, active memories only.
            </p>
          )}

          {display.length === 0
            ? <div className="rounded-xl border border-dashed border-border py-10 text-center text-xs text-muted">
              {semantic && query.trim()
                ? 'Nothing recalled for this query — irrelevant memory stays out by design.'
                : query.trim() || status !== 'all' || mtype !== 'all'
                  ? 'No memories match these filters.'
                  : 'No V2 memories yet — remember something, import, or run the migration.'}
            </div>
            : <div className="space-y-1.5">{display.map(({ m, matchPct }) => (
              <MemoryRow key={m.id} m={m} onChanged={() => void reload()} matchPct={matchPct}
                selectMode={selectMode} selected={selected.has(m.id)} onToggleSel={() => toggleSel(m.id)} />
            ))}</div>}
        </div>
      )}

      {tab === 'import' && <ImportTab />}
      {tab === 'migration' && <MigrationTab />}
      {tab === 'ask' && <TellTab />}
    </div>
  )
}
