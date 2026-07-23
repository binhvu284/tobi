// Safe rich-text renderer for TOBI-generated content (#23, owner: "well presented —
// paragraphs, bullet list, icons, like professional content"). The content is
// markdown-lite from our own recap/spotlight engines; we render a SMALL, SAFE subset
// — paragraphs, bullet lists, and **bold** inline — building React nodes only (we
// NEVER set raw innerHTML), so untrusted source text folded into a recap can never
// inject markup.
import { Fragment } from 'react'

function inline(text: string, keyBase: string) {
  // split on **bold** while keeping the delimiters' content
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${keyBase}-b${i}`} className="font-semibold text-text">{part.slice(2, -2)}</strong>
    }
    return <Fragment key={`${keyBase}-t${i}`}>{part}</Fragment>
  })
}

export default function RichText({ text, className = '' }: { text: string; className?: string }) {
  const lines = text.replace(/\r/g, '').split('\n')
  const blocks: React.ReactNode[] = []
  let list: string[] = []
  const flushList = () => {
    if (!list.length) return
    const items = list
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="my-1.5 space-y-1 pl-1">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-xs leading-5 text-muted">
            <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-accent/70" />
            <span className="min-w-0">{inline(item, `li-${blocks.length}-${i}`)}</span>
          </li>
        ))}
      </ul>,
    )
    list = []
  }
  lines.forEach((raw, idx) => {
    const line = raw.trim()
    if (!line) { flushList(); return }
    const bullet = line.match(/^[-*•]\s+(.*)$/)
    if (bullet) { list.push(bullet[1]); return }
    flushList()
    blocks.push(
      <p key={`p-${idx}`} className="my-1.5 text-xs leading-5 text-muted">{inline(line, `p-${idx}`)}</p>,
    )
  })
  flushList()
  return <div className={className}>{blocks}</div>
}
