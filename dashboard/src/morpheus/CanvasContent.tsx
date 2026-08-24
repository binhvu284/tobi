// What the canvas is currently showing.
//
// The canvas frame knows nothing about its contents; this is the one place that maps a panel
// kind to a component. Adding a new kind of artifact means one case here and one entry in the
// canvas's renderer table, and every frame behaviour (dock, float, rail, resize, new tab) comes
// along for free.
import { Download, Copy, Check } from 'lucide-react'
import { useState } from 'react'
import { useCanvas, type CanvasPanel } from './MorpheusCanvas'
import { useFeedback } from './MorpheusFeedback'
import { TerminalPanel } from './MorpheusTerminal'
import MarkdownView from '../components/chat/MarkdownView'
import { Empty } from './ui'
import { FileText } from 'lucide-react'

/** A rendered document. Uses the same Markdown renderer as Chat, so the two never diverge. */
function MarkdownPanel({ panel }: { panel: CanvasPanel }) {
  const { announce } = useFeedback()
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(panel.body ?? '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch {
      announce({ tone: 'warn', title: 'Could not reach the clipboard' })
    }
  }

  const download = () => {
    const url = URL.createObjectURL(new Blob([panel.body ?? ''], { type: 'text/markdown;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = panel.title.endsWith('.md') ? panel.title : `${panel.title}.md`
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 4000)
    announce({ tone: 'ok', title: 'Saved', detail: a.download })
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-1.5 border-b border-border px-3 py-1.5">
        <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-muted">{panel.title}</span>
        <button onClick={copy} title="Copy the source" aria-label="Copy the source"
          className="morph-tap grid h-[30px] w-[30px] place-items-center rounded-btn text-muted
            hover:bg-overlay/[0.07] hover:text-accent">
          {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
        </button>
        <button onClick={download} title="Download as .md" aria-label="Download as .md"
          className="morph-tap grid h-[30px] w-[30px] place-items-center rounded-btn text-muted
            hover:bg-overlay/[0.07] hover:text-success">
          <Download size={14} />
        </button>
      </div>
      <div data-scroll className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <MarkdownView content={panel.body ?? ''} />
      </div>
    </div>
  )
}

export default function CanvasContent() {
  const { active } = useCanvas()

  if (!active) {
    return (
      <Empty icon={<FileText size={18} />} title="Nothing on the canvas"
        body="Anything Morpheus produces while it works appears here: a live console, a document, a profile." />
    )
  }

  switch (active.kind) {
    // Each terminal item carries its own shell, so the panel shows that one and no other.
    case 'terminal': return <TerminalPanel sessionId={active.sessionId} />
    case 'markdown': return <MarkdownPanel panel={active} />
    default: return null
  }
}
