
// Barrel for the Mission Control API client. Cold domain groups were split into
// sibling modules (#19 refactor) to shrink this file; every symbol is re-exported
// here so existing `from '../api'` / `from './api'` imports keep working unchanged.
export * from './api.performance'
export * from './api.tasks'
export * from './api.office'
export * from './api.abilities'
export * from './api.pm'
export * from './api.brain'
export * from './api.architecture'
export * from './api.graph'
export * from './api.genesis'
export * from './api.mcp'
export * from './api.storage'
export * from './api.explore'
export * from './api.developer'
export * from './api.core'
export * from './api.conductor'
export * from './api.terminal'
export * from './api.chat'
export * from './api.keys'

