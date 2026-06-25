import Phaser from 'phaser'

/**
 * Single React ↔ Phaser message bus. Keeps the engine isolated: React pushes
 * data in (`agents`/`stats`/`mission`/`accent`/`select`/`perf`) and the scene
 * pushes interaction out (`agent-clicked`/`agent-hover`/`scene-ready`). Swapping
 * the renderer later only touches the scene side of these events.
 */
export const EventBus = new Phaser.Events.EventEmitter()

// ── Event name constants (avoid typo drift across files) ──
export const EV = {
  // React → scene
  AGENTS: 'agents',     // Agent[]
  STATS: 'stats',       // OfficeStats | null
  MISSION: 'mission',   // { activeAgentId, status, text, tokens, done }
  ACCENT: 'accent',     // number (0xRRGGBB)
  SELECT: 'select',     // string | null  (selected agent id)
  PERF: 'perf',         // boolean (performance mode)
  INSET: 'inset',       // number (px reserved on the right for HUD panels)
  // scene → React
  CLICKED: 'agent-clicked', // string (agent id)
  HOVER: 'agent-hover',     // string | null (agent id)
  READY: 'scene-ready',     // void
} as const
