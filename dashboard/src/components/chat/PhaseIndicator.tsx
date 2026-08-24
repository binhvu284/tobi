import {
  TrendingUp, Layers, Users, Briefcase, ListChecks, FolderOpen, Activity, Brain, Globe,
  HardDrive, Coins, Clock, BookmarkPlus, FolderPlus, Plus, Terminal, Package,
  MessageSquare, Sparkles, CheckSquare, Wrench, Zap, Trash2, Edit3, Target, Gauge, Server,
  FileSearch, Plug, Cog, type LucideIcon,
} from 'lucide-react'
import { SiGithub, SiGoogle, SiNotion } from '@icons-pack/react-simple-icons'

/**
 * Phase vocabulary + the live phase node for TOBI chat.
 *
 * Replaces the former "thinking orb" (a 9-layer glowing sphere with orbiting particles).
 * The motion budget here is deliberately two loops, not fourteen: a calm breathing node
 * marking the running step, and a shimmer sweep across the running step's text. Everything
 * else that moves does so once, in response to a real event (a new checkpoint arriving).
 *
 * The labels are the backend's real phase strings. Nothing here invents copy or rotates
 * phrases on a timer - if the model is between tool calls, it says so once and the elapsed
 * timer carries the sense of progress.
 *
 * Reduced motion drops both loops; guards live in index.css.
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

/** The general "an operation ran" glyph, for a step whose tool we cannot name. */
export const GENERAL_ACTION_ICON: LucideIcon = Cog

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

/** The honest one-word state for a category, used only when no concrete step exists yet. */
export const PHASE_VERB: Record<OrbCat, string> = {
  think: 'Thinking', recall: 'Recalling', read: 'Reading', act: 'Working', web: 'Searching',
}

/** The live step marker: a breathing halo around a solid core, tinted by `--orb`.
 *  One loop, sized to sit on the checkpoint rail. */
export function PhaseNode({ cat, Icon, reduced, size = 18 }:
  { cat: OrbCat; Icon?: LucideIcon | null; reduced: boolean; size?: number }) {
  return (
    <span
      className="phase-node"
      data-variant={cat}
      data-still={reduced ? 'true' : undefined}
      style={{ ['--orb' as string]: `var(--${CAT_TOKEN[cat]})`, width: size, height: size }}
    >
      <span className="phase-halo" />
      {/* the running step keeps its own action icon; the halo behind it is what says "running".
          Only a step with no identifiable action falls back to the plain core dot. */}
      {Icon
        ? <span className="phase-icon"><Icon size={Math.round(size * 0.58)} /></span>
        : <span className="phase-core" />}
    </span>
  )
}

/** A settled checkpoint: its tool icon, or a check when the step has no specific tool. */
export function StepMarker({ cat, Icon, size = 18 }: { cat: OrbCat; Icon: LucideIcon | null; size?: number }) {
  const token = CAT_TOKEN[cat]
  return (
    <span
      className="step-marker"
      style={{ ['--orb' as string]: `var(--${token})`, width: size, height: size }}
    >
      {(() => { const I = Icon ?? GENERAL_ACTION_ICON; return <I size={Math.round(size * 0.58)} /> })()}
    </span>
  )
}
