// The Morpheus console.
//
// Three jobs in one surface:
//
//   1. WHEN MORPHEUS RUNS A COMMAND it opens its OWN session and the console appears. An agent
//      that can reach the shell should never use it invisibly, and giving each agent run its own
//      session means its output is never tangled with whatever the owner is typing.
//   2. IT IS A REAL PROMPT, with per-session history on the arrow keys.
//   3. IT HOLDS MANY SESSIONS AT ONCE. A strip along the top switches between them; once there
//      are more than fit, the overflow collapses into a compact list that stays readable at any
//      count. Sessions keep running while you are looking at another one.
//
// It can be worn four ways, because where a console belongs depends on what you are doing with
// it: DOCKED under the page, FLOATING as a draggable window, FULL SCREEN, or in its OWN TAB.
//
// Line kinds are distinguished by colour AND by prefix, so a copied transcript still reads
// correctly as plain text.
//
// SHELL ONLY: nothing here touches a real shell. `exec` walks a scripted response so the surface,
// the streaming and the safety affordances can be reviewed before any command can execute.
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode,
} from 'react'
import {
  TerminalSquare, X, Trash2, Power, Square, CornerDownLeft, Plus, ChevronDown, Bot,
  GripHorizontal,
} from 'lucide-react'
import { useCanvas } from './MorpheusCanvas'

export type TermLine =
  | { k: 'cmd'; text: string }
  | { k: 'out'; text: string }
  | { k: 'err'; text: string }
  | { k: 'exit'; code: number; ms: number }
  | { k: 'note'; text: string }

/** Who opened the session. Agent-opened ones are marked so a stray shell is never anonymous. */
export type Origin = 'you' | 'morpheus'

export type Session = {
  id: string
  name: string
  origin: Origin
  lines: TermLine[]
  history: string[]
  busy: boolean
  /** The last command run, for the compact list. */
  last: string
  openedAt: number
}

export type TermMode = 'plan' | 'ask' | 'auto'

const MODE: Record<TermMode, { label: string; hint: string }> = {
  plan: { label: 'Plan', hint: 'Shows what it would run. Executes nothing.' },
  ask: { label: 'Ask', hint: 'Confirms anything that changes the machine.' },
  auto: { label: 'Auto', hint: 'Runs without asking. Blocklist still applies.' },
}

/** Beyond this the strip stops growing and the rest move into the compact list. */
const MAX_TABS = 4

type Ctx = {
  sessions: Session[]
  activeId: string
  active: Session | undefined
  focusSession: (id: string) => void
  openSession: (opts?: { name?: string; origin?: Origin }) => string
  closeSession: (id: string) => void
  run: (command: string, sessionId?: string) => Promise<void>
  clear: (sessionId?: string) => void
  live: boolean
  setLive: (v: boolean) => void
  mode: TermMode
  setMode: (m: TermMode) => void
  /** Any session still working. Drives the dot on the closed toggle. */
  anyBusy: boolean
}

const TerminalContext = createContext<Ctx | null>(null)

/* ── Scripted responses ─────────────────────────────────────────────────── */

const HELP = [
  'Commands',
  '  status              gate, model and encryption state',
  '  models              what is admitted and what is refused',
  '  scan <domain>       surface scan against a public target',
  '  whoami              who this instance answers to',
  '  ls                  what is on the record',
  '  sessions            what else is open',
  '  clear               empty this session',
]

function respond(cmd: string, sessionNames: string[]): { out: string[]; err?: string[]; code: number } {
  const [head, ...rest] = cmd.trim().split(/\s+/)
  const arg = rest.join(' ')
  switch (head) {
    case 'help': return { out: HELP, code: 0 }
    case 'whoami': return {
      out: ['thomas', 'Sole owner. No other principal is configured on this instance.'], code: 0,
    }
    case 'sessions': return { out: sessionNames.map((n, i) => `${i + 1}. ${n}`), code: 0 }
    case 'status': return {
      out: [
        'gate         sealed, 3 factors enrolled',
        'model        Ministral 3 14B, local, no provider filter',
        'storage      encrypted at rest, verified on last write',
        'listener     127.0.0.1 only, no external interface',
      ], code: 0,
    }
    case 'models': return {
      out: [
        'ADMITTED   Ministral 3 14B          freedom 94   apache-2.0',
        'ADMITTED   Qwen 27B (abliterated)   freedom 98   apache-2.0',
        'REFUSED    Claude Opus              freedom 40   guardrails on provider hardware',
        'REFUSED    GPT-5.x                  freedom 38   bypass prohibited by terms',
      ], code: 0,
    }
    case 'ls': return {
      out: ['objects/    3 profiles', 'access/     3 entries, 1 refused', 'agents/     morph1'], code: 0,
    }
    case 'scan': {
      if (!arg) return { out: [], err: ['scan: needs a target', 'usage: scan <domain>'], code: 2 }
      return {
        out: [
          `resolving ${arg}`,
          '17 subdomains from certificate transparency',
          `admin.${arg}:22   OPEN   ssh`,
          `vpn.${arg}:22     OPEN   ssh`,
          'mx records point to Google Workspace',
          '2 findings worth your attention',
        ], code: 0,
      }
    }
    case '': return { out: [], code: 0 }
    default: return { out: [], err: [`${head}: not a Morpheus command`, "try 'help'"], code: 127 }
  }
}

/* ── Provider ───────────────────────────────────────────────────────────── */

let seq = 0
const nextId = () => `s${++seq}`

// Numbered separately from the id sequence. Reusing the id counter meant the first session the
// owner opened was called "shell 7", because the seeded sessions had already consumed ids.
let shellNo = 0
const nextShellName = () => `shell ${++shellNo}`

function blank(name: string, origin: Origin, greet = false): Session {
  return {
    id: nextId(), name, origin, history: [], busy: false, last: '', openedAt: Date.now(),
    lines: greet ? [{ k: 'note', text: 'Morpheus console. Type help to see what it takes.' }] : [],
  }
}

// Mock sessions so the strip, the overflow and the compact list can all be reviewed with content.
function seedSessions(): Session[] {
  const main = blank('main', 'you', true)
  const scan = blank('scan', 'morpheus')
  scan.last = 'scan northwind-capital.com'
  scan.lines = [
    { k: 'cmd', text: 'scan northwind-capital.com' },
    { k: 'out', text: 'resolving northwind-capital.com' },
    { k: 'out', text: '6 subdomains from certificate transparency' },
    { k: 'exit', code: 0, ms: 1420 },
  ]
  const audit = blank('audit', 'you')
  audit.last = 'status'
  audit.lines = [
    { k: 'cmd', text: 'status' },
    { k: 'out', text: 'gate         sealed, 3 factors enrolled' },
    { k: 'exit', code: 0, ms: 210 },
  ]
  return [main, scan, audit]
}

export function MorpheusTerminalProvider({ children }: { children: ReactNode }) {
  const { openPanel } = useCanvas()
  const [sessions, setSessions] = useState<Session[]>(seedSessions)
  const [activeId, setActiveId] = useState<string>(() => sessions[0]?.id ?? '')
  const [live, setLive] = useState(true)
  const [mode, setMode] = useState<TermMode>('ask')

  const liveRef = useRef(live); liveRef.current = live
  const modeRef = useRef(mode); modeRef.current = mode
  const namesRef = useRef<string[]>([])
  namesRef.current = sessions.map(s => s.name)
  const sessionsRef = useRef(sessions)
  sessionsRef.current = sessions

  const patch = useCallback((id: string, fn: (s: Session) => Session) => {
    setSessions(prev => prev.map(s => (s.id === id ? fn(s) : s)))
  }, [])
  const push = useCallback((id: string, ...l: TermLine[]) => {
    patch(id, s => ({ ...s, lines: [...s.lines, ...l] }))
  }, [patch])

  /**
   * ONE TERMINAL IS ONE CANVAS ITEM.
   *
   * Sessions used to be tabs inside a single Console panel, which put a second, private tab
   * system inside a surface that already had one. Now each shell is an item in the rail on its
   * own footing, alongside documents and anything else the canvas holds, and switching between
   * them is the same gesture as switching to any other artifact.
   */
  const reveal = useCallback((sessionId: string, name: string, opts?: { quiet?: boolean }) => {
    openPanel(
      { id: `terminal:${sessionId}`, kind: 'terminal', title: name, sessionId },
      { reveal: !opts?.quiet },
    )
  }, [openPanel])

  const focusSession = useCallback((id: string) => {
    setActiveId(id)
    const s = sessionsRef.current.find(x => x.id === id)
    if (s) reveal(s.id, s.name)
  }, [reveal])

  const openSession = useCallback((opts?: { name?: string; origin?: Origin }) => {
    const s = blank(opts?.name ?? nextShellName(), opts?.origin ?? 'you')
    setSessions(prev => [...prev, s])
    setActiveId(s.id)
    reveal(s.id, s.name)
    return s.id
  }, [reveal])

  const closeSession = useCallback((id: string) => {
    setSessions(prev => {
      // Never leave the console with nothing in it; the last session is emptied rather than removed.
      if (prev.length <= 1) return [blank('main', 'you', true)]
      const next = prev.filter(s => s.id !== id)
      setActiveId(cur => {
        if (cur !== id) return cur
        const idx = prev.findIndex(s => s.id === id)
        return next[Math.max(0, Math.min(idx, next.length - 1))].id
      })
      return next
    })
  }, [])

  const clear = useCallback((sessionId?: string) => {
    const id = sessionId ?? activeId
    patch(id, s => ({ ...s, lines: [] }))
  }, [activeId, patch])

  const exec = useCallback(async (command: string, id: string) => {
    const cmd = command.trim()
    if (!cmd) return
    const s = sessionsRef.current.find(x => x.id === id)
    if (s) reveal(s.id, s.name)
    push(id, { k: 'cmd', text: cmd })
    patch(id, s => ({ ...s, last: cmd }))

    if (cmd === 'clear') { patch(id, s => ({ ...s, lines: [] })); return }

    // The kill switch is checked before anything else, so freezing execution is absolute.
    if (!liveRef.current) {
      push(id, { k: 'err', text: 'execution is frozen. Switch the console to Live to run anything.' })
      return
    }
    if (modeRef.current === 'plan') {
      push(id, { k: 'note', text: `would run: ${cmd}` },
        { k: 'note', text: 'Plan mode executes nothing. Switch to Ask or Auto to let it run.' })
      return
    }

    patch(id, s => ({ ...s, busy: true }))
    const started = Date.now()
    const { out, err, code } = respond(cmd, namesRef.current)

    for (const line of out) {
      await new Promise(r => setTimeout(r, 90))
      push(id, { k: 'out', text: line })
    }
    for (const line of err ?? []) {
      await new Promise(r => setTimeout(r, 70))
      push(id, { k: 'err', text: line })
    }
    push(id, { k: 'exit', code, ms: Date.now() - started })
    patch(id, s => ({ ...s, busy: false }))
  }, [push, patch, reveal])

  /**
   * Commands queue PER SESSION, and only per session.
   *
   * Two sessions are two shells and must run at the same time, which is the whole point of having
   * more than one. Within a session they must serialise: Morpheus can reach the same shell while
   * the owner is typing into it, and without a queue both streamed into the log at once, output
   * interleaved line by line and exit codes impossible to attribute.
   */
  const chains = useRef<Map<string, Promise<void>>>(new Map())
  const run = useCallback((command: string, sessionId?: string) => {
    const id = sessionId ?? activeId
    const prev = chains.current.get(id) ?? Promise.resolve()
    const next = prev.then(() => exec(command, id))
    chains.current.set(id, next.catch(() => undefined))
    return next
  }, [activeId, exec])

  // The shells that already exist appear in the rail on load, without the canvas opening itself.
  const seeded = useRef(false)
  useEffect(() => {
    if (seeded.current) return
    seeded.current = true
    sessionsRef.current.forEach(s => reveal(s.id, s.name, { quiet: true }))
  }, [reveal])

  const active = sessions.find(s => s.id === activeId)
  const anyBusy = sessions.some(s => s.busy)

  const value = useMemo<Ctx>(() => ({
    sessions, activeId, active, focusSession, openSession, closeSession,
    run, clear, live, setLive, mode, setMode, anyBusy,
  }), [sessions, activeId, active, focusSession, openSession, closeSession,
    run, clear, live, mode, anyBusy])

  return <TerminalContext.Provider value={value}>{children}</TerminalContext.Provider>
}

export function useTerminal() {
  const ctx = useContext(TerminalContext)
  if (!ctx) throw new Error('useTerminal must be used within MorpheusTerminalProvider')
  return ctx
}

/* ── Presentation ───────────────────────────────────────────────────────── */

const LINE_STYLE: Record<TermLine['k'], string> = {
  cmd: 'text-accent',
  out: 'text-text/85',
  err: 'text-danger',
  exit: 'text-muted',
  note: 'text-muted italic',
}

function prefixFor(l: TermLine): string {
  if (l.k === 'cmd') return '$ '
  if (l.k === 'err') return '! '
  if (l.k === 'note') return '# '
  return '  '
}

// 30px targets, not 24. The controls sit in a dense row and at 24 they were genuinely fiddly to
// hit; a window's own chrome is the last place to be stingy with hit area.
const ICON_BTN = `morph-tap grid h-[30px] w-[30px] shrink-0 place-items-center rounded-btn text-muted
  hover:bg-overlay/[0.07] hover:text-text`

function StatusDot({ s }: { s: Session }) {
  return (
    <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${
      s.busy ? 'animate-pulse bg-accent' : s.origin === 'morpheus' ? 'bg-purple/70' : 'bg-muted/50'}`} />
  )
}

/**
 * The compact list.
 *
 * Sessions overflow the strip long before they overflow this, so once there are more than a
 * handful this becomes the real way to move between them: one row each, with who opened it, what
 * it last ran, and whether it is still working.
 */
function SessionList({ onPick }: { onPick: () => void }) {
  const { sessions, activeId, focusSession, closeSession, openSession } = useTerminal()
  return (
    <div className="w-[292px] overflow-hidden rounded-card border border-border bg-panel py-1.5 shadow-popover">
      <p className="flex items-baseline justify-between px-3 pb-1 pt-0.5">
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted">Sessions</span>
        <span className="text-[10.5px] tabular-nums text-muted/70">{sessions.length} open</span>
      </p>
      <div className="max-h-[248px] overflow-y-auto">
        {sessions.map(s => (
          <div key={s.id}
            className={`group/row flex items-center gap-2 px-3 py-2 ${
              s.id === activeId ? 'bg-accent/[0.10]' : 'hover:bg-overlay/[0.06]'}`}
            style={{ transition: 'background-color var(--t) var(--ease)' }}>
            <StatusDot s={s} />
            <button onClick={() => { focusSession(s.id); onPick() }}
              className="min-w-0 flex-1 text-left outline-none">
              <span className="flex items-center gap-1.5">
                <span className={`truncate font-mono text-[12.5px] ${
                  s.id === activeId ? 'text-accent' : 'text-heading'}`}>{s.name}</span>
                {s.origin === 'morpheus' && (
                  <Bot size={10} className="shrink-0 text-purple/80" aria-label="Opened by Morpheus" />
                )}
              </span>
              <span className="mt-0.5 block truncate font-mono text-[11px] text-muted">
                {s.busy ? 'working' : s.last || 'no commands yet'}
              </span>
            </button>
            <button onClick={() => closeSession(s.id)} aria-label={`Close ${s.name}`}
              className="morph-reveal morph-tap grid h-7 w-7 shrink-0 place-items-center rounded-btn
                text-muted hover:bg-overlay/[0.07] hover:text-danger">
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
      <div className="mt-1 border-t border-border pt-1">
        <button onClick={() => { openSession(); onPick() }}
          className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12.5px] text-text
            hover:bg-overlay/[0.07] hover:pl-4"
          style={{ transition: 'background-color var(--t) var(--ease), padding-left var(--t) var(--ease)' }}>
          <Plus size={13} className="text-muted" /> New session
        </button>
      </div>
    </div>
  )
}

/** The session strip: a few tabs, then everything else behind a count. */
function SessionStrip() {
  const { sessions, activeId, focusSession, closeSession, openSession } = useTerminal()
  const [listOpen, setListOpen] = useState(false)

  // The active session is always on the strip, even when it would have overflowed.
  const shown = sessions.slice(0, MAX_TABS)
  if (!shown.some(s => s.id === activeId)) {
    const act = sessions.find(s => s.id === activeId)
    if (act) shown[MAX_TABS - 1] = act
  }
  const hidden = sessions.length - shown.length

  return (
    // Scrolls rather than squeezing. Letting the tabs flex down to nothing collapsed the session
    // names to zero width in a narrow window, which left them technically present and impossible
    // to click. A minimum width plus horizontal scroll keeps every tab usable at any size.
    <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
      {shown.map(s => (
        <div key={s.id}
          className={`group/tab flex w-[118px] shrink-0 items-center gap-1.5 rounded-btn px-2 py-1 ${
            s.id === activeId ? 'bg-accent/12 text-accent' : 'text-muted hover:bg-overlay/[0.06] hover:text-text'}`}
          style={{ transition: 'background-color var(--t) var(--ease), color var(--t) var(--ease)' }}>
          <StatusDot s={s} />
          {/* Stretches to the tab's full height so the padding around the label is clickable too,
              rather than only the 17px the text itself occupies. */}
          <button onClick={() => focusSession(s.id)} title={s.last || s.name}
            className="flex min-w-0 flex-1 items-center self-stretch truncate py-1 text-left
              font-mono text-[11.5px] outline-none">
            <span className="truncate">{s.name}</span>
          </button>
          {s.origin === 'morpheus' && <Bot size={11} className="shrink-0 opacity-70" />}
          <button onClick={() => closeSession(s.id)} aria-label={`Close ${s.name}`}
            className="morph-reveal grid h-6 w-6 shrink-0 place-items-center rounded hover:text-danger">
            <X size={12} />
          </button>
        </div>
      ))}

      <button onClick={() => openSession()} title="New session" aria-label="New session"
        className="morph-tap grid h-[30px] w-[30px] shrink-0 place-items-center rounded-btn text-muted
          hover:bg-overlay/[0.07] hover:text-text">
        <Plus size={15} />
      </button>

      {/* The compact list. Always reachable, and the only route to overflowed sessions. */}
      <div className="relative shrink-0">
        <button onClick={() => setListOpen(o => !o)} aria-haspopup="menu" aria-expanded={listOpen}
          aria-label="All sessions"
          className={`morph-tap flex h-[30px] shrink-0 items-center gap-1 rounded-btn px-2 text-[11.5px] ${
            hidden > 0 ? 'bg-overlay/[0.07] text-text' : 'text-muted hover:bg-overlay/[0.07] hover:text-text'}`}>
          {hidden > 0 ? `+${hidden}` : <span className="tabular-nums">{sessions.length}</span>}
          <ChevronDown size={11} className="morph-icon"
            style={{ transform: listOpen ? 'rotate(180deg)' : 'none' }} />
        </button>
        {listOpen && (
          <>
            <button className="fixed inset-0 z-20 cursor-default" aria-hidden onClick={() => setListOpen(false)} />
            <div className="absolute left-0 top-full z-30 mt-1.5">
              <SessionList onPick={() => setListOpen(false)} />
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/**
 * One shell.
 *
 * `sessionId` says which. There is no session strip here any more: each shell is its own item in
 * the canvas rail, so switching between them is the canvas's job, not a second tab bar hidden
 * inside a panel that already lives in one.
 */
export function TerminalPanel({ sessionId }: { sessionId?: string }) {
  const { sessions, activeId, live, setLive, mode, setMode, run, clear } = useTerminal()
  const id = sessionId ?? activeId
  const active = sessions.find(s => s.id === id)
  const [input, setInput] = useState('')
  const [hIdx, setHIdx] = useState(-1)
  const [modeOpen, setModeOpen] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const lines = active?.lines ?? []
  const history = active?.history ?? []
  const busy = active?.busy ?? false

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [lines])
  // Refocus when the shell changes, so typing continues where you are looking.
  useEffect(() => { inputRef.current?.focus(); setInput(''); setHIdx(-1) }, [id])

  const submit = () => {
    const cmd = input.trim()
    if (!cmd) return
    setHIdx(-1)
    setInput('')
    // Runs in THIS panel's shell, not whichever happens to be active elsewhere.
    void run(cmd, id)
  }

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); submit(); return }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      const next = Math.min(hIdx + 1, history.length - 1)
      if (next >= 0) { setHIdx(next); setInput(history[next]) }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      const next = hIdx - 1
      setHIdx(next)
      setInput(next >= 0 ? history[next] : '')
    }
  }

  return (
    <>
      {/* One line: which shell this is, then its controls. No session strip -- the canvas rail
          is where you move between shells. */}
      <div className="flex shrink-0 items-center gap-1.5 border-b border-border px-2.5 py-1.5">
        <TerminalSquare size={13} className="shrink-0 text-accent" />
        <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-heading">
          {active?.name ?? 'no shell'}
        </span>
        {active?.busy && (
          <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-accent/12 px-2 py-0.5
            text-[10.5px] text-accent">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> running
          </span>
        )}

        {/* Approval posture, in one button. */}
        <div className="relative shrink-0">
          <button onClick={() => setModeOpen(o => !o)} aria-haspopup="menu" aria-expanded={modeOpen}
            title={MODE[mode].hint}
            className="morph-tap flex h-[30px] shrink-0 items-center gap-1 rounded-btn px-2.5 text-[11.5px]
              font-medium text-muted hover:bg-overlay/[0.07] hover:text-text">
            {MODE[mode].label}
            <ChevronDown size={11} className="morph-icon"
              style={{ transform: modeOpen ? 'rotate(180deg)' : 'none' }} />
          </button>
          {modeOpen && (
            <>
              <button className="fixed inset-0 z-20 cursor-default" aria-hidden onClick={() => setModeOpen(false)} />
              <div role="menu" className="absolute right-0 top-full z-30 mt-1.5 w-[236px] overflow-hidden
                rounded-card border border-border bg-panel py-1.5 shadow-popover">
                {(['plan', 'ask', 'auto'] as TermMode[]).map(m => (
                  <button key={m} role="menuitemradio" aria-checked={mode === m}
                    onClick={() => { setMode(m); setModeOpen(false) }}
                    className={`block w-full px-3 py-1.5 text-left hover:bg-overlay/[0.07] ${
                      mode === m ? 'text-accent' : 'text-text'}`}>
                    <span className="block text-[12.5px]">{MODE[m].label}</span>
                    <span className="block text-[11px] text-muted">{MODE[m].hint}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <button onClick={() => setLive(!live)}
          title={live ? 'Freeze all execution' : 'Execution frozen. Click to allow commands again.'}
          aria-label={live ? 'Freeze execution' : 'Allow execution'}
          className={`morph-tap grid h-[30px] w-[30px] shrink-0 place-items-center rounded-btn ${
            live ? 'text-success hover:bg-success/12' : 'bg-danger/15 text-danger'}`}>
          <Power size={14} />
        </button>
        <button onClick={() => clear(id)} title="Clear this session" aria-label="Clear this session"
          className={`${ICON_BTN} hover:text-warning`}>
          <Trash2 size={14} />
        </button>
      </div>

      {/* Log */}
      <div ref={logRef} data-scroll
        className="min-h-0 flex-1 overflow-y-auto px-3 py-2.5 font-mono text-[12px] leading-[1.62]">
        {lines.length === 0 && !busy && (
          <p className="text-[12px] italic text-muted/70"># empty session. Type help to see what it takes.</p>
        )}
        {lines.map((l, i) => (
          <p key={i} className={`whitespace-pre-wrap break-words ${LINE_STYLE[l.k]}`}>
            {l.k === 'exit'
              ? `  exit ${l.code} in ${(l.ms / 1000).toFixed(2)}s`
              : `${prefixFor(l)}${l.text}`}
          </p>
        ))}
        {busy && (
          <p className="flex items-center gap-2 text-[12px] text-muted">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> working
          </p>
        )}
      </div>

      {/* Prompt */}
      <div className="flex shrink-0 items-center gap-2 border-t border-border px-3 py-2">
        <span className="shrink-0 font-mono text-[12px] text-accent">
          {active?.name ?? 'morpheus'} $
        </span>
        <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKey}
          spellCheck={false} autoComplete="off" aria-label="Console command"
          placeholder={live ? 'type a command, or help' : 'execution is frozen'}
          className="min-w-0 flex-1 bg-transparent font-mono text-[12px] text-heading outline-none
            placeholder:text-muted/60" />
        {busy ? (
          <span className="flex shrink-0 items-center gap-1.5 text-[11px] text-muted">
            <Square size={10} /> running
          </span>
        ) : (
          <button onClick={submit} disabled={!input.trim()} aria-label="Run command"
            className="morph-tap grid h-[30px] w-[30px] shrink-0 place-items-center rounded-btn text-muted
              hover:bg-overlay/[0.07] hover:text-accent disabled:opacity-30">
            <CornerDownLeft size={14} />
          </button>
        )}
      </div>
    </>
  )
}

/* ── Frames ─────────────────────────────────────────────────────────────── */


/** The console filling its own browser tab. */
export function TerminalStandalone() {
  return (
    <div className="flex h-full flex-col overflow-hidden bg-[rgb(var(--panel))]">
      <TerminalPanel />
    </div>
  )
}
