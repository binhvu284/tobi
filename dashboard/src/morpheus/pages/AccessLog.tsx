// Access log: every attempt to open the gate, in full forensic detail.
//
// The owner chose detection over walls -- no lockouts, no wipe-on-failure -- so this page is the
// tripwire, and it earns that by capturing everything and hiding nothing. Rows lead with the
// judgement rather than the timestamp: you read down the left edge and stop only at something
// that does not look like you.
//
// Two rules the detail view follows:
//   - A signal that was NOT captured is shown as "not captured", never omitted. Absence is
//     evidence: no pointer movement at all is what separates a tired human from a script.
//   - Anything that contradicts the owner's baseline is marked, so the eye lands on it first.
//
// Morph1 turns the whole capture into plain language. The raw signals stay available underneath,
// because an assessment you cannot check is just an opinion.
import { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronRight, ChevronDown, ShieldOff, Monitor, Wifi, Fingerprint, ListOrdered, Clock,
  Sparkles, AlertTriangle, Check, Minus, Maximize2, Copy, Download, X,
} from 'lucide-react'
import { useMorpheus, type AccessEntry, type Signal, type SignalGroup, type AgentReport } from '../MorpheusSession'
import { useFeedback } from '../MorpheusFeedback'
import { ActionButton } from '../../components/async-ui'
import { Page, PageHeader, Card, Badge, Empty, Skeleton, Failure, Rise, Btn } from '../ui'

const VERDICT: Record<AccessEntry['verdict'], { label: string; tone: string }> = {
  you: { label: 'Almost certainly you', tone: 'text-success' },
  likely: { label: 'Likely you', tone: 'text-success' },
  unknown: { label: 'Not you', tone: 'text-danger' },
}

const GROUP_ICON: Record<SignalGroup['kind'], typeof Monitor> = {
  device: Monitor, network: Wifi, behaviour: Fingerprint, sequence: ListOrdered, context: Clock,
}

const THREAT: Record<AgentReport['threat'], { label: string; tone: 'success' | 'warning' | 'danger' }> = {
  none: { label: 'No threat', tone: 'success' },
  low: { label: 'Low threat', tone: 'success' },
  medium: { label: 'Worth attention', tone: 'warning' },
  high: { label: 'Serious', tone: 'danger' },
}

/**
 * The capture as Markdown.
 *
 * One formatter feeds the modal's filename, the clipboard and the downloaded file, so the three
 * can never drift apart. Missing signals are written out as "Not captured" rather than dropped:
 * a report that silently omits what it failed to see is worse than one that admits the gap.
 */
function captureToMarkdown(e: AccessEntry): string {
  const L: string[] = []
  L.push(`# Access attempt: ${e.at}`, '')
  L.push(`- Verdict: ${VERDICT[e.verdict].label} (${e.confidence}% confident)`)
  L.push(`- Outcome: ${e.ok ? `Opened on attempt ${e.attempts}` : `Failed, ${e.attempts} attempts`}`)
  L.push(`- Summary: ${e.summary}`)
  if (e.ruled) L.push(`- Your ruling: ${e.ruled === 'me' ? 'Confirmed you' : 'Marked an intruder'}`)
  if (e.blocked) L.push('- Source blocked: yes')
  L.push('')

  if (e.report) {
    const r = e.report
    L.push(`## ${r.agent} reading`, '')
    L.push(`**${r.headline}**`, '')
    L.push(`- Threat: ${THREAT[r.threat].label}`)
    L.push(`- Confidence: ${r.confidence}%`)
    L.push(`- What they were after: ${r.intent}`, '')
    L.push('### Assessment', '')
    r.assessment.forEach(p => L.push(p, ''))
    L.push('### What happens next', '')
    r.predictions.forEach(p => L.push(`- ${p}`))
    L.push('', '### What you can do', '')
    r.recommended.forEach(p => L.push(`- ${p}`))
    L.push('')
  }

  L.push('## Everything captured', '')
  e.groups.forEach(g => {
    L.push(`### ${g.group}`, '')
    L.push('| Signal | Value | Baseline |', '| --- | --- | --- |')
    g.signals.forEach(s => {
      const val = s.value === null ? 'Not captured' : s.value.replace(/\|/g, '\\|')
      const base = s.verdict === 'match' ? 'matches'
        : s.verdict === 'mismatch' ? 'OFF BASELINE' : ''
      L.push(`| ${s.label} | ${val} | ${base} |`)
    })
    L.push('')
    const notes = g.signals.filter(s => s.note)
    if (notes.length) {
      notes.forEach(s => L.push(`> **${s.label}:** ${s.note}`, ''))
    }
  })

  const off = e.groups.reduce((n, g) => n + g.signals.filter(s => s.verdict === 'mismatch').length, 0)
  const gaps = e.groups.reduce((n, g) => n + g.signals.filter(s => s.value === null).length, 0)
  L.push('---', '')
  L.push(`${off} signals off baseline, ${gaps} not captured.`)
  L.push('Exported from Morpheus. Password characters are never recorded, only their length.')
  return L.join('\n')
}

/** A filename that sorts chronologically and says what it is. */
function captureFilename(e: AccessEntry): string {
  const slug = e.at.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return `morpheus-access-${slug}.md`
}

function SignalRow({ s }: { s: Signal }) {
  const missing = s.value === null
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-[5px]">
      <span className="w-[168px] shrink-0 text-[11.5px] text-muted">{s.label}</span>
      <span className={`min-w-0 flex-1 text-[12.5px] ${
        missing ? 'italic text-muted/70'
          : s.verdict === 'mismatch' ? 'text-danger'
            : s.verdict === 'match' ? 'text-text' : 'text-text'}`}>
        {missing ? 'Not captured' : s.value}
      </span>
      <span className="shrink-0">
        {s.verdict === 'match' && <Check size={11} className="text-success" />}
        {s.verdict === 'mismatch' && <AlertTriangle size={11} className="text-danger" />}
        {missing && !s.verdict && <Minus size={11} className="text-muted/60" />}
      </span>
      {s.note && (
        <p className="w-full pl-0 text-[11.5px] leading-relaxed text-muted sm:pl-[180px]">{s.note}</p>
      )}
    </div>
  )
}

function Report({ r }: { r: AgentReport }) {
  const t = THREAT[r.threat]
  return (
    <Rise>
      <div className={`rounded-card border p-4 ${
        r.threat === 'high' ? 'border-danger/40 bg-danger/[0.06]'
          : r.threat === 'medium' ? 'border-warning/40 bg-warning/[0.06]'
            : 'border-accent/30 bg-accent/[0.05]'}`}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-btn bg-accent/15 text-accent">
            <Sparkles size={12} />
          </span>
          <span className="text-[12.5px] font-semibold text-heading">{r.agent}</span>
          <Badge tone={t.tone}>{t.label}</Badge>
          <span className="text-[11.5px] tabular-nums text-muted">{r.confidence}% confident</span>
          <span className="ml-auto text-[11px] text-muted">{r.generatedAt}</span>
        </div>

        <p className="mt-3 text-[14.5px] font-medium leading-snug text-heading">{r.headline}</p>

        <div className="mt-3 space-y-2.5">
          {r.assessment.map((p, i) => (
            <p key={i} className="text-[13px] leading-relaxed text-text/85">{p}</p>
          ))}
        </div>

        <div className="mt-4 grid gap-4 border-t border-border/60 pt-3.5 sm:grid-cols-2">
          <div>
            <p className="text-[10.5px] font-semibold uppercase tracking-[0.09em] text-muted">
              What they were after
            </p>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-text/85">{r.intent}</p>
            <p className="mt-3.5 text-[10.5px] font-semibold uppercase tracking-[0.09em] text-muted">
              What happens next
            </p>
            <ul className="mt-1.5 space-y-1.5">
              {r.predictions.map(p => (
                <li key={p} className="flex gap-2 text-[12.5px] leading-relaxed text-text/85">
                  <span aria-hidden className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-muted" />{p}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-[10.5px] font-semibold uppercase tracking-[0.09em] text-muted">
              What you can do
            </p>
            <ul className="mt-1.5 space-y-1.5">
              {r.recommended.map(p => (
                <li key={p} className="flex gap-2 text-[12.5px] leading-relaxed text-text/85">
                  <Check size={11} className="mt-1 shrink-0 text-accent" />{p}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </Rise>
  )
}

/** The grouped capture. Shared by the inline panel and the full-screen view, so they cannot drift. */
function SignalGroups({ e, columns = false }: { e: AccessEntry; columns?: boolean }) {
  return (
    <div className={columns ? 'grid gap-x-10 gap-y-6 lg:grid-cols-2' : 'space-y-4'}>
      {e.groups.map(g => {
        const Icon = GROUP_ICON[g.kind]
        return (
          <section key={g.group} className="break-inside-avoid">
            <p className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase
              tracking-[0.09em] text-muted">
              <Icon size={11} className="shrink-0" /> {g.group}
            </p>
            <div className="mt-1.5 divide-y divide-border/50">
              {g.signals.map(s => <SignalRow key={s.label} s={s} />)}
            </div>
          </section>
        )
      })}
    </div>
  )
}

/** Expand, copy, download. Icon-only, because the row header has no room for three labels. */
function CaptureActions({ e, onExpand, compact = false }: {
  e: AccessEntry; onExpand?: () => void; compact?: boolean
}) {
  const { announce } = useFeedback()
  // `morph-tap` adds transform to the shared transition. These are ActionButtons, which take no
  // style prop, and an arbitrary Tailwind `[transition:...]` with commas did not survive the
  // build, so the hover lift snapped while every other control glided. A class is the one route
  // that works for all three buttons here.
  const cls = `morph-tap grid h-7 w-7 place-items-center rounded-btn border border-border bg-surface
    text-muted outline-none hover:-translate-y-px hover:border-accent/50 hover:bg-accent/[0.08]
    hover:text-accent active:translate-y-0 active:scale-95 focus-visible:ring-2 focus-visible:ring-accent/50`

  const copy = useCallback(async () => {
    const md = captureToMarkdown(e)
    try {
      await navigator.clipboard.writeText(md)
      announce({ tone: 'ok', title: 'Capture copied', detail: 'The full record is on your clipboard as Markdown.' })
    } catch {
      // Clipboard access can be refused. Say so rather than pretending it worked.
      announce({ tone: 'warn', title: 'Could not reach the clipboard',
        detail: 'Your browser refused the request. Use Download instead.' })
    }
  }, [e, announce])

  const download = useCallback(async () => {
    const md = captureToMarkdown(e)
    const url = URL.createObjectURL(new Blob([md], { type: 'text/markdown;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = captureFilename(e)
    document.body.appendChild(a)
    a.click()
    a.remove()
    // Revoke on the next tick: revoking synchronously can cancel the download in some browsers.
    setTimeout(() => URL.revokeObjectURL(url), 4000)
    announce({ tone: 'ok', title: 'Capture saved', detail: captureFilename(e) })
  }, [e, announce])

  return (
    <span className="flex shrink-0 items-center gap-1.5" onClick={ev => ev.stopPropagation()}>
      {onExpand && (
        <button onClick={onExpand} className={cls} title="Open full screen"
          aria-label="Open capture full screen">
          <Maximize2 size={12.5} />
        </button>
      )}
      <ActionButton onAction={copy} className={cls} title="Copy as Markdown"
        icon={<Copy size={12.5} />} />
      <ActionButton onAction={download} className={cls} title="Download as .md"
        icon={<Download size={12.5} />} />
      {!compact && null}
    </span>
  )
}

/**
 * Full-screen reading view. The capture is long; this gives it the whole window.
 *
 * Rendered at page level rather than through a portal into `document.body`, and NOT inside any
 * `Rise` wrapper. Two reasons, both learned the hard way:
 *   - A portal into `document.body` sits outside React's root container here, so click handlers
 *     inside it never fired. The modal rendered perfectly and was completely dead.
 *   - `Rise` is a motion element, and a transformed ancestor becomes the containing block for
 *     `position: fixed`, which would pin this to the row instead of the viewport.
 */
function CaptureModal({ e, onClose }: { e: AccessEntry; onClose: () => void }) {
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => { if (ev.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const off = e.groups.reduce((n, g) => n + g.signals.filter(s => s.verdict === 'mismatch').length, 0)
  const gaps = e.groups.reduce((n, g) => n + g.signals.filter(s => s.value === null).length, 0)
  const total = e.groups.reduce((n, g) => n + g.signals.length, 0)

  return (
    <motion.div className="fixed inset-0 z-[75] flex flex-col bg-bg"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      transition={{ duration: 0.18 }}
      role="dialog" aria-modal="true" aria-label={`Full capture for ${e.at}`}>
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border bg-panel px-6 py-3.5">
        <div className="min-w-0 flex-1">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.1em] text-muted">Full capture</p>
          <h2 className="mt-0.5 font-display text-[18px] font-semibold tracking-[-0.01em] text-heading">{e.at}</h2>
        </div>
        <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] tabular-nums text-muted">
          <span>{total} signals</span>
          {off > 0 && <span className="text-danger">{off} off baseline</span>}
          {gaps > 0 && <span>{gaps} not captured</span>}
        </span>
        <CaptureActions e={e} compact />
        <button onClick={onClose} aria-label="Close full capture"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-btn border border-border bg-surface
            text-muted outline-none transition-colors duration-150 hover:border-danger/50 hover:text-danger
            focus-visible:ring-2 focus-visible:ring-accent/50">
          <X size={13} />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-6 py-7">
          {e.report && <div className="mb-7"><Report r={e.report} /></div>}
          <SignalGroups e={e} columns />
          <p className="mt-8 border-t border-border pt-4 text-[11.5px] leading-relaxed text-muted">
            Password characters are never recorded, only how many there were.
            Press Escape to close.
          </p>
        </div>
      </div>
    </motion.div>
  )
}

function Row({ e, index, onExpand }: {
  e: AccessEntry; index: number; onExpand: (e: AccessEntry) => void
}) {
  const { ruleOn, blockSource, analyse } = useMorpheus()
  const { announce, confirm } = useFeedback()
  const [open, setOpen] = useState(false)
  const [showRaw, setShowRaw] = useState(false)
  const v = VERDICT[e.verdict]

  const mismatches = e.groups.reduce(
    (n, g) => n + g.signals.filter(s => s.verdict === 'mismatch').length, 0)
  const missing = e.groups.reduce((n, g) => n + g.signals.filter(s => s.value === null).length, 0)

  const block = async () => {
    const ok = await confirm({
      title: 'Block this device and network?',
      body: 'Future attempts from this source are refused before they reach the gate. You can undo this later from the same entry.',
      confirmLabel: 'Block it', tone: 'danger',
    })
    if (ok) {
      blockSource(e.id)
      announce({ tone: 'ok', title: 'Source blocked', detail: 'That device and network can no longer reach the gate.' })
    }
  }

  const run = async () => {
    announce({ tone: 'info', title: 'Morph1 is reading the entry', detail: 'Comparing every signal against your baseline.' })
    await analyse(e.id)
    announce({ tone: 'ok', title: 'Morph1 has an answer', detail: 'The reading is on the entry.' })
  }

  return (
    <Rise delay={index * 0.04} className="mb-2">
      <button onClick={() => setOpen(o => !o)} aria-expanded={open}
        className={`morph-lift flex w-full items-center gap-3 rounded-card border bg-surface/60 px-3.5 py-3
          text-left outline-none hover:bg-surface/80 focus-visible:ring-2 focus-visible:ring-accent/50 ${
          open ? 'border-accent/45' : 'border-border hover:border-accent/30'}`}>
        <span className="shrink-0 text-muted">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className={`w-[150px] shrink-0 text-[12.5px] font-medium ${v.tone}`}>
          {e.ruled === 'me' ? 'Confirmed you' : e.ruled === 'not-me' ? 'Marked intruder' : v.label}
        </span>
        <span className="w-[142px] shrink-0 text-[12px] tabular-nums text-text">{e.at}</span>
        <span className="hidden min-w-0 flex-1 truncate text-[12px] text-muted sm:block">{e.summary}</span>
        {mismatches > 0 && (
          <span className="hidden shrink-0 items-center gap-1 text-[11px] text-danger md:flex">
            <AlertTriangle size={11} />{mismatches} off baseline
          </span>
        )}
        <span className="shrink-0 text-[11.5px] tabular-nums text-muted">{e.confidence}%</span>
        <Badge tone={e.ok ? 'success' : 'danger'}>
          {e.ok ? `In, try ${e.attempts}` : `Failed ${e.attempts}x`}
        </Badge>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.26, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden">
            <div className="mt-1.5 space-y-3">

              {/* Morph1 first: the reading, then the evidence it rests on. */}
              {e.report ? <Report r={e.report} /> : (
                <Card className="flex flex-wrap items-center gap-3 bg-panel/70 p-4">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-btn bg-accent/12 text-accent">
                    <Sparkles size={13} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-heading">Ask Morph1 to read this</p>
                    <p className="mt-0.5 text-[12px] leading-relaxed text-muted">
                      It compares all {e.groups.reduce((n, g) => n + g.signals.length, 0)} captured
                      signals against your baseline and explains, in plain words, what happened.
                    </p>
                  </div>
                  <ActionButton onAction={run}
                    className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-btn bg-accent px-3.5
                      text-[12.5px] font-medium text-bg outline-none transition-colors hover:bg-accent/90">
                    Analyse
                  </ActionButton>
                </Card>
              )}

              {/* Raw capture */}
              <Card className="bg-panel/70">
                <div className="flex items-center gap-2 px-4 py-2.5">
                  <button onClick={() => setShowRaw(s => !s)} aria-expanded={showRaw}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left text-[12px] text-muted
                      outline-none transition-colors hover:text-text">
                    {showRaw ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    Everything captured
                    <span className="ml-auto flex items-center gap-3 pr-2 text-[11.5px]">
                      {mismatches > 0 && <span className="text-danger">{mismatches} off baseline</span>}
                      {missing > 0 && <span className="text-muted">{missing} not captured</span>}
                    </span>
                  </button>
                  <CaptureActions e={e} onExpand={() => onExpand(e)} />
                </div>
                <AnimatePresence initial={false}>
                  {showRaw && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
                      className="overflow-hidden">
                      <div className="border-t border-border px-4 py-3.5">
                        <SignalGroups e={e} />
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </Card>

              {/* Owner actions */}
              <div className="flex flex-wrap items-center gap-2">
                <ActionButton
                  onAction={() => { ruleOn(e.id, 'me'); announce({ tone: 'ok', title: 'Marked as you', detail: 'Morpheus will treat this pattern as normal.' }) }}
                  className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border px-3 text-[12.5px]
                    text-text outline-none transition-colors duration-150 hover:border-success/50 hover:text-success">
                  This was me
                </ActionButton>
                <ActionButton
                  onAction={() => { ruleOn(e.id, 'not-me'); announce({ tone: 'warn', title: 'Marked as an intruder', detail: 'This entry stays highlighted.' }) }}
                  className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border px-3 text-[12.5px]
                    text-text outline-none transition-colors duration-150 hover:border-danger/50 hover:text-danger">
                  Not me
                </ActionButton>
                <ActionButton onAction={block} disabled={e.blocked} icon={<ShieldOff size={12} />}
                  className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border px-3 text-[12.5px]
                    text-text outline-none transition-colors duration-150 hover:border-danger/50 hover:text-danger">
                  {e.blocked ? 'Source blocked' : 'Block device and network'}
                </ActionButton>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </Rise>
  )
}

export default function AccessLog() {
  const { access, preview } = useMorpheus()
  // Which entry is open full screen. Held here, at page level, so the modal renders outside every
  // motion wrapper -- a transformed ancestor would pin `position: fixed` to the row.
  const [expanded, setExpanded] = useState<AccessEntry | null>(null)

  // Keep the open modal in step with its entry, so a reading attached while it is open appears.
  const live = expanded ? access.find(e => e.id === expanded.id) ?? null : null

  return (
    <>
      {/* Deliberately NOT wrapped in AnimatePresence. Wrapping it kept the modal mounted after
          its state went null, so Escape and the close button both looked broken. An exit fade is
          not worth a dialog the owner cannot dismiss; it opens with an animation and closes at
          once. */}
      {live && <CaptureModal e={live} onClose={() => setExpanded(null)} />}

    <Page width="lg">
      <PageHeader title="Access log"
        lede="Every attempt to open the gate, successful or not, with everything Morpheus was able to capture. Open one and Morph1 will tell you what it means." />

      <div className="mt-7">
        {preview === 'failure' ? (
          <Failure what="Your access history" />
        ) : preview === 'loading' ? (
          <Skeleton rows={5} />
        ) : access.length === 0 ? (
          <Empty icon={<Fingerprint size={19} />} title="No entries recorded"
            body="Every unlock and every refusal will be listed here, with the full forensic detail behind each one." />
        ) : (
          access.map((e, i) => <Row key={e.id} e={e} index={i} onExpand={setExpanded} />)
        )}
      </div>
    </Page>
    </>
  )
}
