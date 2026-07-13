import { Bot, Crown, Radio } from 'lucide-react'
import type { Agent } from '../../api'

const tone = (status: string) => status === 'working' ? 'bg-warning' : status === 'online' ? 'bg-success' : 'bg-muted'

export default function AgentDock({ agents, selectedId, activeAgentId, onSelect }:
  { agents: Agent[]; selectedId?: string; activeAgentId?: string | null; onSelect: (agent: Agent) => void }) {
  return (
    <div className="flex min-w-0 items-stretch overflow-x-auto border-t border-border bg-bg/90 backdrop-blur-xl">
      <div className="flex w-24 shrink-0 flex-col justify-center border-r border-border px-3">
        <span className="text-[9px] font-semibold uppercase text-muted">Agent dock</span>
        <span className="text-[11px] text-text">{agents.filter(a => a.live.status === 'working').length} active</span>
      </div>
      {agents.map(agent => {
        const active = activeAgentId === agent.id
        const selected = selectedId === agent.id
        return (
          <button key={agent.id} onClick={() => onSelect(agent)}
            className={`relative flex w-[150px] shrink-0 items-center gap-2.5 border-r border-border px-3 py-2 text-left transition-colors ${selected ? 'bg-accent/10' : 'hover:bg-overlay/5'}`}>
            <span className="relative flex h-9 w-9 shrink-0 items-center justify-center border border-border bg-surface"
              style={{ boxShadow: active ? `0 0 18px ${agent.color || 'rgb(var(--accent))'}55` : undefined }}>
              <Bot size={17} style={{ color: agent.color || 'rgb(var(--accent))' }} />
              <i className={`absolute -bottom-1 -right-1 h-2.5 w-2.5 border-2 border-bg ${tone(active ? 'working' : agent.live.status)}`} />
            </span>
            <span className="min-w-0">
              <span className="flex items-center gap-1 truncate text-[12px] font-semibold text-heading">
                {agent.name}{agent.is_head && <Crown size={10} className="text-warning" />}
              </span>
              <span className="block truncate text-[10px] text-muted">{active ? 'Working now' : agent.role || agent.live.status}</span>
            </span>
            {active && <Radio size={11} className="absolute right-2 top-2 animate-pulse text-warning" />}
          </button>
        )
      })}
    </div>
  )
}
