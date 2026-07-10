import { useEffect, useRef, useState } from 'react'
import { Terminal, ShieldCheck, Power, RefreshCw, Square, Boxes, Cpu } from 'lucide-react'
import {
  getTerminalStatus, setTerminalMode, setTerminalKillSwitch, getTerminalJobs, killTerminalJob,
  getInstalledTools, type TerminalStatus, type TerminalMode as TMode, type TerminalJob, type InstalledTool,
} from '../../api'

/* TOBI CLI (#11) — the terminal-mode control surface inside Chat [D19].
   Two-axis safety made visible: the approval-mode switch (Plan/Ask/Accept/Auto), the global
   kill-switch, the live background-job list, and the capability registry. The command itself is
   still typed in the normal composer and run by TOBI through the Conductor's run_command tool —
   this panel just exposes the controls + live console. */

const MODE_INFO: Record<TMode, { label: string; hint: string; tone: string }> = {
  plan: { label: 'Plan', hint: 'Proposes only — runs nothing', tone: 'text-muted' },
  ask: { label: 'Ask', hint: 'Confirms medium & high risk', tone: 'text-accent' },
  accept: { label: 'Accept', hint: 'Only high risk confirms', tone: 'text-warning' },
  auto: { label: 'Auto', hint: 'Runs everything (denylist still blocks)', tone: 'text-danger' },
}
const MODES: TMode[] = ['plan', 'ask', 'accept', 'auto']

export default function TerminalMode({ lines, active }: { lines: string[]; active: boolean }) {
  const [status, setStatus] = useState<TerminalStatus | null>(null)
  const [jobs, setJobs] = useState<TerminalJob[]>([])
  const [tools, setTools] = useState<InstalledTool[]>([])
  const [busy, setBusy] = useState(false)
  const consoleRef = useRef<HTMLDivElement>(null)

  const refresh = async () => {
    try { setStatus(await getTerminalStatus()) } catch { /* ignore */ }
    try { setJobs((await getTerminalJobs()).jobs) } catch { /* ignore */ }
    try { setTools((await getInstalledTools()).tools) } catch { /* ignore */ }
  }
  useEffect(() => { refresh() }, [])
  // poll for live job state while a turn runs (a background job may spin up mid-turn)
  useEffect(() => {
    if (!active) { refresh(); return }
    const t = setInterval(() => { getTerminalJobs().then(r => setJobs(r.jobs)).catch(() => {}) }, 2500)
    return () => clearInterval(t)
  }, [active])
  useEffect(() => { if (consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight }, [lines])

  const chooseMode = async (m: TMode) => {
    if (busy || status?.mode === m) return
    setBusy(true)
    try { const r = await setTerminalMode(m); setStatus(s => s ? { ...s, mode: r.mode } : s) }
    catch { /* ignore */ } finally { setBusy(false) }
  }
  const toggleKill = async () => {
    if (!status || busy) return
    setBusy(true)
    try { const r = await setTerminalKillSwitch(!status.enabled); setStatus(s => s ? { ...s, enabled: r.enabled } : s) }
    catch { /* ignore */ } finally { setBusy(false) }
  }
  const kill = async (id: number) => { try { await killTerminalJob(id) } catch { /* ignore */ } refresh() }

  const running = jobs.filter(j => j.status === 'running')

  return (
    <div className="mb-2 rounded-xl border border-border bg-bg/40 text-xs">
      {/* header: engine + kill-switch */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border/70 px-3 py-2">
        <span className="flex items-center gap-1.5 font-medium text-text"><Terminal size={14} className="text-accent" /> Terminal</span>
        {status && (
          <span className="flex items-center gap-1.5 text-muted">
            <Cpu size={12} /> {status.os} · <code className="text-text/90">{status.shell}</code>
          </span>
        )}
        {status?.package_managers?.length ? (
          <span className="hidden items-center gap-1 text-muted sm:flex"><Boxes size={12} /> {status.package_managers.join(', ')}</span>
        ) : null}
        <button onClick={refresh} title="Refresh" className="ml-auto flex h-6 w-6 items-center justify-center rounded-md text-muted hover:bg-overlay/10 hover:text-text"><RefreshCw size={12} /></button>
        <button onClick={toggleKill} title={status?.enabled ? 'Freeze all execution' : 'Execution frozen — click to re-enable'}
          className={`flex items-center gap-1 rounded-md px-2 py-1 font-medium transition-colors ${status?.enabled ? 'text-muted hover:bg-overlay/10 hover:text-text' : 'bg-danger/15 text-danger'}`}>
          <Power size={12} /> {status?.enabled ? 'Live' : 'Frozen'}
        </button>
      </div>

      {/* approval-mode switch (Axis 2) */}
      <div className="flex flex-wrap items-center gap-1.5 px-3 py-2">
        <span className="mr-1 flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted"><ShieldCheck size={12} /> Approval</span>
        {MODES.map(m => {
          const on = status?.mode === m
          return (
            <button key={m} onClick={() => chooseMode(m)} disabled={busy} title={MODE_INFO[m].hint}
              className={`rounded-md px-2 py-1 font-medium transition-colors disabled:opacity-50 ${on ? 'bg-accent/15 text-accent ring-1 ring-accent/40' : 'text-muted hover:bg-overlay/10 hover:text-text'}`}>
              {MODE_INFO[m].label}
            </button>
          )
        })}
        {status && <span className={`ml-1 hidden text-[11px] md:inline ${MODE_INFO[status.mode].tone}`}>{MODE_INFO[status.mode].hint}</span>}
      </div>

      {/* live console */}
      {lines.length > 0 && (
        <div ref={consoleRef} className="max-h-40 overflow-auto border-t border-border/70 bg-black/60 px-3 py-2 font-mono text-[11px] leading-relaxed text-emerald-300/90">
          {lines.map((l, i) => <pre key={i} className="whitespace-pre-wrap break-words">{l}</pre>)}
        </div>
      )}

      {/* background jobs */}
      {running.length > 0 && (
        <div className="border-t border-border/70 px-3 py-2">
          <div className="mb-1 text-[10px] uppercase tracking-wide text-muted">Background jobs</div>
          {running.map(j => (
            <div key={j.id} className="flex items-center gap-2 py-0.5">
              <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-emerald-400" />
              <code className="min-w-0 flex-1 truncate text-text/90">#{j.id} {j.command}</code>
              <button onClick={() => kill(j.id)} title="Kill job" className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-danger hover:bg-danger/15"><Square size={11} /> kill</button>
            </div>
          ))}
        </div>
      )}

      {/* capability registry */}
      {tools.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-border/70 px-3 py-2">
          <span className="text-[10px] uppercase tracking-wide text-muted">Toolset</span>
          {tools.slice(0, 12).map(t => (
            <span key={t.name} title={`${t.status}${t.channel ? ' · ' + t.channel : ''}`}
              className="rounded-md border border-border/70 bg-surface px-1.5 py-0.5 text-[11px] text-text/90">{t.name}</span>
          ))}
        </div>
      )}
    </div>
  )
}
