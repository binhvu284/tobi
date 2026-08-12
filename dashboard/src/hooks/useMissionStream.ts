import { useEffect, useRef, useState } from 'react'
import { softFail } from '../lib/report'
import { getMission, type Mission } from '../api.office'

export type StepState = {
  seq: number; agent_id?: string; agent?: string; action?: string
  status: 'running' | 'done' | 'failed'; text: string; tokens: number
}
export type WarState = {
  status: string
  steps: Record<number, StepState>
  order: number[]
  total: number          // declared step count (from mission_start)
  activeSeq: number | null
  activeAgentId: string | null
  blackboard: string
  totalTokens: number
  summary: string | null
  done: boolean
  connected: boolean
}

const blank = (): WarState => ({
  status: 'planned', steps: {}, order: [], total: 0, activeSeq: null, activeAgentId: null,
  blackboard: '', totalTokens: 0, summary: null, done: false, connected: false,
})

function fromMission(m: Mission): Partial<WarState> {
  const steps: Record<number, StepState> = {}
  const order: number[] = []
  for (const s of m.steps || []) {
    steps[s.seq] = { seq: s.seq, agent_id: s.agent_id, action: s.action, status: (s.status === 'pending' ? 'running' : s.status) as StepState['status'], text: s.output || '', tokens: s.tokens }
    order.push(s.seq)
  }
  const active = (m.steps || []).find(s => s.status === 'running')
  const done = ['done', 'blocked', 'cancelled'].includes(m.status)
  return {
    status: m.status, steps, order, total: order.length,
    activeSeq: active?.seq ?? null, activeAgentId: active?.agent_id ?? null,
    totalTokens: m.cost_tokens, summary: m.summary, done, connected: true,
  }
}

/** Subscribe to a mission's live event stream (SSE) with a polling fallback so the
 * war-room animates even if the proxy buffers text/event-stream. */
export function useMissionStream(missionId: number | null): WarState {
  const [state, setState] = useState<WarState>(blank)
  const esRef = useRef<EventSource | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (missionId == null) { setState(blank()); return }
    setState(blank())
    let gotEvent = false
    const stopPoll = () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }

    const startPolling = () => {
      if (pollRef.current) return
      const tick = async () => {
        try {
          const m = await getMission(missionId)
          setState(s => ({ ...s, ...fromMission(m) }))
          if (['done', 'blocked', 'cancelled'].includes(m.status)) stopPoll()
        } catch (error) { softFail('the mission stream')(error) }
      }
      tick(); pollRef.current = setInterval(tick, 1200)
    }

    const es = new EventSource(`/api/missions/${missionId}/events?since=0`)
    esRef.current = es
    const on = (type: string, handler: (d: any) => void) =>
      es.addEventListener(type, (e) => { gotEvent = true; stopPoll(); try { handler(JSON.parse((e as MessageEvent).data)) } catch { /* ignore */ } })

    on('mission_start', (d) => setState(s => ({ ...s, status: 'running', connected: true, total: d.steps ?? s.total })))
    on('step_start', (d) => setState(s => ({
      ...s, connected: true, activeSeq: d.seq, activeAgentId: d.agent_id,
      order: s.order.includes(d.seq) ? s.order : [...s.order, d.seq],
      steps: { ...s.steps, [d.seq]: { seq: d.seq, agent_id: d.agent_id, agent: d.agent, action: d.action, status: 'running', text: '', tokens: 0 } },
    })))
    on('step_delta', (d) => setState(s => {
      const cur = s.steps[d.seq] || { seq: d.seq, status: 'running' as const, text: '', tokens: 0 }
      return { ...s, steps: { ...s.steps, [d.seq]: { ...cur, text: cur.text + d.text } } }
    }))
    on('step_done', (d) => setState(s => {
      const cur = s.steps[d.seq] || { seq: d.seq, status: 'running' as const, text: '', tokens: 0 }
      return { ...s, activeAgentId: null, totalTokens: d.total_tokens ?? s.totalTokens,
        steps: { ...s.steps, [d.seq]: { ...cur, status: 'done', tokens: d.tokens, text: d.output ?? cur.text } } }
    }))
    on('blackboard_update', (d) => setState(s => ({ ...s, blackboard: d.context || '' })))
    on('mission_done', (d) => setState(s => ({ ...s, status: d.status, done: true, summary: d.summary ?? s.summary, totalTokens: d.tokens ?? s.totalTokens, activeSeq: null, activeAgentId: null })))
    es.onerror = () => { if (!gotEvent) startPolling() } // proxy buffered / SSE unavailable

    return () => { es.close(); esRef.current = null; stopPoll() }
  }, [missionId])

  return state
}
