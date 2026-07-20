// Local Chat page types — extracted from pages/Chat.tsx for reuse and testability.
import type { ChatModeId, ContextChip, ChatArtifactEvent, ChatAttachment, MemoryChip } from '../../api'

export type TierMark = { tier: number; colorKey: string; roman: string; name: string }

export type Meta = {
  elapsedMs?: number; tokens?: number; tools?: string[]; steps?: string[]
  // #16 mode contract (persisted in the message meta column)
  mode?: ChatModeId; run_id?: number; artifact_ids?: number[]
  context?: { projects?: ContextChip[]; resources?: { name?: string }[] }
  artifacts?: ChatArtifactEvent[]
  memoryChips?: MemoryChip[]   // #20: per-memory feedback chips (owner rates each recalled memory)
  turn_id?: string
}
export type Msg = { id?: number; role: string; content: string; model?: string | null; meta?: Meta; thinking?: string | null; feedback?: number | null; created_at?: string }
export type ChatMode = 'chat' | 'agent' | 'terminal' | 'research' | 'project'
export type TurnOpts = {
  attachments?: ChatAttachment[]; web_research?: boolean; connectors?: string[]
  mode?: ChatModeId; deep_research?: boolean; review_mode?: 'ask' | 'session' | 'always'   // #16
  client_turn_id?: string; resume_run_id?: number
}
export type QueuedTurn = {
  text: string
  opts: TurnOpts
  mode: ChatMode
}
