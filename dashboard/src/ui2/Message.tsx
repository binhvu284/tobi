// A message is a message wherever it is shown: the same head, the same body, the same
// evidence blocks under it. The console shows the current exchange live; the Script panel
// shows all of them. Nothing is rendered twice, two ways.
import { memo, useLayoutEffect, useRef, useState } from 'react'
import { ActionButton } from '../components/async-ui'
import { BrandMark, brandForModel } from '../components/LlmLogo'
import {
  ActGlyph, Anthropic, BrandGlyph, ChevDown, Cross, FileGlyph, Retry, Stop, Tick,
} from './icons'
import { OWNER_INITIALS, shortModel, spent, type Act, type Msg } from './model'
import type { LiveSession } from './session'

/** the provider mark carries the vendor, not the accent */
export function ProviderMark({ model, className = 'provider' }: { model: string; className?: string }) {
  const brand = brandForModel(model)
  if (brand === 'claude' || !model) return <Anthropic className={className} />
  return <BrandMark brand={brand} size={15} className={className} />
}

function ActRow({ a, onRetry }: { a: Act; onRetry: () => void }) {
  if (a.status === 'running') return (
    <div className="act running">
      <span className="spin" aria-hidden="true" /><span className="nm">{a.name}</span><span className="stat" />
    </div>
  )
  if (a.status === 'failed') return (
    <div className="act failed">
      <ActGlyph icon={a.icon} className="ic" />
      <span className="nm">{a.name}</span>
      <span className="stat">{a.meta}<Cross className="bad" /></span>
      <button className="retry" onClick={onRetry}><Retry className="ic" />Try again</button>
      <p className="why">{a.why}</p>
    </div>
  )
  if (a.status === 'stopped') return (
    <div className="act stopped">
      <ActGlyph icon={a.icon} className="ic" /><span className="nm">{a.name}</span><span className="stat">Stopped</span>
    </div>
  )
  return (
    <div className="act done">
      <ActGlyph icon={a.icon} className="ic" />
      <span className="nm">{a.name}</span>
      <span className="stat">{a.meta}<Tick className="ok" /></span>
    </div>
  )
}

/** three or more finished steps read as a wall, so they become one line */
function Acts({ m, session }: { m: Msg; session: LiveSession }) {
  if (!m.acts.length) return null
  const rows = m.acts.map(a => <ActRow key={a.id} a={a} onRetry={() => session.retry(m.id, a.id)} />)
  if (!m.folded) return <>{rows}</>
  let secs = 0
  for (const a of m.acts) { const hit = /([0-9.]+)s/.exec(a.meta); if (hit) secs += parseFloat(hit[1]) }
  return (
    <div className={`acts${m.actsOpen ? ' open' : ''}`}>
      <button className="actsum" aria-expanded={!!m.actsOpen} onClick={() => session.unfold(m.id)}>
        <ActGlyph icon="tool" className="ic" />
        <span className="nm"><b className="n">{m.acts.length}</b> actions</span>
        <span className="stat">{secs.toFixed(1)}s<ChevDown className="chev" /></span>
      </button>
      <div className="actlist">{rows}</div>
    </div>
  )
}

/** anything that leaves the machine or cannot be undone asks first, in one line, naming the thing */
function ConfirmRow({ m, session }: { m: Msg; session: LiveSession }) {
  const c = m.confirm
  if (!c) return null
  const pending = c.status === 'pending' || c.status === 'busy'
  return (
    <div className={`act ask${c.status === 'rejected' ? ' stopped' : ''}`}>
      <ActGlyph icon="tool" className="ic" />
      <span className="nm">{pending ? 'Needs your OK: ' : c.status === 'approved' ? 'You said yes: ' : 'You said no: '}{c.action.summary || c.action.tool}</span>
      <span className="stat">{pending ? c.action.risk : c.result || c.status}</span>
      {pending && (
        <>
          <ActionButton className="retry" busy={c.status === 'busy'} onAction={() => session.decide(m.id, 'approve')}>Yes, do it</ActionButton>
          <ActionButton className="retry" busy={c.status === 'busy'} onAction={() => session.decide(m.id, 'reject')}>Not now</ActionButton>
        </>
      )}
      {pending && c.result && <p className="why">{c.result}</p>}
    </div>
  )
}

export const Message = memo(function Message({ m, session }: { m: Msg; session: LiveSession }) {
  const p = useRef<HTMLParagraphElement>(null)
  const [clamped, setClamped] = useState(false)
  /* your prompt is a title over the answer: two lines, then it folds. Measured where
     there is a layout to measure, and by length where there is not. */
  useLayoutEffect(() => {
    if (m.who !== 'you' || m.ghost || m.open) return
    const el = p.current
    setClamped(el && el.scrollHeight ? el.scrollHeight > el.clientHeight + 2 : m.text.length > 90)
  }, [m.text, m.who, m.ghost, m.open])

  const cls = ['msg', m.who, m.queued && 'queued', m.ghost && 'ghost', clamped && 'clamped', m.open && 'open'].filter(Boolean).join(' ')
  return (
    <div className={cls}>
      <span className="who-av" aria-hidden="true">{m.who === 'tobi' ? <BrandGlyph /> : OWNER_INITIALS}</span>
      <div className="body">
        <div className="head">
          <b>{m.who === 'tobi' ? 'TOBI' : 'You'}</b>
          <time>{m.time}</time>
          {m.queued && <span className="qchip">QUEUED</span>}
        </div>
        {m.who === 'tobi' && <Acts m={m} session={session} />}
        <div className="say"><p ref={p}>{m.text}{m.caret && <span className="caret" />}</p></div>
        {m.who === 'you' && clamped && (
          <button className="pmore" onClick={() => session.expandPrompt(m.id)}>
            {m.open ? 'Show less' : 'Show all'}<ChevDown className="chev" />
          </button>
        )}
        <ConfirmRow m={m} session={session} />
        {m.files.map(f => (
          <button key={f.id} className="fileref" onClick={() => session.openDoc(f.id)} disabled={!session.state.docs[f.id]}>
            <FileGlyph kind={f.kind} className="ic" />{f.name}
          </button>
        ))}
        {m.notice && <div className="stopnote"><Retry className="ic" /><span>{m.notice}</span></div>}
        {m.receipt && (
          <div className="runmeta">
            <ProviderMark model={m.receipt.model} />
            <span>{shortModel(m.receipt.model)}</span><span>{m.receipt.secs}s</span><span>{spent(m.receipt.tokens)}</span>
          </div>
        )}
        {m.stopnote && <div className="stopnote"><Stop className="ic" /><span>{m.stopnote}</span></div>}
      </div>
    </div>
  )
})
