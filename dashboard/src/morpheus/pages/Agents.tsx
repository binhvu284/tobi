// Agents: the specialists Morpheus can put to work.
//
// One card per agent, collapsed to what you need to choose between them: when it was created,
// what it is, whether it is live, what it does in a line, and which model drives it. Expanding
// gives the full account, what it can do, and where its authority stops.
//
// That last part is not decoration. An unrestricted model wired into tools that can act is a
// different risk class from a chatbot, so every card states its limits as prominently as its
// skills, and the model is on the card because an agent is only as unrestricted as what drives it.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Sparkles, Check, Ban, Play, Clock, MoreVertical, Pencil, Trash2, Power, ChevronRight, Cpu,
  Calendar,
} from 'lucide-react'
import { useMorpheus, type Agent } from '../MorpheusSession'
import { useFeedback } from '../MorpheusFeedback'
import { ActionButton } from '../../components/async-ui'
import { Page, PageHeader, Card, Badge, Empty, Skeleton, Failure, Rise } from '../ui'

const STATUS: Record<Agent['status'], { label: string; tone: 'success' | 'accent' | 'neutral' }> = {
  ready: { label: 'Ready', tone: 'success' },
  working: { label: 'Working', tone: 'accent' },
  idle: { label: 'Idle', tone: 'neutral' },
}

function AgentCard({ a, index }: { a: Agent; index: number }) {
  const { renameAgent, deleteAgent, setAgentActive } = useMorpheus()
  const { announce, confirm } = useFeedback()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [menu, setMenu] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [val, setVal] = useState(a.name)

  const s = STATUS[a.status]

  const commit = () => {
    setRenaming(false)
    if (val.trim() && val.trim() !== a.name) {
      renameAgent(a.id, val.trim())
      announce({ tone: 'ok', title: 'Renamed' })
    }
  }

  const remove = async () => {
    setMenu(false)
    const ok = await confirm({
      title: `Delete ${a.name}?`,
      body: 'The agent and its history are removed. Anything it has already written stays where it is.',
      confirmLabel: 'Delete', tone: 'danger', typeToConfirm: 'delete',
    })
    if (ok) { deleteAgent(a.id); announce({ tone: 'ok', title: 'Agent deleted' }) }
  }

  const toggle = async () => {
    setMenu(false)
    if (a.active) {
      const ok = await confirm({
        title: `Deactivate ${a.name}?`,
        body: 'It keeps everything it knows but cannot be given work until you turn it back on.',
        confirmLabel: 'Deactivate',
      })
      if (!ok) return
    }
    setAgentActive(a.id, !a.active)
    announce(a.active
      ? { tone: 'warn', title: `${a.name} deactivated`, detail: 'It will not take work until reactivated.' }
      : { tone: 'ok', title: `${a.name} activated`, detail: 'It is ready to be put to work.' })
  }

  return (
    <Rise delay={index * 0.04}>
      <Card className={`overflow-visible ${a.active ? '' : 'opacity-70'}`}>
        {/* Summary line */}
        <div className="flex items-start gap-3.5 p-4">
          <span className={`mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-card ${
            a.active ? 'bg-accent/12 text-accent' : 'bg-overlay/[0.05] text-muted'}`}>
            <Sparkles size={17} />
          </span>

          <button onClick={() => setOpen(o => !o)} aria-expanded={open}
            className="min-w-0 flex-1 text-left outline-none">
            <span className="flex flex-wrap items-center gap-2">
              {renaming ? (
                <input autoFocus value={val} onChange={e => setVal(e.target.value)} onBlur={commit}
                  onClick={e => e.stopPropagation()}
                  onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setRenaming(false) }}
                  aria-label="Agent name"
                  className="rounded-input border border-accent/50 bg-bg px-2 py-1 text-[15px]
                    text-heading outline-none" />
              ) : (
                <span className="font-display text-[16px] font-semibold tracking-[-0.01em] text-heading">
                  {a.name}
                </span>
              )}
              <span className="text-[12.5px] text-muted">{a.role}</span>
              <Badge tone={s.tone}>{s.label}</Badge>
              {!a.active && <Badge tone="warning">Off</Badge>}
            </span>

            <span className="mt-1.5 block text-[12.5px] leading-relaxed text-muted">
              {a.description}
            </span>

            <span className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted">
              <span className="flex items-center gap-1"><Calendar size={10} /> {a.created}</span>
              <span className="flex items-center gap-1"><Cpu size={10} /> {a.model}</span>
              <span className="tabular-nums">{a.runs} runs</span>
              {a.lastRun && <span className="flex items-center gap-1"><Clock size={10} /> {a.lastRun}</span>}
              <span className="flex items-center gap-1 text-accent">
                <ChevronRight size={11} className="morph-icon"
                  style={{ transform: open ? 'rotate(90deg)' : 'none' }} />
                {open ? 'Less' : 'More'}
              </span>
            </span>
          </button>

          <div className="flex shrink-0 items-center gap-1.5">
            <ActionButton
              onAction={() => {
                announce(a.active
                  ? { tone: 'info', title: `${a.name} works from the access log`, detail: 'Open an entry and press Analyse.' }
                  : { tone: 'warn', title: `${a.name} is deactivated`, detail: 'Activate it before giving it work.' })
                if (a.active) navigate('/morpheus/access')
              }}
              disabled={!a.active}
              icon={<Play size={12} />}
              className="morph-tap inline-flex h-8 items-center gap-1.5 rounded-btn bg-accent px-3
                text-[12.5px] font-medium text-bg outline-none hover:bg-accent/90
                disabled:cursor-not-allowed disabled:opacity-40">
              Run
            </ActionButton>

            <div className="relative">
              <button onClick={() => setMenu(m => !m)} aria-haspopup="menu" aria-expanded={menu}
                aria-label={`More options for ${a.name}`}
                className="morph-tap grid h-[30px] w-[30px] place-items-center rounded-btn text-muted
                  hover:bg-overlay/[0.07] hover:text-text">
                <MoreVertical size={15} />
              </button>
              {menu && (
                <>
                  <button className="fixed inset-0 z-20 cursor-default" aria-hidden onClick={() => setMenu(false)} />
                  <div role="menu" className="absolute right-0 top-full z-30 mt-1 w-[180px] overflow-hidden
                    rounded-card border border-border bg-panel py-1.5 shadow-popover">
                    <button role="menuitem" onClick={() => { setVal(a.name); setRenaming(true); setMenu(false) }}
                      className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-text
                        hover:bg-overlay/[0.07] hover:pl-4"
                      style={{ transition: 'background-color var(--t) var(--ease), padding-left var(--t) var(--ease)' }}>
                      <Pencil size={13} className="text-muted" /> Rename
                    </button>
                    <ActionButton onAction={toggle}
                      icon={<Power size={13} className={a.active ? 'text-warning' : 'text-success'} />}
                      className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-text
                        hover:bg-overlay/[0.07]">
                      {a.active ? 'Deactivate' : 'Activate'}
                    </ActionButton>
                    <div className="my-1 border-t border-border" />
                    <ActionButton onAction={remove} icon={<Trash2 size={13} />}
                      className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-danger
                        hover:bg-danger/10">
                      Delete
                    </ActionButton>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Expanded detail */}
        <AnimatePresence initial={false}>
          {open && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
              className="overflow-hidden">
              <div className="border-t border-border px-4 py-4">
                <p className="text-[13px] leading-relaxed text-text/85">{a.detail}</p>
              </div>
              <div className="grid gap-0 border-t border-border sm:grid-cols-2">
                <div className="p-4 sm:border-r sm:border-border">
                  <p className="text-[10.5px] font-semibold uppercase tracking-[0.09em] text-muted">
                    What it can do
                  </p>
                  <ul className="mt-2.5 space-y-2">
                    {a.skills.map(sk => (
                      <li key={sk} className="flex gap-2.5 text-[12.5px] leading-relaxed text-text/85">
                        <Check size={12} className="mt-1 shrink-0 text-success" />{sk}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="border-t border-border p-4 sm:border-t-0">
                  <p className="text-[10.5px] font-semibold uppercase tracking-[0.09em] text-muted">
                    Where it stops
                  </p>
                  <ul className="mt-2.5 space-y-2">
                    {a.limits.map(l => (
                      <li key={l} className="flex gap-2.5 text-[12.5px] leading-relaxed text-text/85">
                        <Ban size={12} className="mt-1 shrink-0 text-muted" />{l}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </Rise>
  )
}

export default function Agents() {
  const { agents, preview } = useMorpheus()

  return (
    <Page>
      <PageHeader title="Agents"
        lede="Specialists Morpheus can put to work on your behalf. Each states what it can do and, just as plainly, where its authority stops." />

      <div className="mt-7">
        {preview === 'failure' ? (
          <Failure what="Your agents" />
        ) : preview === 'loading' ? (
          <Skeleton rows={3} />
        ) : agents.length === 0 ? (
          <Empty icon={<Sparkles size={19} />} title="No agents yet"
            body="Agents read what Morpheus captures and turn it into something you can act on." />
        ) : (
          <div className="space-y-3">
            {agents.map((a, i) => <AgentCard key={a.id} a={a} index={i} />)}
          </div>
        )}
      </div>
    </Page>
  )
}
