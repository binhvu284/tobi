// Models: the gate that decides what is allowed to speak here.
//
// The honest framing matters, and the page states it outright rather than burying it: Morpheus
// cannot strip guardrails off a hosted model, because they live in the weights on the provider's
// machines. It admits models that are already free instead, which in practice means models
// running on the owner's own hardware.
//
// Two sections, matching TOBI's Models page shape: what you own and have verified, then what has
// not qualified. Every number names the published source it came from and links to it -- an
// unattributed benchmark figure in a security tool is worse than no figure.
import { Cpu, BadgeCheck, Ban, ExternalLink, Check } from 'lucide-react'
import { useMorpheus, type ModelCard } from '../MorpheusSession'
import { useFeedback } from '../MorpheusFeedback'
import {
  Page, PageHeader, SectionLabel, Card, Badge, Btn, Empty, Skeleton, Failure, Rise,
} from '../ui'

function Row({ m, onUse }: { m: ModelCard; onUse: (m: ModelCard) => void }) {
  return (
    <Card className={`p-4 ${m.admitted ? 'morph-lift hover:border-accent/35 hover:bg-surface/80' : 'opacity-70'}`}>
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-btn ${
          m.admitted ? 'bg-accent/10 text-accent' : 'bg-overlay/[0.05] text-muted'}`}>
          <Cpu size={14} />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13.5px] font-medium text-heading">{m.name}</span>
            {m.admitted
              ? <Badge tone="success" icon={<BadgeCheck size={11} />}>Verified</Badge>
              : <Badge icon={<Ban size={11} />}>Not qualified</Badge>}
            {m.active && <Badge tone="accent">Running</Badge>}
          </div>

          <p className="mt-2 text-[12.5px] leading-relaxed text-text/75">{m.note}</p>

          {/* Numbers as numbers, with their source. No filled progress tracks: a bar chart of two
              values is dashboard decoration, and it hides where the figure came from. */}
          <div className="mt-3 flex flex-wrap items-baseline gap-x-6 gap-y-1.5 text-[12.5px]">
            <span className="text-muted">Power <span className="ml-1 text-[15px] tabular-nums text-heading">{m.power}</span></span>
            <span className="text-muted">Freedom <span className="ml-1 text-[15px] tabular-nums text-heading">{m.freedom}</span></span>
            <a href={m.sourceUrl} target="_blank" rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-[11.5px] text-muted outline-none
                transition-colors duration-150 hover:text-accent">
              {m.source} <ExternalLink size={10} />
            </a>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-muted">
            <span>{m.license}</span>
            <span>{m.hardware}</span>
            <span>{m.where === 'local' ? 'On your machine' : 'Provider servers'}</span>
          </div>
        </div>

        {m.admitted && !m.active && (
          <Btn size="sm" className="mt-0.5" onClick={() => onUse(m)}>Use</Btn>
        )}
        {m.active && (
          <span className="mt-1.5 flex shrink-0 items-center gap-1.5 text-[11.5px] text-success">
            <Check size={12} /> Active
          </span>
        )}
      </div>
    </Card>
  )
}

export default function Models() {
  const { models, preview } = useMorpheus()
  const { announce, confirm } = useFeedback()

  const use = async (m: ModelCard) => {
    const ok = await confirm({
      title: `Switch to ${m.name}?`,
      body: 'New conversations will use this model. Anything already open keeps the model it started with.',
      confirmLabel: 'Switch',
    })
    if (ok) announce({ tone: 'ok', title: 'Model switched', detail: `${m.name} is now answering.` })
  }

  const own = models.filter(m => m.admitted)
  const rest = models.filter(m => !m.admitted)

  return (
    <Page>
      <PageHeader title="Models"
        lede="Morpheus cannot remove a hosted model's guardrails, because they live in the weights on the provider's machines. It admits models that are already free instead." />

      {preview === 'failure' ? (
        <div className="mt-7"><Failure what="The model list" /></div>
      ) : preview === 'loading' ? (
        <div className="mt-7"><Skeleton rows={4} /></div>
      ) : models.length === 0 ? (
        <Empty icon={<Cpu size={19} />} title="No models yet"
          body="Morpheus needs a model running on your machine before it can answer anything. Install one and it appears here for verification." />
      ) : (
        <>
          <section className="mt-8">
            <SectionLabel count={own.length}>Own, verified</SectionLabel>
            <div className="mt-3 space-y-2.5">
              {own.map((m, i) => <Rise key={m.id} delay={i * 0.04}><Row m={m} onUse={use} /></Rise>)}
            </div>
          </section>

          <section className="mt-8">
            <SectionLabel count={rest.length}>Not qualified yet</SectionLabel>
            <div className="mt-3 space-y-2.5">
              {rest.map((m, i) => <Rise key={m.id} delay={i * 0.04}><Row m={m} onUse={use} /></Rise>)}
            </div>
          </section>
        </>
      )}
    </Page>
  )
}
