import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight } from 'lucide-react'
import { useReducedMotionPref } from '../../context/MotionProvider'
import {
  PhaseNode, StepMarker, CAT_TOKEN, PHASE_VERB, phaseCategory, resolvePhaseIcon, getToolIcon,
  type OrbCat,
} from './PhaseIndicator'

/* ProcessTrace - TOBI's "show your work".

   Live, it is a checkpoint rail: each tool the model runs lands as a settled row with its own
   icon, and the row currently running carries a breathing node and a shimmer across its text.
   Finished, the whole thing folds into one quiet "Worked for Xs" disclosure above the answer,
   so process is never mistaken for result.

   Design note (2026-08-25): this replaced a glowing orb that ran nine animated layers while a
   header cycled invented phrases ("Turning it over...", "Digging into the archives...") on a
   1.9s timer. The phrases described nothing real, and the motion competed with the checkpoint
   list that was already saying what was happening. Now the only things that move are the
   running step and arriving checkpoints, and every word on screen comes from the backend. */

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
  recall_conversations: 'Recalled past conversations', list_github_repos: 'Listed your repos',
}

export function toolPhase(tool: string): string {
  return PHASE_BY_TOOL[tool] || `Used ${tool.replace(/_/g, ' ')}`
}

// Exact reverse of the map above. A rendered step is a human phrase, not a tool name, so
// resolving its icon by keyword ("Listed your repos" contains no "github") lost the right
// glyph on 10 of the 43 phases. Going phrase -> tool -> icon makes every known step exact,
// and keyword matching stays only as the fallback for a phase this build does not know.
const TOOL_BY_PHASE: Record<string, string> = Object.fromEntries(
  Object.entries(PHASE_BY_TOOL).map(([tool, phrase]) => [phrase.toLowerCase(), tool]),
)

/** The icon for a rendered step: its own tool's glyph, else a keyword guess, else null. */
export function stepIcon(step: string) {
  const tool = TOOL_BY_PHASE[step.trim().toLowerCase()]
  return (tool && getToolIcon(tool)) || resolvePhaseIcon(step)
}

const catOf = (step: string): OrbCat => phaseCategory(step)
const GENERIC = /^(thinking|composing)/i

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
  // drop the generic bookend placeholders (Thinking… / Composing…) — a plain reply with no real
  // tool actions or reasoning shows no disclosure at all
  const stepList = (steps?.length ? steps : toolList.map(toolPhase)).filter(s => !GENERIC.test(s.trim()))
  if (!stepList.length && !reasoning && !toolList.length) return null
  return <FinishedTrace steps={stepList} reasoning={reasoning} tools={toolList}
    elapsedMs={elapsedMs} tokens={tokens} reduced={reduced} />
}

/** Reveal arrived steps one at a time.
 *
 *  The stream can hand over several phases in a single update - a fast tool burst, a resumed
 *  run, or a re-render that carries the whole array - and dropping four rows in together reads
 *  as a jolt rather than as progress. This walks a cursor up to the real count so each row
 *  lands on its own beat, in order. A long backlog plays faster so the list never feels behind
 *  the model, and reduced motion skips the cascade entirely. */
function useSequentialReveal(total: number, reduced: boolean) {
  const [count, setCount] = useState(total ? 1 : 0)
  const lastAt = useRef(0)
  useEffect(() => {
    if (reduced) { setCount(total); return }
    if (total < count) { setCount(total); lastAt.current = Date.now(); return }  // a new turn reset it
    if (count >= total) return
    const backlog = total - count
    // pace only what actually piled up. A step that arrives on its own, well after the previous
    // one, has already earned its beat and shows immediately - the cascade must never make the
    // list lag behind the model it is reporting on.
    const minGap = backlog > 3 ? 110 : 240
    const wait = count === 0 ? 0 : Math.max(0, minGap - (Date.now() - lastAt.current))
    const t = setTimeout(() => { lastAt.current = Date.now(); setCount(c => Math.min(c + 1, total)) }, wait)
    return () => clearTimeout(t)
  }, [total, count, reduced])
  return count
}

// ── live: a bare checkpoint rail, the running step breathing and shimmering ─────────────
function LiveTrace({ steps, startedAt, reduced }: { steps: string[]; startedAt: number; reduced: boolean }) {
  // "Thinking…" / "Composing…" are bookend placeholders, not work. Keep one only while it is
  // the row actually running, so a finished turn never leaves "Thinking…" sitting in the list.
  const real = steps.filter(s => !GENERIC.test(s.trim()))
  const tail = steps[steps.length - 1] ?? ''
  const all = real.length || !tail ? (real.length ? real : [PHASE_VERB['think']]) : [...real, tail]
  // the cascade holds back rows that arrived together; the newest visible row stays the live one,
  // so the pulse and the timer walk down the list as it fills instead of blinking out
  const revealed = useSequentialReveal(all.length, reduced)
  const shown = all.slice(0, Math.max(1, revealed))
  const curCat = catOf(shown[shown.length - 1])

  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 100)
    return () => clearInterval(t)
  }, [startedAt])

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0 } }}
      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
      className="py-0.5"
      role="status" aria-live="polite"
      aria-label={`${shown[shown.length - 1]}, ${elapsed.toFixed(0)} seconds elapsed`}
    >
      <ol className="proc-rail">
        <AnimatePresence initial={false}>
          {shown.map((step, i) => {
            const isLast = i === shown.length - 1
            const cat = catOf(step)
            const Icon = stepIcon(step)
            return (
              <motion.li
                key={`${i}-${step}`}
                layout={!reduced}
                initial={{ opacity: 0, y: reduced ? 0 : 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
                className="proc-step"
                data-running={isLast ? 'true' : undefined}
                style={{ ['--orb' as string]: `var(--${CAT_TOKEN[cat]})` }}
              >
                <span className="proc-marker">
                  {isLast
                    ? <PhaseNode cat={cat} Icon={Icon} reduced={reduced} />
                    : <StepMarker cat={cat} Icon={Icon} />}
                </span>
                <span className={isLast ? (reduced ? 'proc-live-still' : 'proc-live') : 'text-muted'}>
                  {step.replace(/…$/, '')}
                </span>
                {isLast && (
                  <span className="ml-1.5 font-mono text-[10px] tabular-nums text-muted/55">{elapsed.toFixed(1)}s</span>
                )}
              </motion.li>
            )
          })}
        </AnimatePresence>
      </ol>
    </motion.div>
  )
}

// ── finished: a compact disclosure above the answer, keeping a tiny colour-tinted orb dot ───
function FinishedTrace({ steps, reasoning, tools, elapsedMs, tokens, reduced }:
  { steps: string[]; reasoning: string; tools: string[]; elapsedMs?: number; tokens?: number; reduced: boolean }) {
  const [open, setOpen] = useState(false)
  const secs = elapsedMs != null ? (elapsedMs / 1000).toFixed(1) : null
  const hasBody = steps.length > 0 || !!reasoning || tools.length > 0
  const domCat = useMemo<OrbCat>(() => steps.length ? catOf(steps[steps.length - 1]) : (reasoning ? 'think' : 'read'), [steps, reasoning])
  const tok = CAT_TOKEN[domCat]
  if (!hasBody) return null
  const when = secs ? ` for ${secs}s` : ''
  const summary = steps.length > 1 ? `Worked${when} · ${steps.length} steps`
    : steps.length === 1 ? `Worked${when} · ${steps[0]}`
      : reasoning ? `Thought${when || ' it through'}`
        : `Worked${when}`
  return (
    <div className="mb-1.5">
      <button onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        aria-label={`${open ? 'Collapse' : 'Expand'} action history`}
        className="flex items-center gap-1.5 text-[11px] text-muted transition-colors hover:text-accent">
        <span className="proc-dot" style={{ ['--orb' as string]: `var(--${tok})` }} aria-hidden />
        {summary}
        {tokens ? <span className="text-muted/70">· {tokens} tok</span> : null}
        <ChevronRight size={11} className={`transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            transition={{ duration: reduced ? 0 : 0.24, ease: 'easeOut' }} className="overflow-hidden">
            <div className="mt-1.5 rounded-lg border border-border bg-bg/40 p-2.5">
              {steps.length > 0 && (
                <ol className="space-y-1">
                  {steps.map((s, i) => {
                    const StepIcon = stepIcon(s)
                    return (
                      <li key={i} className="flex items-center gap-2 text-[12px] text-muted">
                        <StepMarker cat={catOf(s)} Icon={StepIcon} size={16} />
                        {s}
                      </li>
                    )
                  })}
                </ol>
              )}
              {reasoning && (
                <div className={`whitespace-pre-wrap text-[12px] leading-relaxed text-muted ${steps.length ? 'mt-2 border-t border-border/60 pt-2' : ''}`}>{reasoning}</div>
              )}
              {tools.length > 0 && (
                <div className={`flex flex-wrap gap-1 ${(steps.length || reasoning) ? 'mt-2 border-t border-border/60 pt-2' : ''}`}>
                  <span className="text-[10px] uppercase tracking-wide text-muted/70">Tools</span>
                  {tools.map(t => {
                    const ToolIcon = getToolIcon(t) || resolvePhaseIcon(t)
                    return (
                      <span key={t} className="flex items-center gap-1 rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] text-muted">
                        {ToolIcon && <ToolIcon size={10} />}
                        {t.replace(/_/g, ' ')}
                      </span>
                    )
                  })}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
