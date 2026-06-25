import { Component, type ReactNode } from 'react'
import { AlertTriangle, RotateCw } from 'lucide-react'

/**
 * Catches render-time crashes in a page so a single broken page shows a retry
 * panel instead of blanking the whole app (which previously forced a reload).
 * AppShell keys this by pathname, so navigating away clears the error.
 */
export default class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: unknown) {
    console.error('[TOBI] Page render error:', error, info)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full border border-danger/40 bg-danger/10 text-danger">
          <AlertTriangle size={26} />
        </div>
        <div>
          <div className="text-sm font-semibold text-heading">This page hit an error</div>
          <div className="mt-1 max-w-md break-words text-xs text-muted">{error.message || 'Unknown error'}</div>
        </div>
        <button
          onClick={() => this.setState({ error: null })}
          className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs text-text transition-colors hover:border-accent/50 hover:text-accent"
        >
          <RotateCw size={13} /> Retry
        </button>
      </div>
    )
  }
}
