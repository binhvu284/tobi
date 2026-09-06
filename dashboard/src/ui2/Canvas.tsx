// The canvas. Two kinds of thing live in here and they never mix: the four buttons on the
// right each open a panel, one at a time, no tabs; anything you pick out of a panel becomes
// a document, and the tab bar exists only for documents.
import { useEffect, useRef, useState, type PointerEvent as RPointerEvent, type RefObject } from 'react'
import MarkdownView from '../components/chat/MarkdownView'
import { DesignedPane } from './designed'
import { Book, Clock, Corners, Cross, FileGlyph, Files, Sliders, Tick, TileGlyph, tileClass } from './icons'
import { Message } from './Message'
import {
  MAX_W, MIN_W, SNAP, fmtDur, nowStamp, stick, whenLabel,
  type Doc, type MicMode, type SessionRecap, type SessionState,
} from './model'
import type { LiveSession } from './session'

export function RecapPane({ recap }: { recap: SessionRecap }) {
  const when = whenLabel(recap.startedAt)
  const done = recap.decisions ?? recap.done
  return (
    <>
      <h1 className="rectitle">{when}</h1>
      <p className="lede">What this session was about, and what came out of it.</p>
      <div className="meta">
        <span className="chip info recwhen">{when}</span>
        <span className="chip"><b className="n">{fmtDur(recap.secs)}</b></span>
        <span className="chip"><b className="n">{recap.actions}</b> actions</span>
      </div>
      <h2>In one line</h2>
      <p>{recap.line ?? recap.title}</p>
      <h2>{recap.decisions ? 'Decisions' : 'What was done'}</h2>
      {done.length
        ? <ul>{done.map((d, i) => <li key={i} className="done"><span className="tick"><Tick className="ic" /></span><span>{d}</span></li>)}</ul>
        : <p>Nothing ran: no step was needed.</p>}
      <h2>Left open</h2>
      {recap.open.length
        ? <ul>{recap.open.map((o, i) => <li key={i}><span className="tick" /><span>{o}</span></li>)}</ul>
        : <p>Nothing left open.</p>}
    </>
  )
}

export function HistoryRows({ history, onPick }: { history: SessionRecap[]; onPick: (r: SessionRecap) => void }) {
  if (!history.length) return <p>Nothing yet. The first session lands here when it ends.</p>
  return (
    <div className="rows" style={{ marginTop: 18 }}>
      {history.map(r => (
        <button key={r.id} className="rowitem" onClick={() => onPick(r)}>
          <span className="ftile f-time" aria-hidden="true"><Clock className="ic" /></span>
          <span className="t"><b>{whenLabel(r.startedAt)}</b><span>{r.title}</span></span>
          <span className="r">{fmtDur(r.secs)} · {r.actions}</span>
        </button>
      ))}
    </div>
  )
}

function ArtifactsPane({ s, session }: { s: SessionState; session: LiveSession }) {
  const kb = s.artifacts.reduce((n, a) => n + (parseInt(a.size || '', 10) || 0), 0)
  return (
    <>
      <h1>Session artifacts</h1>
      <p className="lede">What this session produced. Everything here is already on disk.</p>
      <div className="meta">
        <span className="chip"><b className="n">{s.artifacts.length}</b> files</span>
        {kb > 0 && <span className="chip"><b className="n">{kb}</b> KB</span>}
        <span className="chip ok">{s.demo ? 'Autosaved' : 'Saved'}</span>
      </div>
      {s.artifacts.length ? (
        <div className="rows" style={{ marginTop: 18 }}>
          {s.artifacts.map(a => (
            <button key={a.id} className="rowitem" onClick={() => session.openDoc(a.id)} disabled={!s.docs[a.id]}
              title={s.docs[a.id] ? undefined : 'Nothing to open for this one yet'}>
              <span className={`ftile ${tileClass(a.kind)}`} aria-hidden="true"><TileGlyph kind={a.kind} className="ic" /></span>
              <span className="t"><b>{a.name}</b><span>{a.note}</span></span>
              <span className="r">{[a.size, a.at].filter(Boolean).join(' · ')}</span>
            </button>
          ))}
        </div>
      ) : <p>Nothing yet. Files he makes in this session land here.</p>}
    </>
  )
}

function ScriptPane({ s, session }: { s: SessionState; session: LiveSession }) {
  const msgs = s.transcript.filter(m => !m.ghost)
  return (
    <>
      <h1>Session script</h1>
      <p className="lede">Everything said and done, in order, exactly as it appeared while it happened.
        It writes itself and saves when the session ends.</p>
      <div className="meta">
        <span className="chip">Started <b className="n">{s.startedAt ? nowStamp(new Date(s.startedAt)) : '--:--'}</b></span>
        <span className="chip"><b className="n">{fmtDur(s.clockSecs)}</b></span>
        <span className="chip"><b className="n">{s.actions}</b> actions</span>
        <span className="chip"><b className="n">{s.artifacts.length}</b> artifacts</span>
      </div>
      <div className="thread">{msgs.map(m => <Message key={m.id} m={m} session={session} />)}</div>
    </>
  )
}

function ConfigurePane({ s, session }: { s: SessionState; session: LiveSession }) {
  const modes: [MicMode, string, string][] = [
    ['onoff', 'On and off', 'Click the microphone, or press the shortcut'],
    ['ptt', 'Push to talk', 'Hold the key, speak, let go'],
    ['locked', 'Locked', 'Nothing opens the microphone but this menu'],
  ]
  return (
    <>
      <h1>Configure</h1>
      <p className="lede">These settings change the shell you are looking at right now.</p>
      <div className="set" style={{ marginTop: 22 }}>
        <section>
          <h3>Voice</h3>
          <p>How the microphone opens. Locked is the state every session starts in.</p>
          <div className="opts">
            {modes.map(([mode, name, hint]) => (
              <button key={mode} className={`opt${s.micMode === mode ? ' on' : ''}`} role="radio" aria-checked={s.micMode === mode}
                onClick={() => session.setMic(mode, false)}>
                <span className="mark" /><span className="t"><b>{name}</b><span>{hint}</span></span>
                {mode === 'onoff' && <span className="keys"><kbd>Alt</kbd><kbd>M</kbd></span>}
                {mode === 'ptt' && <span className="keys"><kbd>Space</kbd></span>}
                {mode === 'locked' && <span className="k">none</span>}
              </button>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}

function DocView({ doc }: { doc: Doc }) {
  const b = doc.body
  if (b.type === 'designed') return <DesignedPane pane={b.pane} />
  if (b.type === 'recap') return <RecapPane recap={b.recap} />
  return (
    <>
      <h1>{doc.title}</h1>
      <div className="meta">
        {doc.at && <span className="chip">Made <b className="n">{doc.at}</b></span>}
        {doc.size && <span className="chip"><b className="n">{doc.size}</b></span>}
      </div>
      {b.type === 'image'
        ? <img src={b.src} alt={b.caption || doc.title} style={{ maxWidth: '100%', marginTop: 18, borderRadius: 'var(--r-ctrl)', border: '1px solid var(--line-soft)' }} />
        : <div style={{ marginTop: 18 }}><MarkdownView content={b.text} /></div>}
    </>
  )
}

export function Canvas({ session, s, pageRef }: { session: LiveSession; s: SessionState; pageRef: RefObject<HTMLDivElement> }) {
  const c = s.canvas
  const showing = c.panel ?? (c.docs.length ? c.active : null)
  const [snapped, setSnapped] = useState(false)
  const doc = useRef<HTMLDivElement>(null)
  useEffect(() => { if (doc.current) doc.current.scrollTop = 0 }, [showing])

  /* the grip really resizes, within the range the layout stays readable in */
  const onGrip = (ev: RPointerEvent<HTMLSpanElement>) => {
    const page = pageRef.current
    if (c.min || !page) return
    ev.preventDefault()
    const box = page.getBoundingClientRect()
    const move = (e: PointerEvent) => {
      const frac = (e.clientX - box.left) / box.width
      const w = stick(Math.round((1 - frac) * 100))
      const width = Math.max(MIN_W, Math.min(MAX_W, w))
      setSnapped(SNAP.includes(width))     // near a preset, take the preset: the edge should feel magnetic
      session.setWidth(width)
    }
    const up = () => { setSnapped(false); window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const n = s.artifacts.length
  const panelButton = (name: typeof c.panel & string, label: string, glyph: JSX.Element, badge?: number) => (
    <button className={`cbtn${c.panel === name ? ' on' : ''}`} aria-label={label} aria-pressed={c.panel === name}
      onClick={() => session.openPanel(name)}>
      {glyph}{badge ? <span className="badge">{badge}</span> : null}
    </button>
  )

  let pane: JSX.Element | null = null
  if (showing === 'artifacts') pane = <ArtifactsPane s={s} session={session} />
  else if (showing === 'script') pane = <ScriptPane s={s} session={session} />
  else if (showing === 'history') pane = (
    <>
      <h1>Session history</h1>
      <p className="lede">Every live session, with what came out of it. Ask TOBI about any of them by name.</p>
      <HistoryRows history={s.history} onPick={r => session.openRecap(r)} />
    </>
  )
  else if (showing === 'configure') pane = <ConfigurePane s={s} session={session} />
  else if (showing && s.docs[showing]) pane = <DocView doc={s.docs[showing]} />

  return (
    <section className={`canvas${c.min ? ' min' : ''}${c.bleed ? ' bleed' : ''}${showing ? '' : ' empty'}`} aria-label="Canvas">
      <span className={`grip${snapped ? ' snapped' : ''}`} role="separator" aria-label="Resize the canvas" aria-orientation="vertical"
        onPointerDown={onGrip} />
      <div className="cbar">
        <button className="cbtn" data-act="collapse" aria-label="Close the canvas" onClick={() => session.toggleMin()}><Cross /></button>
        <button className="cbtn" data-act="full" aria-label={c.bleed ? 'Leave full screen' : 'Full screen'} onClick={() => session.toggleFull()}><Corners /></button>
        <span className="spacer" />
        <div className="cgroup">
          {panelButton('artifacts', `Session artifacts, ${n} in this session`, <Files />, n)}
          {panelButton('script', 'Session script', <Book />)}
          {panelButton('history', 'Session history', <Clock />)}
          {panelButton('configure', 'Configure', <Sliders />)}
        </div>
      </div>

      {!c.panel && c.docs.length > 0 && (
        <div className="ctabs" role="tablist" aria-label="Open documents">
          {c.docs.map(id => {
            const d = s.docs[id]
            if (!d) return null
            const on = id === c.active
            return (
              <button key={id} className={`ctab${on ? ' on' : ''}`} role="tab" aria-selected={on} onClick={() => session.selectDoc(id)}>
                <FileGlyph kind={d.kind} className="ic" />
                <span className="tname">{d.title}</span>{' '}
                <span className="x" role="button" aria-label={`Close ${d.title}`}
                  onClick={e => { e.stopPropagation(); session.closeDoc(id) }}>×</span>
              </button>
            )
          })}
        </div>
      )}

      <div className="doc" tabIndex={0} ref={doc}>
        <div className="doc-inner">{pane}</div>
      </div>
    </section>
  )
}
