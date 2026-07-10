import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Loader2, Check, ChevronRight, Sparkles } from 'lucide-react'
import { useReducedMotionPref } from '../../context/MotionProvider'

/* ProcessTrace — TOBI's "show your work" panel.

   The problem this solves: a multi-step turn used to flash a single rotating phrase in the
   thinking orb, then vanish, leaving no record — so it was impossible to tell TOBI's *process*
   from his *answer*. Modelled on Claude Code / Codex / o1: while working we show a **stable,
   accumulating checkpoint timeline** (each tool step is a line that stays, completed ones get a
   check, the current one spins); when the turn finishes it collapses into a compact
   **"Worked for Xs · N steps"** disclosure rendered ABOVE the answer, expandable to replay the
   steps + any reasoning. The answer itself is always clearly separate, below the trace. */

// Mirrors the backend _TOOL_PHASE map (core/conductor.py) so the persisted view (which only has
// the tool names) reconstructs the same human checkpoints the live stream showed.
const PHASE_BY_TOOL: Record<string, string> = {
  get_evolution: 'Checked your evolution', explain_architecture: 'Reviewed the architecture',
  office_status: 'Looked in on the office', list_projects: 'Read your projects',
  list_tasks: 'Read your tasks', project_overview: 'Reviewed the project',
  check_health: 'Ran a health check', recall: 'Searched your memory',
  read_notion: 'Read Notion', read_github: 'Read GitHub', read_drive: 'Checked Drive',
  web_search: 'Searched the web', storage_status: 'Checked storage', llm_spend: 'Checked spend',
  search_project_resources: 'Searched project resources', get_current_datetime: 'Checked the time',
  remember: 'Saved to memory', create_project: 'Created the project', create_task: 'Added the task',
  create_resource: 'Added a resource', set_project_description: 'Updated the description',
  pick_project_icon: 'Set the project icon', complete_task: 'Completed the task',
  rename_project: 'Renamed the project', create_goal: 'Created a goal', edit_goal: 'Updated a goal',
  assign_task: 'Assigned the task', update_project_progress: 'Updated progress',
  delete_task: 'Removed the task', delete_project: 'Removed the project', run_mission: 'Queued the mission',
  run_command: 'Ran a command', install_package: 'Installed a package', configure_tool: 'Wrote the config',
  connect_tool: 'Connected the tool', kill_job: 'Stopped a job', set_terminal_mode: 'Switched terminal mode',
  terminal_status: 'Checked the terminal', list_jobs: 'Checked jobs', job_output: 'Read job output',
  list_installed_tools: 'Reviewed your toolset',
}

export function toolPhase(tool: string): string {
  return PHASE_BY_TOOL[tool] || `Used ${tool.replace(/_/g, ' ')}`
}

type Props = {
  active?: boolean          // the turn is still running → live timeline
  steps?: string[]          // live checkpoint phrases (backend phases, accumulated)
  tools?: string[]          // finished: derive steps from tool names when `steps` is absent
  thinking?: string | null  // finished: model reasoning, or "Consulted: a, b" (tool list)
  startedAt?: number        // live: elapsed-timer origin
  elapsedMs?: number        // finished: total turn time
  tokens?: number
}

export default function ProcessTrace({ active, steps, tools, thinking, startedAt, elapsedMs, tokens }: Props) {
  const reduced = useReducedMotionPref() !== 'full'

  if (active) return <LiveTrace steps={steps ?? []} startedAt={startedAt ?? Date.now()} reduced={reduced} />

  // ── finished: reconstruct the checkpoints from live steps, else from the stored tool list ──
  const isConsulted = thinking?.startsWith('Consulted: ')
  const reasoning = thinking && !isConsulted ? thinking.trim() : ''
  const toolList = tools?.length ? tools : (isConsulted ? thinking!.slice(11).split(', ').map(s => s.trim()).filter(Boolean) : [])
  // drop the generic "Thinking…" placeholder — a plain reply with no tools/reasoning shows no disclosure
  const stepList = (steps?.length ? steps : toolList.map(toolPhase)).filter(s => !/^thinking…?$/i.test(s.trim()))
  if (!stepList.length && !reasoning && !toolList.length) return null
  return <FinishedTrace steps={stepList} reasoning={reasoning} tools={toolList}
    elapsedMs={elapsedMs} tokens={tokens} reduced={reduced} />
}

// ── live: a stable, accumulating checklist (no rotating flavour text) ──────────────
function LiveTrace({ steps, startedAt, reduced }: { steps: string[]; startedAt: number; reduced: boolean }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 100)
    return () => clearInterval(t)
  }, [startedAt])
  const shown = steps.length ? steps : ['Thinking…']
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
      className="inline-block min-w-[220px] max-w-full rounded-2xl rounded-tl-sm border border-border bg-surface/70 px-3.5 py-2.5 backdrop-blur-sm">
      <div className="mb-1.5 flex items-center gap-2 text-[12px] font-medium text-accent">
        <Loader2 size={13} className={reduced ? '' : 'animate-spin'} /> Working
        <span className="ml-auto pl-3 font-mono text-[10px] tabular-nums text-muted/70">{elapsed.toFixed(1)}s</span>
      </div>
      <ol className="space-y-1">
        <AnimatePresence initial={false}>
          {shown.map((s, i) => {
            const isLast = i === shown.length - 1
            return (
              <motion.li key={`${i}-${s}`} layout={!reduced}
                initial={{ opacity: 0, x: reduced ? 0 : -5 }} animate={{ opacity: 1, x: 0 }}
                className="flex items-center gap-2 text-[12px]">
                <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">
                  {isLast
                    ? <span className={`h-1.5 w-1.5 rounded-full bg-accent ${reduced ? '' : 'animate-pulse'}`} />
                    : <Check size={12} className="text-success" />}
                </span>
                <span className={isLast ? 'text-text' : 'text-muted'}>{s}</span>
              </motion.li>
            )
          })}
        </AnimatePresence>
      </ol>
    </motion.div>
  )
}

// ── finished: a compact disclosure above the answer ────────────────────────────────
function FinishedTrace({ steps, reasoning, tools, elapsedMs, tokens, reduced }:
  { steps: string[]; reasoning: string; tools: string[]; elapsedMs?: number; tokens?: number; reduced: boolean }) {
  const [open, setOpen] = useState(false)
  const secs = elapsedMs != null ? (elapsedMs / 1000).toFixed(1) : null
  const hasBody = steps.length > 0 || !!reasoning || tools.length > 0
  if (!hasBody) return null
  const when = secs ? ` for ${secs}s` : ''
  const summary = steps.length > 1 ? `Worked${when} · ${steps.length} steps`
    : steps.length === 1 ? `Worked${when} · ${steps[0]}`
      : reasoning ? `Thought${when || ' it through'}`
        : `Worked${when}`
  return (
    <div className="mb-1.5">
      <button onClick={() => hasBody && setOpen(o => !o)}
        className={`flex items-center gap-1.5 text-[11px] text-muted transition-colors ${hasBody ? 'hover:text-accent' : 'cursor-default'}`}>
        <Sparkles size={11} /> {summary}
        {tokens ? <span className="text-muted/70">· {tokens} tok</span> : null}
        {hasBody && <ChevronRight size={11} className={`transition-transform ${open ? 'rotate-90' : ''}`} />}
      </button>
      <AnimatePresence initial={false}>
        {open && hasBody && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            transition={{ duration: reduced ? 0 : 0.2 }} className="overflow-hidden">
            <div className="mt-1.5 rounded-lg border border-border bg-bg/40 p-2.5">
              {steps.length > 0 && (
                <ol className="space-y-1">
                  {steps.map((s, i) => (
                    <li key={i} className="flex items-center gap-2 text-[12px] text-muted">
                      <Check size={12} className="shrink-0 text-success/80" /> {s}
                    </li>
                  ))}
                </ol>
              )}
              {reasoning && (
                <div className={`whitespace-pre-wrap text-[12px] leading-relaxed text-muted ${steps.length ? 'mt-2 border-t border-border/60 pt-2' : ''}`}>{reasoning}</div>
              )}
              {tools.length > 0 && (
                <div className={`flex flex-wrap gap-1 ${(steps.length || reasoning) ? 'mt-2 border-t border-border/60 pt-2' : ''}`}>
                  <span className="text-[10px] uppercase tracking-wide text-muted/70">Tools</span>
                  {tools.map(t => <span key={t} className="rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] text-muted">{t.replace(/_/g, ' ')}</span>)}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
