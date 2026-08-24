// The Canvas.
//
// A second surface beside the page: Morpheus works on the left, the canvas shows you what it is
// working ON. The console was the first thing to need it, but it is deliberately not a terminal
// feature. It is a host, and the terminal is simply the first kind of thing it holds.
//
// Three states, and the transitions between them are the point:
//
//   DOCKED    a column on the right. It SHARES the width rather than covering the page, so the
//             chat reflows beside it and nothing is hidden behind a floating window.
//   FLOATING  pull it out by the grip and it becomes a window you can put anywhere and resize
//             from any edge.
//   CLOSED    gone, with its contents kept so reopening returns you to where you were.
//
// Dragging the floating window back toward the right edge re-docks it, with the landing zone
// lit up before you let go. Windows that can only be undocked are a one-way door.
//
// Adding a new kind of content means adding one entry to `RENDERERS` and nothing else.
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode,
} from 'react'
import { motion, AnimatePresence, useMotionValue, type PanInfo } from 'framer-motion'
import {
  X, PanelRight, Minimize2, ExternalLink, GripVertical, TerminalSquare, FileText,
  ChevronsLeft, ChevronsRight, Plus,
} from 'lucide-react'

export type PanelKind = 'terminal' | 'markdown'

export type CanvasPanel = {
  id: string
  kind: PanelKind
  title: string
  /** Kind-specific payload. Markdown panels carry their source here. */
  body?: string
  /** Terminal panels: which shell session this item shows. One terminal, one item. */
  sessionId?: string
}
/**
 * There is no "closed".
 *
 * `rail` is the resting state: a narrow menu of this session's artifacts, always present on the
 * right. Opening one of its items is what summons the canvas, and closing the canvas returns to
 * the rail rather than to nothing. A toggle that can hide the surface entirely turns "where did
 * that go" into a real question; a permanent menu answers it before it is asked.
 */
export type CanvasMode = 'rail' | 'docked' | 'float'

type Ctx = {
  panels: CanvasPanel[]
  activeId: string
  active: CanvasPanel | undefined
  mode: CanvasMode
  setMode: (m: CanvasMode) => void
  /**
   * Adds a panel if it is not already there, and by default brings the canvas out to show it.
   *
   * `reveal: false` registers an item without opening anything, which is how the shell sessions
   * that already exist appear in the rail without the canvas throwing itself open on load.
   */
  openPanel: (p: Omit<CanvasPanel, 'id'> & { id?: string }, opts?: { reveal?: boolean }) => string
  focusPanel: (id: string) => void
  closePanel: (id: string) => void
  close: () => void
  dockWidth: number
  setDockWidth: (w: number) => void
}
const CanvasContext = createContext<Ctx | null>(null)

export function useCanvas() {
  const ctx = useContext(CanvasContext)
  if (!ctx) throw new Error('useCanvas must be used within MorpheusCanvasProvider')
  return ctx
}

const MIN_DOCK = 340
const MIN_W = 380
const MIN_H = 220

export function MorpheusCanvasProvider({ children }: { children: ReactNode }) {
  const [panels, setPanels] = useState<CanvasPanel[]>([])
  const [activeId, setActiveId] = useState('')
  const [mode, setMode] = useState<CanvasMode>('rail')
  const [dockWidth, setDockWidth] = useState(520)

  const openPanel = useCallback((
    p: Omit<CanvasPanel, 'id'> & { id?: string },
    opts?: { reveal?: boolean },
  ) => {
    const id = p.id ?? `${p.kind}:${p.title}`
    setPanels(prev => (prev.some(x => x.id === id)
      ? prev.map(x => (x.id === id ? { ...x, ...p, id } : x))
      : [...prev, { ...p, id }]))
    if (opts?.reveal === false) {
      // Register only. Still make it the active item if nothing else is.
      setActiveId(cur => cur || id)
      return id
    }
    setActiveId(id)
    // Opening an item is what summons the canvas; if it is already out, leave the frame alone.
    setMode(m => (m === 'rail' ? 'docked' : m))
    return id
  }, [])

  const focusPanel = useCallback((id: string) => {
    setActiveId(id)
    setMode(m => (m === 'rail' ? 'docked' : m))
  }, [])

  const closePanel = useCallback((id: string) => {
    setPanels(prev => {
      const next = prev.filter(p => p.id !== id)
      setActiveId(cur => {
        if (cur !== id) return cur
        const i = prev.findIndex(p => p.id === id)
        return next[Math.max(0, Math.min(i, next.length - 1))]?.id ?? ''
      })
      if (next.length === 0) setMode('rail')
      return next
    })
  }, [])

  /** Closing puts the canvas away, not out of existence: back to the rail. */
  const close = useCallback(() => setMode('rail'), [])
  const active = panels.find(p => p.id === activeId)

  const value = useMemo<Ctx>(() => ({
    panels, activeId, active, mode, setMode, openPanel, focusPanel, closePanel, close,
    dockWidth, setDockWidth,
  }), [panels, activeId, active, mode, openPanel, focusPanel, closePanel, close, dockWidth])

  return <CanvasContext.Provider value={value}>{children}</CanvasContext.Provider>
}

/* ── Content ────────────────────────────────────────────────────────────── */

/**
 * Every kind the canvas can show, with the colour that identifies it.
 *
 * Content kinds keep their hue everywhere they appear: the tab, the rail, the toggle. That is
 * what makes a collapsed rail of six icons readable at a glance instead of six grey squares.
 * The hues are drawn from the existing status palette rather than invented, so the canvas still
 * belongs to the same design.
 */
type Renderer = { icon: typeof FileText; tone: string; label: string }
const RENDERERS: Record<PanelKind, Renderer> = {
  terminal: { icon: TerminalSquare, tone: 'text-accent', label: 'Console' },
  markdown: { icon: FileText, tone: 'text-warning', label: 'Document' },
}

export function panelIcon(kind: PanelKind) { return RENDERERS[kind].icon }
export function panelTone(kind: PanelKind) { return RENDERERS[kind].tone }

/* ── Chrome ─────────────────────────────────────────────────────────────── */

const ICON_BTN = `morph-tap grid h-[30px] w-[30px] shrink-0 place-items-center rounded-btn text-muted
  hover:bg-overlay/[0.07] hover:text-text`

/**
 * The canvas header. Panel tabs on the left, frame controls on the right, and the grip that
 * pulls a docked canvas out into a window.
 */
function CanvasHeader({ onGripDown, grippable }: {
  onGripDown?: (e: React.PointerEvent) => void
  grippable?: boolean
}) {
  const { panels, activeId, focusPanel, closePanel, mode, setMode, close } = useCanvas()

  return (
    <div
      onPointerDown={grippable ? e => {
        if ((e.target as HTMLElement).closest('button,input')) return
        onGripDown?.(e)
      } : undefined}
      className={`flex shrink-0 items-center gap-1 border-b border-border bg-panel px-2 py-1.5 ${
        grippable ? 'cursor-grab select-none active:cursor-grabbing' : ''}`}>
      <GripVertical size={13} className="shrink-0 text-muted/60" aria-hidden />

      <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        {panels.map(p => {
          const Icon = panelIcon(p.kind)
          const on = p.id === activeId
          return (
            <div key={p.id}
              style={{ transition: 'background-color var(--t) var(--ease), color var(--t) var(--ease)' }}
              className={`group/tab flex w-[132px] shrink-0 items-center gap-1.5 rounded-btn px-2 ${
                on ? 'bg-overlay/[0.08] text-heading' : 'text-muted hover:bg-overlay/[0.06] hover:text-text'}`}>
              {/* The kind's colour stays on even when the tab is inactive: it is identity, not state. */}
              <Icon size={12} className={`shrink-0 ${panelTone(p.kind)}`} />
              <button onClick={() => focusPanel(p.id)} title={p.title}
                className="flex min-w-0 flex-1 items-center self-stretch py-1.5 text-left text-[11.5px] outline-none">
                <span className="truncate">{p.title}</span>
              </button>
              <button onClick={() => closePanel(p.id)} aria-label={`Close ${p.title}`}
                className="morph-reveal grid h-6 w-6 shrink-0 place-items-center rounded hover:text-danger">
                <X size={12} />
              </button>
            </div>
          )
        })}
      </div>

      {/* Frame controls, each with its own hue so the row is scannable rather than six grey
          glyphs. Muted at rest, coloured on hover and while active. */}
      <span aria-hidden className="mx-0.5 h-3.5 w-px shrink-0 bg-border" />
      <button onClick={() => setMode('docked')} title="Dock to the right" aria-label="Dock the canvas"
        className={`${ICON_BTN} hover:text-accent ${mode === 'docked' ? 'bg-accent/12 text-accent' : ''}`}>
        <PanelRight size={14} />
      </button>
      <button onClick={() => setMode('float')} title="Float as a window" aria-label="Float the canvas"
        className={`${ICON_BTN} hover:text-purple ${mode === 'float' ? 'bg-purple/12 text-purple' : ''}`}>
        <Minimize2 size={14} />
      </button>
      <button onClick={() => window.open('/morpheus/console?open=1', '_blank', 'noopener')}
        title="Open in a new tab" aria-label="Open in a new tab"
        className={`${ICON_BTN} hover:text-success`}>
        <ExternalLink size={14} />
      </button>
      {/* Puts the canvas away to the rail. Nothing is discarded, so this is a chevron rather than
          a cross: a cross would promise the artifacts are gone. */}
      <button onClick={close} title="Put away, back to the rail" aria-label="Put the canvas away"
        className={`${ICON_BTN} hover:text-accent`}>
        <ChevronsRight size={14} />
      </button>
    </div>
  )
}

/**
 * The collapsed rail.
 *
 * A narrow column of the session's artifacts: one button per panel, each keeping its kind's
 * colour, so a glance tells you what this session produced without giving up any width. Clicking
 * one expands straight back to that panel.
 */
export function CanvasRail({ onNewShell }: { onNewShell?: () => void }) {
  const { mode, panels, activeId, focusPanel, setMode } = useCanvas()

  // Present whenever the canvas is not occupying the column itself. While the canvas floats the
  // rail stays, so another item can be opened without first putting the window away.
  if (mode === 'docked') return null

  return (
    <aside
      aria-label="Canvas rail"
      style={{ boxShadow: 'inset 1px 0 0 rgb(var(--accent) / 0.10)' }}
      className="flex w-[52px] shrink-0 flex-col items-center gap-1.5 border-l-2 border-accent/25 bg-panel py-2">
      <button onClick={() => setMode('docked')} title="Open the canvas" aria-label="Open the canvas"
        className={`${ICON_BTN} hover:text-accent`}>
        <ChevronsLeft size={15} />
      </button>
      <span aria-hidden className="my-0.5 h-px w-6 bg-border" />

      <div className="flex min-h-0 flex-1 flex-col items-center gap-1 overflow-y-auto">
        {panels.length === 0 && (
          <span className="px-1 text-center text-[9.5px] leading-tight text-muted/60">no artifacts</span>
        )}
        {panels.map(p => {
          const Icon = panelIcon(p.kind)
          const on = p.id === activeId
          return (
            <button key={p.id} onClick={() => { focusPanel(p.id); setMode('docked') }}
              title={p.title} aria-label={p.title}
              className={`morph-tap relative grid h-9 w-9 shrink-0 place-items-center rounded-btn
                ${on ? 'bg-overlay/[0.10]' : 'hover:bg-overlay/[0.07]'}`}>
              {on && (
                <span aria-hidden className="absolute -left-2 top-1/2 h-4 w-[2px] -translate-y-1/2
                  rounded-r bg-accent" />
              )}
              <Icon size={16} className={panelTone(p.kind)} />
            </button>
          )
        })}
      </div>

      {/* New shell. Terminals are created from the rail because a terminal IS a rail item. */}
      {onNewShell && (
        <button onClick={onNewShell} title="New shell" aria-label="New shell"
          className={`${ICON_BTN} hover:text-accent`}>
          <Plus size={15} />
        </button>
      )}
      <span className="text-[10px] tabular-nums text-muted/70">{panels.length}</span>
    </aside>
  )
}

/* ── Resize ─────────────────────────────────────────────────────────────── */

type Dir = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
const CURSOR: Record<Dir, string> = {
  n: 'cursor-ns-resize', s: 'cursor-ns-resize', e: 'cursor-ew-resize', w: 'cursor-ew-resize',
  ne: 'cursor-nesw-resize', sw: 'cursor-nesw-resize', nw: 'cursor-nwse-resize', se: 'cursor-nwse-resize',
}

function ResizeGrips({ onStart }: { onStart: (e: React.PointerEvent, dir: Dir) => void }) {
  const edges: [Dir, string][] = [
    ['n', 'left-3 right-3 top-0 h-1.5'], ['s', 'left-3 right-3 bottom-0 h-1.5'],
    ['w', 'top-3 bottom-3 left-0 w-1.5'], ['e', 'top-3 bottom-3 right-0 w-1.5'],
  ]
  const corners: [Dir, string][] = [
    ['nw', 'left-0 top-0'], ['ne', 'right-0 top-0'], ['sw', 'left-0 bottom-0'], ['se', 'right-0 bottom-0'],
  ]
  return (
    <>
      {edges.map(([d, pos]) => (
        <span key={d} role="separator" aria-label={`Resize ${d}`} onPointerDown={e => onStart(e, d)}
          className={`absolute ${pos} ${CURSOR[d]}`} />
      ))}
      {corners.map(([d, pos]) => (
        <span key={d} role="separator" aria-label={`Resize ${d}`} onPointerDown={e => onStart(e, d)}
          className={`group/grip absolute ${pos} h-4 w-4 ${CURSOR[d]}`}>
          {d === 'se' && (
            <span aria-hidden className="absolute bottom-1.5 right-1.5 h-2 w-2 rounded-br-[3px]
              border-b border-r border-muted/40 transition-colors group-hover/grip:border-accent" />
          )}
        </span>
      ))}
    </>
  )
}

/* ── Frames ─────────────────────────────────────────────────────────────── */

/**
 * The canvas reads as a different material from the conversation, deliberately.
 *
 * Chat is a page: near-black, open, text-led. The canvas is an instrument panel sitting on top of
 * it, so it is a shade darker, carries a lit top edge, and is separated by an accent-tinted rule
 * rather than the hairline used between ordinary sections. Without that contrast the two surfaces
 * blur into one wide column and it stops being obvious which half you are reading.
 */
const SHELL = 'flex flex-col overflow-hidden bg-[rgb(var(--bg))]'

/** A one-pixel highlight along the top edge, so the panel catches light like a real surface. */
const LIT_EDGE = 'linear-gradient(90deg, transparent, rgb(255 255 255 / 0.07) 22%, rgb(255 255 255 / 0.07) 78%, transparent)'
/** How close to the right edge a dragged window must land to re-dock. */
const DOCK_ZONE = 120

/**
 * The docked column.
 *
 * Rendered as a sibling of the page rather than over it, so the content beside it reflows. Its
 * left edge is a drag handle for width, and the header grip pulls the whole thing out into a
 * floating window once you have moved far enough to mean it.
 */
export function CanvasDock({ children }: { children: ReactNode }) {
  const { mode, dockWidth, setDockWidth, setMode } = useCanvas()
  const startWidth = useRef(0)

  const resizeWidth = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    const handle = e.currentTarget as HTMLElement
    handle.setPointerCapture(e.pointerId)
    const px = e.clientX
    startWidth.current = dockWidth
    let w = dockWidth
    const move = (ev: PointerEvent) => {
      w = Math.max(MIN_DOCK, Math.min(startWidth.current - (ev.clientX - px), window.innerWidth - 320))
      setDockWidth(w)
    }
    const up = () => {
      handle.removeEventListener('pointermove', move)
      handle.removeEventListener('pointerup', up)
    }
    handle.addEventListener('pointermove', move)
    handle.addEventListener('pointerup', up)
  }, [dockWidth, setDockWidth])

  // Pulling the header left far enough detaches the canvas. A small threshold would make every
  // stray click on the header throw the panel into a window.
  const pullOut = useCallback((e: React.PointerEvent) => {
    const px = e.clientX
    const onMove = (ev: PointerEvent) => {
      if (px - ev.clientX > 70) {
        setMode('float')
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
      }
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [setMode])

  if (mode !== 'docked') return null

  return (
    <aside
      aria-label="Morpheus canvas"
      style={{
        width: dockWidth,
        // A tinted rule plus a soft shadow falling back onto the conversation: the canvas sits
        // ON the page rather than beside it.
        boxShadow: '-18px 0 40px -24px rgb(0 0 0 / 0.85), inset 1px 0 0 rgb(var(--accent) / 0.10)',
      }}
      className={`${SHELL} relative shrink-0 border-l-2 border-accent/25`}>
      <span aria-hidden className="pointer-events-none absolute inset-x-0 top-0 z-10 h-px"
        style={{ background: LIT_EDGE }} />
      <span role="separator" aria-label="Resize the canvas" onPointerDown={resizeWidth}
        className="absolute inset-y-0 left-0 z-10 w-1.5 cursor-ew-resize hover:bg-accent/40" />
      <CanvasHeader grippable onGripDown={pullOut} />
      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
    </aside>
  )
}

/** The floating window, and the landing zone that shows where it will re-dock. */
export function CanvasFloat({ children }: { children: ReactNode }) {
  const { mode, setMode } = useCanvas()
  const winRef = useRef<HTMLElement>(null)
  const boundsRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 560, h: 560 })
  const [nearDock, setNearDock] = useState(false)
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const placed = useRef(false)

  useEffect(() => {
    if (mode !== 'float' || placed.current) return
    placed.current = true
    x.set(Math.max(12, window.innerWidth - size.w - 40))
    y.set(70)
  }, [mode, size.w, x, y])

  const startResize = useCallback((e: React.PointerEvent, dir: Dir) => {
    e.preventDefault(); e.stopPropagation()
    const handle = e.currentTarget as HTMLElement
    handle.setPointerCapture(e.pointerId)
    const px = e.clientX, py = e.clientY
    const w0 = size.w, h0 = size.h
    const x0 = x.get(), y0 = y.get()
    const maxW = window.innerWidth - 16, maxH = window.innerHeight - 16
    let w = w0, h = h0
    const move = (ev: PointerEvent) => {
      const dx = ev.clientX - px, dy = ev.clientY - py
      if (dir.includes('e')) w = Math.max(MIN_W, Math.min(w0 + dx, maxW))
      if (dir.includes('w')) { w = Math.max(MIN_W, Math.min(w0 - dx, maxW)); x.set(x0 + (w0 - w)) }
      if (dir.includes('s')) h = Math.max(MIN_H, Math.min(h0 + dy, maxH))
      if (dir.includes('n')) { h = Math.max(MIN_H, Math.min(h0 - dy, maxH)); y.set(y0 + (h0 - h)) }
      const el = winRef.current
      if (el) { el.style.width = `${w}px`; el.style.height = `${h}px` }
    }
    const up = () => {
      handle.removeEventListener('pointermove', move)
      handle.removeEventListener('pointerup', up)
      setSize({ w, h })
    }
    handle.addEventListener('pointermove', move)
    handle.addEventListener('pointerup', up)
  }, [size, x, y])

  const onDrag = useCallback((_: unknown, info: PanInfo) => {
    setNearDock(window.innerWidth - info.point.x < DOCK_ZONE)
  }, [])
  const onDragEnd = useCallback((_: unknown, info: PanInfo) => {
    if (window.innerWidth - info.point.x < DOCK_ZONE) { placed.current = false; setMode('docked') }
    setNearDock(false)
  }, [setMode])

  if (mode !== 'float') return null

  return (
    <div ref={boundsRef} className="pointer-events-none fixed inset-0 z-[78]">
      {/* Landing zone. Lit while a drag is close enough to re-dock on release. */}
      <AnimatePresence>
        {nearDock && (
          <motion.div aria-hidden
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-y-0 right-0 w-[420px] border-l-2 border-accent bg-accent/[0.07]" />
        )}
      </AnimatePresence>

      <motion.section
        ref={winRef}
        drag dragMomentum={false} dragElastic={0} dragConstraints={boundsRef}
        onDrag={onDrag} onDragEnd={onDragEnd}
        dragListener
        // Opacity and scale only. Animating `y` here would fight the motion value that positions
        // the window and snap it back to the top of the screen.
        initial={{ opacity: 0, scale: 0.985 }} animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
        whileDrag={{ scale: 1.004 }}
        style={{ x, y, width: size.w, height: size.h }}
        role="dialog" aria-label="Morpheus canvas"
        className={`${SHELL} pointer-events-auto absolute left-0 top-0 rounded-card border
          border-accent/25 ring-1 ring-black/40 shadow-popover`}>
        <span aria-hidden className="pointer-events-none absolute inset-x-3 top-0 z-10 h-px"
          style={{ background: LIT_EDGE }} />
        <CanvasHeader />
        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
        <ResizeGrips onStart={startResize} />
      </motion.section>
    </div>
  )
}
