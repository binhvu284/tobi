import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useReducedMotionPref } from '../../context/MotionProvider'
import {
  TrendingUp, Layers, Users, Briefcase, ListChecks, FolderOpen, Activity, Brain,
  Globe, HardDrive, Coins, Search, Clock, BookmarkPlus, FolderPlus, Plus,
  Terminal, Package, MessageSquare, GitBranch, Sparkles, CheckSquare, Wrench,
  Zap, Trash2, Edit3, Target, Gauge, Server, FileSearch, Plug, type LucideIcon,
} from 'lucide-react'
import { SiGithub, SiGoogle, SiNotion } from '@icons-pack/react-simple-icons'

/**
 * The signature TOBI "thinking" orb (Premium Chat v2 · P2, polished).
 *
 * A morphing-gradient orb (layered glow + sonar ripple + rotating ring + orbiting particles)
 * whose look + micro-animation change **per live phase** — recalling memory, reading, acting,
 * searching the web, or composing. The phase label **evolves continuously** (it never sits on a
 * single word): a themed phrase pool cycles every ~1.8s with a soft blur-slide, the live tool
 * phase (when present) leads the rotation, and animated dots + an elapsed timer keep it alive.
 * Fully reduced-motion aware: calm static orb, no ripple, gentle text fades only.
 */

export type OrbCat = 'think' | 'recall' | 'read' | 'act' | 'web'

/** Map a backend phase string (+ tool chips) to an orb category. */
export function phaseCategory(phase: string, tools?: string[]): OrbCat {
  const hay = `${(phase || '').toLowerCase()} ${(tools || []).join(' ').toLowerCase()}`
  if (/memor|recall|remember|saving that/.test(hay)) return 'recall'
  if (/web|search the web|web_search/.test(hay)) return 'web'
  if (/creat|add|updat|remov|delet|assign|complet|prepar|run_mission|mission/.test(hay)) return 'act'
  if (/read|check|look|review|evolution|health|notion|github|drive|project|task|architecture|office/.test(hay)) return 'read'
  return 'think'
}

export const CAT_TOKEN: Record<OrbCat, string> = {
  think: 'accent', recall: 'purple', read: 'accent', act: 'success', web: 'warning',
}

/** Tool-specific icon mapping — each checkpoint gets a distinctive icon.
 *  Falls back to a category-based default when no specific match. */
export const TOOL_ICONS: Record<string, LucideIcon> = {
  // evolution / architecture
  get_evolution: TrendingUp, explain_architecture: Layers,
  // office / agents
  office_status: Users,
  // projects / tasks
  list_projects: Briefcase, project_overview: FolderOpen, list_tasks: ListChecks,
  create_project: FolderPlus, create_task: Plus, complete_task: CheckSquare,
  delete_task: Trash2, delete_project: Trash2, assign_task: Users,
  update_project_progress: Gauge, create_goal: Target, edit_goal: Target,
  rename_project: Edit3, set_project_description: Edit3, pick_project_icon: Sparkles,
  create_resource: Plus,
  // memory / recall
  recall: Brain, remember: BookmarkPlus, recall_conversations: MessageSquare,
  // integrations
  read_notion: SiNotion as unknown as LucideIcon,
  read_github: SiGithub as unknown as LucideIcon,
  list_github_repos: SiGithub as unknown as LucideIcon,
  read_drive: SiGoogle as unknown as LucideIcon,
  // web
  web_search: Globe,
  // system
  check_health: Activity, storage_status: HardDrive, llm_spend: Coins,
  search_project_resources: FileSearch, get_current_datetime: Clock,
  // terminal
  run_command: Terminal, install_package: Package, configure_tool: Wrench,
  connect_tool: Plug, terminal_status: Server, list_jobs: ListChecks,
  job_output: Terminal, kill_job: Zap, set_terminal_mode: Wrench,
  list_installed_tools: Package, ask_owner_details: MessageSquare,
  run_mission: Zap,
}

/** Get the icon for a tool name, or null if no specific icon. */
export function getToolIcon(toolName: string): LucideIcon | null {
  return TOOL_ICONS[toolName] || null
}

/** Resolve an icon from a phase string (tries tool name, then keyword matching). */
export function resolvePhaseIcon(phase: string): LucideIcon | null {
  const lower = (phase || '').toLowerCase()
  // direct tool name match
  for (const [name, icon] of Object.entries(TOOL_ICONS)) {
    if (lower.includes(name.replace(/_/g, ' '))) return icon
  }
  // keyword matching
  if (/github/.test(lower)) return SiGithub as unknown as LucideIcon
  if (/notion/.test(lower)) return SiNotion as unknown as LucideIcon
  if (/drive|gmail|calendar|google/.test(lower)) return SiGoogle as unknown as LucideIcon
  if (/memory|recall/.test(lower)) return Brain
  if (/web|search/.test(lower)) return Globe
  if (/terminal|command|install|package/.test(lower)) return Terminal
  if (/project/.test(lower)) return Briefcase
  if (/task/.test(lower)) return ListChecks
  if (/health/.test(lower)) return Activity
  if (/storage|disk/.test(lower)) return HardDrive
  if (/spend|cost|token/.test(lower)) return Coins
  if (/evolution|tier/.test(lower)) return TrendingUp
  if (/architecture/.test(lower)) return Layers
  if (/time|date/.test(lower)) return Clock
  return null
}

// themed phrase pools so the label keeps evolving even when the backend phase is static
// each category has a rich set so the cycling feels alive, not repetitive
export const PHRASES: Record<OrbCat, string[]> = {
  think: [
    'Thinking it through…', 'Reasoning…', 'Connecting the dots…', 'Weighing the options…',
    'Processing that…', 'Holding it in mind…', 'Turning it over…', 'Composing a reply…',
    'Structuring the answer…', 'Putting it together…',
  ],
  recall: [
    'Searching your memory…', 'Recalling the context…', 'Pulling the details…', 'Piecing it together…',
    'Looking back through what I know…', 'Finding the right thread…', 'Digging into the archives…',
    'Recalling what we discussed…', 'Retrieving the context…',
  ],
  read: [
    'Reading the data…', 'Checking the board…', 'Looking it over…', 'Gathering the facts…',
    'Pulling up the numbers…', 'Scanning the overview…', 'Reviewing the latest…',
    'Checking the system…', 'Looking into it…', 'Getting the full picture…',
  ],
  act: [
    'Making it happen…', 'Applying the change…', 'Updating things…', 'Putting it in place…',
    'Executing the action…', 'Working on it…', 'Setting that up…', 'Taking care of it…',
  ],
  web: [
    'Searching the web…', 'Scanning sources…', 'Gathering results…', 'Cross-checking…',
    'Browsing for answers…', 'Looking it up…', 'Checking multiple sources…',
    'Finding the most current info…',
  ],
}

export function ThinkingOrb({ phase, tools, startedAt }: { phase: string; tools?: string[]; startedAt: number }) {
  const reduced = useReducedMotionPref() !== 'full'
  const [elapsed, setElapsed] = useState(0)
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 100)
    return () => clearInterval(t)
  }, [startedAt])

  const cat = phaseCategory(phase || '', tools)
  const token = CAT_TOKEN[cat]
  // a concrete tool phase (anything but the generic "Thinking…") leads the rotation
  const specific = phase && !/^thinking/i.test(phase.trim()) ? phase.trim() : ''
  const pool = useMemo(() => {
    const base = PHRASES[cat]
    return specific ? [specific, ...base.filter(p => p !== specific)] : base
  }, [cat, specific])

  // restart the rotation whenever the pool identity changes (new phase / category)
  useEffect(() => { setIdx(0) }, [pool])
  useEffect(() => {
    const t = setInterval(() => setIdx(i => (i + 1) % pool.length), reduced ? 2600 : 1850)
    return () => clearInterval(t)
  }, [pool, reduced])

  const label = pool[idx % pool.length]

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
      className="flex items-center gap-3"
    >
      <Orb cat={cat} reduced={reduced} />
      <div
        className="flex flex-wrap items-center gap-x-2.5 gap-y-1 rounded-2xl rounded-tl-sm border border-border bg-surface/80 px-3.5 py-2.5 backdrop-blur-sm"
        style={{ ['--orb' as string]: `var(--${token})` }}
      >
        <span className="orb-label-grad inline-flex items-center text-[13px] font-medium">
          <AnimatePresence mode="wait">
            <motion.span
              key={label}
              initial={{ opacity: 0, y: reduced ? 0 : 7, filter: reduced ? 'none' : 'blur(3px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              exit={{ opacity: 0, y: reduced ? 0 : -7, filter: reduced ? 'none' : 'blur(3px)' }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
              className="inline-block"
            >
              {label}
            </motion.span>
          </AnimatePresence>
        </span>
        <span className="orb-dots" aria-hidden>
          <i className="orb-dot" style={{ ['--i' as string]: 0 }} />
          <i className="orb-dot" style={{ ['--i' as string]: 1 }} />
          <i className="orb-dot" style={{ ['--i' as string]: 2 }} />
        </span>
        <span className="font-mono text-[10px] tabular-nums text-muted/70">{elapsed.toFixed(1)}s</span>
        {tools?.map(t => {
          const ToolIcon = TOOL_ICONS[t]
          return (
            <span key={t} className="flex items-center gap-1 rounded-full border border-accent/30 bg-accent/5 px-1.5 py-0.5 text-[10px] text-accent">
              {ToolIcon && <ToolIcon size={10} />}
              {t.replace(/_/g, ' ')}
            </span>
          )
        })}
      </div>
    </motion.div>
  )
}

/** The orb itself — CSS loops (theme-tinted via --orb) + framer-motion particles.
 *  Reused by ProcessTrace as the live "current step" bullet. */
export function Orb({ cat, reduced }: { cat: OrbCat; reduced: boolean }) {
  const token = CAT_TOKEN[cat]
  return (
    <div className="orb-wrap" data-variant={cat} style={{ ['--orb' as string]: `var(--${token})` }}>
      <div className="orb-ripple" />
      <div className="orb-ripple orb-ripple-2" />
      <div className="orb-glow" />
      <div className="orb-core" />
      <div className="orb-ring" />
      <div className="orb-scan" />
      <div className="orb-spark" />
      {!reduced && (
        <motion.div
          className="orb-particles"
          animate={{ rotate: 360 }}
          transition={{ duration: cat === 'web' ? 2.4 : cat === 'act' ? 3.4 : 5, repeat: Infinity, ease: 'linear' }}
        >
          {[0, 1, 2, 3].map(i => (
            <motion.span
              key={i}
              className="orb-particle"
              style={{ ['--a' as string]: `${i * 90}deg` }}
              animate={{ scale: cat === 'recall' ? [1, 0.4, 1] : [0.7, 1.15, 0.7], opacity: [0.5, 1, 0.5] }}
              transition={{ duration: cat === 'act' ? 1.1 : 1.8, repeat: Infinity, ease: 'easeInOut', delay: i * 0.18 }}
            />
          ))}
        </motion.div>
      )}
    </div>
  )
}

export default ThinkingOrb
