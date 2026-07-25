import type { Agent, Mission } from '../../api.office'
import type { OfficeArtifact } from '../../api.officev3'

export type OfficeSelection =
  | { type: 'agent'; item: Agent }
  | { type: 'mission'; item: Mission }
  | { type: 'artifact'; item: OfficeArtifact }
  | null

export type OfficeRailTab = 'command' | 'tobi' | 'artifacts' | 'activity'
