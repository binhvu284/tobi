import { useSyncExternalStore } from 'react'
import { hasVaultSession, subscribeVaultSession } from '../api'

export function useVaultSession(): boolean {
  return useSyncExternalStore(subscribeVaultSession, hasVaultSession, () => false)
}
