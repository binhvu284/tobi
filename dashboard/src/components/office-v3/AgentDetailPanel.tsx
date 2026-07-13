import { Bot, BrainCircuit, Cpu, Gauge, Radio, ShieldCheck } from 'lucide-react'
import type { Agent } from '../../api'

export default function AgentDetailPanel({ agent }: { agent: Agent | null }) {
  if (!agent) return (
    <div className="flex h-full min-h-52 flex-col items-center justify-center px-6 text-center text-muted">
      <Bot size={24} /><p className="mt-2 text-xs">Select an agent on the floor or in the dock to inspect its current work.</p>
    </div>
  )
  const metrics = [
    { icon: Gauge, label: 'Status', value: agent.live.status },
    { icon: Cpu, label: 'Model', value: agent.model || agent.provider },
    { icon: ShieldCheck, label: 'Autonomy', value: agent.autonomy },
    { icon: BrainCircuit, label: 'Steps', value: String(agent.scorecard?.steps ?? 0) },
  ]
  return (
    <div className="h-full overflow-y-auto">
      <div className="border-b border-border p-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center border border-border bg-overlay/5" style={{ color: agent.color || 'rgb(var(--accent))' }}><Bot size={20} /></span>
          <div className="min-w-0"><h3 className="truncate text-base font-semibold text-heading">{agent.name}</h3><p className="truncate text-[11px] text-muted">{agent.role || 'Mission specialist'}</p></div>
          <span className="ml-auto flex items-center gap-1 text-[9px] uppercase text-success"><Radio size={10} /> {agent.live.status}</span>
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-text/80">{agent.live.detail || agent.persona || 'No current work detail.'}</p>
      </div>
      <div className="grid grid-cols-2 border-b border-border">
        {metrics.map(({ icon: Icon, label, value }) => <div key={label} className="border-b border-r border-border p-3"><div className="flex items-center gap-1.5 text-[9px] uppercase text-muted"><Icon size={11} /> {label}</div><div className="mt-1 truncate text-[12px] font-semibold capitalize text-text">{value}</div></div>)}
      </div>
      <div className="p-4">
        <div className="text-[9px] font-semibold uppercase text-muted">Skills</div>
        <div className="mt-2 flex flex-wrap gap-1.5">{agent.skills.length ? agent.skills.map(skill => <span key={skill} className="border border-border px-2 py-1 text-[10px] text-muted">{skill}</span>) : <span className="text-xs text-muted">No skills registered.</span>}</div>
      </div>
    </div>
  )
}
