import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Brain as BrainIcon, Lock, Unlock, RefreshCw, Upload, Sparkles, ArrowLeft,
  ThumbsUp, ThumbsDown, XCircle, Trash2, Archive, CheckCircle2, ChevronDown,
  ChevronRight, Loader2, ShieldAlert, Search, Database, GitMerge, Eye, Play,
} from 'lucide-react'
import {
  type V2Memory, type V2Stats, type V2JobStatus, type V2Candidate,
  type V2MigrationStatus, type V2MigrationItem, type V2RecallItem,
  type V2Influence, type V2CleanupProposal,
  v2Stats, v2Profile, v2Memories, v2SetStatus, v2Feedback, v2Influence,
  v2Purge, v2Recall, v2ImportCreate, v2ImportCandidates, v2ImportCommand,
  v2ImportDecide, v2MigrationCreate, v2MigrationItems, v2MigrationCommand,
  v2MigrationDecide, v2CleanupPreview, v2CleanupApply,
} from '../api.brainV2'
import { useToast } from '../context/ToastProvider'

type Tab = 'overview' | 'library' | 'import' | 'migration' | 'ask'

const STATUSES = ['active', 'pending', 'rejected', 'archived', 'superseded'] as const
const TYPES = ['fact', 'identity', 'preference', 'correction', 'behavior_rule',
  'workflow_standard', 'frustration_trigger', 'decision', 'project_context', 'relationship']

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

// ── memory row (library) ──────────────────────────────────────────────────────
function MemoryRow({ m, onChanged }: { m: V2Memory; onChanged: () => void }) {
  const { toast } = useToast()
  const [open, setOpen] = useState(false)
  const [influence, setInfluence] = useState<V2Influence[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmPurge, setConfirmPurge] = useState(false)

  const act = useCallback(async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true)
    try { await fn(); toast({ kind: 'success', title: done }); onChanged() }
    catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [toast, onChanged])

  const loadInfluence = useCallback(async () => {
    try { setInfluence(await v2Influence(m.id)) } catch { setInfluence([]) }
  }, [m.id])

  return (
    <div className="rounded-xl border border-border bg-surface/40">
      <button onClick={() => { setOpen(o => !o); if (!open && influence === null) void loadInfluence() }}
        className="flex w-full items-start gap-2 px-3 py-2.5 text-left">
        {open ? <ChevronDown size={14} className="mt-0.5 shrink-0 text-muted" /> : <ChevronRight size={14} className="mt-0.5 shrink-0 text-muted" />}
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs text-text">{m.sensitive && <ShieldAlert size={11} className="mr-1 inline text-warning" />}{m.distilled_text}</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Badge tone={statusTone(m.status)}>{m.status}</Badge>
            <Badge>{m.memory_type}</Badge>
            {m.authority === 'hard' && <Badge tone="purple">hard rule</Badge>}
            {m.explicitness === 'inferred' && <Badge tone="warning">inferred</Badge>}
            {m.trust === 'untrusted' && <Badge tone="warning">imported</Badge>}
            <Badge>conf {Math.round(m.confidence * 100)}%</Badge>
            <Badge>quality {Math.round(m.quality_score)}</Badge>
            {m.scope_key && <Badge tone="accent">{m.scope_type}:{m.scope_key}</Badge>}
          </div>
        </div>
      </button>
      {open && (
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

  const refresh = useCallback(async (id: number) => {
    setCands(await v2ImportCandidates(id))
  }, [])

  const start = useCallback(async () => {
    setBusy(true)
    try {
      const j = await v2ImportCreate(filename, content)
      const done = await v2ImportCommand(j.id, 'run')      // dry-run to completion
      setJob(done)
      await refresh(j.id)
      toast({ kind: 'success', title: 'Dry-run complete — review the candidates below' })
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [filename, content, refresh, toast])

  const cmd = useCallback(async (command: 'commit' | 'cancel') => {
    if (!job) return
    setBusy(true)
    try {
      const st = await v2ImportCommand(job.id, command)
      setJob(st)
      await refresh(job.id)
      toast({ kind: 'success', title: command === 'commit' ? `Committed — ${st.applied ?? 0} applied` : 'Import cancelled' })
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [job, refresh, toast])

  const decide = useCallback(async (approve: boolean, payload: { ids?: number[]; outcome?: string }) => {
    if (!job) return
    try { await v2ImportDecide(job.id, approve, payload); await refresh(job.id) }
    catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
  }, [job, refresh, toast])

  return (
    <div className="space-y-3">
      {!job && (
        <div className="space-y-2 rounded-xl border border-border bg-surface/40 p-3.5">
          <p className="text-xs text-muted">Paste TXT / MD / JSON content (≤10 MiB). Import always dry-runs first — nothing is saved until you commit approved candidates.</p>
          <input value={filename} onChange={e => setFilename(e.target.value)}
            className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs text-text" placeholder="filename.md" />
          <textarea value={content} onChange={e => setContent(e.target.value)} rows={8}
            className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs text-text" placeholder="Paste the content to import…" />
          <button disabled={busy || !content.trim()} onClick={start}
            className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20 disabled:opacity-50">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Dry-run import
          </button>
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
                  <button onClick={() => decide(true, {})} className="rounded-lg border border-border px-2 py-1 text-[11px] text-muted hover:text-text">Approve all</button>
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
          <div className="space-y-1.5">
            {cands.map(c => (
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

// ── ask brain tab ─────────────────────────────────────────────────────────────
function AskTab() {
  const { toast } = useToast()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<V2RecallItem[] | null>(null)
  const [busy, setBusy] = useState(false)

  const ask = useCallback(async () => {
    if (!query.trim()) return
    setBusy(true)
    try { setResults(await v2Recall(query.trim())) }
    catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
    finally { setBusy(false) }
  }, [query, toast])

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && ask()}
          className="flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-xs text-text"
          placeholder="Ask what TOBI would recall for a turn — e.g. 'how should I format the weekly report?'" />
        <button disabled={busy} onClick={ask}
          className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20 disabled:opacity-50">
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />} Recall
        </button>
      </div>
      {results !== null && (
        results.length === 0
          ? <div className="rounded-xl border border-dashed border-border py-8 text-center text-xs text-muted">Nothing relevant — irrelevant memory stays out by design.</div>
          : <div className="space-y-1.5">
            {results.map(r => (
              <div key={r.memory_id} className="rounded-xl border border-border bg-surface/40 px-3 py-2">
                <p className="text-xs text-text">{r.hedged && <em className="text-warning">(unconfirmed) </em>}{r.text}</p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  <Badge tone={r.authority === 'hard' ? 'purple' : 'muted'}>{r.authority === 'hard' ? 'hard rule' : r.type}</Badge>
                  <Badge>score {r.score.toFixed(2)}</Badge>
                  <Badge>relevance {Math.round((r.signals.semantic ?? 0) * 100)}%</Badge>
                  <Badge>{r.scope}</Badge>
                  <Badge tone={r.chip.evidence === 'owner' ? 'muted' : 'warning'}>{r.chip.evidence}</Badge>
                </div>
              </div>
            ))}
          </div>
      )}
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

  const reload = useCallback(async () => {
    try {
      const [s, p, m] = await Promise.all([
        v2Stats(), v2Profile(),
        v2Memories({ status: status === 'all' ? undefined : status, memory_type: mtype === 'all' ? undefined : mtype }),
      ])
      setStats(s); setProfile(p); setMemories(m)
    } catch (e) { toast({ kind: 'error', title: errMsg(e) }) }
  }, [status, mtype, toast])

  useEffect(() => { void reload() }, [reload])

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

  const total = useMemo(() => stats ? Object.values(stats.by_status).reduce((a, b) => a + b, 0) : 0, [stats])

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
          <Link to="/brain" className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"><ArrowLeft size={13} /> Legacy Brain</Link>
          <button onClick={() => void reload()} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted hover:text-text"><RefreshCw size={13} /> Refresh</button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {([['overview', 'Overview', Database], ['library', 'Library', BrainIcon], ['import', 'Import', Upload],
        ['migration', 'Migration', GitMerge], ['ask', 'Ask Brain', Sparkles]] as [Tab, string, typeof Database][]).map(([id, label, Icon]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs ${tab === id ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>
            <Icon size={13} /> {label}
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
          <div className="flex flex-wrap gap-1.5">
            {['all', ...STATUSES].map(s => (
              <button key={s} onClick={() => setStatus(s)}
                className={`rounded-full border px-2.5 py-1 text-[11px] ${status === s ? 'border-accent/50 bg-accent/15 text-accent' : 'border-border text-muted hover:text-text'}`}>{s}</button>
            ))}
            <select value={mtype} onChange={e => setMtype(e.target.value)}
              className="ml-auto rounded-lg border border-border bg-surface px-2 py-1 text-[11px] text-muted">
              <option value="all">all types</option>
              {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          {memories.length === 0
            ? <div className="rounded-xl border border-dashed border-border py-10 text-center text-xs text-muted">No V2 memories match — remember something, import, or run the migration.</div>
            : <div className="space-y-1.5">{memories.map(m => <MemoryRow key={m.id} m={m} onChanged={() => void reload()} />)}</div>}
        </div>
      )}

      {tab === 'import' && <ImportTab />}
      {tab === 'migration' && <MigrationTab />}
      {tab === 'ask' && <AskTab />}
    </div>
  )
}
