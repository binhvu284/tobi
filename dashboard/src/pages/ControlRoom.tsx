import { useEffect, useState } from 'react'
import { softFail } from '../lib/report'
import { motion } from 'framer-motion'
import { Play, Loader2, CheckCircle2, AlertTriangle, Terminal, FlaskConical, Building2, FileText, Crown } from 'lucide-react'
import { getRunReadiness, runEngine, type Readiness, type RunResult, type EngineName } from '../api.officev3'
import { useToast } from '../context/ToastProvider'
import { AmbientField } from '../components/motion'
import { Link } from 'react-router-dom'

const ICONS: Record<string, typeof Play> = { research: FlaskConical, execute: Building2, report: FileText, ceo: Crown }

// Plain-language names for the keys TOBI may be missing, so the owner is told
// what to do, not which internal variable to find.
const FRIENDLY_KEYS: Record<string, string> = {
  TAVILY_API_KEY: 'its research key (Tavily)',
  ANTHROPIC_API_KEY: 'its Claude key',
  OPENAI_API_KEY: 'its OpenAI key',
  DEEPSEEK_API_KEY: 'its DeepSeek key',
  GEMINI_API_KEY: 'its Gemini key',
  GROK_API_KEY: 'its Grok key',
}

export default function ControlRoom() {
  const [engines, setEngines] = useState<Readiness[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, RunResult>>({})
  const { toast } = useToast()

  const load = () => getRunReadiness().then(r => setEngines(r.engines)).catch(softFail('the control room'))
  useEffect(() => { load() }, [])

  const run = async (name: string) => {
    setBusy(name)
    toast({ kind: 'info', title: `Running ${name}…`, detail: 'Triggered from Control Room' })
    try {
      const r = await runEngine(name as EngineName)
      setResults(s => ({ ...s, [name]: r }))
      toast({ kind: r.ok ? 'success' : 'error', title: r.message || name, detail: r.detail })
    } catch (e) {
      const r: RunResult = { ok: false, message: 'Request failed', detail: (e as Error).message }
      setResults(s => ({ ...s, [name]: r }))
      toast({ kind: 'error', title: 'Failed', detail: (e as Error).message })
    } finally { setBusy(null) }
  }

  const readyCount = engines.filter(e => e.ready).length

  return (
    <div className="relative p-6">
      <AmbientField tone="rgb(var(--success))" />
      <div className="mb-5 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/15 text-accent"><Terminal size={20} /></div>
        <div>
          <h1 className="text-xl font-bold text-heading">Control Room</h1>
          <p className="text-xs text-muted">Trigger and observe every engine in one place · {readyCount}/{engines.length} ready</p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {engines.map(e => {
          const Icon = ICONS[e.engine] || Play
          const res = results[e.engine]
          const running = busy === e.engine
          return (
            <div key={e.engine} className="rounded-xl border border-border bg-surface p-4">
              <div className="mb-2 flex items-start justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-bg text-accent"><Icon size={17} /></div>
                  <div>
                    <div className="text-sm font-semibold text-heading">{e.label}</div>
                    <div className="text-[11px] text-muted">{e.note}</div>
                  </div>
                </div>
                <span className={`shrink-0 whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-medium ${e.ready ? 'bg-success/20 text-success' : 'bg-warning/20 text-warning'}`}>
                  {e.ready ? '● ready' : '○ needs config'}
                </span>
              </div>

              {!e.ready && e.needs && (
                <div className="mb-2 rounded border border-warning/30 bg-warning/10 px-2.5 py-1.5 text-[11px] text-warning">
                  Not ready — TOBI needs {FRIENDLY_KEYS[e.needs] ?? 'a missing key'} to run this.{' '}
                  <Link to="/integrations" className="underline hover:text-heading">Add it on the Integrations page</Link>
                  <span className="ml-1 font-mono opacity-70">({e.needs})</span>
                </div>
              )}

              <button onClick={() => run(e.engine)} disabled={!e.ready || running}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent/15 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent/25 disabled:opacity-40">
                {running ? <><Loader2 size={14} className="animate-spin" /> Running…</> : <><Play size={14} /> Run / Test</>}
              </button>

              {res && (
                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                  className={`mt-3 rounded-lg border p-3 text-xs ${res.ok ? 'border-success/30 bg-success/10' : 'border-danger/30 bg-danger/10'}`}>
                  <div className={`flex items-center gap-1.5 font-medium ${res.ok ? 'text-success' : 'text-danger'}`}>
                    {res.ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />} {res.message}
                  </div>
                  {res.detail && <div className="mt-1 leading-relaxed text-text">{res.detail}</div>}
                </motion.div>
              )}
            </div>
          )
        })}
      </div>

      <div className="mt-4 rounded-lg border border-border bg-surface/50 p-3 text-[11px] text-muted">
        Tip: outward-facing actions (Telegram sends) are intentionally not exposed here — the Daily Report
        builds from the DB only and never sends. Use the Office mission board to run multi-agent missions
        (with a <span className="font-mono">mock</span> toggle), and the Ability page to coach skills.
      </div>
    </div>
  )
}
