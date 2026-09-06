// Screen 01: asleep, then a real staged boot that hands over to the session.
import { Ctx, ModelMenu, type Ui } from './Console'
import { ChevDown, Clock, Cross, Tick } from './icons'
import { ProviderMark } from './Message'
import { Neuron } from './Neuron'
import { fmtDur, shortModel, type SessionState } from './model'
import type { LiveSession } from './session'

function ago(iso: string) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

export function Standby({ session, s, ui }: { session: LiveSession; s: SessionState; ui: Ui }) {
  if (s.view === 'boot') return <Boot session={session} s={s} ui={ui} />
  const last = s.history[0]
  return (
    <div className="page solo">
      <section className="console" aria-label="Session">
        <div className="corner">
          <button className="pill" aria-haspopup="menu" aria-expanded={ui.menu === 'model'} aria-busy={s.modelBusy}
            onClick={() => ui.toggleMenu('model')}>
            <ProviderMark model={s.model} />
            <span className="mname">{s.model ? shortModel(s.model) : s.modelsError ? 'no model' : 'finding a model…'}</span>
            <ChevDown className="ic chev" style={{ width: 13, height: 13 }} />
          </button>
          {ui.menu === 'model' && <ModelMenu s={s} session={session} className="cornermenu" onClose={ui.closeMenus} />}
          <button className="pill" onClick={() => ui.openOverlay('history')}>
            <Clock className="ic" style={{ width: 15, height: 15, color: 'var(--muted)' }} />History
          </button>
        </div>
        <div className="stage">
          <Neuron variant="asleep" label="TOBI is asleep" still={ui.still} />
          <div className="state" style={{ color: 'var(--faint)' }}>Asleep</div>
          <button className="start" disabled={s.view !== 'standby'} onClick={() => void session.goBoot()}>Start TOBI</button>
          <p className="lastrun">
            {last
              ? <>Last session <b className="lastwhen">{ago(last.endedAt)}</b> · {fmtDur(last.secs)} · {last.actions} actions</>
              : <>No session yet. The first one lands here when it ends.</>}
          </p>
        </div>
      </section>
    </div>
  )
}

function Boot({ session, s, ui }: { session: LiveSession; s: SessionState; ui: Ui }) {
  const b = s.boot
  const ready = b.n === b.checks.length
  return (
    <div className="page solo">
      <section className="console" aria-label="Starting the session">
        <div className="statusbar" style={{ opacity: ready ? 1 : 0.5 }}>
          <span className="model"><ProviderMark model={s.model} />{shortModel(s.model) || '—'}</span>
          <span className="rule" />
          <Ctx tokens={b.ctx} max={s.ctxMax} />
          <span className="rule" />
          <span className="clock">00:00</span>
          <span className="health" style={ready ? undefined : { background: 'var(--muted)', boxShadow: 'none' }} />
        </div>
        <div className="stage">
          <Neuron variant="booting" label="TOBI is waking up" still={ui.still} />
          <div className="state shimmer">Waking up</div>
          <div className="checks">
            {b.checks.map(c => (
              <div key={c.name} className={`check ${c.status}`}>
                <span className="st">
                  {c.status === 'done' ? <Tick className="ic" /> : c.status === 'now' ? <span className="spin" /> : c.status === 'failed' ? <Cross className="ic" /> : null}
                </span>
                <span className="nm">{c.name}</span>
                <span className="val">{c.status === 'now' ? '…' : c.val}</span>
              </div>
            ))}
          </div>
          <div className="bootbar">
            <span className="track"><i style={{ width: `${(b.n / b.checks.length) * 100}%` }} /></span>
            <span className="num">{b.n} of {b.checks.length} · {b.left}s</span>
          </div>
          {b.error ? (
            <>
              <p className="boothint" style={{ color: 'var(--bad)' }}>{b.error}</p>
              <div className="bootacts">
                <button className="btn" disabled={!b.error} onClick={() => void session.goBoot()}>Try again</button>
                <button className="btn" onClick={() => session.goStandby()}>Not now</button>
              </div>
            </>
          ) : <p className="boothint">Starting runs to the end. Nothing to press.</p>}
        </div>
      </section>
    </div>
  )
}
