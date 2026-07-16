import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, Copy, Download, History, Maximize2, Network, RotateCcw, ZoomIn, ZoomOut,
} from 'lucide-react'
import DOMPurify from 'dompurify'
import {
  getArchitectureConfig, getArchitectureDiagram, getArchitectureDiagrams,
  getArchitectureHistory, getArchitectureVersion,
  type ArchDiagram, type ArchDiagramMeta, type ArchVersion,
} from '../api'
import { useToast } from '../context/ToastProvider'
import MarkdownView from '../components/chat/MarkdownView'
import PageLoader from '../components/PageLoader'
import ArchitectureLegacy from './ArchitectureLegacy'

// Mermaid (~500KB) is dynamically imported so it only loads once this page mounts.
let _mermaid: Promise<typeof import('mermaid')['default']> | null = null
function loadMermaid() {
  if (!_mermaid) _mermaid = import('mermaid').then(m => m.default)
  return _mermaid
}

// Parse our OWN .mmd source into an adjacency list — far more robust than scraping mermaid's
// generated DOM ids across versions. Node ids are simple identifiers in the canonical diagrams.
type EdgeGraph = { out: Map<string, Set<string>>; inc: Map<string, Set<string>> }
const _EDGE_RE = /^([A-Za-z0-9_]+)(?:[[({].*?[\])}])?\s*(?:--+>|--+|-\.-+>?|==+>?|--[ox]|[ox]--[ox])\s*(?:\|[^|]*\|\s*)?([A-Za-z0-9_]+)/
function parseEdges(src: string): EdgeGraph {
  const out = new Map<string, Set<string>>()
  const inc = new Map<string, Set<string>>()
  for (const raw of src.split('\n')) {
    const line = raw.trim()
    if (!line || line.startsWith('%%') || line.startsWith('flowchart') || line === 'end' || line.startsWith('subgraph')) continue
    const m = _EDGE_RE.exec(line)
    if (!m) continue
    const [, a, b] = m
    if (!out.has(a)) out.set(a, new Set())
    if (!inc.has(b)) inc.set(b, new Set())
    out.get(a)!.add(b)
    inc.get(b)!.add(a)
  }
  return { out, inc }
}

function themeIsDark(): boolean {
  const attr = document.documentElement.getAttribute('data-theme')
  if (attr === 'dark') return true
  if (attr === 'light') return false
  return !!window.matchMedia?.('(prefers-color-scheme: dark)').matches
}

function nodeIdFromEl(el: Element): string | null {
  const id = el.id || ''
  const m = /^flowchart-(.+?)-\d+$/.exec(id)
  return m ? m[1] : null
}

export default function Architecture() {
  const [flagKnown, setFlagKnown] = useState(false)
  const [v2, setV2] = useState(false)

  useEffect(() => {
    let alive = true
    getArchitectureConfig()
      .then(c => { if (alive) setV2(!!c.v2_enabled) })
      .catch(() => { if (alive) setV2(false) })
      .finally(() => { if (alive) setFlagKnown(true) })
    return () => { alive = false }
  }, [])

  if (!flagKnown) return <PageLoader preset="architecture" />
  if (!v2) return <ArchitectureLegacy />
  return <ArchitectureV2 />
}

function ArchitectureV2() {
  const { toast } = useToast()
  const [tabs, setTabs] = useState<ArchDiagramMeta[]>([])
  const [activeId, setActiveId] = useState<string>('')
  const [diagram, setDiagram] = useState<ArchDiagram | null>(null)
  const [svg, setSvg] = useState<string>('')
  const [renderError, setRenderError] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [history, setHistory] = useState<ArchVersion[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [selected, setSelected] = useState<string>('')

  const [scale, setScale] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const guideRef = useRef<HTMLDivElement | null>(null)

  const edges = useMemo<EdgeGraph>(
    () => (diagram?.content ? parseEdges(diagram.content) : { out: new Map<string, Set<string>>(), inc: new Map<string, Set<string>>() }),
    [diagram],
  )

  useEffect(() => {
    let alive = true
    getArchitectureDiagrams()
      .then(list => {
        if (!alive) return
        setTabs(list.items)
        setActiveId(prev => prev || list.items[0]?.id || '')
      })
      .catch(() => { if (alive) setTabs([]) })
    return () => { alive = false }
  }, [])

  // Fetch the active diagram + its history.
  useEffect(() => {
    if (!activeId) return
    let alive = true
    setLoading(true); setSelected(''); setScale(1); setPan({ x: 0, y: 0 })
    getArchitectureDiagram(activeId)
      .then(d => { if (alive) setDiagram(d) })
      .catch(() => { if (alive) setDiagram(null) })
      .finally(() => { if (alive) setLoading(false) })
    getArchitectureHistory(activeId, 10)
      .then(h => { if (alive) setHistory(h.available ? h.items : []) })
      .catch(() => { if (alive) setHistory([]) })
    return () => { alive = false }
  }, [activeId])

  // Render mermaid → sanitize → set SVG. Re-render on theme change.
  const renderMermaid = useCallback(async (content: string) => {
    setRenderError('')
    if (!content) { setSvg(''); return }
    try {
      const mermaid = await loadMermaid()
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: themeIsDark() ? 'dark' : 'default',
        flowchart: { htmlLabels: false, useMaxWidth: true },
      })
      const { svg: raw } = await mermaid.render('arch-svg-' + Math.random().toString(36).slice(2), content)
      setSvg(DOMPurify.sanitize(raw, { USE_PROFILES: { svg: true, svgFilters: true } }))
    } catch (e) {
      setSvg(''); setRenderError((e as Error)?.message || 'Failed to render the diagram.')
    }
  }, [])

  useEffect(() => {
    if (diagram?.valid && diagram.content) void renderMermaid(diagram.content)
    else setSvg('')
  }, [diagram, renderMermaid])

  useEffect(() => {
    const obs = new MutationObserver(() => { if (diagram?.valid && diagram.content) void renderMermaid(diagram.content) })
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [diagram, renderMermaid])

  // Wire node clicks after the SVG lands in the DOM.
  useEffect(() => {
    const stage = stageRef.current
    if (!stage || !svg) return
    const nodes = Array.from(stage.querySelectorAll('g.node'))
    const handlers: Array<() => void> = []
    nodes.forEach(node => {
      const id = nodeIdFromEl(node)
      if (!id) return
      ;(node as HTMLElement).style.cursor = 'pointer'
      const onClick = () => setSelected(prev => (prev === id ? '' : id))
      node.addEventListener('click', onClick)
      handlers.push(() => node.removeEventListener('click', onClick))
    })
    return () => handlers.forEach(fn => fn())
  }, [svg])

  // Apply highlight/dim when the selection changes.
  useEffect(() => {
    const stage = stageRef.current
    if (!stage || !svg) return
    const neighbors = new Set<string>()
    if (selected) {
      neighbors.add(selected)
      edges.out.get(selected)?.forEach(n => neighbors.add(n))
      edges.inc.get(selected)?.forEach(n => neighbors.add(n))
    }
    stage.querySelectorAll('g.node').forEach(node => {
      const id = nodeIdFromEl(node)
      ;(node as HTMLElement).style.opacity = !selected || (id && neighbors.has(id)) ? '1' : '0.18'
    })
    stage.querySelectorAll<SVGElement>('path[id^="L_"], g.edgePaths path, .flowchart-link').forEach(edge => {
      if (!selected) { edge.style.opacity = '1'; return }
      const m = /^L_([A-Za-z0-9_]+)_([A-Za-z0-9_]+)_/.exec(edge.id || '')
      const touches = m ? (m[1] === selected || m[2] === selected) : false
      edge.style.opacity = touches ? '1' : '0.12'
    })
    if (selected && guideRef.current) {
      const target = guideRef.current.querySelector(`[data-guide-anchor="${selected.toLowerCase()}"]`)
      target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [selected, svg, edges])

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    setScale(s => Math.min(4, Math.max(0.3, s * (e.deltaY < 0 ? 1.1 : 0.9))))
  }
  const onDown = (e: React.MouseEvent) => { drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y } }
  const onMove = (e: React.MouseEvent) => {
    if (!drag.current) return
    setPan({ x: drag.current.px + (e.clientX - drag.current.x), y: drag.current.py + (e.clientY - drag.current.y) })
  }
  const onUp = () => { drag.current = null }
  const reset = () => { setScale(1); setPan({ x: 0, y: 0 }); setSelected('') }

  const copyMermaid = async () => {
    if (!diagram?.content) return
    try { await navigator.clipboard.writeText(diagram.content); toast({ kind: 'success', title: 'Copied', detail: 'Mermaid source copied to clipboard' }) }
    catch { toast({ kind: 'error', title: 'Copy failed', detail: 'Clipboard is unavailable' }) }
  }
  const exportSvg = () => {
    if (!svg) return
    const clean = DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true } })
    const blob = new Blob([clean], { type: 'image/svg+xml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `${activeId || 'architecture'}.svg`; a.click()
    URL.revokeObjectURL(url)
    toast({ kind: 'success', title: 'Exported', detail: 'Sanitized SVG downloaded' })
  }
  const loadVersion = async (sha: string) => {
    try {
      const v = await getArchitectureVersion(activeId, sha)
      await renderMermaid(v.content)
      setShowHistory(false)
      toast({ kind: 'info', title: 'Historical version', detail: `Showing ${sha.slice(0, 8)} — reload the tab to return to current` })
    } catch { toast({ kind: 'error', title: 'Version unavailable', detail: 'That revision could not be loaded' }) }
  }

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <Network size={20} className="text-accent" />
        <h1 className="text-lg font-semibold">Architecture</h1>
        <div className="ml-2 flex gap-1 rounded-lg border border-border p-0.5">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setActiveId(t.id)}
              className={`rounded-md px-3 py-1 text-sm transition ${activeId === t.id ? 'bg-accent/15 text-accent' : 'text-muted hover:text-fg'}`}
            >
              {t.title}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <IconBtn title="Zoom out" onClick={() => setScale(s => Math.max(0.3, s * 0.9))}><ZoomOut size={16} /></IconBtn>
          <IconBtn title="Zoom in" onClick={() => setScale(s => Math.min(4, s * 1.1))}><ZoomIn size={16} /></IconBtn>
          <IconBtn title="Reset view" onClick={reset}><RotateCcw size={16} /></IconBtn>
          <IconBtn title="Fit" onClick={() => { setScale(1); setPan({ x: 0, y: 0 }) }}><Maximize2 size={16} /></IconBtn>
          <IconBtn title="Version history" onClick={() => setShowHistory(v => !v)} active={showHistory}><History size={16} /></IconBtn>
          <IconBtn title="Copy Mermaid" onClick={copyMermaid}><Copy size={16} /></IconBtn>
          <IconBtn title="Export SVG" onClick={exportSvg}><Download size={16} /></IconBtn>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 gap-3">
        {/* diagram stage */}
        <div className="relative min-h-0 flex-1 overflow-hidden rounded-xl border border-border bg-card">
          {loading ? (
            <div className="grid h-full place-items-center text-muted">Loading diagram…</div>
          ) : !diagram ? (
            <FailurePanel title="Diagram unavailable" detail="The diagram could not be loaded." />
          ) : !diagram.valid ? (
            <FailurePanel title="Diagram failed validation" detail={diagram.reasons?.[0] || 'The source is not a safe flowchart.'} />
          ) : renderError ? (
            <FailurePanel title="Render error" detail={renderError} />
          ) : (
            <div
              ref={stageRef}
              className="h-full w-full cursor-grab active:cursor-grabbing"
              onWheel={onWheel}
              onMouseDown={onDown}
              onMouseMove={onMove}
              onMouseUp={onUp}
              onMouseLeave={onUp}
            >
              <div
                className="origin-top-left transition-transform duration-75"
                style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})` }}
                // eslint-disable-next-line react/no-danger -- sanitized with DOMPurify (svg profile) above
                dangerouslySetInnerHTML={{ __html: svg }}
              />
            </div>
          )}
          {showHistory && (
            <div className="absolute right-2 top-2 max-h-[70%] w-72 overflow-y-auto rounded-lg border border-border bg-card p-2 shadow-lg">
              <p className="mb-1 px-1 text-xs font-medium text-muted">Recent versions</p>
              {history.length === 0 ? (
                <p className="px-1 py-2 text-xs text-muted">No git history for this diagram.</p>
              ) : history.map(v => (
                <button
                  key={v.sha}
                  onClick={() => loadVersion(v.sha)}
                  className="block w-full rounded px-2 py-1.5 text-left text-xs hover:bg-accent/10"
                >
                  <span className="font-mono text-accent">{v.short}</span>{' '}
                  <span className="text-muted">{(v.date || '').slice(0, 10)}</span>
                  <span className="block truncate text-fg/80">{v.subject}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* guide */}
        <aside ref={guideRef} className="hidden w-80 min-h-0 shrink-0 overflow-y-auto rounded-xl border border-border bg-card p-4 lg:block">
          {diagram && <GuidePanel guide={diagram.guide} />}
        </aside>
      </div>
      <p className="text-xs text-muted">
        Click a node to trace its connections and jump to its guide section. Diagrams are the canonical
        repository sources under <code className="rounded bg-accent/10 px-1">docs/architecture/diagrams/</code>.
      </p>
    </div>
  )
}

function IconBtn({ children, title, onClick, active }: { children: React.ReactNode; title: string; onClick: () => void; active?: boolean }) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={`grid h-8 w-8 place-items-center rounded-md border border-border transition hover:text-accent ${active ? 'bg-accent/15 text-accent' : 'text-muted'}`}
    >
      {children}
    </button>
  )
}

function FailurePanel({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="grid h-full place-items-center p-6 text-center">
      <div>
        <AlertTriangle size={28} className="mx-auto mb-2 text-warning" />
        <p className="font-medium">{title}</p>
        <p className="mt-1 text-sm text-muted">{detail}</p>
      </div>
    </div>
  )
}

// Render the guide markdown, tagging each `## <id>` section with a scroll anchor so a node click
// can jump to it. We split on the H2 headings ourselves; each section body is rendered by MarkdownView.
function GuidePanel({ guide }: { guide: string }) {
  const sections = useMemo(() => {
    const parts: Array<{ id: string; body: string }> = []
    const lines = guide.split('\n')
    let cur: { id: string; body: string } | null = { id: '', body: '' }
    for (const line of lines) {
      const h2 = /^##\s+(.+)$/.exec(line)
      if (h2) {
        if (cur) parts.push(cur)
        cur = { id: h2[1].trim(), body: `## ${h2[1].trim()}\n` }
      } else if (cur) {
        cur.body += line + '\n'
      }
    }
    if (cur) parts.push(cur)
    return parts
  }, [guide])

  return (
    <div className="space-y-3 text-sm">
      {sections.map((s, i) => (
        <div key={i} data-guide-anchor={s.id.toLowerCase()} className="scroll-mt-2">
          <MarkdownView content={s.body} />
        </div>
      ))}
    </div>
  )
}
