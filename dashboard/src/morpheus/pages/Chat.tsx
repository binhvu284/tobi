// Morpheus Chat.
//
// Reuses TOBI's `MarkdownView` rather than reimplementing it: headings, GFM tables, lists,
// blockquotes, fenced code with copy, and per-block memoisation so a long streaming reply does
// not re-parse itself on every tick. It is written entirely against theme tokens, so dropped
// into Morpheus it adopts Morpheus's palette.
//
// The conversation layout follows the shape the owner asked for, which is also what the current
// generation of assistants converged on:
//
//   PROMPTS SIT RIGHT, in a contained bubble. Answers sit left and run full width with no bubble.
//   The asymmetry does the work an avatar used to: you can see who said what from the shape of
//   the page alone, and the answer gets the whole column for tables and code.
//
//   THINKING IS A SHIMMER, not a spinner. A highlight travels through the word while an elapsed
//   counter runs. Once the answer lands it collapses to "Thought for 4.2s", which is a summary
//   you can reopen rather than a state that vanishes.
//
//   TOOL STEPS ARE A RAIL, in the manner of Claude Code and Codex: a vertical line, one row per
//   call, the tool name in mono with its target beside it, the result indented underneath, and a
//   duration on the right. Running steps pulse; finished steps get a tick. It is dense, scannable
//   and honest about what was actually done.
//
// SHELL ONLY: replies come from a local scripted streamer so streaming, stopping, settling and
// promotion can all be reviewed. Swapping in the real endpoint touches `send` alone.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowUp, Paperclip, ChevronDown, ChevronRight, Plus, ScanSearch, MessageSquare, Trash2,
  Square, ArrowDown, Copy, Check, Globe, Server, ShieldAlert, FileSearch, CornerDownRight,
  TerminalSquare, PanelRight, PanelLeftClose, PanelLeftOpen, Pencil, Files, ChevronUp,
} from 'lucide-react'
import {
  useCanvas, panelIcon, panelTone, CanvasDock, CanvasRail, CanvasFloat,
} from '../MorpheusCanvas'
import CanvasContent from '../CanvasContent'
import { useMorpheus } from '../MorpheusSession'
import { useFeedback } from '../MorpheusFeedback'
import { useTerminal } from '../MorpheusTerminal'
import { ActionButton } from '../../components/async-ui'
import MarkdownView from '../../components/chat/MarkdownView'
import { Empty, Failure, Skeleton, Badge } from '../ui'

type StepIcon = 'web' | 'dns' | 'breach' | 'read' | 'shell'
type Step = {
  id: string
  tool: string
  target: string
  result: string
  ms: number
  icon: StepIcon
  /** Set when the step reaches the shell. Runs in the console, visibly. */
  command?: string
}
type Msg = {
  id: string
  role: 'you' | 'morpheus'
  body: string
  steps?: Step[]
  /** Total time spent before the first token, in seconds. */
  thoughtFor?: number
  entities?: string[]
}
type Thread = { id: string; title: string; when: string; messages: Msg[] }

const STEP_ICON: Record<StepIcon, typeof Globe> = {
  web: Globe, dns: Server, breach: ShieldAlert, read: FileSearch, shell: TerminalSquare,
}

// Sample run. Markdown so the renderer has real structure, and steps so the rail has real work.
const SCRIPTED_STEPS: Step[] = [
  { id: 's1', tool: 'web_search', target: '"acme-robotics.com"', result: '14 results, 6 worth reading', ms: 940, icon: 'web' },
  { id: 's2', tool: 'read_dns', target: 'MX, TXT, A records', result: 'Google Workspace, 17 subdomains', ms: 310, icon: 'dns' },
  // The one step that reaches the shell. It opens the console on its own: an agent with access
  // to a terminal should never use it somewhere the owner cannot see.
  { id: 's3', tool: 'run_command', target: 'scan acme-robotics.com', result: '2 admin hosts answering on 22', ms: 620, icon: 'shell', command: 'scan acme-robotics.com' },
  { id: 's4', tool: 'breach_index', target: 'first.last@acme-robotics.com', result: '1 match, 2023 dump', ms: 1180, icon: 'breach' },
]

const SCRIPTED_BODY = `Straight answer: **moderate exposure**, and you can close most of it in a week.

### The three real holes

| # | Hole | Why it matters |
| --- | --- | --- |
| 1 | Two admin subdomains answer on port 22 | A login surface facing the whole internet for no reason |
| 2 | Staff email pattern is \`first.last\` | Guessable, and one address is already in a 2023 breach dump |
| 3 | DNS leaks your mail provider | Hands an attacker the right phishing template |

### What I would do

1. Close 22 at the firewall. Five minutes, removes the worst of it.
2. Force a reset on the exposed address and check it is not reused anywhere.
3. Accept the third one knowingly, or move the record behind a proxy.

> None of this needs a consultant. It needs an afternoon.

If you want the full footprint with sources, promote the domain into an object.`

/* ── Thinking ───────────────────────────────────────────────────────────── */

/** The live indicator: shimmering label, running clock, and the rail building underneath. */
function Thinking({ startedAt, steps }: { startedAt: number; steps: Step[] }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const id = window.setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 100)
    return () => window.clearInterval(id)
  }, [startedAt])

  return (
    <div>
      <p className="flex items-baseline gap-2.5 text-[13px] font-medium">
        <span className="morph-shimmer">Thinking</span>
        <span className="font-mono text-[11px] tabular-nums text-muted/70">{elapsed.toFixed(1)}s</span>
      </p>
      {steps.length > 0 && <Rail steps={steps} running />}
    </div>
  )
}

/**
 * The step rail.
 *
 * One row per tool call against a single hairline, the tool in mono, its target beside it, the
 * result indented underneath and the duration right-aligned. The last row is left open while the
 * run is live so the line reads as still descending rather than closed off.
 */
function Rail({ steps, running = false }: { steps: Step[]; running?: boolean }) {
  return (
    <ol className="relative mt-3 space-y-3 pl-[18px]">
      {/* The rail itself. Stops short of the final marker while running. */}
      <span aria-hidden
        className="absolute left-[4px] top-[7px] w-px bg-border"
        style={{ bottom: running ? 18 : 8 }} />
      {steps.map((s, i) => {
        const Icon = STEP_ICON[s.icon]
        const live = running && i === steps.length - 1
        return (
          <li key={s.id} className="morph-rise relative" style={{ animationDelay: '0s' }}>
            <span aria-hidden
              className={`absolute -left-[18px] top-[6px] block h-[7px] w-[7px] rounded-full ${
                live ? 'morph-ping bg-accent text-accent' : 'bg-accent/60'}`} />
            <div className="flex items-baseline gap-2">
              <Icon size={12} className="shrink-0 translate-y-[2px] text-muted" />
              <span className="font-mono text-[12px] text-heading">{s.tool}</span>
              <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-muted">{s.target}</span>
              <span className="shrink-0 font-mono text-[10.5px] tabular-nums text-muted/70">
                {(s.ms / 1000).toFixed(1)}s
              </span>
            </div>
            <p className="mt-0.5 flex items-start gap-1.5 text-[12px] leading-relaxed text-text/70">
              <CornerDownRight size={11} className="mt-[3px] shrink-0 text-muted/60" />
              {s.result}
            </p>
          </li>
        )
      })}
    </ol>
  )
}

/** Once the answer lands, the run collapses to a line you can reopen. */
function Thought({ seconds, steps }: { seconds: number; steps: Step[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mb-3">
      <button onClick={() => setOpen(o => !o)} aria-expanded={open}
        className="flex items-center gap-1.5 text-[12.5px] text-muted hover:text-text">
        <ChevronRight size={13} className="morph-icon" style={{ transform: open ? 'rotate(90deg)' : 'none' }} />
        Thought for {seconds.toFixed(1)}s
        <span className="text-muted/60">· {steps.length} steps</span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden">
            <Rail steps={steps} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ── Messages ───────────────────────────────────────────────────────────── */

function Prompt({ body }: { body: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[78%] rounded-card rounded-br-[4px] border border-border bg-surface/80
        px-4 py-2.5 text-[14px] leading-[1.6] text-text">
        <p className="whitespace-pre-wrap">{body}</p>
      </div>
    </div>
  )
}

function Reply({ msg, text, streaming }: { msg: Msg; text: string; streaming: boolean }) {
  const navigate = useNavigate()
  const { announce } = useFeedback()
  const { openPanel } = useCanvas()
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(msg.body)
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch {
      announce({ tone: 'warn', title: 'Could not reach the clipboard' })
    }
  }

  const promote = (e: string) => {
    announce({ tone: 'info', title: 'Object created', detail: `Building a profile for ${e}.` })
    navigate(`/morpheus/osint/${encodeURIComponent(e)}`)
  }

  return (
    <div className="group/msg">
      {/* Stays visible while the answer streams. The work is already done by the time the first
          token lands, and hiding the record of it until the reply finishes means the reader
          watches text arrive with no idea what produced it. */}
      {msg.thoughtFor !== undefined && msg.steps?.length ? (
        <Thought seconds={msg.thoughtFor} steps={msg.steps} />
      ) : null}

      <MarkdownView content={text} />
      {streaming && (
        <span className="ml-0.5 inline-block h-[15px] w-[2px] translate-y-[3px] animate-blink bg-accent" />
      )}

      {!streaming && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button onClick={copy} title="Copy this answer"
            className="morph-tap inline-flex items-center gap-1.5 rounded-btn border border-border px-2.5 py-1
              text-[12px] text-muted outline-none hover:-translate-y-px hover:border-accent/45 hover:text-accent">
            {copied ? <Check size={11} className="text-success" /> : <Copy size={11} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          {/* Any answer can be sent to the canvas, where it sits beside the conversation as a
              document you can keep open while you carry on talking. */}
          <button
            onClick={() => {
              openPanel({ kind: 'markdown', title: 'Answer.md', body: msg.body })
              announce({ tone: 'info', title: 'Opened on the canvas', detail: 'It stays there while you keep talking.' })
            }}
            title="Open this answer on the canvas"
            className="morph-tap inline-flex items-center gap-1.5 rounded-btn border border-border px-2.5 py-1
              text-[12px] text-muted outline-none hover:-translate-y-px hover:border-warning/50 hover:text-warning">
            <PanelRight size={11} />
            Canvas
          </button>
          {msg.entities?.map(e => (
            <button key={e} onClick={() => promote(e)}
              className="morph-tap inline-flex items-center gap-1.5 rounded-btn border border-border px-2.5 py-1
                text-[12px] text-text outline-none hover:-translate-y-px hover:border-accent/50 hover:text-accent">
              <ScanSearch size={11} />
              Profile {e}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Header ─────────────────────────────────────────────────────────────── */

/**
 * The conversation's header, matching what TOBI's Chat carries: a title you can rename in place,
 * a one-line objective for the session, and the artifacts it has produced.
 *
 * The artifacts menu is the answer to "where did that go". Anything Morpheus produces during a
 * conversation lands on the canvas, and the canvas can be closed; without a list attached to the
 * conversation itself, closing it would make the work feel lost even though it is still held.
 */
function ChatHeader({ title, onRename, objective, onObjective, sidebarOpen, onToggleSidebar }: {
  title: string
  onRename: (t: string) => void
  objective: string
  onObjective: (o: string) => void
  sidebarOpen: boolean
  onToggleSidebar: () => void
}) {
  const { panels, focusPanel, mode, setMode } = useCanvas()
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(title)
  const [objEditing, setObjEditing] = useState(false)
  const [objVal, setObjVal] = useState(objective)
  const [filesOpen, setFilesOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  const commit = () => { setEditing(false); if (val.trim()) onRename(val.trim()) }
  const commitObj = () => { setObjEditing(false); onObjective(objVal.trim()) }

  return (
    <header className="shrink-0 border-b border-border px-4 py-2.5">
      <div className="flex items-center gap-2">
        <button onClick={onToggleSidebar}
          title={sidebarOpen ? 'Hide the conversation list' : 'Show the conversation list'}
          aria-label={sidebarOpen ? 'Hide the conversation list' : 'Show the conversation list'}
          className="morph-tap hidden h-[30px] w-[30px] place-items-center rounded-btn text-muted
            hover:bg-overlay/[0.07] hover:text-text md:grid">
          {sidebarOpen ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
        </button>

        {editing ? (
          <input autoFocus value={val} onChange={e => setVal(e.target.value)} onBlur={commit}
            onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false) }}
            aria-label="Conversation title"
            className="min-w-0 flex-1 rounded-input border border-accent/50 bg-bg px-2 py-1
              text-[14px] text-heading outline-none" />
        ) : (
          <button onClick={() => { setVal(title); setEditing(true) }} title="Rename this conversation"
            className="group/t flex min-w-0 flex-1 items-center gap-2 rounded-btn px-1 py-1 text-left
              outline-none hover:bg-overlay/[0.05]">
            <span className="truncate text-[14px] font-medium text-heading">{title}</span>
            <Pencil size={11} className="morph-reveal shrink-0 text-muted" />
          </button>
        )}

        {/* Session artifacts */}
        <div className="relative shrink-0">
          <button onClick={() => setFilesOpen(o => !o)} aria-haspopup="menu" aria-expanded={filesOpen}
            title="Files and artifacts from this conversation"
            className={`morph-tap flex h-[30px] items-center gap-1.5 rounded-btn border px-2.5 text-[12px] ${
              panels.length ? 'border-border text-text hover:border-accent/45 hover:text-accent'
                            : 'border-border text-muted hover:text-text'}`}>
            <Files size={13} />
            Files
            {panels.length > 0 && (
              <span className="rounded-full bg-overlay/[0.10] px-1.5 text-[10.5px] tabular-nums">
                {panels.length}
              </span>
            )}
          </button>
          {filesOpen && (
            <>
              <button className="fixed inset-0 z-20 cursor-default" aria-hidden onClick={() => setFilesOpen(false)} />
              <div role="menu" className="absolute right-0 top-full z-30 mt-1.5 w-[276px] overflow-hidden
                rounded-card border border-border bg-panel py-1.5 shadow-popover">
                <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted">
                  This conversation
                </p>
                {panels.length === 0 ? (
                  <p className="px-3 py-2 text-[12px] leading-relaxed text-muted">
                    Nothing yet. Consoles and documents Morpheus produces are kept here.
                  </p>
                ) : panels.map(p => {
                  const Icon = panelIcon(p.kind)
                  return (
                    <button key={p.id} role="menuitem"
                      onClick={() => { focusPanel(p.id); setFilesOpen(false) }}
                      className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-text
                        hover:bg-overlay/[0.07] hover:pl-4"
                      style={{ transition: 'background-color var(--t) var(--ease), padding-left var(--t) var(--ease)' }}>
                      <Icon size={14} className={`shrink-0 ${panelTone(p.kind)}`} />
                      <span className="min-w-0 flex-1 truncate">{p.title}</span>
                    </button>
                  )
                })}
                <div className="mt-1 border-t border-border pt-1">
                  <button role="menuitem"
                    onClick={() => { setMode(mode === 'rail' ? 'docked' : 'rail'); setFilesOpen(false) }}
                    className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[12.5px] text-muted
                      hover:bg-overlay/[0.07] hover:text-text">
                    <PanelRight size={13} />
                    {mode === 'rail' ? 'Open the canvas' : 'Put the canvas away'}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        <button onClick={() => setCollapsed(c => !c)}
          title={collapsed ? 'Show the objective' : 'Hide the objective'}
          aria-label={collapsed ? 'Show the objective' : 'Hide the objective'}
          className="morph-tap grid h-[30px] w-[30px] shrink-0 place-items-center rounded-btn text-muted
            hover:bg-overlay/[0.07] hover:text-text">
          <ChevronUp size={14} className="morph-icon"
            style={{ transform: collapsed ? 'rotate(180deg)' : 'none' }} />
        </button>
      </div>

      {!collapsed && (
        objEditing ? (
          <input autoFocus value={objVal} onChange={e => setObjVal(e.target.value)} onBlur={commitObj}
            onKeyDown={e => { if (e.key === 'Enter') commitObj(); if (e.key === 'Escape') setObjEditing(false) }}
            placeholder="What is this conversation for?"
            aria-label="Conversation objective"
            className="mt-1.5 w-full rounded-input border border-accent/50 bg-bg px-2 py-1 text-[12.5px]
              text-text outline-none" />
        ) : (
          <button onClick={() => { setObjVal(objective); setObjEditing(true) }}
            className="mt-1 w-full truncate rounded px-1 py-0.5 text-left text-[12.5px] text-muted
              outline-none hover:bg-overlay/[0.05] hover:text-text">
            {objective || 'Set an objective for this conversation'}
          </button>
        )
      )}
    </header>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */

export default function Chat() {
  const { models, preview } = useMorpheus()
  const { announce, confirm } = useFeedback()
  const { run: runCommand, openSession } = useTerminal()
  const [params, setParams] = useSearchParams()
  const admitted = models.filter(m => m.admitted)
  const [modelId, setModelId] = useState(admitted.find(m => m.active)?.id ?? admitted[0]?.id ?? '')
  const [picker, setPicker] = useState(false)
  const [threads, setThreads] = useState<Thread[]>([])
  const [activeThread, setActiveThread] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [objective, setObjective] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    try { return localStorage.getItem('morpheus.chat.sidebar') !== '0' } catch { return true }
  })
  useEffect(() => {
    try { localStorage.setItem('morpheus.chat.sidebar', sidebarOpen ? '1' : '0') } catch { /* ignore */ }
  }, [sidebarOpen])

  /** The run in progress: thinking, with steps arriving one at a time. */
  const [run, setRun] = useState<{ at: number; replyId: string; steps: Step[] } | null>(null)
  /** The reply currently being written out. */
  const [live, setLive] = useState<{ id: string; full: string; shown: number } | null>(null)

  const endRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const atBottomRef = useRef(true)
  const [atBottom, setAtBottom] = useState(true)
  const timers = useRef<number[]>([])

  const thread = threads.find(t => t.id === activeThread) ?? null
  const model = admitted.find(m => m.id === modelId)
  const busy = !!run || !!live

  useEffect(() => () => { timers.current.forEach(window.clearTimeout); timers.current = [] }, [])

  /* Scroll anchoring: only follow when the reader is already at the bottom. Yanking someone back
     down while they re-read an earlier answer is the worst thing a chat UI can do. */
  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const bottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    atBottomRef.current = bottom
    setAtBottom(bottom)
  }
  const jumpToLatest = () => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
    atBottomRef.current = true
    setAtBottom(true)
  }
  useEffect(() => {
    if (atBottomRef.current) endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [thread?.messages.length, live?.shown, run?.steps.length])

  /* Composer auto-grow. The zero guard matters: when the textarea is not laid out yet (hidden
     tab, route transition) scrollHeight reads 0, and pinning that collapses it to nothing. */
  useLayoutEffect(() => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    if (!el.scrollHeight) { el.style.height = ''; return }
    el.style.height = `${Math.min(Math.max(el.scrollHeight, 24), 200)}px`
  }, [draft])

  /* The scripted stream. */
  useEffect(() => {
    if (!live) return
    if (live.shown >= live.full.length) { setLive(null); return }
    const id = window.setTimeout(() => {
      setLive(l => (l ? { ...l, shown: Math.min(l.full.length, l.shown + 5) } : l))
    }, 16)
    return () => window.clearTimeout(id)
  }, [live])

  const send = useCallback((body: string) => {
    const text = body.trim()
    if (!text || busy) return
    const you: Msg = { id: `y${Date.now()}`, role: 'you', body: text }
    const replyId = `m${Date.now()}`
    const reply: Msg = { id: replyId, role: 'morpheus', body: SCRIPTED_BODY, entities: ['acme-robotics.com'] }
    const startedAt = Date.now()

    setThreads(prev => {
      const existing = prev.find(t => t.id === activeThread)
      if (existing) {
        return prev.map(t => (t.id === existing.id ? { ...t, messages: [...t.messages, you, reply] } : t))
      }
      const t: Thread = {
        id: `t${Date.now()}`,
        title: text.length > 40 ? `${text.slice(0, 40)}...` : text,
        when: 'Just now', messages: [you, reply],
      }
      setActiveThread(t.id)
      return [t, ...prev]
    })
    setDraft('')
    setRun({ at: startedAt, replyId, steps: [] })

    // Steps arrive one at a time, each after its own duration, so the rail builds the way a real
    // tool loop would rather than appearing complete.
    let acc = 420
    SCRIPTED_STEPS.forEach(step => {
      acc += step.ms
      timers.current.push(window.setTimeout(() => {
        setRun(r => (r && r.replyId === replyId ? { ...r, steps: [...r.steps, step] } : r))
        // A step that reaches the shell gets its OWN session, named after the tool, and the
        // console opens to show it. Two reasons: the owner sees the command at the moment it
        // happens rather than in a later summary, and an agent's output never lands in the middle
        // of whatever the owner is typing somewhere else.
        if (step.command) {
          const sid = openSession({ name: step.command.split(/\s+/)[0], origin: 'morpheus' })
          void runCommand(step.command, sid)
        }
      }, acc))
    })

    timers.current.push(window.setTimeout(() => {
      setRun(r => {
        if (r?.replyId !== replyId) return r
        const secs = (Date.now() - startedAt) / 1000
        setThreads(prev => prev.map(t => ({
          ...t,
          messages: t.messages.map(m =>
            m.id === replyId ? { ...m, steps: SCRIPTED_STEPS, thoughtFor: secs } : m),
        })))
        setLive({ id: replyId, full: SCRIPTED_BODY, shown: 0 })
        return null
      })
    }, acc + 500))
  }, [activeThread, busy, runCommand, openSession])

  /**
   * Stop generating.
   *
   * The partial text has to be committed into the message. Without it the reply falls back to its
   * full stored body the moment streaming state clears, so Stop revealed the entire answer
   * instantly, which is the opposite of stopping. A reply stopped before it wrote anything is
   * removed rather than left as a blank turn.
   */
  const stop = useCallback(() => {
    timers.current.forEach(window.clearTimeout)
    timers.current = []
    if (live) {
      const cut = live.full.slice(0, live.shown)
      setThreads(prev => prev.map(t => ({
        ...t,
        messages: cut.trim()
          ? t.messages.map(m => (m.id === live.id ? { ...m, body: cut, entities: undefined } : m))
          : t.messages.filter(m => m.id !== live.id),
      })))
    }
    if (run) {
      const id = run.replyId
      setThreads(prev => prev.map(t => ({ ...t, messages: t.messages.filter(m => m.id !== id) })))
    }
    setRun(null)
    setLive(null)
    announce({ tone: 'info', title: 'Stopped', detail: 'The reply was cut where it stood.' })
  }, [live, run, announce])

  useEffect(() => {
    const q = params.get('q')
    if (!q) return
    send(q)
    setParams({}, { replace: true })
  }, [params, send, setParams])

  const remove = async (id: string, title: string) => {
    const ok = await confirm({
      title: 'Delete this conversation?',
      body: `"${title}" and everything in it is removed. This cannot be undone.`,
      confirmLabel: 'Delete', tone: 'danger',
    })
    if (!ok) return
    setThreads(p => p.filter(t => t.id !== id))
    if (activeThread === id) setActiveThread(null)
    announce({ tone: 'ok', title: 'Conversation deleted' })
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Conversations. Collapsible, and the choice is remembered: a list you have deliberately
          hidden should stay hidden the next time you open Chat. */}
      {/* Collapse is structural, not animated.
          Width was originally a `w-[220px]` / `w-0` class swap with a transition, and it could
          appear stuck open: a CSS transition does not advance while the tab is in the background,
          so the width sat at its starting value indefinitely. Layout state must never depend on
          an animation completing, so the column simply is the width it should be. */}
      <aside
        style={{ width: sidebarOpen ? 220 : 0, minWidth: 0 }}
        className={`hidden flex-col overflow-hidden bg-panel/40 md:flex ${
          sidebarOpen ? 'border-r border-border' : ''}`}>
        <div className="p-2.5">
          <button onClick={() => { setActiveThread(null); setDraft('') }}
            className="morph-tap flex w-full items-center gap-2 rounded-btn border border-border px-3 py-2
              text-[12.5px] text-text outline-none hover:border-accent/45 hover:text-accent
              focus-visible:ring-2 focus-visible:ring-accent/50">
            <Plus size={14} />
            New conversation
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {preview === 'loading' ? (
            <div className="px-0.5 pt-2"><Skeleton rows={3} /></div>
          ) : threads.length === 0 ? (
            <p className="px-2.5 py-3 text-[12px] leading-relaxed text-muted">
              Nothing yet. Conversations are kept here, encrypted, for you alone.
            </p>
          ) : threads.map(t => (
            <div key={t.id}
              style={{ transition: 'background-color var(--t) var(--ease)' }}
              className={`group mb-0.5 flex items-start gap-2 rounded-btn px-2.5 py-2 ${
              t.id === activeThread ? 'bg-accent/[0.11] text-heading' : 'text-muted hover:bg-overlay/[0.05]'}`}>
              <button onClick={() => setActiveThread(t.id)}
                className="flex min-w-0 flex-1 items-start gap-2.5 text-left outline-none">
                <MessageSquare size={13} className="mt-0.5 shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px]">{t.title}</span>
                  <span className="block text-[11px] text-muted">{t.when}</span>
                </span>
              </button>
              <ActionButton onAction={() => remove(t.id, t.title)} title={`Delete ${t.title}`}
                icon={<Trash2 size={12} />}
                className="morph-reveal morph-tap mt-0.5 shrink-0 rounded p-0.5 text-muted
                  outline-none hover:text-danger" />
            </div>
          ))}
        </div>
      </aside>

      {/* Thread */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        <ChatHeader
          title={thread?.title ?? 'New conversation'}
          onRename={t => setThreads(p => p.map(x => (x.id === activeThread ? { ...x, title: t } : x)))}
          objective={objective}
          onObjective={setObjective}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(o => !o)} />

        <div ref={scrollRef} onScroll={onScroll} data-scroll className="min-h-0 flex-1 overflow-y-auto">
          {preview === 'failure' ? (
            <div className="mx-auto max-w-3xl px-7 py-8"><Failure what="This conversation" /></div>
          ) : !thread ? (
            <Empty icon={<MessageSquare size={19} />} title="Ask anything"
              body="Nothing here is filtered, sent anywhere else, or softened. Morpheus answers the question you actually asked." />
          ) : (
            <div className="mx-auto max-w-3xl space-y-7 px-7 py-9">
              {thread.messages.map(m => {
                if (m.role === 'you') return <Prompt key={m.id} body={m.body} />
                const isLive = live?.id === m.id
                // While the run is still thinking, its reply has nothing to show yet.
                if (run?.replyId === m.id) return null
                return (
                  <Reply key={m.id} msg={m}
                    text={isLive ? live.full.slice(0, live.shown) : m.body}
                    streaming={!!isLive} />
                )
              })}

              {run && <Thinking startedAt={run.at} steps={run.steps} />}

              <div ref={endRef} />
            </div>
          )}
        </div>

        <AnimatePresence>
          {!atBottom && thread && (
            <motion.button
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              onClick={jumpToLatest}
              className="morph-tap absolute bottom-[104px] left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5
                rounded-full border border-border bg-panel px-3 py-1.5 text-[12px] text-text shadow-popover
                hover:border-accent/50 hover:text-accent">
              <ArrowDown size={12} /> Jump to latest
            </motion.button>
          )}
        </AnimatePresence>

        {/* Composer */}
        <div className="shrink-0 border-t border-border px-7 py-4">
          <div className="mx-auto max-w-3xl rounded-card border border-border bg-surface/70 px-3.5 py-2.5
            transition-colors duration-[var(--t)] focus-within:border-accent/55"
            style={{ transitionTimingFunction: 'var(--ease)' }}>
            <textarea
              ref={taRef}
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(draft) } }}
              rows={1}
              aria-label="Message Morpheus"
              placeholder="Ask Morpheus anything."
              className="w-full resize-none overflow-y-auto bg-transparent text-[14px] leading-relaxed
                text-heading outline-none placeholder:text-muted/70" />
            <div className="mt-2 flex items-center gap-1.5">
              <button aria-label="Attach a file" title="Attach a file"
                onClick={() => announce({ tone: 'info', title: 'Attachments', detail: 'Files, images and links are read and encrypted the moment they land.' })}
                className="morph-tap grid h-7 w-7 place-items-center rounded-btn text-muted outline-none
                  hover:bg-overlay/[0.07] hover:text-text">
                <Paperclip size={14} />
              </button>

              <div className="relative">
                <button onClick={() => setPicker(o => !o)} aria-haspopup="listbox" aria-expanded={picker}
                  className="morph-tap flex h-7 items-center gap-1.5 rounded-btn px-2 text-[12px] text-muted
                    outline-none hover:bg-overlay/[0.07] hover:text-text">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  {model?.name ?? 'No model'}
                  <ChevronDown size={12} className="morph-icon"
                    style={{ transform: picker ? 'rotate(180deg)' : 'none' }} />
                </button>
                {picker && (
                  <>
                    <button className="fixed inset-0 z-20 cursor-default" aria-hidden onClick={() => setPicker(false)} />
                    <motion.div role="listbox"
                      initial={{ opacity: 0, y: 6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                      className="absolute bottom-full left-0 z-30 mb-2 w-[268px] overflow-hidden
                        rounded-card border border-border bg-panel py-1.5 shadow-popover">
                      <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted">
                        Verified models
                      </p>
                      {admitted.length === 0 ? (
                        <p className="px-3 py-2 text-[12.5px] text-muted">None verified yet.</p>
                      ) : admitted.map(m => (
                        <button key={m.id} role="option" aria-selected={m.id === modelId}
                          onClick={() => {
                            setModelId(m.id); setPicker(false)
                            announce({ tone: 'ok', title: 'Model switched', detail: `${m.name} is now answering.` })
                          }}
                          className={`flex w-full items-baseline gap-2 px-3 py-2 text-left text-[13px]
                            hover:bg-overlay/[0.07] hover:pl-4 ${m.id === modelId ? 'text-accent' : 'text-text'}`}
                          style={{ transition: 'background-color var(--t) var(--ease), padding-left var(--t) var(--ease), color var(--t) var(--ease)' }}>
                          <span className="min-w-0 flex-1 truncate">{m.name}</span>
                          <span className="shrink-0 tabular-nums text-[11px] text-muted">freedom {m.freedom}</span>
                        </button>
                      ))}
                    </motion.div>
                  </>
                )}
              </div>

              <Badge tone="accent">Unrestricted</Badge>

              {busy ? (
                <button onClick={stop} title="Stop generating" aria-label="Stop generating"
                  className="morph-tap ml-auto grid h-7 w-7 place-items-center rounded-btn border
                    border-danger/50 bg-danger/15 text-danger outline-none hover:bg-danger/25">
                  <Square size={12} />
                </button>
              ) : (
                <button onClick={() => send(draft)} disabled={!draft.trim()} aria-label="Send"
                  className="morph-tap ml-auto grid h-7 w-7 place-items-center rounded-btn bg-accent text-bg
                    outline-none hover:bg-accent/90 active:scale-95 focus-visible:ring-2
                    focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg
                    disabled:cursor-not-allowed disabled:opacity-30">
                  <ArrowUp size={14} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* The canvas lives here, beside the conversation it belongs to. Docked it takes width from
          the thread; at rest it is the rail on the right edge. */}
      <CanvasDock><CanvasContent /></CanvasDock>
      <CanvasRail onNewShell={() => openSession()} />
      <CanvasFloat><CanvasContent /></CanvasFloat>
    </div>
  )
}
