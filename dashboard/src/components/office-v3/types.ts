import type { Agent, Mission, OfficeArtifact } from '../../api'

export type OfficeSelection =
  | { type: 'agent'; item: Agent }
  | { type: 'mission'; item: Mission }
  | { type: 'artifact'; item: OfficeArtifact }
  | null

export type OfficeRailTab = 'command' | 'tobi' | 'artifacts' | 'activity'
