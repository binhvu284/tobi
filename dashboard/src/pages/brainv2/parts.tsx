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


export type Tab = 'overview' | 'library' | 'import' | 'migration' | 'ask'

export const STATUSES = ['active', 'pending', 'rejected', 'archived', 'superseded'] as const
export const TYPES = ['fact', 'identity', 'preference', 'correction', 'behavior_rule',
  'workflow_standard', 'frustration_trigger', 'decision', 'project_context', 'relationship']

// One hue per memory type — drives the row bar, the type chip, and the filter tabs.
export const TYPE_META: Record<string, { label: string; color: string }> = {
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
export function typeMeta(t: string) { return TYPE_META[t] ?? { label: t, color: '#a78bfa' } }

export function errMsg(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e)
  return /423|locked/i.test(m) ? 'Vault is locked — unlock it in Settings first.' : m
}

export function Badge({ children, tone = 'muted' }: { children: React.ReactNode; tone?: string }) {
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

export function statusTone(s: string): string {
  return s === 'active' ? 'success' : s === 'pending' ? 'warning'
    : s === 'rejected' ? 'danger' : s === 'superseded' ? 'purple' : 'muted'
}

export function StatTile({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface/60 px-3.5 py-2.5">
      <div className={`text-lg font-bold ${tone || 'text-heading'}`}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  )
}

export function ConfidenceBar({ value }: { value: number }) {
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
export const SORT_OPTIONS = [
  { id: 'default', label: 'Default', desc: 'Quality first', Icon: Sparkles },
  { id: 'latest', label: 'Latest First', desc: 'Most recently updated', Icon: CalendarClock },
  { id: 'confidence', label: 'Confidence First', desc: 'High → low confidence', Icon: TrendingUp },
  { id: 'az', label: 'A → Z', desc: 'Alphabetical', Icon: ArrowDownAZ },
] as const

export function SortMenu({ sortBy, setSortBy }: { sortBy: string; setSortBy: (v: string) => void }) {
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
export function MemoryRow({ m, onChanged, selectMode = false, selected = false, onToggleSel, matchPct }: {
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
