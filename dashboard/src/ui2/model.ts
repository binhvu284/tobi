// TOBI UI 2.0 (#36) — the session model.
//
// Everything the live screen shows is a view of the one state below. The graph, the status
// line and the transcript cannot disagree because they all read the same `mood`; a document
// on the canvas and the file chip in the answer are the same `Doc`. The shell
// (docs/feature-idea-queue/TOBI_UI_2_SHELL.html) decided these shapes; the names match its
// script so a behaviour can be checked against it line by line.
import type { PendingAction } from '../api.brain'

/* ── The five agent states, from one table ──────────────────────────────────
   gain/period/dir steer the wave through the memory graph; timed says whether
   the status line carries elapsed time and tokens for the run. */
export type Mood = 'idle' | 'listening' | 'thinking' | 'working' | 'speaking'
export const STATES: Record<Mood, { label: string; gain: number; period: number; dir: 1 | -1; timed: boolean }> = {
  idle:      { label: 'Ready',     gain: 0,    period: 2.60, dir:  1, timed: false },
  listening: { label: 'Listening', gain: 0.85, period: 1.35, dir: -1, timed: false },
  thinking:  { label: 'Thinking',  gain: 1.00, period: 1.50, dir:  1, timed: true  },
  working:   { label: 'Working',   gain: 0.62, period: 2.10, dir:  1, timed: true  },
  speaking:  { label: 'Speaking',  gain: 0.55, period: 2.38, dir:  1, timed: false },
}

/** The owner's avatar initials. Thomas is the canonical owner name. */
export const OWNER_INITIALS = 'TH'

/* ── Actions: one row per step ──────────────────────────────────────────── */
export type ActIcon = 'tool' | 'canvas' | 'doc' | 'chart' | 'sheet' | 'log'
export type ActSpec = { run: string; done: string; meta?: string; icon?: ActIcon }
export type ActFail = { name: string; reason: string; why: string }
export type ActStatus = 'running' | 'done' | 'failed' | 'stopped'
export type Act = {
  id: string; status: ActStatus; name: string; meta: string; icon: ActIcon
  why?: string; spec: ActSpec; startedAt: number
}

/* ── Files, receipts, confirmations ─────────────────────────────────────── */
export type FileKind = 'doc' | 'image' | 'sheet' | 'log'
export type FileRef = { id: string; name: string; kind: FileKind; note?: string; size?: string; at?: string }
export type Receipt = { model: string; secs: string; tokens: number }
export type Confirm = {
  action: PendingAction
  status: 'pending' | 'busy' | 'approved' | 'rejected'
  result?: string
}

/* ── A message is a message wherever it is shown ────────────────────────── */
export type Msg = {
  id: string
  who: 'you' | 'tobi'
  text: string
  time: string
  queued?: boolean       // waiting its turn behind him
  ghost?: boolean        // what he is hearing, before it is a message
  caret?: boolean        // still being written
  acts: Act[]
  folded?: boolean       // three or more steps read as one line
  actsOpen?: boolean     // the folded list, unfolded
  files: FileRef[]
  receipt?: Receipt
  notice?: string        // said once, in the transcript: a fallback, a substitution
  stopnote?: string
  open?: boolean         // a long prompt, unfolded
  confirm?: Confirm
}

/* ── Canvas: four panels, and documents ─────────────────────────────────── */
export type Panel = 'artifacts' | 'script' | 'history' | 'configure'
export const PANELS: Panel[] = ['artifacts', 'script', 'history', 'configure']
export type DesignedPane = 'plan' | 'burndown' | 'items' | 'scriptdoc'
export type DocBody =
  | { type: 'designed'; pane: DesignedPane }
  | { type: 'markdown'; text: string }
  | { type: 'image'; src: string; caption?: string }
  | { type: 'recap'; recap: SessionRecap }
export type Doc = { id: string; title: string; kind: FileKind | 'recap'; body: DocBody; size?: string; at?: string }

/** Lists and settings are narrow; anything read gets half the page. The grip overrides both. */
export const SNAP = [30, 50, 70]
export const MIN_W = SNAP[0], MAX_W = SNAP[SNAP.length - 1], STICK = 3
const SHORT = ['artifacts', 'history', 'configure']
export function widthFor(what: string | null): number { return what && SHORT.includes(what) ? 30 : 50 }
export function stick(w: number): number {
  for (const s of SNAP) if (Math.abs(w - s) <= STICK) return s
  return w
}

/* ── Sessions ───────────────────────────────────────────────────────────── */
export type SessionRecap = {
  id: string; startedAt: string; endedAt: string; secs: number
  actions: number; artifacts: number; title: string
  asked: string[]; done: string[]; open: string[]
  /** the designed recaps carry a one-line summary and decisions; real ones derive theirs */
  line?: string; decisions?: string[]
}
export type ModelChoice = { id: string; label: string; hint: string; context?: number }
export type MicMode = 'locked' | 'onoff' | 'ptt'
export type BootCheck = { name: string; val: string; status: 'wait' | 'now' | 'done' | 'failed' }
export type View = 'standby' | 'boot' | 'live'
export type CanvasState = {
  panel: Panel | null; docs: string[]; active: string | null; width: number; min: boolean; bleed: boolean
}
export type SessionState = {
  demo: boolean
  view: View
  boot: { checks: BootCheck[]; n: number; left: number; error: string | null; ctx: number }
  mood: Mood; label: string; labelKey: number; timing: boolean; since: number; tokens: number; tick: number
  clockSecs: number; startedAt: number
  ctxTokens: number; ctxMax: number
  model: string; models: ModelChoice[]; modelBusy: boolean; modelsError: string | null
  transcript: Msg[]; exchangeStart: number
  run: { msgId: string; done: number; total: number | null } | null
  actions: number
  micMode: MicMode; micLive: boolean
  voiceOn: boolean; volume: number
  canvas: CanvasState
  docs: Record<string, Doc>
  artifacts: FileRef[]
  history: SessionRecap[]
  health: { ok: boolean; detail: string }
}

/* ── What a driver can do to the screen while a turn runs ───────────────── */
export interface Sink {
  mood(name: Mood, label?: string): void
  plan(total: number): void
  actStart(spec: ActSpec): string
  actDone(id: string, meta?: string): void
  actFail(id: string, fail: ActFail): void
  open(doc: Doc): void
  delta(text: string): void
  file(ref: FileRef): void
  receipt(r: Receipt): void
  spend(contextTokens: number, max?: number): void
  tokens(n: number): void
  spentTokens(): number
  elapsed(): number
  model(): string
  confirm(action: PendingAction): void
  note(text: string): void
}
export interface Ear { heard(text: string): void }
export type RunOpts = { attachments: File[] }

/** The thing behind the glass. Scripted for the design review, the chat runtime for real. */
export interface Driver {
  readonly demo: boolean
  /** true when a failed step can be re-run on its own row; false means Try again re-asks */
  readonly retriesInPlace: boolean
  models(): Promise<{ models: ModelChoice[]; current: string }>
  chooseModel(id: string): Promise<void>
  /** what a boot check shows while it waits its turn ('' when nothing is known yet) */
  bootPreview(step: number): string
  /** the value each boot check reports; a rejection is a failed boot with that reason */
  bootValue(step: number, model: string): Promise<string>
  /** opens the backend session, if there is one */
  prepare(model: string): Promise<void>
  greeting(): string
  /** what a fresh session starts with: nothing for real, the designed set for the demo */
  seed(): { artifacts: FileRef[]; history: SessionRecap[]; docs: Doc[] }
  run(text: string, sink: Sink, signal: AbortSignal, opts: RunOpts): Promise<void>
  retry(actId: string, spec: ActSpec, sink: Sink, signal: AbortSignal): Promise<void>
  hear(ear: Ear): { stop(): string }
  decide(action: PendingAction, decision: 'approve' | 'reject'): Promise<string>
  end(): Promise<void>
}

/* ── Small helpers the shell used everywhere ────────────────────────────── */
export const two = (n: number) => (n < 10 ? '0' : '') + n
export const spent = (n: number) => (n < 1000 ? String(n) : (n / 1000).toFixed(1) + 'k') + ' tokens'
export const shortTokens = (n: number) => (n < 1000 ? String(n) : (n / 1000).toFixed(1) + 'k')
export function nowStamp(d = new Date()) { return two(d.getHours()) + ':' + two(d.getMinutes()) }
export function clockText(secs: number) { return two((secs / 60) | 0) + ':' + two(secs % 60) }
/** 31m 48s under an hour, 1h 14m over it — the way the shell wrote every duration */
export function fmtDur(secs: number) {
  const h = (secs / 3600) | 0, m = ((secs % 3600) / 60) | 0, s = secs % 60
  return h ? `${h}h ${two(m)}m` : `${m}m ${two(s)}s`
}
/** Today, 09:12 · Yesterday, 16:40 · Tuesday, 11:05 · Mon 3 Sep, 08:58 */
export function whenLabel(iso: string) {
  const d = new Date(iso), now = new Date()
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((day(now) - day(d)) / 86400000)
  const hm = nowStamp(d)
  if (diff === 0) return `Today, ${hm}`
  if (diff === 1) return `Yesterday, ${hm}`
  if (diff < 7) return `${d.toLocaleDateString([], { weekday: 'long' })}, ${hm}`
  return `${d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })}, ${hm}`
}
export function fmtKb(bytes: number) { return bytes < 1024 ? `${bytes} B` : `${Math.max(1, Math.round(bytes / 1024))} KB` }
let counter = 0
export const uid = (p = 'm') => `${p}${Date.now().toString(36)}${(++counter).toString(36)}`
export const shortModel = (id: string) => (id || '').split(':').pop()?.split('/').pop() || id
