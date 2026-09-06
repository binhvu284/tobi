// TOBI UI 2.0 (#36) — what runs behind the glass.
//
// scriptedDriver is the shell's own demonstration run (the FLOW table, the alternating
// failure, the fake ear), kept so the build can be checked against the design one state at a
// time. chatDriver is the real thing for phase 1: typed only, through the Chat runtime that
// already routes tools through Conductor. Both speak to the screen only through a Sink.
import type { PendingAction } from '../api.brain'
import {
  createChatSession, getChatArtifact, getChatConfig, getLlmConfig, patchChatSession, streamChatSession,
  type ChatAttachment,
} from '../api.chat'
import { getConductorStatus, confirmConductorAction } from '../api.conductor'
import { getProjects } from '../api.core'
import { DEMO_ARTIFACTS, DEMO_HISTORY, DESIGNED_DOCS } from './designed'
import {
  fmtKb, nowStamp, shortModel,
  type ActIcon, type ActSpec, type ActFail, type Driver, type FileKind, type ModelChoice, type Mood, type Sink,
} from './model'

const reason = (e: unknown) => (e instanceof Error ? e.message : String(e || 'no reason was reported'))
const GREETING = 'I am up. Memory is linked and the tools are loaded. What are we doing?'

/** a timer that dies with the run, so a stop leaves nothing ticking */
function waiter(signal: AbortSignal) {
  return (ms: number) => new Promise<void>((res, rej) => {
    if (signal.aborted) { rej(new DOMException('Aborted', 'AbortError')); return }
    const id = setTimeout(() => { signal.removeEventListener('abort', onAbort); res() }, ms)
    const onAbort = () => { clearTimeout(id); rej(new DOMException('Aborted', 'AbortError')) }
    signal.addEventListener('abort', onAbort, { once: true })
  })
}
/** the answer arrives as it is written, not all at once */
async function typeOut(line: string, sink: Sink, wait: (ms: number) => Promise<void>) {
  for (const ch of line) { sink.delta(ch); await wait(22) }
  await wait(420)
}

/* ══ The design's scripted session ═════════════════════════════════════════ */
type Flow = { state: Mood; label: string; ms: number; act?: ActSpec; fail?: ActFail; open?: string }
/* Each step names what it is doing to what. The row appears the moment the
   step starts, spins while it runs, and is replaced by its own result. */
const FLOW: Flow[] = [
  { state: 'thinking', label: 'Working out what you are asking for', ms: 820 },
  { state: 'working', label: 'Reading the brain for Monolith 1',
    act: { run: 'Reading the brain for Monolith 1', done: 'Read the brain for Monolith 1', meta: '4 projects · 0.3s' }, ms: 1050 },
  { state: 'working', label: 'Reading the run log for week 1',
    act: { run: 'Reading the run log', done: 'Read the run log', meta: '2,104 lines · 0.4s' },
    fail: { name: 'Could not read the run log', reason: 'No response · 2.1s',
      why: 'The run log service did not answer. That is on the service, not on the plan: everything else in this answer still stands.' },
    ms: 950 },
  { state: 'working', label: 'Opening foundation-plan.md on the canvas',
    act: { run: 'Opening foundation-plan.md', done: 'Opened foundation-plan.md on the canvas', meta: '12 KB · 0.2s', icon: 'canvas' },
    open: 'plan', ms: 900 },
]
const REPLIES = [
  'Noted. It is on the canvas.',
  'That one sits in week two. Say the word and I will move it.',
  'Saved to the session script.',
  'Two items are still behind in week one. Same two as this morning.',
]
const HEARD = ['Where', 'did', 'we', 'leave', 'Monolith', '1', 'this', 'morning?']
const DEMO_MODELS: ModelChoice[] = [
  { id: 'claude-opus-5', label: 'claude-opus-5', hint: 'deep work', context: 200000 },
  { id: 'claude-sonnet-5', label: 'claude-sonnet-5', hint: 'everyday', context: 200000 },
  { id: 'claude-haiku-4.5', label: 'claude-haiku-4.5', hint: 'fast', context: 200000 },
]
const DEMO_BOOT = ['claude-opus-5', '4 projects', '24 ready', 'idle', 'locked off']

export function scriptedDriver(): Driver {
  let runN = 0, replyN = 0, drove = false
  let current = DEMO_MODELS[0].id
  return {
    demo: true, retriesInPlace: true,
    models: async () => ({ models: DEMO_MODELS, current }),
    chooseModel: async id => { current = id },
    bootPreview: i => DEMO_BOOT[i],
    bootValue: async (i, model) => (i === 0 ? shortModel(model) : DEMO_BOOT[i]),
    prepare: async () => { /* nothing behind the glass */ },
    greeting: () => GREETING,
    seed: () => ({ artifacts: DEMO_ARTIFACTS, history: DEMO_HISTORY, docs: DESIGNED_DOCS }),
    async run(_text, sink, signal) {
      const wait = waiter(signal)
      // about 300 a second, as one of these runs
      const ticker = window.setInterval(() => sink.tokens(22 + Math.round(Math.random() * 18)), 100)
      signal.addEventListener('abort', () => clearInterval(ticker), { once: true })
      try {
        const breaks = ++runN % 2 === 0          // alternate, so both outcomes can be seen
        let broke = false
        sink.plan(FLOW.filter(x => x.act).length)
        for (const fl of FLOW) {
          sink.mood(fl.state, fl.label)
          const id = fl.act ? sink.actStart(fl.act) : null
          await wait(fl.ms)
          if (id && fl.act) {
            if (fl.fail && breaks) { sink.actFail(id, fl.fail); broke = true }
            else sink.actDone(id, fl.act.meta)
          }
          if (fl.open) { const doc = DESIGNED_DOCS.find(d => d.id === fl.open); if (doc) sink.open(doc) }
        }
        const thought = sink.spentTokens()      // what the run had spent before he opened his mouth
        sink.mood('speaking')
        const line = broke
          ? 'The plan is on the canvas. I could not reach the run log, so the burndown is from this morning, not from now.'
          : (drove ? REPLIES[replyN++ % REPLIES.length]
            : 'It is on the canvas. Six weeks end to end, and week one is two items behind.')
        drove = true
        await typeOut(line, sink, wait)
        sink.file({ id: 'plan', name: 'foundation-plan.md', kind: 'doc', note: 'Edited from the canvas', size: '12 KB', at: nowStamp() })
        const tokens = thought + Math.round(line.length / 3.6)
        sink.receipt({ model: sink.model(), secs: sink.elapsed().toFixed(1), tokens })
        sink.spend(tokens)
      } finally { clearInterval(ticker) }
    },
    async retry(actId, spec, sink, signal) {
      const wait = waiter(signal)
      sink.mood('working', spec.run)
      await wait(950)
      sink.actDone(actId, spec.meta)
    },
    hear(ear) {
      let n = 0
      const iv = window.setInterval(() => { if (n < HEARD.length) ear.heard(HEARD.slice(0, ++n).join(' ')) }, 300)
      return { stop: () => { clearInterval(iv); return HEARD.slice(0, n).join(' ') } }
    },
    decide: async (_a, decision) => (decision === 'approve' ? 'Done' : 'Declined'),
    end: async () => { /* nothing to close */ },
  }
}

/* ══ The real thing: typed, through the Chat runtime and Conductor ═════════ */
async function readDataURL(f: File) {
  return new Promise<string>((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result as string); r.onerror = rej; r.readAsDataURL(f) })
}
async function toAttachment(f: File): Promise<ChatAttachment> {
  const mime = f.type || 'application/octet-stream'
  if (mime.startsWith('image/')) return { name: f.name, mime, kind: 'image', data_url: await readDataURL(f) }
  if (mime === 'application/pdf') return { name: f.name, mime, kind: 'pdf', data_url: await readDataURL(f) }
  if (mime.startsWith('text/') || /\.(md|txt|csv|json|ya?ml|py|ts|tsx|js|html|css|log)$/i.test(f.name)) {
    return { name: f.name, mime, kind: 'text', text: await f.text() }
  }
  return { name: f.name, mime, kind: 'file', data_url: await readDataURL(f) }
}
function iconFor(tool: string): ActIcon {
  const t = tool.toLowerCase()
  if (/chart|image|draw|png|render/.test(t)) return 'chart'
  if (/csv|sheet|table|export/.test(t)) return 'sheet'
  if (/log|run/.test(t)) return 'log'
  if (/read|file|open|doc|note|plan/.test(t)) return 'doc'
  if (/canvas|show|view/.test(t)) return 'canvas'
  return 'tool'
}
function kindOf(kind: string): FileKind {
  const k = (kind || '').toLowerCase()
  if (/image|png|jpg|chart/.test(k)) return 'image'
  if (/csv|table|sheet/.test(k)) return 'sheet'
  if (/log|script/.test(k)) return 'log'
  return 'doc'
}
const PROVIDER_HINT: Record<string, string> = {
  anthropic: 'Anthropic', openai: 'OpenAI', codex: 'OpenAI', glm: 'GLM', zai: 'Z.ai', gemini: 'Google', google: 'Google',
  grok: 'xAI', xai: 'xAI', openrouter: 'OpenRouter', deepseek: 'DeepSeek', ollama: 'local',
}
/** a failed step says whose fault it was */
function whoseFault(d: Record<string, unknown>): string {
  const detail = String(d.detail || d.message || '').trim()
  const theirs = d.retryable === true || /provider|model|timeout|network|unreachable|rate/i.test(String(d.code || ''))
  const blame = theirs
    ? 'That is on the service, not on what you asked: everything else in this answer still stands.'
    : 'That is on TOBI, not on what you asked.'
  return detail ? `${detail.replace(/\.?$/, '.')} ${blame}` : blame
}

export function chatDriver(): Driver {
  let sid: number | null = null
  let modeV2 = false
  let models: ModelChoice[] = []
  const loadModels = async () => {
    const cfg = await getLlmConfig()
    models = cfg.models.map(m => {
      // the backend's display label is "<provider label> · <model>"; the menu shows the model
      // under a provider heading, so the heading is the label with its own model taken off
      const name = m.model || shortModel(m.id)
      const suffix = ` · ${name}`
      const group = m.label && m.label.endsWith(suffix) ? m.label.slice(0, -suffix.length)
        : PROVIDER_HINT[(m.provider || '').toLowerCase()] || m.provider || 'Other'
      return { id: m.id, label: name, group, hint: m.context ? `${Math.round(m.context / 1000)}k` : '', context: m.context }
    })
    if (!models.length) throw new Error('no model is set up yet. Add a provider key on the Models page, then start again')
    const wanted = cfg.config?.default_model
    const current = wanted && models.some(m => m.id === wanted) ? wanted : models[0].id
    return { models, current }
  }
  const ctxOf = (model: string) => models.find(m => m.id === model)?.context || 200000
  return {
    demo: false, retriesInPlace: false,
    models: loadModels,
    chooseModel: async id => { if (sid != null) await patchChatSession(sid, { model: id }) },
    bootPreview: () => '',
    async bootValue(i, model) {
      switch (i) {
        case 0: { if (!models.length) await loadModels(); return shortModel(model) }
        case 1: {
          const r = (await getProjects()) as unknown
          const list = Array.isArray(r) ? r : Array.isArray((r as { projects?: unknown[] })?.projects) ? (r as { projects: unknown[] }).projects : []
          return `${list.length} project${list.length === 1 ? '' : 's'}`
        }
        case 2: {
          const st = await getConductorStatus()
          const n = (st.read_tools?.length ?? 0) + (st.act_tools?.length ?? 0)
          return `${n} ready`
        }
        case 3: return 'idle'
        default: return 'locked off'
      }
    },
    async prepare(model) {
      const cfg = await getChatConfig().catch(() => ({ mode_v2: false }))
      modeV2 = !!cfg.mode_v2
      const when = new Date().toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      const s = await createChatSession(model || null, `Live session · ${when}`)
      sid = s.id
    },
    greeting: () => GREETING,
    seed: () => ({ artifacts: [], history: [], docs: [] }),
    async run(text, sink, signal, opts) {
      if (sid == null) throw new Error('no live session is open')
      const attachments = await Promise.all(opts.attachments.map(toAttachment))
      sink.mood('thinking', 'Working out what you are asking for')
      let current: string | null = null       // the step under way, until its result replaces it
      let answered = false
      const t0 = Date.now()
      const close = () => { if (current) { sink.actDone(current); current = null } }
      await streamChatSession(sid, text, sink.model(), {
        onThinking: (phase, tools) => {
          const label = phase.trim()
          if (!label) return
          const tool = tools && tools.length ? tools[tools.length - 1] : ''
          if (tool) { close(); current = sink.actStart({ run: label, done: label, icon: iconFor(tool) }); sink.mood('working', label) }
          else sink.mood('thinking', label)
        },
        onPlan: plan => {
          close()
          const n = plan.steps.length
          const id = sink.actStart({ run: `Planning ${n} step${n === 1 ? '' : 's'}`, done: `Planned ${n} step${n === 1 ? '' : 's'}` })
          sink.actDone(id, plan.title || undefined)
          sink.mood('working', plan.title || 'Working through the plan')
        },
        onRuntimeEvent: ev => {
          if (ev.type !== 'step_failed') return
          const d = ev.data || {}
          const name = String(d.message || 'A step failed')
          const id = current ?? sink.actStart({ run: name, done: name })
          current = null
          sink.actFail(id, { name, reason: String(d.code || 'failed'), why: whoseFault(d) })
        },
        onDelta: t => {
          close()
          if (!answered) { answered = true; sink.mood('speaking') }
          sink.delta(t)
          sink.tokens(Math.max(1, Math.round(t.length / 3.6)))
        },
        onUsage: u => {
          close()
          const model = u.actual_model || u.model || sink.model()
          const used = (u.prompt_tokens || 0) + (u.completion_tokens || 0)
          sink.receipt({ model, secs: ((u.latency_ms || Date.now() - t0) / 1000).toFixed(1), tokens: used })
          sink.spend(used, ctxOf(model))
          if (u.requested_model && u.actual_model && u.requested_model !== u.actual_model) {
            sink.note(`Answered by ${shortModel(u.actual_model)}: ${shortModel(u.requested_model)} did not respond${u.fallback_reason ? ` (${u.fallback_reason})` : ''}.`)
          }
        },
        onNotice: n => {
          if (n.kind !== 'model_issue') return
          close()
          const id = sink.actStart({ run: 'Asking the model', done: 'Asked the model' })
          sink.actFail(id, {
            name: 'The model did not answer properly', reason: n.reason || 'no usable answer',
            why: n.detail || 'The model returned nothing usable. That is on the model, not on what you asked. Try again sends the same request.',
          })
        },
        onAction: a => { close(); sink.confirm(a) },
        onArtifact: a => {
          void getChatArtifact(a.id).then(art => {
            const kind = kindOf(art.kind)
            const ref = {
              id: `art:${a.id}`, name: art.title || a.title || `artifact ${a.id}`, kind,
              note: 'Made in this session', size: art.content ? fmtKb(art.content.length) : undefined, at: nowStamp(),
            }
            sink.file(ref)
            if (art.content) {
              sink.open({
                id: ref.id, title: ref.name, kind, size: ref.size, at: ref.at,
                body: kind === 'image' && art.content.startsWith('data:') ? { type: 'image', src: art.content } : { type: 'markdown', text: art.content },
              })
            }
          }).catch((e: unknown) => sink.note(`Could not open ${a.title || 'the artifact'}: ${reason(e)}`))
        },
      }, signal, {
        attachments: attachments.length ? attachments : undefined,
        ...(modeV2 ? { mode: 'agent' as const, review_mode: 'ask' as const } : {}),
      })
      close()
    },
    async retry() { /* a chat turn cannot re-run one step; the session re-asks instead */ },
    hear(ear) {
      ear.heard('Voice arrives in phase 2. Type for now.')
      return { stop: () => '' }
    },
    async decide(action: PendingAction, decision) {
      const r = await confirmConductorAction(action.id, decision)
      if (r.error) throw new Error(r.error)
      return r.summary || (decision === 'approve' ? `Done · ${r.status}` : 'Declined')
    },
    end: async () => { /* the transcript stays with Chat's memory; nothing to close */ },
  }
}
