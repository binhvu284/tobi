import { useSyncExternalStore } from 'react'
import { hasVaultSession, subscribeVaultSession } from '../apiVault'

export function useVaultSession(): boolean {
  return useSyncExternalStore(subscribeVaultSession, hasVaultSession, () => false)
}
