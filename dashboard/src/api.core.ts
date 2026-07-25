// Core status/projects/lessons reads
//
// Split out of api.ts (pre-#21 refactor) so the barrel stops being an import hub;
// still re-exported from './api' for any consumer that wants the barrel.
import { get, request } from './apiCore'
import { vreq } from './apiVault'
import type { PendingAction } from './api.brain'

export async function getStatus() {
  return get('/api/status')
}

export async function getProjects() {
  return get('/api/projects')
}

export async function getLessons() {
  return get('/api/lessons')
}
