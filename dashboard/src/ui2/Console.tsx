// The console: three parts, and only the middle one moves.
//   Head: the graph and what it is doing, fixed, never scrolls away.
//   Body: this exchange, and only this one. It scrolls when it is too tall.
//   Dock: always where you left it.
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { useWorkspaceTabs } from '../context/WorkspaceTabsContext'
import {
  ArrowDown, ChevDown, ChevUp, Mic, MicLock, MicMute, Paperclip, Plug, Plus, Power, Send, SpeakerLoud, SpeakerOff, Tick,
} from './icons'
import { Message, ProviderMark } from './Message'
import { Neuron } from './Neuron'
import { clockText, shortModel, spent, type MicMode, type SessionState } from './model'
import type { LiveSession } from './session'

export type MenuName = 'model' | 'add' | 'vol' | 'mic'
export type Ui = {
  menu: MenuName | null
  toggleMenu: (name: MenuName) => void
  closeMenus: () => void
  openOverlay: (name: 'end' | 'history') => void
  still: boolean
  /** the page hands the attach picker to the keyboard shortcut */
  attachRef: React.MutableRefObject<(() => void) | null>
}

/** the header and the receipts are the same number seen twice */
export function Ctx({ tokens, max }: { tokens: number; max: number }) {
  const pct = max > 0 ? (tokens / max) * 100 : 0
  return (
    <span className="ctx" title="Context used">
      <svg className="donut" viewBox="0 0 36 36" aria-hidden="true">
        <circle cx="18" cy="18" r="15" fill="none" stroke="#2b333d" strokeWidth="4" />
        <circle cx="18" cy="18" r="15" fill="none" stroke="#58a6ff" strokeWidth="4" strokeLinecap="round"
          strokeDasharray={`${(pct * 0.942).toFixed(1)} 94.2`} transform="rotate(-90 18 18)" />
      </svg>
      <span className="pct">{pct < 10 ? pct.toFixed(1) : Math.round(pct)}%</span>
      <span className="of">{(tokens / 1000).toFixed(1)}k / {Math.round(max / 1000)}k</span>
    </span>
  )
}

/** the models, grouped under their provider when there is more than one, in a list that
 *  scrolls while the note under it stays put */
export function ModelMenu({ s, session, className, onClose }: {
  s: SessionState; session: LiveSession; className: string; onClose: () => void
}) {
  const groups: { name: string; rows: SessionState['models'] }[] = []
  for (const m of s.models) {
    const name = m.group || ''
    const g = groups.find(x => x.name === name)
    if (g) g.rows.push(m); else groups.push({ name, rows: [m] })
  }
  const headed = groups.length > 1
  // twenty models scroll; the one in use is where the eye lands when the menu opens
  const list = useRef<HTMLDivElement>(null)
  useEffect(() => { list.current?.querySelector('button.on')?.scrollIntoView({ block: 'center' }) }, [])
  return (
    <div className={`menu ${className}`} role="menu">
      <div className="mlist" ref={list}>
        {groups.map(g => (
          <div key={g.name} className="mgroup">
            {headed && <div className="lab mhead">{g.name}</div>}
            {g.rows.map(m => (
              <button key={m.id} role="menuitemradio" aria-checked={m.id === s.model} className={m.id === s.model ? 'on' : ''}
                title={m.id} onClick={() => { void session.setModel(m.id); onClose() }}>
                <Tick className="ic tick" /><ProviderMark model={m.id} /><span className="mn">{m.label}</span>
                {m.hint && <span className="k">{m.hint}</span>}
              </button>
            ))}
          </div>
        ))}
        {!s.models.length && <p className="foot">{s.modelsError ? s.modelsError : 'Finding the models…'}</p>}
      </div>
      <p className="foot">The model can change mid-session. The context already spent stays spent.</p>
    </div>
  )
}

function micLabel(mode: MicMode, live: boolean) {
  return mode === 'locked' ? 'Voice is locked. Choose a mode from the menu'
    : mode === 'ptt' ? 'Push to talk. Hold Space, or hold this button'
    : (live ? 'Listening. Click to stop' : 'Voice is off. Click to listen')
}

export function Console({ session, s, ui }: { session: LiveSession; s: SessionState; ui: Ui }) {
  const { openTab } = useWorkspaceTabs()
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const fileInput = useRef<HTMLInputElement>(null)
  useEffect(() => { ui.attachRef.current = () => fileInput.current?.click(); return () => { ui.attachRef.current = null } }, [ui.attachRef])

  const send = () => {
    if (!text.trim() && !files.length) return
    session.send(text, files)
    setText(''); setFiles([])
  }
  const onKey = (ev: KeyboardEvent<HTMLInputElement>) => { if (ev.key === 'Enter') { ev.preventDefault(); send() } }

  /* ── Scrolling: the view follows him only while you are already at the bottom ──
     The moment you scroll up it lets go and stays where you left it, and anything that
     lands while you are up there is counted on the way back down. */
  const convo = useRef<HTMLDivElement>(null)
  const stuck = useRef(true)
  const [jump, setJump] = useState({ hidden: true, unread: 0 })
  const unread = useRef(0)
  const paintJump = () => setJump({ hidden: stuck.current, unread: unread.current })
  const measure = useCallback(() => {
    const c = convo.current
    if (!c) return
    stuck.current = c.scrollHeight - c.scrollTop - c.clientHeight < 26
    if (stuck.current) unread.current = 0
    paintJump()
  }, [])
  const bottom = (smooth: boolean) => {
    const c = convo.current
    if (!c) return
    if (smooth) c.scrollTo({ top: c.scrollHeight, behavior: 'smooth' })
    else c.scrollTop = c.scrollHeight
  }
  const toLatest = () => { stuck.current = true; unread.current = 0; bottom(true); paintJump() }

  const exchange = s.transcript.slice(s.exchangeStart)
  const last = exchange[exchange.length - 1]
  const blocks = exchange.length + exchange.reduce((n, m) => n + m.acts.length + m.files.length + (m.receipt ? 1 : 0) + (m.stopnote ? 1 : 0), 0)
  const prevBlocks = useRef(0)
  useLayoutEffect(() => { stuck.current = true; unread.current = 0; paintJump() }, [s.exchangeStart])
  useLayoutEffect(() => {
    const landed = blocks !== prevBlocks.current      // a whole block landed
    prevBlocks.current = blocks
    if (landed) { if (!stuck.current) { unread.current++; paintJump() } else bottom(true) }
    else if (stuck.current) bottom(false)             // per character: creeping, not jumping
  }, [blocks, last?.text, last?.open, last?.actsOpen])

  const elapsed = s.timing ? `${((s.tick - s.since) / 1000).toFixed(1)}s` : ''

  return (
    <section className="console" aria-label="Conversation">
      <div className="statusbar">
        <button className="model" aria-haspopup="menu" aria-expanded={ui.menu === 'model'} aria-busy={s.modelBusy}
          onClick={() => ui.toggleMenu('model')}>
          <ProviderMark model={s.model} />
          <span className="mname">{shortModel(s.model)}</span>
          <ChevDown className="ic chev" style={{ width: 13, height: 13 }} />
        </button>
        {ui.menu === 'model' && <ModelMenu s={s} session={session} className="modelmenu" onClose={ui.closeMenus} />}
        <span className="rule" />
        <Ctx tokens={s.ctxTokens} max={s.ctxMax} />
        <span className="rule" />
        <span className="clock">{clockText(s.clockSecs)}</span>
        <span className="health" title={s.health.detail}
          style={s.health.ok ? undefined : { background: 'var(--warn)', boxShadow: '0 0 0 3px rgba(210,153,34,.14),0 0 10px rgba(210,153,34,.5)' }} />
      </div>

      <div className="stage">
        <Neuron variant="live" mood={s.mood} ctxPct={s.ctxMax ? (s.ctxTokens / s.ctxMax) * 100 : 0}
          label={`TOBI is ${s.label.toLowerCase()}`} still={ui.still} />
        <div className={`statusslot${s.mood === 'idle' ? ' gone' : ''}`}>
          <div className={`status${s.timing ? ' timing' : ''}${s.run || s.mood === 'listening' ? ' stoppable' : ''}`}
            data-state={s.mood} role="status" aria-live="polite" aria-atomic="true">
            <span className="sglyph" aria-hidden="true">
              <span className="g g-dot" />
              <span className="g g-bars"><i /><i /><i /></span>
              <svg className="g g-arc" viewBox="0 0 24 24">
                <circle className="track" cx="12" cy="12" r="8.4" />
                <circle className="run" cx="12" cy="12" r="8.4" />
              </svg>
            </span>
            <span key={s.labelKey} className="slabel in">{s.label}</span>
            <span className="srun">
              <span className="selapsed">{elapsed}</span>
              {s.timing && s.tokens > 0 && <span className="stokens">{spent(s.tokens)}</span>}
            </span>
            <button className="sstop" onClick={() => session.stopRun()}>Esc to stop</button>
          </div>
        </div>
      </div>

      {/* one exchange at a time, built by the renderer the script panel uses */}
      <div className="convowrap">
        <div className="convo" tabIndex={0} ref={convo} onScroll={measure}>
          <div className="script">
            {exchange.map(m => <Message key={m.id} m={m} session={session} />)}
          </div>
        </div>
        {!jump.hidden && (
          <button className={`jump${jump.unread ? ' new' : ''}`} onClick={toLatest}>
            <ArrowDown className="ic" />Jump to latest<span className="unread">{jump.unread || ''}</span>
          </button>
        )}
      </div>

      <div className="dock">
        <button className="sq" aria-label="Add a file or a connector" aria-haspopup="menu" aria-expanded={ui.menu === 'add'}
          onClick={() => ui.toggleMenu('add')}><Plus /></button>
        {ui.menu === 'add' && (
          <div className="menu addmenu" role="menu">
            <button onClick={() => { ui.closeMenus(); fileInput.current?.click() }}>
              <Paperclip />Attach a file<span className="keys"><kbd>Ctrl</kbd><kbd>U</kbd></span>
            </button>
            <button onClick={() => { ui.closeMenus(); openTab('/integrations') }}>
              <Plug />Connect a source<span className="k">Integrations</span>
            </button>
            <p className="foot">Attached files stay with this session and appear on the canvas.</p>
          </div>
        )}
        <input ref={fileInput} type="file" multiple hidden aria-hidden="true" tabIndex={-1}
          onChange={e => { const picked = Array.from(e.target.files || []); if (picked.length) setFiles(f => [...f, ...picked]); e.target.value = '' }} />

        <button className={`sq speak${!s.voiceOn || s.volume === 0 ? ' muted' : ''}`}
          aria-label={s.voiceOn ? `TOBI's voice, ${s.volume} percent` : "TOBI's voice is off"}
          aria-haspopup="menu" aria-expanded={ui.menu === 'vol'} onClick={() => ui.toggleMenu('vol')}>
          <SpeakerLoud className="ic g g-loud" /><SpeakerOff className="ic g g-off" />
        </button>
        {ui.menu === 'vol' && (
          <div className={`menu volmenu${s.voiceOn ? '' : ' off'}`} role="menu">
            <button className={s.voiceOn ? 'on' : ''} role="menuitemcheckbox" aria-checked={s.voiceOn}
              onClick={() => session.setVoice(!s.voiceOn, s.volume)}>
              <Tick className="ic tick" />TOBI&apos;s voice<span className="k">{s.voiceOn ? 'on' : 'off'}</span>
            </button>
            <div className="vol">
              <SpeakerLoud />
              <input type="range" min={0} max={100} value={s.volume} step={1} aria-label="Volume"
                style={{ '--fill': `${s.volume}%` } as CSSProperties}
                onChange={e => session.setVoice(s.voiceOn, Number(e.target.value))} />
              <span className="pctv">{s.volume}%</span>
            </div>
            <p className="foot">His voice only. Nothing else in the room gets quieter.</p>
          </div>
        )}

        <div className="field">
          {files.map(f => (
            <span className="chip info" key={f.name + f.size}>{f.name}
              <button aria-label={`Remove ${f.name}`} onClick={() => setFiles(list => list.filter(x => x !== f))}>×</button>
            </span>
          ))}
          <input type="text" placeholder="Type to TOBI. He finishes speaking first." aria-label="Message TOBI"
            value={text} onChange={e => setText(e.target.value)} onKeyDown={onKey} />
          <button className="send" aria-label="Send" onClick={send}><Send className="ic" /></button>
        </div>

        <div className={`ctrl mic m-${s.micMode}${s.micLive ? ' live' : ''}`} role="group" aria-label="Voice">
          <button className="glyph" aria-label={micLabel(s.micMode, s.micLive)}
            onClick={() => { if (s.micMode === 'onoff') session.setMic('onoff', !s.micLive); else if (s.micMode === 'locked') ui.toggleMenu('mic') }}
            onPointerDown={e => { if (s.micMode === 'ptt') { e.preventDefault(); session.setMic('ptt', true) } }}
            onPointerUp={() => { if (s.micMode === 'ptt') session.setMic('ptt', false) }}
            onPointerLeave={() => { if (s.micMode === 'ptt' && s.micLive) session.setMic('ptt', false) }}
            onPointerCancel={() => { if (s.micMode === 'ptt') session.setMic('ptt', false) }}>
            <MicLock className="ic g g-lock" /><Mic className="ic g g-mic" /><MicMute className="ic g g-mute" />
          </button>
          <span className="div" />
          <button className="drop" aria-label="Voice mode" aria-haspopup="menu" aria-expanded={ui.menu === 'mic'}
            onClick={() => ui.toggleMenu('mic')}><ChevUp className="chev" /></button>
        </div>
        {ui.menu === 'mic' && (
          <div className="menu micmenu" role="menu">
            {([['onoff', 'On and off'], ['ptt', 'Push to talk'], ['locked', 'Locked']] as [MicMode, string][]).map(([mode, name]) => (
              <button key={mode} role="menuitemradio" aria-checked={s.micMode === mode} className={s.micMode === mode ? 'on' : ''}
                onClick={() => { session.setMic(mode, false); ui.closeMenus() }}>
                <Tick className="ic tick" />{name}
                {mode === 'onoff' && <span className="keys"><kbd>Alt</kbd><kbd>M</kbd></span>}
                {mode === 'ptt' && <span className="keys">hold <kbd>Space</kbd></span>}
                {mode === 'locked' && <span className="k">menu only</span>}
              </button>
            ))}
            <p className="foot">Esc puts the microphone back to Locked from anywhere.</p>
          </div>
        )}

        <span className="rule" />
        <button className="ctrl end" aria-label="End the session" onClick={() => ui.openOverlay('end')}><Power className="ic" /></button>
      </div>
    </section>
  )
}
