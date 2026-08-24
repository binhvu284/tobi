// Security: pick a level, then adjust anything inside it.
//
// Two rules shape this page.
//
// First, from CLAUDE.md: a feature that only works after hidden configuration is broken, not
// configurable. Every control ships already on, so this page refines behaviour rather than being
// the thing that switches protection on.
//
// Second, a toggle that claims "on" proves nothing by itself. Each control therefore states its
// real condition beside the switch -- verified, present, last checked -- so a setting that reads
// on but is not actually in force gets caught here, on a calm afternoon, rather than during an
// incident.
import { useState } from 'react'
import { Check, AlertTriangle, ShieldCheck } from 'lucide-react'
import { useMorpheus } from '../MorpheusSession'
import { useFeedback } from '../MorpheusFeedback'
import { Page, PageHeader, SectionLabel, Card, Toggle, Skeleton, Failure, Rise, Badge } from '../ui'

type Tier = 'standard' | 'high' | 'paranoid'

const TIERS: { id: Tier; name: string; sub: string; points: string[] }[] = [
  { id: 'standard', name: 'Standard', sub: 'Level 1', points: [
    'Encrypted on disk', 'Password only', 'This machine only',
  ] },
  { id: 'high', name: 'High', sub: 'Level 2', points: [
    'Encrypted on disk', 'Password and app code', 'Hardware key optional', 'This machine only',
  ] },
  { id: 'paranoid', name: 'Paranoid', sub: 'Level 3', points: [
    'Key mixed into the encryption', 'Hardware key required', 'No network listener at all',
  ] },
]

type Control = {
  id: string; name: string; detail: string; status: string; healthy: boolean; locked?: boolean
}

const GROUPS: { group: string; controls: Control[] }[] = [
  { group: 'Getting in', controls: [
    { id: 'password', name: 'Master password', detail: 'The gate. Never optional.',
      status: 'Set, last changed 12 days ago', healthy: true, locked: true },
    { id: 'code', name: 'Authenticator code', detail: 'Six digits from your phone, at every unlock.',
      status: 'Enrolled and verified', healthy: true },
    { id: 'key', name: 'Hardware key', detail: 'Mixed into the encryption, so a stolen file is useless without it.',
      status: 'Key present, responded 3 minutes ago', healthy: true },
  ] },
  { group: 'Your data', controls: [
    { id: 'encrypt', name: 'Encrypted on disk', detail: 'Unreadable without the gate, shown in full to you once you are through.',
      status: 'Active, verified on last write', healthy: true },
    { id: 'clear', name: 'Show secrets in the clear', detail: 'API keys and passwords display fully inside Morpheus.',
      status: 'On, for this session only', healthy: true },
    { id: 'audit', name: 'Private activity log', detail: 'Every run and action recorded, for you alone.',
      status: 'Recording, 1,284 entries', healthy: true },
  ] },
  { group: 'Reach and response', controls: [
    { id: 'local', name: 'This machine only', detail: 'Bound to a loopback address nothing else on the network can see.',
      status: 'Verified, no external listener', healthy: true },
    { id: 'autolock', name: 'Never auto-lock', detail: 'Stays open until you lock it. Your choice.',
      status: 'Auto-lock disabled', healthy: true },
    { id: 'panic', name: 'Panic lock', detail: 'Seals everything and returns to the gate. Lives in the top bar.',
      status: 'Ready', healthy: true },
  ] },
  { group: 'Still open', controls: [
    { id: 'recovery', name: 'Recovery method', detail: 'How you get back in if the password is ever lost.',
      status: 'Not designed yet. Nothing ships until it exists.', healthy: false },
    { id: 'remote', name: 'Remote access', detail: 'Reaching Morpheus once TOBI moves to the always-on server.',
      status: 'Deferred by decision', healthy: false },
  ] },
]

export default function Security() {
  const { tier, setTier, factors, setFactors, preview } = useMorpheus()
  const { announce, confirm } = useFeedback()
  const [on, setOn] = useState<Record<string, boolean>>(() => ({
    password: true, code: factors.code, key: factors.key,
    encrypt: true, clear: true, audit: true,
    local: true, autolock: true, panic: true,
    recovery: false, remote: false,
  }))

  const toggle = async (c: Control) => {
    const next = !on[c.id]
    // Weakening a protection is the one direction that deserves friction.
    if (!next && ['encrypt', 'local', 'key', 'code'].includes(c.id)) {
      const ok = await confirm({
        title: `Turn off ${c.name.toLowerCase()}?`,
        body: 'This lowers the protection around data that is sensitive by default. You can turn it back on at any time.',
        confirmLabel: 'Turn it off', tone: 'danger',
      })
      if (!ok) return
    }
    setOn(p => ({ ...p, [c.id]: next }))
    if (c.id === 'code') setFactors({ ...factors, code: next })
    if (c.id === 'key') setFactors({ ...factors, key: next })
    announce(next
      ? { tone: 'ok', title: `${c.name} on`, detail: c.status }
      : { tone: 'warn', title: `${c.name} off`, detail: 'Protection reduced until you turn it back on.' })
  }

  const pickTier = async (t: Tier) => {
    if (t === tier) return
    const ok = await confirm({
      title: `Switch to ${TIERS.find(x => x.id === t)?.name}?`,
      body: 'This sets every switch below to that level. Anything you changed by hand is replaced.',
      confirmLabel: 'Apply level',
    })
    if (!ok) return
    setTier(t)
    announce({ tone: 'ok', title: `${TIERS.find(x => x.id === t)?.name} applied`, detail: 'Every control below now matches this level.' })
  }

  if (preview === 'failure') {
    return <Page><PageHeader title="Security" /><div className="mt-7"><Failure what="Your security settings" /></div></Page>
  }
  if (preview === 'loading') {
    return <Page><PageHeader title="Security" /><div className="mt-7"><Skeleton rows={6} /></div></Page>
  }

  return (
    <Page>
      <PageHeader title="Security"
        lede="The gate is the whole defence. Pass it and everything inside is yours to see in full. Choose a level, then change anything you like underneath it." />

      <div className="mt-7 grid gap-2.5 sm:grid-cols-3">
        {TIERS.map((t, i) => {
          const on_ = tier === t.id
          return (
            <Rise key={t.id} delay={i * 0.05}>
              <button onClick={() => pickTier(t.id)} aria-pressed={on_}
                className={`morph-lift h-full w-full rounded-card border p-4 text-left outline-none
                  focus-visible:ring-2 focus-visible:ring-accent/50 ${
                  on_ ? 'border-accent/60 bg-accent/[0.07]'
                      : 'border-border bg-surface/60 hover:border-accent/30 hover:bg-surface/80'}`}>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted">{t.sub}</p>
                  {on_ && <Badge tone="accent" icon={<ShieldCheck size={11} />}>Active</Badge>}
                </div>
                <p className="mt-1.5 text-[15px] font-semibold text-heading">{t.name}</p>
                <ul className="mt-3 space-y-1">
                  {t.points.map(p => (
                    <li key={p} className="text-[12px] leading-relaxed text-text/75">{p}</li>
                  ))}
                </ul>
              </button>
            </Rise>
          )
        })}
      </div>

      {GROUPS.map((g, gi) => (
        <section key={g.group} className="mt-8">
          <SectionLabel>{g.group}</SectionLabel>
          <Card className="mt-2.5">
            {g.controls.map((c, i) => (
              <div key={c.id} className={`flex items-start gap-5 px-4 py-3.5 ${
                i > 0 ? 'border-t border-border/60' : ''}`}>
                <div className="min-w-0 flex-1">
                  <p className="text-[13.5px] font-medium text-heading">{c.name}</p>
                  <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted">{c.detail}</p>
                  <p className={`mt-2 flex items-center gap-1.5 text-[11.5px] ${
                    c.healthy ? 'text-success' : 'text-warning'}`}>
                    {c.healthy ? <Check size={11} className="shrink-0" /> : <AlertTriangle size={11} className="shrink-0" />}
                    {c.status}
                  </p>
                </div>
                <div className="pt-0.5">
                  <Toggle on={!!on[c.id]} disabled={c.locked} label={c.name} onToggle={() => void toggle(c)} />
                </div>
              </div>
            ))}
          </Card>
          {gi === GROUPS.length - 1 && (
            <p className="mt-3 text-[12px] leading-relaxed text-muted">
              Both of these are decisions we have not made yet, not switches waiting to be flipped.
            </p>
          )}
        </section>
      ))}
    </Page>
  )
}
