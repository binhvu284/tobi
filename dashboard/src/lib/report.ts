// Reporting a failure the owner did not ask for, without shouting.
//
// Most swallowed failures in the app were background work: a 45s poll, a secondary widget, a
// refresh nobody was watching. `LoadFailure` is wrong for those -- it is for data a page cannot
// render without. But `.catch(() => {})` was wrong too: it meant a connector could be failing
// every 45 seconds for an hour with nothing anywhere saying so.
//
// This is the middle: log every time, tell the owner once, and stay quiet after that until the
// situation has had time to change. A poll that fails forty times is one notice, not forty.
import { emitToast } from '../context/ToastProvider'

/** How long the same subject stays quiet after it has been reported once. */
const QUIET_MS = 60_000
const lastToldAt = new Map<string, number>()

function reason(error: unknown): string {
  if (error instanceof Error) return error.message
  const text = String(error ?? '')
  return text && text !== '[object Object]' ? text : 'No reason was reported.'
}

/** A `.catch()` handler for background work: `.catch(softFail('your abilities'))`.
 *
 *  `what` is the subject in the owner's words, and doubles as the quiet-period key, so two
 *  different failing things are both reported while one flapping thing is reported once. */
export function softFail(what: string): (error: unknown) => void {
  return (error: unknown) => {
    // Aborts are how the app cancels its own in-flight work on unmount or re-query. Reporting
    // one would be telling the owner about something the app did on purpose.
    const name = (error as { name?: string } | null)?.name
    if (name === 'AbortError' || name === 'CanceledError') return

    console.warn(`[tobi] couldn't load ${what}:`, error)
    const now = Date.now()
    const previous = lastToldAt.get(what) ?? 0
    if (now - previous < QUIET_MS) return
    lastToldAt.set(what, now)
    emitToast({ kind: 'error', title: `Couldn't load ${what}`, detail: reason(error).slice(0, 180) })
  }
}

/** Clears the quiet periods. Only for tests. */
export function _resetSoftFail(): void { lastToldAt.clear() }
