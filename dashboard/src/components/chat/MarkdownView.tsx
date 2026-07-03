import { memo, useState, type ReactNode } from 'react'
import { Check, Copy, Info, AlertTriangle, CheckCircle2, XCircle, ExternalLink, FileText } from 'lucide-react'
import Chart from './Charts'
import { useReducedMotionPref } from '../../context/MotionProvider'

/**
 * Compact, dependency-free Markdown + rich-block renderer for the premium chat.
 * Supports: headings, bold/italic/inline-code, links, ordered/unordered lists,
 * fenced code (with copy), GFM pipe tables, blockquotes, hr — plus TOBI's
 * structured ```tobi:card | tobi:table | tobi:callout | tobi:keyvalue |
 * tobi:reference | tobi:status``` JSON blocks rendered as full-width components.
 *
 * Streaming-render notes: every unit below (paragraph, list, heading, code
 * block, …) is its own top-level Block with a stable index-key, rendered by a
 * `memo()`-wrapped component. While a reply is streaming, only the LAST
 * (still-growing) unit's props actually change between ticks — every earlier,
 * already-settled unit bails out of re-rendering entirely. That's what keeps a
 * long reply smooth instead of re-parsing the whole answer from scratch on
 * every token (which is what used to stall the tab on long replies) — and
 * since each unit mounts once and stays mounted, a tiny fade-in plays exactly
 * once per new paragraph/list/etc. instead of the whole tail popping in.
 */

// ── inline ────────────────────────────────────────────────────────────────────
const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(__[^_]+__)|(\*[^*]+\*)|(_[^_]+_)|(\[[^\]]+\]\([^)]+\))/g

function renderInline(text: string, keyBase = 'i'): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0, m: RegExpExecArray | null, k = 0
  INLINE.lastIndex = 0
  while ((m = INLINE.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('`')) {
      out.push(<code key={`${keyBase}${k++}`} className="rounded bg-bg/70 px-1 py-0.5 font-mono text-[0.85em] text-accent">{tok.slice(1, -1)}</code>)
    } else if (tok.startsWith('**') || tok.startsWith('__')) {
      out.push(<strong key={`${keyBase}${k++}`} className="font-semibold text-heading">{tok.slice(2, -2)}</strong>)
    } else if (tok.startsWith('[')) {
      const mm = /\[([^\]]+)\]\(([^)]+)\)/.exec(tok)!
      out.push(<a key={`${keyBase}${k++}`} href={mm[2]} target="_blank" rel="noreferrer" className="text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent">{mm[1]}</a>)
    } else {
      out.push(<em key={`${keyBase}${k++}`} className="italic">{tok.slice(1, -1)}</em>)
    }
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

// ── light, dependency-free syntax highlight ─────────────────────────────────────
const HL = /(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/)|(`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(\b\d[\d_.]*(?:e[+-]?\d+)?\b)|(\b(?:const|let|var|function|return|if|else|elif|for|while|class|import|from|export|default|def|None|True|False|null|undefined|true|false|async|await|new|try|except|catch|finally|throw|with|as|in|of|public|private|protected|static|void|interface|type|enum|struct|fn|pub|use|match|select|case|switch|break|continue|yield|lambda|self|this)\b)/g

function highlight(code: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0, m: RegExpExecArray | null, k = 0
  HL.lastIndex = 0
  while ((m = HL.exec(code))) {
    if (m.index > last) out.push(code.slice(last, m.index))
    const cls = m[1] ? 'text-muted/80 italic' : m[2] ? 'text-success' : m[3] ? 'text-warning' : 'text-purple'
    out.push(<span key={k++} className={cls}>{m[0]}</span>)
    last = m.index + m[0].length
  }
  if (last < code.length) out.push(code.slice(last))
  return out
}

// ── fade-in wrapper: plays once when a unit first mounts, stays put after ──────
function FadeIn({ children }: { children: ReactNode }) {
  const reduced = useReducedMotionPref() !== 'full'
  return <div className={reduced ? '' : 'tobi-block-in'}>{children}</div>
}

// ── code block w/ copy ──────────────────────────────────────────────────────────
const CodeBlock = memo(function CodeBlock({ code, lang }: { code: string; lang?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => { navigator.clipboard?.writeText(code).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1400) }).catch(() => {}) }
  return (
    <div className="group relative my-2 overflow-hidden rounded-lg border border-border bg-bg/60">
      {lang && <div className="border-b border-border/60 px-3 py-1 font-mono text-[10px] uppercase tracking-wide text-muted">{lang}</div>}
      <button onClick={copy} className="absolute right-2 top-2 z-10 flex items-center gap-1 rounded border border-border bg-surface/80 px-1.5 py-1 text-[10px] text-muted opacity-0 transition-opacity hover:text-accent group-hover:opacity-100">
        {copied ? <Check size={11} /> : <Copy size={11} />}{copied ? 'Copied' : 'Copy'}
      </button>
      <pre className="overflow-x-auto px-3 py-2.5 text-[12.5px] leading-relaxed"><code className="font-mono text-text">{highlight(code)}</code></pre>
    </div>
  )
})

// ── structured tobi:* blocks ────────────────────────────────────────────────────
const CALLOUT = {
  info: { icon: Info, cls: 'border-accent/30 bg-accent/5 text-accent' },
  warn: { icon: AlertTriangle, cls: 'border-warning/40 bg-warning/5 text-warning' },
  warning: { icon: AlertTriangle, cls: 'border-warning/40 bg-warning/5 text-warning' },
  success: { icon: CheckCircle2, cls: 'border-success/40 bg-success/5 text-success' },
  error: { icon: XCircle, cls: 'border-danger/40 bg-danger/5 text-danger' },
} as const

const Table = memo(function Table({ columns, rows }: { columns: string[]; rows: (string | number)[][] }) {
  return (
    <div className="my-2 overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-left text-[13px]">
        <thead><tr className="border-b border-border bg-surface/60">
          {columns.map((c, i) => <th key={i} className="px-3 py-1.5 font-semibold text-heading">{renderInline(String(c), `th${i}`)}</th>)}
        </tr></thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri} className="border-b border-border/50 last:border-0 hover:bg-surface/40">
              {r.map((cell, ci) => <td key={ci} className="px-3 py-1.5 text-text">{renderInline(String(cell ?? ''), `td${ri}-${ci}`)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
})

function KeyValue({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <div className="my-2 grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2">
      {items.map((it, i) => (
        <div key={i} className="bg-surface px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-muted">{it.label}</div>
          <div className="mt-0.5 text-sm text-text">{it.value}</div>
        </div>
      ))}
    </div>
  )
}

const TobiBlock = memo(function TobiBlock({ kind, raw }: { kind: string; raw: string }) {
  let data: any
  try { data = JSON.parse(raw) } catch { return <CodeBlock code={raw} lang={`tobi:${kind}`} /> }

  if (kind === 'chart') return <Chart raw={raw} />

  if (kind === 'table' && Array.isArray(data.columns) && Array.isArray(data.rows))
    return <Table columns={data.columns} rows={data.rows} />

  if (kind === 'keyvalue') {
    const items = Array.isArray(data.items) ? data.items
      : Object.entries(data.pairs || data).map(([label, value]) => ({ label, value }))
    return <KeyValue items={items.map((it: any) => ({ label: String(it.label), value: renderInline(String(it.value ?? ''), 'kv') }))} />
  }

  if (kind === 'callout') {
    const c = CALLOUT[(data.kind || 'info') as keyof typeof CALLOUT] || CALLOUT.info
    const Icon = c.icon
    return (
      <div className={`my-2 flex gap-2 rounded-lg border p-3 ${c.cls}`}>
        <Icon size={16} className="mt-0.5 shrink-0" />
        <div className="text-sm text-text">
          {data.title && <div className="mb-0.5 font-semibold text-heading">{data.title}</div>}
          <div className="leading-relaxed">{renderInline(String(data.body ?? data.text ?? ''), 'co')}</div>
        </div>
      </div>
    )
  }

  if (kind === 'reference') {
    const items: any[] = data.items || data.references || []
    return (
      <div className="my-2 space-y-1.5">
        {items.map((it, i) => (
          <a key={i} href={it.url || '#'} target="_blank" rel="noreferrer"
            className="flex items-start gap-2 rounded-lg border border-border bg-surface/60 px-3 py-2 transition-colors hover:border-accent/40">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent/10 text-[10px] font-bold text-accent">{i + 1}</span>
            <span className="min-w-0">
              <span className="flex items-center gap-1 text-sm font-medium text-heading">{it.title || it.url}<ExternalLink size={11} className="text-muted" /></span>
              {it.snippet && <span className="block truncate text-xs text-muted">{it.snippet}</span>}
            </span>
          </a>
        ))}
      </div>
    )
  }

  if (kind === 'status') {
    const items: any[] = data.items || [data]
    return (
      <div className="my-2 flex flex-wrap gap-2">
        {items.map((it, i) => {
          const state = (it.state || 'info') as keyof typeof CALLOUT
          const c = CALLOUT[state] || CALLOUT.info
          return <span key={i} className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${c.cls}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" />{it.label}{it.value != null && <span className="text-text">· {String(it.value)}</span>}
          </span>
        })}
      </div>
    )
  }

  // tobi:card (default)
  return (
    <div className="my-2 rounded-xl border border-border bg-surface/60 p-3.5">
      {data.title && <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-heading">{data.icon && <FileText size={14} className="text-accent" />}{data.title}</div>}
      {data.body && <div className="text-sm leading-relaxed text-text">{renderInline(String(data.body), 'cb')}</div>}
      {Array.isArray(data.items) && (
        <div className="mt-2 space-y-1">
          {data.items.map((it: any, i: number) => (
            <div key={i} className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-muted">{it.label}</span><span className="font-medium text-text">{String(it.value ?? '')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
})

// ── granular block model ────────────────────────────────────────────────────────
// Every paragraph / list / heading / table / blockquote / hr is its own Block,
// not lumped into one big markdown chunk — that's what lets each one memoize
// and fade in independently as the answer streams in.
type Block =
  | { t: 'code'; lang?: string; body: string }
  | { t: 'tobi'; kind: string; body: string }
  | { t: 'p'; text: string }
  | { t: 'h'; level: number; text: string }
  | { t: 'hr' }
  | { t: 'quote'; text: string }
  | { t: 'ul' | 'ol'; items: string[] }
  | { t: 'table'; columns: string[]; rows: string[][] }

function isTableRow(l: string) { return /^\s*\|.*\|\s*$/.test(l) }
function splitRow(l: string) { return l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim()) }

/** Walk a contiguous stretch of non-fenced lines into granular structural Blocks. */
function splitMdUnits(lines: string[]): Block[] {
  const out: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { i++; continue }

    // GFM table
    if (isTableRow(line) && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      const columns = splitRow(line); const rows: string[][] = []
      i += 2
      while (i < lines.length && isTableRow(lines[i])) { rows.push(splitRow(lines[i])); i++ }
      out.push({ t: 'table', columns, rows }); continue
    }
    // heading
    const h = /^(#{1,6})\s+(.*)$/.exec(line)
    if (h) { out.push({ t: 'h', level: h[1].length, text: h[2] }); i++; continue }
    // hr
    if (/^(\s*[-*_]){3,}\s*$/.test(line)) { out.push({ t: 'hr' }); i++; continue }
    // blockquote
    if (/^\s*>\s?/.test(line)) {
      const buf: string[] = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, '')); i++ }
      out.push({ t: 'quote', text: buf.join(' ') }); continue
    }
    // unordered list
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, '')); i++ }
      out.push({ t: 'ul', items }); continue
    }
    // ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+\.\s+/, '')); i++ }
      out.push({ t: 'ol', items }); continue
    }
    // paragraph (gather until blank/structural) — do-while guarantees at least
    // one line is always consumed, so a stray line that matches the stop-regex
    // (e.g. ```` or a fence with trailing args that the outer tokenizer didn't
    // recognize as a real fence) can never stall `i` and spin the loop forever.
    const para: string[] = []
    do {
      para.push(lines[i]); i++
    } while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*[-*]\s|\s*\d+\.\s|\s*>\s?|```)/.test(lines[i]) && !isTableRow(lines[i]))
    out.push({ t: 'p', text: para.join(' ') })
  }
  return out
}

/** Top-level tokenizer: splits fenced code/tobi blocks out, granular-splits everything else. */
function tokenize(src: string): Block[] {
  const lines = src.split('\n')
  const blocks: Block[] = []
  let md: string[] = []
  const flush = () => { if (md.length) { blocks.push(...splitMdUnits(md)); md = [] } }
  for (let i = 0; i < lines.length; i++) {
    const fence = /^```\s*([^\s`]*)\s*$/.exec(lines[i])
    if (fence) {
      flush()
      const info = fence[1] || ''
      const body: string[] = []
      i++
      while (i < lines.length && !/^```\s*$/.test(lines[i])) { body.push(lines[i]); i++ }
      if (info.startsWith('tobi:')) blocks.push({ t: 'tobi', kind: info.slice(5), body: body.join('\n') })
      else blocks.push({ t: 'code', lang: info || undefined, body: body.join('\n') })
      continue
    }
    md.push(lines[i])
  }
  flush()
  return blocks
}

// ── per-unit renderers (memoized — each bails out once its content settles) ────
const Heading = memo(function Heading({ level, text }: { level: number; text: string }) {
  const sz = level <= 1 ? 'text-lg' : level === 2 ? 'text-base' : 'text-sm'
  return <div className={`mt-3 mb-1 font-bold text-heading ${sz}`}>{renderInline(text, 'h')}</div>
})
const Hr = memo(function Hr() { return <hr className="my-3 border-border" /> })
const Quote = memo(function Quote({ text }: { text: string }) {
  return <blockquote className="my-2 border-l-2 border-accent/40 pl-3 text-sm italic text-muted">{renderInline(text, 'q')}</blockquote>
})
const Ul = memo(function Ul({ items }: { items: string[] }) {
  return <ul className="my-1.5 ml-1 space-y-1">{items.map((it, j) => (
    <li key={j} className="flex gap-2 text-sm leading-relaxed text-text"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent/70" /><span>{renderInline(it, `ul${j}`)}</span></li>
  ))}</ul>
})
const Ol = memo(function Ol({ items }: { items: string[] }) {
  return <ol className="my-1.5 ml-1 space-y-1">{items.map((it, j) => (
    <li key={j} className="flex gap-2 text-sm leading-relaxed text-text"><span className="font-mono text-xs text-accent">{j + 1}.</span><span>{renderInline(it, `ol${j}`)}</span></li>
  ))}</ol>
})
const Para = memo(function Para({ text }: { text: string }) {
  return <p className="my-1.5 text-sm leading-relaxed text-text">{renderInline(text, 'p')}</p>
})

export default function MarkdownView({ content }: { content: string }) {
  const blocks = tokenize(content || '')
  return (
    <div className="tobi-md">
      {blocks.map((b, i) => {
        switch (b.t) {
          case 'code': return <FadeIn key={i}><CodeBlock code={b.body} lang={b.lang} /></FadeIn>
          case 'tobi': return <FadeIn key={i}><TobiBlock kind={b.kind} raw={b.body} /></FadeIn>
          case 'table': return <FadeIn key={i}><Table columns={b.columns} rows={b.rows} /></FadeIn>
          case 'h': return <FadeIn key={i}><Heading level={b.level} text={b.text} /></FadeIn>
          case 'hr': return <FadeIn key={i}><Hr /></FadeIn>
          case 'quote': return <FadeIn key={i}><Quote text={b.text} /></FadeIn>
          case 'ul': return <FadeIn key={i}><Ul items={b.items} /></FadeIn>
          case 'ol': return <FadeIn key={i}><Ol items={b.items} /></FadeIn>
          default: return <FadeIn key={i}><Para text={b.text} /></FadeIn>
        }
      })}
    </div>
  )
}
