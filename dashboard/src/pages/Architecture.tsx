import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import Logo from '../components/Logo'
import { AmbientField } from '../components/motion'

type Node = {
  id: string
  label: string
  logo?: string        // brand logo name → <Logo>
  emoji?: string       // fallback glyph for non-brand concepts
  desc: string
  file?: string
  example?: string
  tip?: string         // "if there's a problem…" — for infra management
  children?: string[]
  tags?: string[]      // small badges, e.g. "primary", "fallback"
}

type Zone = {
  id: string
  title: string
  subtitle: string     // plain-language one-liner for a non-technical owner
  accent: string       // tailwind classes: border + text
  glow: string         // rgba for connectors / hover
  layout: 'row' | 'grid'
  nodes: Node[]
}

const ZONES: Zone[] = [
  {
    id: 'host',
    title: 'Host',
    subtitle: 'Where Tobi lives — a cloud computer that stays powered on so he\'s always reachable.',
    accent: 'border-accent text-accent',
    glow: 'rgba(88,166,255,0.5)',
    layout: 'row',
    nodes: [
      {
        id: 'codespace',
        label: 'GitHub Codespace',
        logo: 'github',
        desc: 'A cloud development machine from GitHub. When it boots, a startup script launches Tobi automatically inside a tmux session so he keeps running even after you close the browser.',
        file: '.devcontainer/devcontainer.json → scripts/autostart.sh',
        example: 'devcontainer (post-start) → autostart.sh → tmux session → python main.py start',
        tip: 'If Tobi is totally unreachable, the Codespace may be stopped or asleep. Reopen the Codespace; autostart.sh relaunches him.',
        children: ['devcontainer', 'autostart.sh', 'tmux', 'main.py start'],
      },
    ],
  },
  {
    id: 'runtime',
    title: 'Runtime',
    subtitle: 'The always-on engine and language that bring Tobi to life.',
    accent: 'border-purple text-purple',
    glow: 'rgba(139,92,246,0.5)',
    layout: 'row',
    nodes: [
      {
        id: 'hermes',
        label: 'Hermes',
        emoji: '⚡',
        desc: 'The always-on agent framework that gives Tobi his power: persona, skills, scheduled cron jobs and long-term memory. On startup Tobi copies his SOUL.md and skill files into Hermes (~/.hermes/) so the framework always runs the latest version of him.',
        file: '~/.hermes/  ·  synced by sync_soul_and_skills() in main.py',
        example: 'SOUL.md → ~/.hermes/SOUL.md · hermes_skills/*.md → ~/.hermes/skills/tobi/',
        tip: 'In the current run mode Tobi does his own Telegram polling — Hermes supplies persona/skills/cron, it is not a message gateway. If persona changes don\'t take effect, check the sync ran at startup.',
        tags: ['always-on'],
        children: ['persona (SOUL.md)', 'skills', 'cron', 'memory'],
      },
      {
        id: 'python',
        label: 'Python 3.12',
        logo: 'python',
        desc: 'The language Tobi is written in. main.py is the orchestrator that, in "start" mode, runs the Telegram bot, the API + dashboard servers, and the scheduler together in one process.',
        file: 'main.py',
        example: 'python main.py start → bot + API + dashboard + scheduler',
        tip: 'If a feature dies, check logs/tobi.log for a Python traceback — that names the failing module.',
        children: ['bot', 'API', 'dashboard', 'scheduler'],
      },
    ],
  },
  {
    id: 'interface',
    title: 'Interface',
    subtitle: 'How you talk to Tobi.',
    accent: 'border-accent text-accent',
    glow: 'rgba(88,166,255,0.5)',
    layout: 'row',
    nodes: [
      {
        id: 'user',
        label: 'You',
        emoji: '👤',
        desc: 'You send messages to Tobi through Telegram — your phone\'s messaging app. No special tools needed, just chat naturally.',
        example: '"write a Python script to parse CSV" or "what\'s my revenue this month?"',
      },
      {
        id: 'bot',
        label: 'Telegram Bot',
        logo: 'telegram',
        desc: 'Tobi\'s ears and mouth. It polls Telegram 24/7 for your messages, sends back replies, and handles /commands like /status or /research.',
        file: 'core/telegram_bot.py',
        example: 'Receives "write me a script" → passes it to the classifier',
        tip: 'If Tobi stops replying on Telegram, polling likely stopped. Check the Health page → recent errors, then restart "main.py start".',
      },
    ],
  },
  {
    id: 'core',
    title: 'App Core',
    subtitle: 'Tobi\'s brain: it routes your message, picks an AI model, runs the worker engines, and schedules recurring jobs.',
    accent: 'border-success text-success',
    glow: 'rgba(63,185,80,0.5)',
    layout: 'row',
    nodes: [
      {
        id: 'classifier',
        label: 'Task Classifier',
        emoji: '🧭',
        desc: 'The router. It reads your message and instantly decides what kind of task it is — no AI needed, just fast pattern matching.',
        file: 'core/task_classifier.py',
        example: '"write code" → CODING | "research niches" → RESEARCH | "hi" → SMALLTALK',
        children: ['SMALLTALK', 'CODING', 'RESEARCH', 'STATUS', 'EXECUTION'],
      },
      {
        id: 'llm',
        label: 'LLM Router',
        emoji: '⚡',
        desc: 'Picks the right AI model for each job to balance cost and quality — a big brain for complex strategy, a quick brain for simple replies.',
        file: 'core/model_router.py',
        example: 'Research → smartest model | Code → balanced | Chat → fast/cheap',
        tip: 'If replies fail, an LLM key may be missing or rate-limited — see Configured services on the Health page.',
        children: ['OpenRouter', 'Claude', 'OpenAI'],
      },
      {
        id: 'engines',
        label: 'Core Engines',
        emoji: '⚙️',
        desc: 'The workers. Three specialized engines that actually DO the work: find new business ideas, execute project tasks, and run strategic reviews.',
        file: 'core/research_engine.py · project_executor.py · ceo_loop.py',
        example: 'Research finds niches → Executor builds them → CEO Loop reviews monthly',
        children: ['Research Engine', 'Project Executor', 'CEO Loop'],
      },
      {
        id: 'scheduler',
        label: 'Scheduler',
        emoji: '⏰',
        desc: 'Runs Tobi\'s recurring jobs on a timer (Vietnam GMT+7) without you asking — daily briefings, execution cycles, weekly research and the monthly CEO review.',
        file: 'main.py (schedule library)',
        example: 'every 6h execute · daily 08:00 report · Sun 20:00 research + reflection · 1st of month CEO review',
        tip: 'If a scheduled job seems to have skipped, the Health page shows when each engine last ran.',
        children: ['6h execution', 'daily 08:00', 'Sun 20:00', 'monthly CEO'],
      },
    ],
  },
  {
    id: 'llm',
    title: 'LLM Providers',
    subtitle: 'The AI models Tobi thinks with — the cheapest capable model first, smarter ones as fallback.',
    accent: 'border-warning text-warning',
    glow: 'rgba(210,153,34,0.5)',
    layout: 'grid',
    nodes: [
      {
        id: 'openrouter',
        label: 'OpenRouter',
        logo: 'openrouter',
        desc: 'The default gateway — routes to a free/cheap capable model for most tasks to keep costs near zero.',
        file: 'core/model_router.py',
        tags: ['primary'],
        tip: 'Needs OPENROUTER_API_KEY. If missing, the router raises an error at startup.',
      },
      {
        id: 'anthropic',
        label: 'Claude (Anthropic)',
        logo: 'claude',
        desc: 'The smart fallback — used for complex reasoning, research and the CEO review when the primary model isn\'t enough.',
        file: 'core/model_router.py',
        tags: ['fallback'],
        tip: 'Needs ANTHROPIC_API_KEY. Optional, but recommended for high-quality reasoning.',
      },
      {
        id: 'openai',
        label: 'OpenAI',
        logo: 'openai',
        desc: 'A configured alternative provider available in the fallback chain.',
        file: 'core/model_router.py',
        tags: ['configured'],
      },
    ],
  },
  {
    id: 'data',
    title: 'Data',
    subtitle: 'Tobi\'s memory — everything he knows is stored here.',
    accent: 'border-muted text-muted',
    glow: 'rgba(139,148,158,0.5)',
    layout: 'grid',
    nodes: [
      {
        id: 'sqlite',
        label: 'SQLite Database',
        logo: 'sqlite',
        desc: 'A single local database file holding all business data — projects, revenue, lessons learned and conversation history.',
        file: '~/.mmo_agent/agent.db',
        example: '7 tables: projects, tasks, revenue, lessons, strategy, reports, conversations',
        tip: 'If the dashboard shows no data, this file may be missing or at a different DB_PATH. The Health page checks DB connectivity directly.',
        children: ['projects', 'tasks', 'revenue', 'lessons', 'strategy', 'reports', 'conversations'],
      },
      {
        id: 'hermes-mem',
        label: 'Hermes Memory',
        emoji: '🧠',
        desc: 'The always-on framework keeps its own persistent memory and state separate from the business database.',
        file: '~/.hermes/ (state.db, memories/)',
      },
    ],
  },
  {
    id: 'external',
    title: 'External Tools',
    subtitle: 'Real-world services Tobi uses to research and ship work.',
    accent: 'border-danger text-danger',
    glow: 'rgba(248,81,73,0.5)',
    layout: 'grid',
    nodes: [
      {
        id: 'tavily',
        label: 'Tavily',
        logo: 'tavily',
        desc: 'Web search API used by the Research Engine to find and score new business niches.',
        file: 'core/research_engine.py',
        tip: 'Without TAVILY_API_KEY, research falls back to mock data.',
      },
      {
        id: 'notion',
        label: 'Notion',
        logo: 'notion',
        desc: 'Docs and databases. Tobi can create pages and notes as part of executing a project.',
        file: 'core/integrations.py',
        tip: 'Needs NOTION_API_KEY to be active.',
      },
      {
        id: 'github',
        label: 'GitHub',
        logo: 'github',
        desc: 'Code hosting. Tobi can push code and manage repos.',
        file: 'core/integrations.py',
        tip: 'Needs GITHUB_TOKEN to be active.',
      },
      {
        id: 'vercel',
        label: 'Vercel',
        logo: 'vercel',
        desc: 'Deployment. Tobi can deploy sites and check deployment status.',
        file: 'core/integrations.py',
        tip: 'Needs VERCEL_TOKEN to be active.',
      },
      {
        id: 'supabase',
        label: 'Supabase',
        logo: 'supabase',
        desc: 'Hosted Postgres database and auth for projects Tobi builds.',
        file: 'core/integrations.py',
        tip: 'Needs SUPABASE_URL + SUPABASE_ANON_KEY to be active.',
      },
      {
        id: 'google',
        label: 'Google',
        logo: 'google',
        desc: 'Google Workspace (Calendar, Docs, Sheets). Integration is stubbed — OAuth not yet implemented.',
        file: 'core/integrations.py',
        tags: ['planned'],
      },
    ],
  },
]

const FLAT: Node[] = ZONES.flatMap(z => z.nodes)

function NodeGlyph({ node, size }: { node: Node; size: number }) {
  if (node.logo) return <Logo name={node.logo} size={size} />
  return (
    <span className="inline-flex items-center justify-center" style={{ fontSize: size }}>
      {node.emoji ?? '•'}
    </span>
  )
}

function Tag({ text }: { text: string }) {
  return (
    <span className="rounded bg-black/30 px-1.5 py-0.5 text-[10px] uppercase tracking-wide opacity-80">
      {text}
    </span>
  )
}

function ZoneBlock({
  zone, active, onPick,
}: { zone: Zone; active: Node | null; onPick: (n: Node) => void }) {
  return (
    <motion.div
      variants={{ hidden: { opacity: 0, y: 18 }, show: { opacity: 1, y: 0 } }}
      className={`w-full rounded-xl border bg-surface/40 p-4 ${zone.accent.split(' ')[0]}`}
      style={{ borderColor: zone.glow.replace('0.5', '0.4') }}
    >
      <div className="mb-3">
        <div className={`text-xs font-bold uppercase tracking-widest ${zone.accent.split(' ')[1]}`}>
          {zone.title}
        </div>
        <div className="text-muted text-xs mt-0.5">{zone.subtitle}</div>
      </div>

      <div className={zone.layout === 'grid'
        ? 'grid grid-cols-2 gap-2 sm:grid-cols-3'
        : 'flex flex-wrap gap-2'}>
        {zone.nodes.map(node => {
          const isActive = active?.id === node.id
          const compact = zone.layout === 'grid'
          return (
            <motion.button
              key={node.id}
              onClick={() => onPick(node)}
              whileHover={{ scale: 1.03, boxShadow: `0 0 14px ${zone.glow}` }}
              whileTap={{ scale: 0.97 }}
              className={`flex items-center gap-3 rounded-lg border bg-bg/60 p-3 text-left transition-colors
                ${zone.layout === 'row' ? 'min-w-[200px] flex-1' : ''}
                ${isActive ? 'ring-2 ring-white/40' : 'border-border hover:border-white/20'}`}
            >
              <NodeGlyph node={node} size={compact ? 22 : 26} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-sm font-semibold text-heading">{node.label}</span>
                  {node.tags?.map(t => <Tag key={t} text={t} />)}
                </div>
                {node.file && (
                  <div className="mt-0.5 truncate font-mono text-[10px] text-muted">{node.file}</div>
                )}
              </div>
            </motion.button>
          )
        })}
      </div>
    </motion.div>
  )
}

export default function Architecture() {
  const [active, setActive] = useState<Node | null>(null)
  const toggle = (node: Node) => setActive(prev => (prev?.id === node.id ? null : node))

  return (
    <div className="relative flex h-full gap-6 p-6">
      <AmbientField tone="rgb(var(--accent))" />
      {/* Zone stack */}
      <div className="flex-1 overflow-y-auto">
        <div className="mb-5">
          <h1 className="text-xl font-bold text-heading">Architecture</h1>
          <p className="mt-1 text-xs text-muted">
            Tobi&apos;s full stack, top to bottom — from the cloud machine he runs on down to the tools he uses. Click any piece to learn what it does and what to check if it breaks.
          </p>
        </div>

        <motion.div
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: 0.08 } } }}
          className="flex flex-col items-center gap-2"
        >
          {ZONES.map((zone, i) => (
            <div key={zone.id} className="flex w-full flex-col items-center">
              <ZoneBlock zone={zone} active={active} onPick={toggle} />
              {i < ZONES.length - 1 && (
                <svg width="2" height="20" viewBox="0 0 2 20" className="my-0.5">
                  <line x1="1" y1="0" x2="1" y2="14" stroke={ZONES[i + 1].glow}
                    strokeWidth="2" strokeDasharray="4 3" className="svg-flow-line" />
                  <polygon points="1,20 -3,12 5,12" fill={ZONES[i + 1].glow} />
                </svg>
              )}
            </div>
          ))}
        </motion.div>

        <div className="mx-auto mt-5 max-w-md text-center text-xs leading-relaxed text-muted">
          {FLAT.length} components across {ZONES.length} layers. Each message you send flows down
          through the App Core in under 2 seconds.
        </div>
      </div>

      {/* Detail panel */}
      <AnimatePresence>
        {active && (
          <motion.div
            key={active.id}
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
            transition={{ duration: 0.22 }}
            className="sticky top-0 h-fit w-80 flex-shrink-0 rounded-lg border border-border bg-surface p-5"
          >
            <div className="mb-4 flex items-start justify-between">
              <div className="flex items-center gap-3">
                <NodeGlyph node={active} size={30} />
                <div>
                  <div className="font-bold text-heading">{active.label}</div>
                  {active.file && (
                    <div className="mt-0.5 break-all font-mono text-[10px] text-muted">{active.file}</div>
                  )}
                </div>
              </div>
              <button onClick={() => setActive(null)}
                className="text-muted transition-colors hover:text-text">
                <X size={16} />
              </button>
            </div>

            <p className="mb-4 text-sm leading-relaxed text-text">{active.desc}</p>

            {active.example && (
              <div className="mb-3 rounded border border-border bg-bg p-3">
                <div className="mb-1 text-xs uppercase tracking-wider text-muted">Flow / Example</div>
                <div className="font-mono text-xs leading-relaxed text-text">{active.example}</div>
              </div>
            )}

            {active.children && (
              <div className="mb-3">
                <div className="mb-2 text-xs uppercase tracking-wider text-muted">Components</div>
                <div className="flex flex-wrap gap-1.5">
                  {active.children.map(c => (
                    <span key={c} className="rounded border border-border bg-bg px-2 py-0.5 text-xs text-text">
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {active.tip && (
              <div className="rounded border border-warning/40 bg-warning/10 p-3">
                <div className="mb-1 text-xs uppercase tracking-wider text-warning">If there&apos;s a problem</div>
                <div className="text-xs leading-relaxed text-text">{active.tip}</div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {!active && (
        <div className="flex w-80 flex-shrink-0 items-center justify-center">
          <div className="text-center text-muted">
            <div className="mb-3 text-4xl">👈</div>
            <div className="text-sm">Click any component to see details</div>
          </div>
        </div>
      )}
    </div>
  )
}
