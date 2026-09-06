// TOBI UI 2.0 (#36) — the live session, as one store.
//
// This is the shell's script (TOBI_UI_2_SHELL.html) with the DOM taken out: the same
// functions, the same names, the same timings, writing to one immutable state object that
// React reads through useSyncExternalStore. A driver (drivers.ts) does the work behind the
// glass and reports back through a Sink; nothing here knows whether the run was scripted
// or real. The instance outlives the page so a closed tab does not end a session.
import { useSyncExternalStore } from 'react'
import { get } from '../apiCore'
import { softFail } from '../lib/report'
import { setWave } from './brain'
import { chatDriver, scriptedDriver } from './drivers'
import {
  STATES, nowStamp, uid, whenLabel, widthFor,
  type Act, type BootCheck, type CanvasState, type Doc, type Driver, type MicMode, type Mood, type Msg,
  type Panel, type SessionRecap, type SessionState, type Sink,
} from './model'

/* ── the boot, on a real clock ─────────────────────────────────────────────
   Each check is revealed no earlier than its designed moment and no earlier
   than its answer arrives, so the rhythm is the shell's and the values are true. */
const BOOT = [520, 1240, 2050, 2960, 3820], BOOT_END = 4600
const CHECKS = ['Model connected', 'Memory linked', 'Tools loaded', 'Canvas ready to call', 'Voice engine']
const BOOT_CTX = [0, 1200, 2400, 3800, 5600, 8000]   // the designed handover spends 8k

const HIST_KEY = 'tobi.ui2.history', VOICE_KEY = 'tobi.ui2.voice'
function loadJson<T>(key: string, fallback: T): T {
  try { const raw = localStorage.getItem(key); return raw ? (JSON.parse(raw) as T) : fallback } catch { return fallback }
}
function saveJson(key: string, value: unknown) { try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* private mode */ } }
const reason = (e: unknown) => (e instanceof Error ? e.message : String(e || 'no reason was reported'))
const delay = (ms: number) => new Promise<void>(res => setTimeout(res, Math.max(0, ms)))
const blankBoot = (driver: Driver): SessionState['boot'] => ({
  checks: CHECKS.map((name, i) => ({ name, val: driver.bootPreview(i), status: 'wait' })), n: 0, left: 5, error: null, ctx: 0,
})
const blankCanvas = (): CanvasState => ({ panel: null, docs: [], active: null, width: 30, min: true, bleed: false })

function initial(driver: Driver): SessionState {
  const voice = loadJson<{ on: boolean; volume: number }>(VOICE_KEY, { on: true, volume: 70 })
  const seed = driver.seed()
  return {
    demo: driver.demo, view: 'standby', boot: blankBoot(driver),
    mood: 'idle', label: 'Ready', labelKey: 0, timing: false, since: 0, tokens: 0, tick: 0,
    clockSecs: 0, startedAt: 0, ctxTokens: 0, ctxMax: 200000,
    model: '', models: [], modelBusy: false, modelsError: null,
    transcript: [], exchangeStart: 0, run: null, actions: 0,
    micMode: 'locked', micLive: false,
    voiceOn: voice.on !== false, volume: Math.max(0, Math.min(100, Number(voice.volume ?? 70))),
    canvas: blankCanvas(),
    docs: Object.fromEntries(seed.docs.map(d => [d.id, d])),
    artifacts: [], history: driver.demo ? seed.history : loadJson<SessionRecap[]>(HIST_KEY, []),
    health: { ok: true, detail: 'All systems healthy' },
  }
}

export class LiveSession {
  state: SessionState
  private subs = new Set<() => void>()
  private timers = new Set<number>()
  private clock: number | null = null
  private elapsedTick: number | null = null
  private healthTick: number | null = null
  private abort: AbortController | null = null
  private ear: { msgId: string; handle: { stop(): string } } | null = null
  private queue: { id: string; text: string; files: File[] }[] = []
  private lastAsk = ''
  private bootToken = 0
  private greetingToken = 0

  constructor(readonly driver: Driver) { this.state = initial(driver) }

  subscribe = (fn: () => void) => { this.subs.add(fn); return () => { this.subs.delete(fn) } }
  getSnapshot = () => this.state

  private patch(p: Partial<SessionState>) { this.state = { ...this.state, ...p }; for (const f of this.subs) f() }
  private updateMsg(id: string, fn: (m: Msg) => Msg) {
    this.patch({ transcript: this.state.transcript.map(m => (m.id === id ? fn(m) : m)) })
  }
  private updateAct(msgId: string, actId: string, fn: (a: Act) => Act) {
    this.updateMsg(msgId, m => ({ ...m, acts: m.acts.map(a => (a.id === actId ? fn(a) : a)) }))
  }
  private after(ms: number, fn: () => void) {
    const id = window.setTimeout(() => { this.timers.delete(id); fn() }, ms)
    this.timers.add(id)
  }
  private stopTimers() { for (const id of this.timers) clearTimeout(id); this.timers.clear() }

  /* ── models ─────────────────────────────────────────────────────────────── */
  async loadModels() {
    try {
      const { models, current } = await this.driver.models()
      const model = this.state.model && models.some(m => m.id === this.state.model) ? this.state.model : current
      this.patch({ models, model, modelsError: null, ctxMax: models.find(m => m.id === model)?.context || 200000 })
    } catch (e) { this.patch({ modelsError: reason(e) }) }
  }
  async setModel(id: string) {
    if (id === this.state.model) return
    this.patch({ model: id, modelBusy: true, ctxMax: this.state.models.find(m => m.id === id)?.context || 200000 })
    try { await this.driver.chooseModel(id) }
    catch (e) { softFail('the model change')(e) }
    finally { this.patch({ modelBusy: false }) }
  }

  /* ── Screen 01 · starting, on a real clock ──────────────────────────────── */
  async goBoot() {
    this.leaveLive()
    const token = ++this.bootToken
    const checks: BootCheck[] = CHECKS.map((name, i) => ({ name, val: this.driver.bootPreview(i), status: 'wait' }))
    this.patch({ view: 'boot' })
    this.setBoot(0, checks)                          // the screen changes before anything is fetched
    const t0 = Date.now()
    if (!this.state.model) {
      await this.loadModels()
      if (token !== this.bootToken) return
      if (!this.state.model) {
        checks[0] = { ...checks[0], val: 'failed', status: 'failed' }
        this.patch({ boot: { ...this.state.boot, checks: [...checks], error: `${CHECKS[0]}: ${this.state.modelsError || 'no model answered'}` } })
        return
      }
    }
    for (let i = 0; i < CHECKS.length; i++) {
      this.setBoot(i, checks)
      try {
        const [val] = await Promise.all([this.driver.bootValue(i, this.state.model), delay(BOOT[i] - (Date.now() - t0))])
        if (token !== this.bootToken) return
        checks[i] = { ...checks[i], val, status: 'done' }
      } catch (e) {
        if (token !== this.bootToken) return
        checks[i] = { ...checks[i], val: 'failed', status: 'failed' }
        this.patch({ boot: { ...this.state.boot, checks: [...checks], error: `${CHECKS[i]}: ${reason(e)}` } })
        return
      }
    }
    this.setBoot(CHECKS.length, checks)
    await delay(BOOT_END - (Date.now() - t0))       // it runs to the end: nothing stops it
    if (token !== this.bootToken) return
    await this.goLive()
  }
  private setBoot(n: number, checks: BootCheck[]) {
    const rows = checks.map((c, i) => ({ ...c, status: i < n ? 'done' : i === n ? 'now' : 'wait' } as BootCheck))
    const left = Math.max(0, Math.round((BOOT_END - (n ? BOOT[n - 1] : 0)) / 1000))
    this.patch({ boot: { checks: rows, n, left, error: null, ctx: this.state.demo ? BOOT_CTX[n] : 0 } })
  }
  goStandby() { this.leaveLive(); this.patch({ view: 'standby', boot: blankBoot(this.driver) }) }

  /* ── Screen 02 · the session ────────────────────────────────────────────── */
  private async goLive() {
    try { await this.driver.prepare(this.state.model) }
    catch (e) { this.patch({ boot: { ...this.state.boot, error: `Could not open a session: ${reason(e)}` } }); return }
    const seed = this.driver.seed()
    this.patch({
      view: 'live', startedAt: Date.now(), clockSecs: 0, actions: 0, transcript: [], exchangeStart: 0, run: null,
      canvas: blankCanvas(), docs: Object.fromEntries(seed.docs.map(d => [d.id, d])), artifacts: seed.artifacts,
      ctxTokens: this.state.demo ? 8000 : 0, micMode: 'locked', micLive: false, boot: blankBoot(this.driver),
    })
    this.clockOn()
    this.pollHealth()
    this.setMood('speaking')
    const m = this.turn('tobi', '')
    const token = ++this.greetingToken
    await this.typeOut(m.id, this.driver.greeting(), () => token === this.greetingToken)
    if (token !== this.greetingToken) return
    this.setMood('idle')
    this.drain()
  }

  /** the answer arrives as it is written, not all at once */
  private typeOut(msgId: string, line: string, alive: () => boolean): Promise<void> {
    return new Promise(res => {
      let i = 0
      this.updateMsg(msgId, m => ({ ...m, caret: true }))
      const iv = window.setInterval(() => {
        if (!alive()) { clearInterval(iv); this.timers.delete(iv); res(); return }
        i++
        this.updateMsg(msgId, m => ({ ...m, text: line.slice(0, i) }))
        if (i >= line.length) {
          clearInterval(iv); this.timers.delete(iv)
          this.after(420, () => { this.updateMsg(msgId, m => ({ ...m, caret: false })); res() })
        }
      }, 22)
      this.timers.add(iv)
    })
  }

  /* ── one state, three views of it ───────────────────────────────────────── */
  setMood(name: Mood, label?: string) {
    const S = STATES[name]
    setWave(S.gain, S.period, S.dir)
    const text = label ?? S.label
    const wasTiming = this.elapsedTick != null
    if (this.elapsedTick != null) { clearInterval(this.elapsedTick); this.elapsedTick = null }
    let { since, tokens } = this.state
    if (S.timed) {
      if (!wasTiming) { since = Date.now(); tokens = 0 }   // one run, however many steps it takes
      // a slow step must never look like a stuck one
      this.elapsedTick = window.setInterval(() => this.patch({ tick: Date.now() }), 100)
    }
    this.patch({
      mood: name, label: text, labelKey: text !== this.state.label ? this.state.labelKey + 1 : this.state.labelKey,
      timing: S.timed, since, tokens, tick: Date.now(),
    })
  }

  private clockOn() {
    this.clockOff()
    this.patch({ clockSecs: 0 })
    this.clock = window.setInterval(() => this.patch({ clockSecs: this.state.clockSecs + 1 }), 1000)
  }
  private clockOff() { if (this.clock != null) clearInterval(this.clock); this.clock = null }

  private pollHealth() {
    if (this.state.demo) return
    const tick = async () => {
      try {
        const h = (await get('/api/health')) as { up?: Record<string, { ok: boolean; detail?: string }> }
        const bad = Object.entries(h.up ?? {}).find(([, u]) => !u.ok)
        this.patch({ health: bad ? { ok: false, detail: `${bad[0]}: ${bad[1].detail || 'down'}` } : { ok: true, detail: 'All systems healthy' } })
      } catch { this.patch({ health: { ok: false, detail: 'Mission Control is not answering' } }) }
    }
    void tick()
    this.healthTick = window.setInterval(() => void tick(), 30000)
  }

  /* ── the transcript ─────────────────────────────────────────────────────── */
  private turn(who: 'you' | 'tobi', text: string, opts: Partial<Pick<Msg, 'queued' | 'ghost' | 'caret'>> = {}): Msg {
    const m: Msg = { id: uid(), who, text, time: nowStamp(), acts: [], files: [], ...opts }
    this.patch({ transcript: [...this.state.transcript, m] })
    return m
  }
  /** one exchange on screen at a time; the Script panel keeps every one of them */
  private newExchange() { this.patch({ exchangeStart: this.state.transcript.length }) }

  send(text: string, files: File[] = []) {
    const clean = text.trim()
    if (!clean && !files.length) return
    const line = clean || `Sent ${files.map(f => f.name).join(', ')}`
    if (this.state.mood !== 'idle' || this.abort) {           // typing never interrupts him
      const mine = this.turn('you', line, { queued: true })   // it waits, visibly, under what he is saying
      this.queue.push({ id: mine.id, text: line, files })
      return
    }
    this.ask(line, files)
  }
  private drain() {
    const next = this.queue.shift()
    if (!next) return
    this.patch({ transcript: this.state.transcript.filter(m => m.id !== next.id) })
    this.ask(next.text, next.files)
  }
  private ask(text: string, files: File[]) {
    this.newExchange()
    this.lastAsk = text
    this.turn('you', text)
    this.answer(text, files)
  }

  private answer(text: string, files: File[]) {
    const msg = this.turn('tobi', '')
    const ac = new AbortController()
    this.abort = ac
    this.patch({ run: { msgId: msg.id, done: 0, total: null } })
    const sink = this.sinkFor(msg.id)
    this.driver.run(text, sink, ac.signal, { attachments: files })
      .catch((e: unknown) => {
        if (ac.signal.aborted) return
        // a turn that fails as a whole is reported like any failed step: whose fault, and Try again
        const id = sink.actStart({ run: 'Finishing the reply', done: 'Finished the reply' })
        sink.actFail(id, {
          name: 'Could not finish the reply', reason: 'no answer',
          why: `TOBI did not get an answer back (${reason(e)}). That is on the service or the model, not on what you asked. Try again sends the same request.`,
        })
      })
      .finally(() => {
        if (this.abort !== ac) return                 // stopped by hand: stopRun already settled it
        this.abort = null
        this.settle(msg.id)
        this.drain()
      })
  }
  private settle(msgId: string) {
    this.updateMsg(msgId, m => ({ ...m, caret: false, folded: m.folded || m.acts.length >= 3 }))
    this.patch({ run: null })
    this.setMood('idle')
  }

  /** the one control over a run: everything that landed is kept */
  stopRun() {
    const ac = this.abort
    const run = this.state.run
    if (this.state.mood === 'idle' || !ac || !run) return
    this.abort = null
    ac.abort()
    const { done, total } = run
    this.updateMsg(run.msgId, m => ({
      ...m, caret: false,
      acts: m.acts.map(a => (a.status === 'running' ? { ...a, status: 'stopped', meta: 'Stopped' } : a)),
      stopnote: `Stopped by you after ${done}${total != null ? ` of ${total}` : ''} steps. Everything above it is kept.`,
    }))
    this.patch({ run: null })
    this.setMood('idle')
    this.drain()
  }

  /** a failed step offers the one thing worth offering: doing it again */
  retry(msgId: string, actId: string) {
    const msg = this.state.transcript.find(m => m.id === msgId)
    const act = msg?.acts.find(a => a.id === actId)
    if (!act || act.status !== 'failed' || this.abort) return
    if (!this.driver.retriesInPlace) { this.ask(this.lastAsk, []); return }
    const ac = new AbortController()
    this.abort = ac
    this.updateAct(msgId, actId, a => ({ ...a, status: 'running', name: a.spec.run, meta: '', why: undefined, startedAt: Date.now() }))
    this.patch({ run: { msgId, done: 0, total: null } })
    this.driver.retry(actId, act.spec, this.sinkFor(msgId), ac.signal)
      .catch(() => { /* stopped by hand */ })
      .finally(() => { if (this.abort !== ac) return; this.abort = null; this.settle(msgId); this.drain() })
  }

  /** the driver writes to the screen through this, and only this */
  private sinkFor(msgId: string): Sink {
    const s = this
    return {
      mood: (n, l) => s.setMood(n, l),
      plan: total => s.patch({ run: s.state.run && { ...s.state.run, total } }),
      actStart: spec => {
        const id = uid('a')
        const act: Act = { id, status: 'running', name: spec.run, meta: '', icon: spec.icon ?? 'tool', spec, startedAt: Date.now() }
        s.updateMsg(msgId, m => ({ ...m, acts: [...m.acts, act] }))
        return id
      },
      actDone: (id, meta) => {
        s.updateAct(msgId, id, a => ({
          ...a, status: 'done', name: a.spec.done,
          meta: meta ?? a.spec.meta ?? `${((Date.now() - a.startedAt) / 1000).toFixed(1)}s`,
        }))
        s.patch({ actions: s.state.actions + 1, run: s.state.run && { ...s.state.run, done: s.state.run.done + 1 } })
      },
      actFail: (id, fail) => {
        s.updateAct(msgId, id, a => ({ ...a, status: 'failed', name: fail.name, meta: fail.reason, why: fail.why }))
        s.patch({ run: s.state.run && { ...s.state.run, done: s.state.run.done + 1 } })
      },
      open: doc => { s.patch({ docs: { ...s.state.docs, [doc.id]: doc } }); s.openDoc(doc.id) },
      delta: text => s.updateMsg(msgId, m => ({ ...m, text: m.text + text, caret: true, folded: m.folded || m.acts.length >= 3 })),
      file: ref => {
        s.updateMsg(msgId, m => ({ ...m, files: m.files.some(f => f.id === ref.id) ? m.files : [...m.files, ref] }))
        if (!s.state.artifacts.some(a => a.id === ref.id)) s.patch({ artifacts: [...s.state.artifacts, ref] })
      },
      receipt: r => s.updateMsg(msgId, m => ({ ...m, receipt: r })),
      // the demo counts context up as the shell did; a real call reports the context it used
      spend: (n, max) => s.patch({ ctxTokens: s.state.demo ? s.state.ctxTokens + n : n, ctxMax: max ?? s.state.ctxMax }),
      tokens: n => s.patch({ tokens: s.state.tokens + n }),
      spentTokens: () => s.state.tokens,
      elapsed: () => (Date.now() - s.state.since) / 1000,
      model: () => s.state.model,
      confirm: action => s.updateMsg(msgId, m => ({ ...m, confirm: { action, status: 'pending' } })),
      note: text => s.updateMsg(msgId, m => ({ ...m, notice: text })),
    }
  }

  /** anything that leaves the machine or cannot be undone asked first; this is the answer */
  async decide(msgId: string, decision: 'approve' | 'reject') {
    const c = this.state.transcript.find(m => m.id === msgId)?.confirm
    if (!c || c.status !== 'pending') return
    this.updateMsg(msgId, m => ({ ...m, confirm: { ...c, status: 'busy' } }))
    try {
      const result = await this.driver.decide(c.action, decision)
      this.updateMsg(msgId, m => ({ ...m, confirm: { action: c.action, status: decision === 'approve' ? 'approved' : 'rejected', result } }))
      if (decision === 'approve') this.patch({ actions: this.state.actions + 1 })
    } catch (e) {
      this.updateMsg(msgId, m => ({ ...m, confirm: { ...c, status: 'pending', result: reason(e) } }))
      throw e
    }
  }

  unfold(msgId: string) { this.updateMsg(msgId, m => ({ ...m, actsOpen: !m.actsOpen })) }
  expandPrompt(msgId: string) { this.updateMsg(msgId, m => ({ ...m, open: !m.open })) }

  /* ── voice: three modes, and what he hears ──────────────────────────────── */
  setMic(mode: MicMode, live: boolean) {
    const micLive = mode === 'locked' ? false : live && !this.abort   // barge-in is phase 2: a run keeps the ear shut
    this.patch({ micMode: mode, micLive })
    if (micLive) this.openEar()
    else if (this.state.mood === 'listening') this.closeEar()
  }
  private openEar() {
    if (this.ear) return
    this.setMood('listening')
    const g = this.turn('you', '', { ghost: true, caret: true })
    const handle = this.driver.hear({ heard: text => this.updateMsg(g.id, m => ({ ...m, text })) })
    this.ear = { msgId: g.id, handle }
  }
  private closeEar() {
    if (!this.ear) return
    const { msgId, handle } = this.ear
    this.ear = null
    const said = handle.stop()
    this.patch({ transcript: this.state.transcript.filter(m => m.id !== msgId) })
    if (!said) { this.setMood('idle'); return }
    this.ask(said, [])
  }

  /* ── his voice: on or off, and how loud ─────────────────────────────────── */
  setVoice(on: boolean, volume: number) {
    this.patch({ voiceOn: on, volume })
    saveJson(VOICE_KEY, { on, volume })
  }

  /* ── the canvas: panels one at a time, documents in tabs ────────────────── */
  private setCanvas(next: CanvasState) {
    const showing = next.panel ?? (next.docs.length ? next.active : null)
    // nothing to show, so there is no canvas to show it in
    this.patch({ canvas: showing ? next : { ...next, min: true, bleed: false } })
  }
  openPanel(name: Panel) {
    const c = this.state.canvas
    const panel = c.panel === name ? null : name
    this.setCanvas({ ...c, panel, width: widthFor(panel ?? c.active), min: false })
  }
  openDoc(id: string) {
    if (!this.state.docs[id]) return
    const c = this.state.canvas
    const docs = c.docs.filter(d => d !== id)
    docs.push(id)
    if (docs.length > 4) docs.shift()          // four documents stay open; the least used parks
    this.setCanvas({ ...c, panel: null, docs, active: id, width: widthFor(id), min: false })
  }
  openRecap(recap: SessionRecap) {
    const id = `recap:${recap.id}`
    this.patch({ docs: { ...this.state.docs, [id]: { id, title: whenLabel(recap.startedAt), kind: 'recap', body: { type: 'recap', recap } } } })
    this.openDoc(id)
  }
  selectDoc(id: string) {
    const c = this.state.canvas
    if (!c.docs.includes(id)) return
    this.setCanvas({ ...c, panel: null, active: id, width: widthFor(id) })
  }
  closeDoc(id: string) {
    const c = this.state.canvas
    const docs = c.docs.filter(d => d !== id)
    const active = docs[docs.length - 1] ?? null
    this.setCanvas({ ...c, docs, active, width: active ? widthFor(active) : c.width })
  }
  setWidth(width: number) { this.patch({ canvas: { ...this.state.canvas, width } }) }
  toggleMin() { const c = this.state.canvas; this.patch({ canvas: { ...c, min: !c.min } }) }
  /** full screen means the browser tab, not the machine: the canvas covers the page */
  toggleFull() { const c = this.state.canvas; const bleed = !c.bleed; this.patch({ canvas: { ...c, bleed, min: bleed ? false : c.min } }) }
  unbleed() { const c = this.state.canvas; if (c.bleed) this.patch({ canvas: { ...c, bleed: false } }) }

  /* ── ending: a conversation with a recap ────────────────────────────────── */
  endSession() {
    const s = this.state
    const asked = s.transcript.filter(m => m.who === 'you' && !m.ghost && !m.queued && m.text).map(m => m.text)
    const acts = s.transcript.flatMap(m => m.acts)
    const recap: SessionRecap = {
      id: uid('s'), startedAt: new Date(s.startedAt || Date.now()).toISOString(), endedAt: new Date().toISOString(),
      secs: s.clockSecs, actions: s.actions, artifacts: s.artifacts.length,
      title: asked[0] ?? 'A quiet session: nothing was asked',
      asked, done: acts.filter(a => a.status === 'done').map(a => a.name),
      open: acts.filter(a => a.status === 'failed' || a.status === 'stopped').map(a => a.name),
    }
    const history = [recap, ...s.history].slice(0, 50)
    if (!s.demo) saveJson(HIST_KEY, history)
    void this.driver.end().catch(() => { /* nothing to close */ })
    this.leaveLive()
    this.patch({ view: 'standby', history, boot: blankBoot(this.driver) })
  }
  /** every timer and stream the session owns, without writing anything down */
  private leaveLive() {
    this.bootToken++; this.greetingToken++
    const ac = this.abort; this.abort = null; ac?.abort()
    if (this.ear) { this.ear.handle.stop(); this.ear = null }
    this.queue = []
    this.stopTimers(); this.clockOff()
    if (this.elapsedTick != null) { clearInterval(this.elapsedTick); this.elapsedTick = null }
    if (this.healthTick != null) { clearInterval(this.healthTick); this.healthTick = null }
    setWave(0, 2.6, 1)
    this.patch({ mood: 'idle', label: 'Ready', timing: false, run: null, micMode: 'locked', micLive: false })
  }
  dispose() { this.leaveLive(); this.subs.clear() }
}

/* ── one session at a time, kept while the tab is closed ─────────────────── */
let current: LiveSession | null = null
export function getSession(demo: boolean): LiveSession {
  if (current && current.driver.demo === demo) return current
  current?.dispose()
  current = new LiveSession(demo ? scriptedDriver() : chatDriver())
  return current
}
export function useSessionState(session: LiveSession): SessionState {
  return useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot)
}
