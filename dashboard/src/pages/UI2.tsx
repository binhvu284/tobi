// TOBI Agent Mission Control UI 2.0 (#36) — one live screen where you talk to TOBI and he
// runs the whole of Mission Control for you. The shell in
// docs/feature-idea-queue/TOBI_UI_2_SHELL.html decided every component, state and timing;
// this page is that shell as real components, driven by ui2/session.ts.
//
// `?demo=1` runs the design's scripted session (the one the shell ships with) instead of
// the Chat runtime, so the build can be checked against the design state by state.
import '@fontsource-variable/geist-mono/wght.css'
import '../ui2/ui2.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useReducedMotionPref } from '../context/MotionProvider'
import { Canvas, HistoryRows, RecapPane } from '../ui2/Canvas'
import { Console, type MenuName, type Ui } from '../ui2/Console'
import { Clock, Cross } from '../ui2/icons'
import { fmtDur, type SessionRecap } from '../ui2/model'
import { getSession, useSessionState } from '../ui2/session'
import { Standby } from '../ui2/Standby'

type OverlayName = 'end' | 'history'

export default function UI2() {
  const location = useLocation()
  const demo = new URLSearchParams(location.search || window.location.search).get('demo') === '1'
  const session = useMemo(() => getSession(demo), [demo])
  const s = useSessionState(session)
  const level = useReducedMotionPref()
  const still = level !== 'full' || (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches)

  const [menu, setMenu] = useState<MenuName | null>(null)
  const [overlay, setOverlay] = useState<OverlayName | null>(null)
  const [pick, setPick] = useState<SessionRecap | null>(null)
  const menuRef = useRef(menu); menuRef.current = menu
  const overlayRef = useRef(overlay); overlayRef.current = overlay
  const root = useRef<HTMLDivElement>(null)
  const page = useRef<HTMLDivElement>(null)
  const attachRef = useRef<(() => void) | null>(null)

  useEffect(() => { void session.loadModels() }, [session])
  useEffect(() => { setMenu(null); setOverlay(null); setPick(null) }, [s.view])

  /* a click anywhere else puts the menus away */
  useEffect(() => {
    const h = (e: MouseEvent) => {
      const t = e.target as Element | null
      if (t?.closest?.('.menu') || t?.closest?.('[aria-haspopup="menu"]')) return
      setMenu(null)
    }
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [])

  /* the keys: only while this page is the one on screen, never from a hidden tab */
  useEffect(() => {
    const visible = () => { const r = root.current; return !!r && r.offsetWidth > 0 }
    const down = (ev: KeyboardEvent) => {
      if (!visible()) return
      const st = session.state
      const target = ev.target as HTMLElement | null
      const tag = target?.tagName || ''
      const typing = tag === 'INPUT' || tag === 'TEXTAREA' || !!target?.isContentEditable
      if (ev.key === 'Escape') {
        if (st.canvas.bleed) { session.unbleed(); return }
        if (menuRef.current || overlayRef.current) { setMenu(null); setOverlay(null); return }
        if (st.run) { session.stopRun(); return }              // a run in flight is what Escape is for
        if (st.view === 'live') session.setMic('locked', false)
        return
      }
      if ((ev.metaKey || ev.ctrlKey) && !ev.altKey && (ev.key === 'u' || ev.key === 'U') && st.view === 'live') {
        ev.preventDefault(); attachRef.current?.(); return
      }
      if (typing) return
      if (ev.altKey && (ev.key === 'm' || ev.key === 'M')) {          // belongs to On and off
        if (st.view === 'live' && st.micMode === 'onoff') { ev.preventDefault(); session.setMic('onoff', !st.micLive) }
        return
      }
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return
      if (ev.code === 'Space' && st.micMode === 'ptt' && st.view === 'live') {
        ev.preventDefault()
        if (!ev.repeat) session.setMic('ptt', true)
      }
    }
    const up = (ev: KeyboardEvent) => {
      if (!visible()) return
      if (ev.code === 'Space' && session.state.micMode === 'ptt') session.setMic('ptt', false)
    }
    document.addEventListener('keydown', down)
    document.addEventListener('keyup', up)
    return () => { document.removeEventListener('keydown', down); document.removeEventListener('keyup', up) }
  }, [session])

  const ui: Ui = {
    menu, still, attachRef,
    toggleMenu: name => setMenu(m => (m === name ? null : name)),
    closeMenus: () => setMenu(null),
    openOverlay: name => { setMenu(null); setPick(null); setOverlay(name) },
  }
  const dismiss = (e: React.MouseEvent<HTMLDivElement>) => { if (e.target === e.currentTarget) setOverlay(null) }

  return (
    <div ref={root} className="ui2" data-view={s.view} data-demo={s.demo ? '1' : undefined}>
      {s.view === 'live' ? (
        <div ref={page} className={`page${s.canvas.min ? ' min' : ''}`}
          style={{ gridTemplateColumns: s.canvas.min ? undefined : `1fr ${s.canvas.width}%` }}>
          <Console session={session} s={s} ui={ui} />
          <Canvas session={session} s={s} pageRef={page} />
        </div>
      ) : <Standby session={session} s={s} ui={ui} />}

      {overlay === 'end' && (
        <div className="scrim" onClick={dismiss}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="ui2-endtitle">
            <h3 id="ui2-endtitle">End this live session?</h3>
            <p>TOBI stops listening, the canvas closes, and the session is written to History with a recap you can ask him about later.</p>
            <div className="row">
              <span className="chip"><b className="n">{fmtDur(s.clockSecs)}</b></span>
              <span className="chip"><b className="n">{s.actions}</b> actions</span>
              <span className="chip ok"><b className="n">{s.artifacts.length}</b> artifacts saved</span>
            </div>
            <div className="acts">
              <button className="btn" onClick={() => setOverlay(null)}>Keep going</button>
              <button className="btn danger" onClick={() => { setOverlay(null); session.endSession() }}>End session</button>
            </div>
          </div>
        </div>
      )}

      {overlay === 'history' && (
        <div className="scrim" onClick={dismiss}>
          <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="ui2-histtitle">
            <header>
              <Clock className="ic" style={{ color: 'var(--accent)' }} />
              <h3 id="ui2-histtitle">{pick ? 'Session recap' : 'Session history'}</h3>
              {pick && <button className="iconbtn" aria-label="Back to the list" onClick={() => setPick(null)}><Clock className="ic" /></button>}
              <button className="iconbtn" aria-label="Close" onClick={() => setOverlay(null)} style={pick ? { marginLeft: 0 } : undefined}><Cross /></button>
            </header>
            <div className="body">
              {pick
                ? <div className="doc" style={{ padding: '16px 20px 24px', background: 'transparent' }}><div className="doc-inner"><RecapPane recap={pick} /></div></div>
                : <div style={{ padding: '4px 8px 8px' }}><HistoryRows history={s.history} onPick={r => { if (s.view === 'live') { session.openRecap(r); setOverlay(null) } else setPick(r) }} /></div>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
