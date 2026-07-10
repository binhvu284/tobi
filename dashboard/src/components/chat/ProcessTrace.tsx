import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, ChevronRight } from 'lucide-react'
import { useReducedMotionPref } from '../../context/MotionProvider'
import { Orb, CAT_TOKEN, PHRASES, phaseCategory, type OrbCat } from './ThinkingOrb'

/* ProcessTrace — TOBI's "show your work", with the old thinking-orb's soul.

   Structure (from the flicker fix): a stable, accumulating checkpoint timeline while working,
   collapsing into a "Worked for Xs" disclosure above the answer once done — so process is never
   confused with result. Feel (restored per the owner): the live orb *leads* the current step,
   shifting colour by the action category (recall=purple · web=amber · act=green · read/think=
   accent); a living header label cycles soft phrases with a blur-slide; each new checkpoint eases
   in with a dreamy blur-slide; the panel carries a soft category-tinted glow + a slow sheen.
   Reduced-motion collapses to a calm static orb + gentle fades (guards live in index.css). */

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

const catOf = (step: string): OrbCat => phaseCategory(step)
const rgb = (token: string, a?: number) => a != null ? `rgb(var(--${token}) / ${a})` : `rgb(var(--${token}))`

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
  const stepList = (steps?.length ? steps : toolList.map(toolPhase)).filter(s => !/^(thinking|composing)/i.test(s.trim()))
  if (!stepList.length && !reasoning && !toolList.length) return null
  return <FinishedTrace steps={stepList} reasoning={reasoning} tools={toolList}
    elapsedMs={elapsedMs} tokens={tokens} reduced={reduced} />
}

// ── live: orb-led checklist under a living label, softly glowing per current action ─────
function LiveTrace({ steps, startedAt, reduced }: { steps: string[]; startedAt: number; reduced: boolean }) {
  const shown = steps.length ? steps : ['Thinking…']
  const curCat = catOf(shown[shown.length - 1])
  const token = CAT_TOKEN[curCat]

  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 100)
    return () => clearInterval(t)
  }, [startedAt])

  // living header: ambient category phrases that keep evolving (the concrete work is the list)
  const pool = PHRASES[curCat]
  const [idx, setIdx] = useState(0)
  useEffect(() => { setIdx(0) }, [curCat])
  useEffect(() => {
    const t = setInterval(() => setIdx(i => (i + 1) % pool.length), reduced ? 2800 : 1950)
    return () => clearInterval(t)
  }, [pool, reduced])
  const label = pool[idx % pool.length]

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0 } }}
      className="proc-panel inline-block min-w-[240px] max-w-full" style={{ ['--orb' as string]: `var(--${token})` }}>
      <div className="proc-sheen" aria-hidden />
      <div className="relative">
        {/* living label + soft dot wave + elapsed */}
        <div className="mb-2 flex items-center gap-2">
          <span className="orb-label-grad inline-flex text-[13px] font-medium">
            <AnimatePresence mode="wait">
              <motion.span key={label}
                initial={{ opacity: 0, y: reduced ? 0 : 7, filter: reduced ? 'none' : 'blur(3px)' }}
                animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                exit={{ opacity: 0, y: reduced ? 0 : -7, filter: reduced ? 'none' : 'blur(3px)' }}
                transition={{ duration: 0.42, ease: 'easeOut' }} className="inline-block">{label}</motion.span>
            </AnimatePresence>
          </span>
          <span className="orb-dots" aria-hidden>
            <i className="orb-dot" style={{ ['--i' as string]: 0 }} />
            <i className="orb-dot" style={{ ['--i' as string]: 1 }} />
            <i className="orb-dot" style={{ ['--i' as string]: 2 }} />
          </span>
          <span className="ml-auto pl-3 font-mono text-[10px] tabular-nums text-muted/70">{elapsed.toFixed(1)}s</span>
        </div>
        {/* checkpoint timeline — orb leads the current step, faint category checks on the done ones */}
        <ol className="space-y-1.5">
          <AnimatePresence initial={false}>
            {shown.map((s, i) => {
              const isLast = i === shown.length - 1
              const cat = catOf(s)
              const tok = CAT_TOKEN[cat]
              return (
                <motion.li key={`${i}-${s}`} layout={!reduced}
                  initial={{ opacity: 0, y: reduced ? 0 : 6, filter: reduced ? 'none' : 'blur(3px)' }}
                  animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                  transition={{ duration: 0.4, ease: 'easeOut' }}
                  className="flex items-center gap-2.5 text-[12.5px]">
                  {isLast
                    ? <span className="proc-orb"><Orb cat={cat} reduced={reduced} /></span>
                    : <span className="flex h-[22px] w-[22px] shrink-0 items-center justify-center">
                        <Check size={13} style={{ color: rgb(tok, 0.7) }} />
                      </span>}
                  <span className={isLast ? 'font-medium' : 'text-muted'} style={isLast ? { color: rgb(tok) } : undefined}>{s}</span>
                </motion.li>
              )
            })}
          </AnimatePresence>
        </ol>
      </div>
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
                  {steps.map((s, i) => (
                    <li key={i} className="flex items-center gap-2 text-[12px] text-muted">
                      <Check size={12} className="shrink-0" style={{ color: rgb(CAT_TOKEN[catOf(s)], 0.7) }} /> {s}
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
