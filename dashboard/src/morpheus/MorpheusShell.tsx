// The Morpheus shell: sidebar, workspace tab strip, top bar.
//
// Same mechanics as TOBI's AppShell (src/components/AppShell.tsx) -- grouped sidebar, a
// browser-style tab strip, one scrolling pane per tab. The owner asked for TOBI's layout with
// Morpheus's pages and Morpheus's mood, so the structure is inherited and only the identity, the
// routes and the top bar differ.
//
// The sidebar is split by how often things are touched: the daily surfaces sit at the top, the
// one big capability gets its own section, and everything that is configuration or system
// watching is folded into a menu at the bottom so it never competes for attention.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence, LayoutGroup, useReducedMotion } from 'framer-motion'
import {
  Plus, X, Lock, ChevronLeft, Eye, FlaskConical, Settings, LogOut, ChevronRight,
} from 'lucide-react'
import {
  MORPHEUS_ROUTES, MAX_MORPHEUS_TABS, getMorpheusRouteMeta, useMorpheusTabs,
} from './MorpheusTabsContext'
import { useMorpheus, type PreviewMode } from './MorpheusSession'
import { useFeedback } from './MorpheusFeedback'
import { ActionButton } from '../components/async-ui'

/** Daily surfaces first, then the one big capability. Everything else lives in the bottom menu. */
const NAV_PRIMARY = ['/morpheus', '/morpheus/chat']
const NAV_FEATURES = ['/morpheus/osint', '/morpheus/agents']
/** Configuration and system watching. Reached from Settings, not from the main list. */
const NAV_SETTINGS = ['/morpheus/models', '/morpheus/security', '/morpheus/access']

/**
 * Panic lock.
 *
 * Deliberately the loudest control in the app, because in the moment it matters the owner will
 * be looking for it rather than reading. Two-stage: it sits in the top bar of every page, which
 * is exactly where a stray click lands, and losing an unlocked session to a misclick would teach
 * him to distrust it. The ring drains over the three seconds the armed state lasts, so the
 * window to confirm is visible rather than guessed at.
 */
function PanicLock({ onLock }: { onLock: () => void }) {
  const reduce = useReducedMotion()
  const [armed, setArmed] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (!armed) return
    timer.current = window.setTimeout(() => setArmed(false), 3000)
    return () => window.clearTimeout(timer.current)
  }, [armed])

  return (
    <button
      onClick={() => (armed ? onLock() : setArmed(true))}
      onMouseLeave={() => setArmed(false)}
      title={armed ? 'Press again to seal the gate' : 'Panic lock: seal everything and return to the gate'}
      aria-label={armed ? 'Confirm panic lock' : 'Panic lock'}
      style={{ transition: 'color var(--t) var(--ease), background-color var(--t) var(--ease), border-color var(--t) var(--ease), transform var(--t) var(--ease)' }}
      className={`group relative flex h-8 shrink-0 items-center gap-2 overflow-hidden rounded-btn border
        px-3 text-[12.5px] font-semibold outline-none
        focus-visible:ring-2 focus-visible:ring-danger/50 focus-visible:ring-offset-2
        focus-visible:ring-offset-strip hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.97] ${
        armed
          ? 'border-danger bg-danger/20 text-danger'
          : 'border-danger/35 bg-danger/[0.07] text-danger/85 hover:border-danger/70 hover:bg-danger/15 hover:text-danger'}`}>

      {/* Sweep on hover: the control announces it is live before it is armed. */}
      <span aria-hidden className="pointer-events-none absolute inset-0 -translate-x-full
        bg-gradient-to-r from-transparent via-danger/25 to-transparent
        transition-transform duration-[750ms] ease-out group-hover:translate-x-full" />

      {/* Armed: a slow pulse behind the label, so it reads as counting down. */}
      {armed && !reduce && (
        <motion.span aria-hidden className="pointer-events-none absolute inset-0 bg-danger/20"
          animate={{ opacity: [0.25, 0.6, 0.25] }}
          transition={{ duration: 1, repeat: Infinity, ease: 'easeInOut' }} />
      )}

      <span className="relative grid h-[15px] w-[15px] shrink-0 place-items-center">
        {/* The draining ring: the three-second window made visible. */}
        {armed && !reduce && (
          <svg viewBox="0 0 20 20" className="absolute inset-0 -rotate-90" aria-hidden>
            <motion.circle cx="10" cy="10" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.6"
              strokeLinecap="round" pathLength={1}
              initial={{ pathLength: 1, opacity: 0.9 }}
              animate={{ pathLength: 0, opacity: 0.35 }}
              transition={{ duration: 3, ease: 'linear' }} />
          </svg>
        )}
        <motion.span className="grid place-items-center"
          animate={armed && !reduce ? { rotate: [0, -14, 12, -6, 0] } : { rotate: 0 }}
          transition={{ duration: 0.45 }}>
          <Lock size={12.5} className="transition-transform duration-200 group-hover:scale-110" />
        </motion.span>
      </span>

      <span className="relative tracking-[0.02em]">{armed ? 'Confirm' : 'Panic lock'}</span>
    </button>
  )
}

/** Build-phase control that makes every page state reachable for review. Removed with the backend. */
function ReviewStates() {
  const { preview, setPreview } = useMorpheus()
  const { announce, confirm } = useFeedback()
  const [open, setOpen] = useState(false)

  const modes: { id: PreviewMode; label: string; note: string }[] = [
    { id: 'live', label: 'With data', note: 'The normal, populated state' },
    { id: 'loading', label: 'Loading', note: 'Skeletons while data arrives' },
    { id: 'empty', label: 'Empty', note: 'Nothing created yet' },
    { id: 'failure', label: 'Failed to load', note: 'The page says so, honestly' },
  ]

  return (
    <div className="relative shrink-0">
      <button onClick={() => setOpen(o => !o)} aria-haspopup="menu" aria-expanded={open}
        title="Preview UI states (build phase)"
        className={`flex h-8 items-center gap-1.5 rounded-btn border px-2.5 text-[12px] outline-none
          transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent/50 ${
          preview === 'live' ? 'border-border bg-surface text-muted hover:text-text'
                             : 'border-accent/50 bg-accent/12 text-accent'}`}>
        <FlaskConical size={12.5} />
        {preview === 'live' ? 'States' : modes.find(m => m.id === preview)?.label}
      </button>
      {open && (
        <>
          <button className="fixed inset-0 z-20 cursor-default" aria-hidden onClick={() => setOpen(false)} />
          <div role="menu" className="absolute right-0 top-full z-30 mt-1.5 w-[266px] overflow-hidden
            rounded-card border border-border bg-panel py-1.5 shadow-popover">
            <p className="px-3 pb-1.5 pt-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted">
              Page state
            </p>
            {modes.map(m => (
              <button key={m.id} role="menuitemradio" aria-checked={preview === m.id}
                onClick={() => { setPreview(m.id); setOpen(false) }}
                className={`block w-full px-3 py-2 text-left transition-colors hover:bg-overlay/[0.06] ${
                  preview === m.id ? 'text-accent' : 'text-text'}`}>
                <span className="block text-[13px]">{m.label}</span>
                <span className="block text-[11.5px] text-muted">{m.note}</span>
              </button>
            ))}
            <div className="my-1.5 border-t border-border" />
            <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted">
              Announcements
            </p>
            {([
              ['ok', 'Success', 'Profile built', '14 sources, nothing contradicted itself.'],
              ['info', 'Information', 'Model switched', 'Qwen 27B is now answering.'],
              ['warn', 'Warning', 'Hardware key not found', 'Falling back to your authenticator code.'],
              ['danger', 'Alert', 'Entry refused', 'An unknown device failed at the gate.'],
            ] as const).map(([tone, label, title, detail]) => (
              <button key={tone} role="menuitem"
                onClick={() => { announce({ tone, title, detail }); setOpen(false) }}
                className="block w-full px-3 py-1.5 text-left text-[13px] text-text transition-colors hover:bg-overlay/[0.06]">
                {label}
              </button>
            ))}
            <div className="my-1.5 border-t border-border" />
            <ActionButton
              onAction={async () => {
                setOpen(false)
                const ok = await confirm({
                  title: 'Erase this object?',
                  body: 'The profile and every source it gathered are removed from your library. This cannot be undone.',
                  confirmLabel: 'Erase it', tone: 'danger', typeToConfirm: 'erase',
                })
                announce(ok
                  ? { tone: 'ok', title: 'Object erased', detail: 'It is gone from the library.' }
                  : { tone: 'info', title: 'Nothing was erased' })
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] text-text transition-colors hover:bg-overlay/[0.06]">
              Confirmation dialog
            </ActionButton>
          </div>
        </>
      )}
    </div>
  )
}

function TabStrip() {
  const { tabs, activeId, focusTab, closeTab, reorderTabs, openTab, notice, clearNotice } = useMorpheusTabs()
  const [dragId, setDragId] = useState<string | null>(null)
  const [picker, setPicker] = useState(false)
  const openRoutes = tabs.map(t => t.route)

  useEffect(() => {
    if (!notice) return
    const t = setTimeout(clearNotice, 2600)
    return () => clearTimeout(t)
  }, [notice, clearNotice])

  return (
    <div className="relative flex min-w-0 flex-1 items-end">
      <nav aria-label="Morpheus tabs" className="min-w-0 flex-1">
        <div role="tablist" aria-label="Open pages" className="flex min-w-0 items-end gap-0.5 px-2">
          <LayoutGroup id="morpheusTabs">
            <AnimatePresence initial={false}>
              {tabs.map(tab => {
                const meta = getMorpheusRouteMeta(tab.route)
                const active = tab.id === activeId
                return (
                  <motion.div key={tab.id} layout role="tab" aria-selected={active}
                    initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 5 }}
                    transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                    draggable
                    onDragStart={() => setDragId(tab.id)}
                    onDragOver={e => e.preventDefault()}
                    onDragEnd={() => setDragId(null)}
                    onDrop={e => { e.preventDefault(); if (dragId) reorderTabs(dragId, tab.id); setDragId(null) }}
                    style={{ transition: 'background-color var(--t) var(--ease), color var(--t) var(--ease)' }}
                    className={`group flex min-w-0 max-w-[186px] flex-1 items-center gap-2 rounded-t-[10px] px-3 py-2
                      text-[12.5px] ${
                      active ? 'bg-bg text-heading shadow-[inset_0_1px_0_rgb(255_255_255/0.04)]'
                             : 'text-muted hover:bg-overlay/[0.05] hover:text-text'
                    } ${dragId === tab.id ? 'opacity-50' : ''}`}>
                    <button onClick={() => focusTab(tab.id)} title={meta.label}
                      className="flex min-w-0 flex-1 items-center gap-2 outline-none">
                      <meta.Icon size={13}
                        className={`morph-icon shrink-0 group-hover:scale-110 ${active ? 'text-accent' : ''}`} />
                      <span className="truncate">{meta.label}</span>
                    </button>
                    {tabs.length > 1 && (
                      <button onClick={() => closeTab(tab.id)} aria-label={`Close ${meta.label}`}
                        className="morph-reveal shrink-0 rounded p-0.5 text-muted outline-none
                          hover:scale-125 hover:text-danger"
                        style={{ transition: 'opacity var(--t) var(--ease), color var(--t) var(--ease), transform var(--t) var(--ease)' }}>
                        <X size={12} />
                      </button>
                    )}
                  </motion.div>
                )
              })}
            </AnimatePresence>
            {tabs.length < MAX_MORPHEUS_TABS && (
              <div className="relative">
                <button onClick={() => setPicker(o => !o)} aria-label="Open new tab"
                  aria-haspopup="menu" aria-expanded={picker}
                  className="mb-1 grid h-7 w-7 place-items-center rounded-btn text-muted outline-none
                    transition-colors duration-150 hover:bg-overlay/[0.07] hover:text-text
                    focus-visible:ring-2 focus-visible:ring-accent/50">
                  <Plus size={14} />
                </button>
                {picker && (
                  <>
                    <button className="fixed inset-0 z-20 cursor-default" aria-hidden onClick={() => setPicker(false)} />
                    <div role="menu" className="absolute left-0 top-full z-30 mt-1 w-52 overflow-hidden
                      rounded-card border border-border bg-panel py-1.5 shadow-popover">
                      <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted">
                        Open in new tab
                      </p>
                      {MORPHEUS_ROUTES.filter(r => !openRoutes.includes(r.route)).map(r => (
                        <button key={r.route} role="menuitem"
                          onClick={() => { openTab(r.route); setPicker(false) }}
                          className="group/mi flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px]
                            text-text hover:bg-overlay/[0.07] hover:pl-4"
                          style={{ transition: 'background-color var(--t) var(--ease), padding-left var(--t) var(--ease), color var(--t) var(--ease)' }}>
                          <r.Icon size={14} className="text-muted" />
                          {r.label}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </LayoutGroup>
        </div>
      </nav>
      {notice && (
        <p role="status" className="absolute -bottom-8 left-3 z-10 rounded-btn border border-border
          bg-panel px-2.5 py-1 text-[11.5px] text-muted shadow-popover">
          {notice}
        </p>
      )}
    </div>
  )
}

function SideLink({ route }: { route: string }) {
  const meta = getMorpheusRouteMeta(route)
  return (
    <NavLink to={route} end={route === '/morpheus'}
      className={({ isActive }) =>
        `group relative flex items-center gap-2.5 overflow-hidden rounded-btn px-2.5 py-[7px] text-[13px]
         outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
          isActive ? 'bg-accent/[0.13] text-heading' : 'text-muted hover:bg-overlay/[0.05] hover:text-text'}`}>
      {({ isActive }) => (
        <>
          {/* The active marker grows out of the edge rather than blinking on, so moving between
              pages reads as one continuous motion instead of two separate states. */}
          <span aria-hidden
            className="absolute left-0 top-1/2 w-[2px] -translate-y-1/2 rounded-r bg-accent"
            style={{
              height: isActive ? 16 : 0,
              opacity: isActive ? 1 : 0,
              transition: 'height var(--t) var(--ease), opacity var(--t) var(--ease)',
            }} />
          <meta.Icon size={15}
            className={`morph-icon shrink-0 group-hover:-translate-y-px group-hover:scale-[1.12]
              ${isActive ? 'text-accent' : ''}`} />
          {meta.label}
        </>
      )}
    </NavLink>
  )
}

/** Bottom menu: settings surfaces plus the way out. Opens upward, away from the page content. */
function SettingsMenu({ onExit }: { onExit: () => void }) {
  const { lock } = useMorpheus()
  const { confirm } = useFeedback()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  const logout = async () => {
    setOpen(false)
    const ok = await confirm({
      title: 'Lock Morpheus and leave?',
      body: 'The gate seals behind you. You will need your password, code and key to get back in.',
      confirmLabel: 'Lock and leave',
    })
    if (ok) lock()
  }

  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)} aria-haspopup="menu" aria-expanded={open}
        className={`group flex w-full items-center gap-2.5 rounded-btn px-2.5 py-[7px] text-[13px] outline-none
          transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent/40 ${
          open ? 'bg-overlay/[0.06] text-heading' : 'text-muted hover:bg-overlay/[0.05] hover:text-text'}`}>
        <Settings size={15} className="shrink-0 transition-transform duration-500 group-hover:rotate-90" />
        Settings
        <ChevronRight size={13} className={`ml-auto shrink-0 transition-transform duration-200 ${
          open ? '-rotate-90' : ''}`} />
      </button>

      <AnimatePresence>
        {open && (
          <>
            <button className="fixed inset-0 z-20 cursor-default" aria-hidden onClick={() => setOpen(false)} />
            <motion.div role="menu"
              initial={{ opacity: 0, y: 6, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 4, scale: 0.98 }}
              transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
              className="absolute bottom-full left-0 z-30 mb-1.5 w-[196px] overflow-hidden rounded-card
                border border-border bg-panel py-1.5 shadow-popover">
              {NAV_SETTINGS.map(route => {
                const meta = getMorpheusRouteMeta(route)
                return (
                  <button key={route} role="menuitem"
                    onClick={() => { navigate(route); setOpen(false) }}
                    className="group/mi flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px]
                      text-text outline-none hover:bg-overlay/[0.07] hover:pl-4"
                    style={{ transition: 'background-color var(--t) var(--ease), padding-left var(--t) var(--ease)' }}>
                    <meta.Icon size={14} className="morph-icon shrink-0 text-muted group-hover/mi:text-accent" />
                    {meta.label}
                  </button>
                )
              })}
              <div className="my-1.5 border-t border-border" />
              <button role="menuitem" onClick={() => { onExit(); setOpen(false) }}
                className="group/mi flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px]
                  text-text outline-none hover:bg-overlay/[0.07] hover:pl-4"
                style={{ transition: 'background-color var(--t) var(--ease), padding-left var(--t) var(--ease)' }}>
                <ChevronLeft size={14} className="morph-icon shrink-0 text-muted group-hover/mi:-translate-x-0.5" />
                Back to TOBI
              </button>
              <ActionButton onAction={logout}
                icon={<LogOut size={14} className="shrink-0" />}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-danger
                  outline-none transition-colors hover:bg-danger/10">
                Log out
              </ActionButton>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function MorpheusShell({ children, onExit }: { children: ReactNode; onExit: () => void }) {
  const { lock, models } = useMorpheus()
  const { announce } = useFeedback()
  const active = models.find(m => m.active)

  return (
    <div className="flex h-full min-h-0 bg-bg text-text">
      {/* ── Sidebar ─────────────────────────────────────────── */}
      <aside className="flex w-[214px] shrink-0 flex-col border-r border-border bg-panel">
        <div className="flex items-center gap-2.5 px-4 pb-5 pt-4">
          <span className="grid h-[26px] w-[26px] shrink-0 place-items-center rounded-btn bg-accent/12 text-accent">
            <Eye size={14} />
          </span>
          <span className="font-display text-[13.5px] font-semibold tracking-[0.16em] text-heading">MORPHEUS</span>
        </div>

        <nav className="flex-1 space-y-6 px-2.5">
          <div className="space-y-0.5">
            {NAV_PRIMARY.map(r => <SideLink key={r} route={r} />)}
          </div>
          <div>
            <p className="px-2.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted/80">
              Features
            </p>
            <div className="space-y-0.5">
              {NAV_FEATURES.map(r => <SideLink key={r} route={r} />)}
            </div>
          </div>
        </nav>

        <div className="border-t border-border px-2.5 py-2.5">
          <SettingsMenu onExit={onExit} />
        </div>
      </aside>

      {/* ── Main ────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[44px] shrink-0 items-end gap-2.5 border-b border-border bg-strip pr-3">
          <TabStrip />
          <div className="flex shrink-0 items-center gap-2 pb-1.5">
            <button
              onClick={() => announce(active
                ? { tone: 'info', title: active.name, detail: 'Running on your machine, answering without a provider filter.' }
                : { tone: 'warn', title: 'No model running', detail: 'Open Models to choose one.' })}
              className="hidden h-8 items-center gap-2 rounded-btn px-2.5 text-[12px] text-muted outline-none
                transition-colors duration-150 hover:bg-overlay/[0.06] hover:text-text lg:flex">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-success" />
              {active ? active.name : 'No model'}
            </button>
            <ReviewStates />
            <PanicLock onLock={lock} />
          </div>
        </header>
        {/* The canvas is NOT mounted here. It holds the artifacts of one conversation, so it
            belongs to Chat and appears only there; carrying it onto Models or Security would
            imply a scope it does not have. Its state still lives at app level, so leaving Chat
            and coming back finds it exactly as it was. */}
        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  )
}
