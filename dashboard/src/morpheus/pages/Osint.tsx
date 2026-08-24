// OSINT: the object library, and one object's file.
//
// An object is a target you build up over time, and it has two halves that must never be
// confused with each other:
//
//   INPUT DATA    everything raw you have collected. Files, emails, phones, socials, links,
//                 notes. Each carries when it was last touched. This is material, not findings.
//   PROFILE       the compiled picture. Every line of it names the raw items it came from, and
//                 hovering shows them. A profile field that cannot point at its evidence is an
//                 assertion, and an assertion in an intelligence tool is worse than a blank.
//
// Owner edits are marked as written rather than derived, so a hand-typed line is never mistaken
// for something the agent found.
import { useCallback, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Plus, Search, SlidersHorizontal, MoreVertical, Pencil, Trash2, ChevronRight, X, Check,
  Mail, Phone, User, AtSign, Link2, FileText, Image, MapPin, StickyNote, Sparkles, Clock,
  ScanSearch,
} from 'lucide-react'
import { useMorpheus, type OsintObject, type InputItem, type InputKind } from '../MorpheusSession'
import { useFeedback } from '../MorpheusFeedback'
import { ActionButton } from '../../components/async-ui'
import { Card, Btn, Pill, Empty, Skeleton, Failure, Rise, Badge } from '../ui'

const KIND_ICON: Record<InputKind, typeof Mail> = {
  name: User, email: Mail, phone: Phone, social: AtSign, link: Link2,
  file: FileText, image: Image, location: MapPin, note: StickyNote,
}
const KIND_LABEL: Record<InputKind, string> = {
  name: 'Name', email: 'Email', phone: 'Phone', social: 'Social', link: 'Link',
  file: 'File', image: 'Image', location: 'Location', note: 'Note',
}
const INPUT_KINDS = Object.keys(KIND_LABEL) as InputKind[]

const OBJECT_KINDS: OsintObject['kind'][] = ['Person', 'Company', 'Domain', 'IP', 'URL', 'File']

/** Default avatar: initials on a tinted ground, derived from the name so it is stable. */
function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  const initials = name.replace(/https?:\/\//, '').split(/[\s.@-]+/).filter(Boolean)
    .slice(0, 2).map(w => w[0]?.toUpperCase()).join('') || '?'
  return (
    <span
      style={{ width: size, height: size, fontSize: size * 0.34 }}
      className="grid shrink-0 place-items-center rounded-full border border-accent/25 bg-accent/10
        font-medium text-accent">
      {initials}
    </span>
  )
}

/* ── Toolbars ───────────────────────────────────────────────────────────── */

/** Where you are, and every step back. Always the first line of the page. */
function Breadcrumb({ trail }: { trail: { id: string | null; label: string }[] }) {
  const navigate = useNavigate()
  return (
    <nav aria-label="Object navigation" className="flex flex-wrap items-center gap-1 text-[13px]">
      {trail.map((step, i) => {
        const last = i === trail.length - 1
        return (
          <span key={step.id ?? 'root'} className="flex items-center gap-1">
            {i > 0 && <ChevronRight size={13} className="shrink-0 text-muted/60" />}
            {last ? (
              <span className="font-medium text-heading">{step.label}</span>
            ) : (
              <button onClick={() => navigate(step.id ? `/morpheus/osint/${step.id}` : '/morpheus/osint')}
                className="morph-tap rounded px-1 py-0.5 text-muted outline-none hover:bg-overlay/[0.06] hover:text-accent">
                {step.label}
              </button>
            )}
          </span>
        )
      })}
    </nav>
  )
}

/* ── Add object ─────────────────────────────────────────────────────────── */

function AddObjectModal({ onClose, parentId }: { onClose: () => void; parentId?: string }) {
  const { addObject } = useMorpheus()
  const { announce } = useFeedback()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [kind, setKind] = useState<OsintObject['kind']>('Person')

  const create = () => {
    if (!name.trim()) return
    const id = addObject(name, kind, parentId)
    announce({ tone: 'ok', title: 'Object created', detail: `${name.trim()} is in your library.` })
    onClose()
    navigate(`/morpheus/osint/${id}`)
  }

  return (
    <motion.div className="fixed inset-0 z-[80] grid place-items-center px-6"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}>
      <button aria-label="Cancel" onClick={onClose}
        className="absolute inset-0 cursor-default bg-bg/80 backdrop-blur-sm" />
      <motion.div role="dialog" aria-modal="true" aria-labelledby="add-obj"
        initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.98 }}
        transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
        className="relative w-full max-w-[420px] rounded-card border border-border bg-panel p-5 shadow-popover">
        <h2 id="add-obj" className="text-[16px] font-semibold text-heading">New object</h2>
        <p className="mt-1 text-[12.5px] text-muted">Give it a name. You can add material to it afterwards.</p>

        <label htmlFor="obj-name" className="mt-4 block text-[11px] font-medium uppercase tracking-[0.08em] text-muted">
          Name
        </label>
        <input id="obj-name" autoFocus value={name} onChange={e => setName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') create(); if (e.key === 'Escape') onClose() }}
          placeholder="Elena Vasquez, acme-robotics.com, 203.0.113.44"
          className="mt-1.5 w-full rounded-input border border-border bg-bg px-3 py-2 text-[13.5px]
            text-heading outline-none transition-colors focus:border-accent/60 focus:ring-2 focus:ring-accent/15" />

        <p className="mt-4 text-[11px] font-medium uppercase tracking-[0.08em] text-muted">Type</p>
        <div className="mt-1.5 flex flex-wrap gap-2">
          {OBJECT_KINDS.map(k => <Pill key={k} on={kind === k} onClick={() => setKind(k)}>{k}</Pill>)}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" disabled={!name.trim()} onClick={create}>Create</Btn>
        </div>
      </motion.div>
    </motion.div>
  )
}

/* ── List ───────────────────────────────────────────────────────────────── */

function ObjectRow({ o, index }: { o: OsintObject; index: number }) {
  const navigate = useNavigate()
  const { renameObject, deleteObject } = useMorpheus()
  const { announce, confirm } = useFeedback()
  const [menu, setMenu] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [val, setVal] = useState(o.name)

  const commit = () => {
    setRenaming(false)
    if (val.trim() && val.trim() !== o.name) {
      renameObject(o.id, val.trim())
      announce({ tone: 'ok', title: 'Renamed' })
    }
  }

  const remove = async () => {
    setMenu(false)
    const ok = await confirm({
      title: `Delete ${o.name}?`,
      body: 'Its raw material and compiled profile are removed, along with any objects nested under it. This cannot be undone.',
      confirmLabel: 'Delete', tone: 'danger', typeToConfirm: 'delete',
    })
    if (ok) {
      deleteObject(o.id)
      announce({ tone: 'ok', title: 'Object deleted' })
    }
  }

  return (
    <Rise delay={index * 0.03}>
      <div className="morph-lift group/row relative flex items-center gap-3.5 rounded-card border
        border-border bg-surface/60 px-4 py-3 hover:border-accent/35 hover:bg-surface/80">
        <Avatar name={o.name} />

        <button onClick={() => navigate(`/morpheus/osint/${o.id}`)}
          className="min-w-0 flex-1 text-left outline-none">
          {renaming ? (
            <input autoFocus value={val} onChange={e => setVal(e.target.value)} onBlur={commit}
              onClick={e => e.stopPropagation()}
              onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setRenaming(false) }}
              aria-label="Object name"
              className="w-full rounded-input border border-accent/50 bg-bg px-2 py-1 text-[14px]
                text-heading outline-none" />
          ) : (
            <span className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
              <span className="truncate text-[14px] font-medium text-heading">{o.name}</span>
              <span className="font-mono text-[11px] text-muted">{o.id}</span>
              <Badge>{o.kind}</Badge>
              {o.flagged && <Badge tone="warning">Flagged</Badge>}
            </span>
          )}
          <span className="mt-1 line-clamp-2 block text-[12.5px] leading-relaxed text-muted">
            {o.summary}
          </span>
        </button>

        <span className="hidden shrink-0 text-right text-[11px] tabular-nums text-muted sm:block">
          {o.inputs.length} inputs
          <span className="block">{o.built}</span>
        </span>

        <div className="relative shrink-0">
          <button onClick={() => setMenu(m => !m)} aria-haspopup="menu" aria-expanded={menu}
            aria-label={`More options for ${o.name}`}
            className="morph-tap grid h-[30px] w-[30px] place-items-center rounded-btn text-muted
              hover:bg-overlay/[0.07] hover:text-text">
            <MoreVertical size={15} />
          </button>
          {menu && (
            <>
              <button className="fixed inset-0 z-20 cursor-default" aria-hidden onClick={() => setMenu(false)} />
              <div role="menu" className="absolute right-0 top-full z-30 mt-1 w-[168px] overflow-hidden
                rounded-card border border-border bg-panel py-1.5 shadow-popover">
                <button role="menuitem" onClick={() => { setVal(o.name); setRenaming(true); setMenu(false) }}
                  className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-text
                    hover:bg-overlay/[0.07] hover:pl-4"
                  style={{ transition: 'background-color var(--t) var(--ease), padding-left var(--t) var(--ease)' }}>
                  <Pencil size={13} className="text-muted" /> Rename
                </button>
                <ActionButton onAction={remove}
                  icon={<Trash2 size={13} />}
                  className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-danger
                    hover:bg-danger/10">
                  Delete
                </ActionButton>
              </div>
            </>
          )}
        </div>
      </div>
    </Rise>
  )
}

function ObjectList() {
  const { objects, preview } = useMorpheus()
  const [query, setQuery] = useState('')
  const [kinds, setKinds] = useState<OsintObject['kind'][]>([])
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [adding, setAdding] = useState(false)

  const shown = useMemo(() => objects.filter(o => {
    if (kinds.length && !kinds.includes(o.kind)) return false
    if (!query.trim()) return true
    const q = query.toLowerCase()
    return o.name.toLowerCase().includes(q) || o.id.toLowerCase().includes(q)
      || o.summary.toLowerCase().includes(q)
  }), [objects, query, kinds])

  const toggleKind = (k: OsintObject['kind']) =>
    setKinds(p => (p.includes(k) ? p.filter(x => x !== k) : [...p, k]))

  return (
    <>
      {/* Second toolbar. Only the list has it: search and filter make no sense on one object. */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search objects" aria-label="Search objects"
            className="h-[34px] w-full rounded-btn border border-border bg-surface/70 pl-9 pr-3 text-[13px]
              text-heading outline-none transition-colors focus:border-accent/55 placeholder:text-muted/70" />
        </div>

        <div className="relative shrink-0">
          <button onClick={() => setFiltersOpen(o => !o)} aria-haspopup="menu" aria-expanded={filtersOpen}
            className={`morph-tap flex h-[34px] items-center gap-1.5 rounded-btn border px-3 text-[12.5px] ${
              kinds.length ? 'border-accent/50 bg-accent/10 text-accent'
                           : 'border-border bg-surface/70 text-muted hover:text-text'}`}>
            <SlidersHorizontal size={13} />
            Filter
            {kinds.length > 0 && (
              <span className="rounded-full bg-accent/20 px-1.5 text-[10.5px] tabular-nums">{kinds.length}</span>
            )}
          </button>
          {filtersOpen && (
            <>
              <button className="fixed inset-0 z-20 cursor-default" aria-hidden onClick={() => setFiltersOpen(false)} />
              <div role="menu" className="absolute left-0 top-full z-30 mt-1.5 w-[196px] overflow-hidden
                rounded-card border border-border bg-panel p-2 shadow-popover">
                <p className="px-1 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted">Type</p>
                <div className="flex flex-wrap gap-1.5">
                  {OBJECT_KINDS.map(k => (
                    <Pill key={k} on={kinds.includes(k)} onClick={() => toggleKind(k)}>{k}</Pill>
                  ))}
                </div>
                {kinds.length > 0 && (
                  <button onClick={() => setKinds([])}
                    className="mt-2 w-full rounded-btn px-2 py-1.5 text-left text-[12px] text-muted hover:text-text">
                    Clear
                  </button>
                )}
              </div>
            </>
          )}
        </div>

        <Btn variant="primary" size="sm" icon={<Plus size={14} />} onClick={() => setAdding(true)}
          className="h-[34px] shrink-0">
          Add object
        </Btn>
      </div>

      <div className="mt-5">
        {preview === 'failure' ? (
          <Failure what="Your object library" />
        ) : preview === 'loading' ? (
          <Skeleton rows={4} />
        ) : shown.length === 0 ? (
          <Empty icon={<ScanSearch size={19} />}
            title={objects.length ? 'Nothing matches' : 'No objects yet'}
            body={objects.length
              ? 'No object matches that search or filter.'
              : 'Create an object, then feed it whatever you have: files, emails, socials, links.'}
            action={objects.length
              ? <Btn onClick={() => { setQuery(''); setKinds([]) }}>Clear the search</Btn>
              : <Btn variant="primary" icon={<Plus size={14} />} onClick={() => setAdding(true)}>Add object</Btn>} />
        ) : (
          <div className="space-y-2">
            {shown.map((o, i) => <ObjectRow key={o.id} o={o} index={i} />)}
          </div>
        )}
      </div>

      <AnimatePresence>
        {adding && <AddObjectModal onClose={() => setAdding(false)} />}
      </AnimatePresence>
    </>
  )
}

/* ── Detail ─────────────────────────────────────────────────────────────── */

/** One raw item. The material, with when it was last touched. */
function InputRow({ item, onRemove }: { item: InputItem; onRemove: () => void }) {
  const Icon = KIND_ICON[item.kind]
  return (
    <div className="group/in flex items-start gap-3 px-4 py-2.5">
      <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-btn bg-overlay/[0.05] text-muted">
        <Icon size={13} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-baseline gap-x-2 text-[13px]">
          <span className="font-medium text-heading">{item.label}</span>
          <span className="text-[10.5px] uppercase tracking-[0.07em] text-muted/70">{KIND_LABEL[item.kind]}</span>
        </p>
        <p className="mt-0.5 break-words font-mono text-[12.5px] text-text/85">{item.value}</p>
        <p className="mt-1 flex flex-wrap items-center gap-x-2.5 text-[11px] text-muted">
          <span>{item.origin}</span>
          <span className="flex items-center gap-1"><Clock size={9} /> {item.updatedAt}</span>
        </p>
      </div>
      <button onClick={onRemove} aria-label={`Remove ${item.label}`}
        className="morph-reveal morph-tap grid h-7 w-7 shrink-0 place-items-center rounded-btn
          text-muted hover:text-danger">
        <Trash2 size={13} />
      </button>
    </div>
  )
}

function AddInput({ objectId }: { objectId: string }) {
  const { addInput } = useMorpheus()
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<InputKind>('email')
  const [label, setLabel] = useState('')
  const [value, setValue] = useState('')

  const save = () => {
    if (!value.trim()) return
    addInput(objectId, { kind, label: label.trim() || KIND_LABEL[kind], value: value.trim(), origin: 'You, added by hand' })
    setLabel(''); setValue(''); setOpen(false)
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="morph-tap flex w-full items-center gap-2 border-t border-border px-4 py-2.5
          text-left text-[12.5px] text-muted hover:bg-overlay/[0.05] hover:text-accent">
        <Plus size={14} /> Add material
      </button>
    )
  }

  return (
    <div className="space-y-2.5 border-t border-border px-4 py-3">
      <div className="flex flex-wrap gap-1.5">
        {INPUT_KINDS.map(k => <Pill key={k} on={kind === k} onClick={() => setKind(k)}>{KIND_LABEL[k]}</Pill>)}
      </div>
      <input value={label} onChange={e => setLabel(e.target.value)} placeholder={`Label (default: ${KIND_LABEL[kind]})`}
        aria-label="Label"
        className="w-full rounded-input border border-border bg-bg px-3 py-1.5 text-[13px] text-heading
          outline-none focus:border-accent/60" />
      <input autoFocus value={value} onChange={e => setValue(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setOpen(false) }}
        placeholder="Value" aria-label="Value"
        className="w-full rounded-input border border-border bg-bg px-3 py-1.5 text-[13px] text-heading
          outline-none focus:border-accent/60" />
      <div className="flex justify-end gap-2">
        <Btn variant="ghost" size="sm" onClick={() => setOpen(false)}>Cancel</Btn>
        <Btn variant="primary" size="sm" disabled={!value.trim()} onClick={save}>Add</Btn>
      </div>
    </div>
  )
}

/**
 * One compiled field, with its evidence.
 *
 * Hovering reveals the raw items it was built from. That tooltip is the difference between a
 * profile you can act on and one you have to take on faith.
 */
function ProfileRow({ objectId, field, inputs }: {
  objectId: string
  field: { id: string; label: string; value: string; from: string[]; manual?: boolean }
  inputs: InputItem[]
}) {
  const { editField } = useMorpheus()
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(field.value)
  const [showEvidence, setShowEvidence] = useState(false)

  const evidence = field.from.map(id => inputs.find(i => i.id === id)).filter(Boolean) as InputItem[]

  const commit = () => {
    setEditing(false)
    if (val.trim() && val.trim() !== field.value) editField(objectId, field.id, val.trim())
  }

  return (
    <div className="group/f flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-2.5">
      <span className="w-[120px] shrink-0 text-[12px] text-muted">{field.label}</span>

      {editing ? (
        <input autoFocus value={val} onChange={e => setVal(e.target.value)} onBlur={commit}
          onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false) }}
          aria-label={field.label}
          className="min-w-0 flex-1 rounded-input border border-accent/50 bg-bg px-2 py-1 text-[13px]
            text-heading outline-none" />
      ) : (
        <span className="relative min-w-0 flex-1">
          <button
            onMouseEnter={() => setShowEvidence(true)} onMouseLeave={() => setShowEvidence(false)}
            onFocus={() => setShowEvidence(true)} onBlur={() => setShowEvidence(false)}
            onClick={() => { setVal(field.value); setEditing(true) }}
            className={`text-left text-[13px] outline-none ${
              evidence.length ? 'text-text decoration-dotted underline-offset-4 hover:underline' : 'text-text'}`}>
            {field.value}
          </button>

          {showEvidence && evidence.length > 0 && (
            <span role="tooltip"
              className="absolute left-0 top-full z-30 mt-1.5 w-[300px] rounded-card border border-border
                bg-panel p-3 text-left shadow-popover">
              <span className="block text-[10px] font-semibold uppercase tracking-[0.1em] text-muted">
                From the raw data
              </span>
              {evidence.map(e => {
                const Icon = KIND_ICON[e.kind]
                return (
                  <span key={e.id} className="mt-2 flex items-start gap-2">
                    <Icon size={12} className="mt-0.5 shrink-0 text-accent" />
                    <span className="min-w-0">
                      <span className="block text-[12px] text-heading">{e.label}</span>
                      <span className="block break-words font-mono text-[11.5px] text-text/80">{e.value}</span>
                      <span className="block text-[10.5px] text-muted">{e.origin} · {e.updatedAt}</span>
                    </span>
                  </span>
                )
              })}
            </span>
          )}
        </span>
      )}

      {field.manual && <Badge>Written by you</Badge>}
      {!field.manual && evidence.length > 0 && (
        <span className="shrink-0 text-[10.5px] tabular-nums text-muted/70">
          {evidence.length} source{evidence.length === 1 ? '' : 's'}
        </span>
      )}
      <button onClick={() => { setVal(field.value); setEditing(true) }} aria-label={`Edit ${field.label}`}
        className="morph-reveal morph-tap grid h-6 w-6 shrink-0 place-items-center rounded text-muted
          hover:text-accent">
        <Pencil size={11} />
      </button>
    </div>
  )
}

function ObjectDetail({ object }: { object: OsintObject }) {
  const { removeInput, buildProfile } = useMorpheus()
  const { announce } = useFeedback()

  const build = useCallback(async () => {
    announce({ tone: 'info', title: 'Compiling the profile', detail: `Reading ${object.inputs.length} items of raw material.` })
    await buildProfile(object.id)
    announce({ tone: 'ok', title: 'Profile compiled', detail: 'Every line points back at its source.' })
  }, [object.id, object.inputs.length, buildProfile, announce])

  const hasProfile = object.profile.length > 0

  return (
    <div className="mt-4 grid gap-4 lg:grid-cols-2">
      {/* ── Input data ──────────────────────────────────────── */}
      <section className="min-w-0">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-[13px] font-semibold text-heading">Input data</h2>
          <span className="text-[11px] tabular-nums text-muted">{object.inputs.length} items</span>
        </div>
        <p className="mt-1 text-[12px] leading-relaxed text-muted">
          Everything raw you hold on this object. Material, not conclusions.
        </p>

        <Card className="mt-3 overflow-visible">
          {object.inputs.length === 0 ? (
            <p className="px-4 py-6 text-center text-[12.5px] text-muted">
              Nothing yet. Add a file, an address, a social handle, anything.
            </p>
          ) : (
            <div className="divide-y divide-border/60">
              {object.inputs.map(i => (
                <InputRow key={i.id} item={i} onRemove={() => removeInput(object.id, i.id)} />
              ))}
            </div>
          )}
          <AddInput objectId={object.id} />
        </Card>
      </section>

      {/* ── Profile ─────────────────────────────────────────── */}
      <section className="min-w-0">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-[13px] font-semibold text-heading">Profile</h2>
          {object.profileBuiltAt && (
            <span className="text-[11px] text-muted">built {object.profileBuiltAt}</span>
          )}
        </div>
        <p className="mt-1 text-[12px] leading-relaxed text-muted">
          The compiled picture. Hover any value to see the raw data it came from.
        </p>

        <Card className="mt-3 overflow-visible">
          {/* The subject, presented as a person rather than a record. */}
          <div className="flex items-center gap-3.5 border-b border-border px-4 py-4">
            <Avatar name={object.name} size={52} />
            <div className="min-w-0">
              <p className="truncate text-[16px] font-semibold text-heading">{object.name}</p>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[12px] text-muted">
                <span>{object.kind}</span>
                <span aria-hidden>·</span>
                <span className="font-mono">{object.id}</span>
              </p>
            </div>
          </div>

          {hasProfile ? (
            <div className="divide-y divide-border/60">
              {object.profile.map(sec => (
                <div key={sec.id}>
                  <p className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted">
                    {sec.title}
                  </p>
                  <div className="divide-y divide-border/40">
                    {sec.fields.map(f => (
                      <ProfileRow key={f.id} objectId={object.id} field={f} inputs={object.inputs} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="px-4 py-8 text-center">
              <p className="text-[13px] text-heading">No profile yet</p>
              <p className="mx-auto mt-1.5 max-w-xs text-[12.5px] leading-relaxed text-muted">
                Compile the raw material into a single picture. Every line will point back at
                the item it came from.
              </p>
            </div>
          )}

          <div className="border-t border-border p-3">
            {/* The only gradient in the app, on the only action that creates something new.
                Scarcity is what makes it read as significant rather than decorative. */}
            <ActionButton onAction={build} disabled={object.inputs.length === 0}
              icon={<Sparkles size={14} />}
              className="morph-tap morph-gradient relative flex w-full items-center justify-center gap-2
                overflow-hidden rounded-btn px-4 py-2.5 text-[13px] font-semibold text-bg outline-none
                hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-40
                disabled:hover:translate-y-0">
              {hasProfile ? 'Rebuild profile' : 'Create profile'}
            </ActionButton>
          </div>
        </Card>
      </section>
    </div>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */

export default function Osint() {
  const { objectId } = useParams()
  const { objects } = useMorpheus()

  const object = objectId ? objects.find(o => o.id === decodeURIComponent(objectId)) : undefined

  // Walk the parent chain so nested objects read as a path rather than a flat jump.
  const trail = useMemo(() => {
    const steps: { id: string | null; label: string }[] = [{ id: null, label: 'All objects' }]
    if (!object) return steps
    const chain: OsintObject[] = []
    let cur: OsintObject | undefined = object
    while (cur) {
      chain.unshift(cur)
      cur = cur.parentId ? objects.find(o => o.id === cur!.parentId) : undefined
    }
    chain.forEach(o => steps.push({ id: o.id, label: o.name }))
    return steps
  }, [object, objects])

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-7 py-6">
        <Breadcrumb trail={trail} />

        {objectId && !object ? (
          <Empty icon={<ScanSearch size={19} />} title="No such object"
            body="It may have been deleted. Go back to the library and pick another." />
        ) : object ? (
          <ObjectDetail object={object} />
        ) : (
          <ObjectList />
        )}
      </div>
    </div>
  )
}
