import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, Copy, Download, History, Maximize2, Minimize2, Network, RotateCcw,
  ZoomIn, ZoomOut, Loader2, List, FileText, Search, X, GripVertical, Crosshair, ArrowLeftRight,
  User, LayoutDashboard, Send, TerminalSquare, Plug, Cpu, Database, Brain, Workflow, Wrench,
  FolderKanban, Boxes, Globe, Server, Circle, type LucideIcon,
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
  // mermaid 11 ids look like "arch-svg-<rand>-flowchart-<nodeId>-<n>" (older mermaid was just
  // "flowchart-<nodeId>-<n>"). Match the trailing "flowchart-<id>-<n>" wherever it appears.
  const m = /flowchart-(.+?)-\d+$/.exec(el.id || '')
  return m ? m[1] : null
}

// A distinct hue per node id — gives the diagram real visual structure instead of a
// wall of identical grey boxes. Deterministic so a node keeps its colour across renders.
const NODE_PALETTE = ['#58a6ff', '#3fb950', '#d29922', '#a371f7', '#db61a2',
  '#f0883e', '#39c5cf', '#e3b341', '#7ee787', '#ff7b72', '#79c0ff', '#d2a8ff']
function hueFor(id: string): string {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return NODE_PALETTE[h % NODE_PALETTE.length]
}

// Colour every node at the mermaid level via injected classDef/class statements.
// `color:` sets the LABEL text fill too, so this fixes contrast + colour in one pass,
// before any DOM sanitising can interfere. Ids come from the parsed edges (all nodes
// in the canonical diagrams have edges); unknown ids are simply never referenced.
function colorizeSource(src: string, textColor: string): string {
  const { out, inc } = parseEdges(src)
  const ids = [...new Set<string>([...out.keys(), ...inc.keys()])]
  if (ids.length === 0) return src
  const groups = new Map<string, string[]>()
  for (const id of ids) {
    const c = hueFor(id)
    if (!groups.has(c)) groups.set(c, [])
    groups.get(c)!.push(id)
  }
  const lines: string[] = []
  let i = 0
  for (const [color, gids] of groups) {
    const cls = `ac${i++}`
    lines.push(`classDef ${cls} fill:${color}22,stroke:${color},stroke-width:1.5px,color:${textColor};`)
    lines.push(`class ${gids.join(',')} ${cls};`)
  }
  return `${src}\n${lines.join('\n')}\n`
}

// Icon per guide section, matched on the section title (which mirrors the node id).
function sectionIcon(title: string): LucideIcon {
  const t = title.toLowerCase()
  if (/owner/.test(t)) return User
  if (/mission control|\bmc\b|dashboard|web app/.test(t)) return LayoutDashboard
  if (/telegram|\btg\b/.test(t)) return Send
  if (/\bcli\b|terminal/.test(t)) return TerminalSquare
  if (/integration|connected|service/.test(t)) return Plug
  if (/model|llm|provider/.test(t)) return Cpu
  if (/sqlite|database|storage|\bfile/.test(t)) return Database
  if (/brain|memory|graph|context/.test(t)) return Brain
  if (/conductor|scheduler|\bjob|workflow/.test(t)) return Workflow
  if (/\btool|action/.test(t)) return Wrench
  if (/project|task|goal/.test(t)) return FolderKanban
  if (/engine|research|execution|explore|ceo/.test(t)) return Boxes
  if (/mcp|a2a|\bapi\b|external/.test(t)) return Globe
  if (/main|process|server/.test(t)) return Server
  return Circle
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

type TextTab = 'guide' | 'map'
type FullPane = 'diagram' | 'text' | null

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
  const [histBusy, setHistBusy] = useState(false)
  const [verBusy, setVerBusy] = useState<string>('')
  const [copyBusy, setCopyBusy] = useState(false)
  const [exportBusy, setExportBusy] = useState(false)
  const [selected, setSelected] = useState<string>('')
  const [nodeLabels, setNodeLabels] = useState<Map<string, string>>(new Map())

  const [textTab, setTextTab] = useState<TextTab>('guide')
  const [mapQuery, setMapQuery] = useState('')
  const [split, setSplit] = useState(0.62)          // left-pane share of the body width
  const [full, setFull] = useState<FullPane>(null)
  const [swapped, setSwapped] = useState(false)     // false: diagram left / text right

  const [scale, setScale] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const guideRef = useRef<HTMLDivElement | null>(null)
  const bodyRef = useRef<HTMLDivElement | null>(null)

  const edges = useMemo<EdgeGraph>(
    () => (diagram?.content ? parseEdges(diagram.content) : { out: new Map(), inc: new Map() }),
    [diagram],
  )

  // Node labels straight from the .mmd source (id[Label], id(Label), id[(Label)], …). This is
  // the source of truth we draw ourselves, so labels never depend on mermaid/DOMPurify surviving.
  const labelMap = useMemo(() => {
    const m = new Map<string, string>()
    const re = /\b([A-Za-z0-9_]+)\s*[[({]+\s*"?(.*?)"?\s*[\])}]+/g
    let x: RegExpExecArray | null
    while (diagram?.content && (x = re.exec(diagram.content))) {
      const id = x[1]
      const label = x[2].replace(/<br\s*\/?>/gi, ' ').replace(/["']/g, '').trim()
      if (label && !m.has(id)) m.set(id, label)
    }
    return m
  }, [diagram])

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
    setHistBusy(true)
    getArchitectureHistory(activeId, 10)
      .then(h => { if (alive) setHistory(h.available ? h.items : []) })
      .catch(() => { if (alive) setHistory([]) })
      .finally(() => { if (alive) setHistBusy(false) })
    return () => { alive = false }
  }, [activeId])

  // Render mermaid → sanitize → set SVG. Re-render on theme change.
  const renderMermaid = useCallback(async (content: string) => {
    setRenderError('')
    if (!content) { setSvg(''); return }
    const dark = themeIsDark()
    const textColor = dark ? '#e6edf3' : '#1f2328'
    try {
      const mermaid = await loadMermaid()
      mermaid.initialize({
        startOnLoad: false,
        // Canonical, repo-owned diagrams (not user input) → 'loose' so mermaid emits real
        // HTML labels (foreignObject), the same path Notion renders. Output is still run
        // through DOMPurify below, which keeps foreignObject/style but drops scripts.
        securityLevel: 'loose',
        theme: 'base',
        themeVariables: {
          background: 'transparent',
          primaryColor: dark ? '#1f2937' : '#eef2ff',
          primaryTextColor: textColor,
          primaryBorderColor: dark ? '#4b5563' : '#c7d2fe',
          lineColor: dark ? '#8b949e' : '#94a3b8',
          textColor,
          fontSize: '14px',
          clusterBkg: dark ? 'rgba(88,166,255,0.05)' : 'rgba(99,102,241,0.06)',
          clusterBorder: dark ? '#374151' : '#cbd5e1',
        },
        flowchart: { htmlLabels: true, useMaxWidth: true, curve: 'basis', padding: 14 },
      })
      let raw = ''
      try {
        raw = (await mermaid.render('arch-svg-' + Math.random().toString(36).slice(2), colorizeSource(content, textColor))).svg
      } catch {
        // Injected classDefs can rarely upset an edge case — fall back to the raw source.
        raw = (await mermaid.render('arch-svg-' + Math.random().toString(36).slice(2), content)).svg
      }
      // Keep foreignObject (HTML labels), its inner markup (html profile), and <style>.
      setSvg(DOMPurify.sanitize(raw, {
        USE_PROFILES: { svg: true, svgFilters: true, html: true },
        ADD_TAGS: ['foreignObject', 'style'],
        ADD_ATTR: ['xmlns', 'xmlns:xlink', 'dominant-baseline'],
      }))
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

  // After the SVG lands: colourise shapes and draw EVERY node label ourselves as native SVG
  // <text>. We do NOT trust mermaid's own labels — mermaid 11 emits them as HTML inside
  // <foreignObject>, and DOMPurify strips the XHTML namespace off the inner <div>, leaving the
  // text in the DOM but rendered as an invisible SVG element. So we remove mermaid's label and
  // paint our own from the .mmd source — deterministic, never depends on the sanitizer.
  useEffect(() => {
    const stage = stageRef.current
    if (!stage || !svg) return
    const dark = themeIsDark()
    const textFill = dark ? '#e6edf3' : '#1f2328'
    const NS = 'http://www.w3.org/2000/svg'
    const labels = new Map<string, string>()
    const handlers: Array<() => void> = []

    stage.querySelectorAll('g.node').forEach(node => {
      const id = nodeIdFromEl(node)
      const color = id ? hueFor(id) : (dark ? '#8b949e' : '#64748b')
      node.querySelectorAll<SVGElement>('rect, polygon, circle, ellipse').forEach(shape => {
        shape.style.fill = color + '22'; shape.style.stroke = color; shape.style.strokeWidth = '1.5px'
      })
      if (!id) return
      const label = (labelMap.get(id) || id).trim()
      labels.set(id, label)

      // remove mermaid's own (unreliable) label — the HTML foreignObject and any SVG <text> it
      // emitted — but never the shape. Then draw ours.
      node.querySelectorAll('foreignObject, text:not([data-arch])').forEach(n => n.remove())
      node.querySelectorAll('text[data-arch="1"]').forEach(n => n.remove())

      // find the node's box to size + centre the label
      const shape = node.querySelector('rect, polygon, circle, ellipse, path') as SVGGraphicsElement | null
      let cx = 0, cy = 0, boxW = 120
      try {
        const b = shape?.getBBox()
        if (b && b.width > 0) { cx = b.x + b.width / 2; cy = b.y + b.height / 2; boxW = b.width }
      } catch { /* getBBox can throw if not yet laid out; fall back to rect attrs below */ }
      if (boxW === 120 && shape && shape.tagName === 'rect') {
        const x = +(shape.getAttribute('x') || 0), y = +(shape.getAttribute('y') || 0)
        const w = +(shape.getAttribute('width') || 120), h = +(shape.getAttribute('height') || 36)
        cx = x + w / 2; cy = y + h / 2; boxW = w
      }

      // word-wrap to the box width
      const maxChars = Math.max(6, Math.floor(boxW / 7.2))
      const lines: string[] = []
      let cur = ''
      for (const w of label.split(/\s+/)) {
        if (cur && (cur + ' ' + w).length > maxChars) { lines.push(cur); cur = w }
        else cur = cur ? cur + ' ' + w : w
      }
      if (cur) lines.push(cur)
      const lh = 14, startY = cy - ((lines.length - 1) * lh) / 2
      const text = document.createElementNS(NS, 'text')
      text.setAttribute('data-arch', '1'); text.setAttribute('text-anchor', 'middle')
      text.setAttribute('fill', textFill)
      text.style.fill = textFill; text.style.fontSize = '13px'; text.style.fontWeight = '500'; text.style.pointerEvents = 'none'
      lines.forEach((ln, i) => {
        const tspan = document.createElementNS(NS, 'tspan')
        tspan.setAttribute('x', String(cx)); tspan.setAttribute('y', String(startY + i * lh))
        tspan.setAttribute('dominant-baseline', 'central')
        tspan.textContent = ln
        text.appendChild(tspan)
      })
      node.appendChild(text)

      ;(node as HTMLElement).style.cursor = 'pointer'
      const onClick = () => { setSelected(prev => (prev === id ? '' : id)); setTextTab('guide') }
      node.addEventListener('click', onClick)
      handlers.push(() => node.removeEventListener('click', onClick))
    })
    setNodeLabels(labels)
    return () => handlers.forEach(fn => fn())
  }, [svg, labelMap])

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
      const lit = !selected || (id && neighbors.has(id))
      ;(node as HTMLElement).style.opacity = lit ? '1' : '0.16'
      ;(node as HTMLElement).style.transition = 'opacity 160ms ease'
      // thicken the chosen node's border so a selection is obvious
      node.querySelectorAll<SVGElement>('rect, polygon, circle, ellipse').forEach(s => {
        s.style.strokeWidth = selected && id === selected ? '3px' : '1.5px'
      })
    })
    stage.querySelectorAll<SVGElement>('g.edgePaths path, path.flowchart-link, path[data-id^="L_"]').forEach(edge => {
      if (!selected) { edge.style.opacity = '1'; return }
      const ref = edge.getAttribute('data-id') || edge.id || ''
      const m = /L_([A-Za-z0-9]+)_([A-Za-z0-9]+)_/.exec(ref)
      const touches = m ? (m[1] === selected || m[2] === selected) : false
      edge.style.opacity = touches ? '1' : '0.1'
    })
    if (selected && guideRef.current) {
      const target = guideRef.current.querySelector(`[data-guide-anchor="${selected.toLowerCase()}"]`)
      target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [selected, svg, edges])

  const onWheel = (e: React.WheelEvent) => {
    setScale(s => Math.min(4, Math.max(0.3, s * (e.deltaY < 0 ? 1.1 : 0.9))))
  }
  const onDown = (e: React.MouseEvent) => { drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y } }
  const onMove = (e: React.MouseEvent) => {
    if (!drag.current) return
    setPan({ x: drag.current.px + (e.clientX - drag.current.x), y: drag.current.py + (e.clientY - drag.current.y) })
  }
  const onUp = () => { drag.current = null }
  const reset = () => { setScale(1); setPan({ x: 0, y: 0 }); setSelected('') }

  // pan the diagram so a node lands in the centre of its stage (screen-space delta,
  // which is exactly what the translate() pan applies) — clear feedback for Map clicks.
  const centerNode = useCallback((id: string) => {
    const stage = stageRef.current
    const el = stage?.querySelector(`g.node[id*="flowchart-${id}-"]`) as HTMLElement | null
    if (!stage || !el) return
    const nb = el.getBoundingClientRect(); const sb = stage.getBoundingClientRect()
    setPan(p => ({
      x: p.x + (sb.left + sb.width / 2) - (nb.left + nb.width / 2),
      y: p.y + (sb.top + sb.height / 2) - (nb.top + nb.height / 2),
    }))
  }, [])

  const selectFromMap = useCallback((id: string) => {
    const willSelect = selected !== id
    setSelected(willSelect ? id : '')
    if (willSelect) requestAnimationFrame(() => centerNode(id))
  }, [selected, centerNode])

  // draggable divider between the two panes
  const onDividerDown = (e: React.MouseEvent) => {
    e.preventDefault()
    const rect = bodyRef.current?.getBoundingClientRect()
    if (!rect) return
    const onMoveDoc = (ev: MouseEvent) => {
      const r = Math.min(0.8, Math.max(0.28, (ev.clientX - rect.left) / rect.width))
      setSplit(r)
    }
    const onUpDoc = () => {
      window.removeEventListener('mousemove', onMoveDoc)
      window.removeEventListener('mouseup', onUpDoc)
      document.body.style.userSelect = ''
    }
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', onMoveDoc)
    window.addEventListener('mouseup', onUpDoc)
  }

  const copyMermaid = async () => {
    if (!diagram?.content || copyBusy) return
    setCopyBusy(true)
    try { await navigator.clipboard.writeText(diagram.content); toast({ kind: 'success', title: 'Copied', detail: 'Mermaid source copied to clipboard' }) }
    catch { toast({ kind: 'error', title: 'Copy failed', detail: 'Clipboard is unavailable' }) }
    finally { setCopyBusy(false) }
  }
  const exportSvg = async () => {
    if (!svg || exportBusy) return
    setExportBusy(true)
    try {
      const clean = DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true }, ADD_TAGS: ['style'] })
      const blob = new Blob([clean], { type: 'image/svg+xml' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `${activeId || 'architecture'}.svg`; a.click()
      URL.revokeObjectURL(url)
      toast({ kind: 'success', title: 'Exported', detail: 'Sanitized SVG downloaded' })
    } finally { setExportBusy(false) }
  }
  const loadVersion = async (sha: string) => {
    if (verBusy) return
    setVerBusy(sha)
    try {
      const v = await getArchitectureVersion(activeId, sha)
      await renderMermaid(v.content)
      setShowHistory(false)
      toast({ kind: 'info', title: 'Historical version', detail: `Showing ${sha.slice(0, 8)} — reload the tab to return to current` })
    } catch { toast({ kind: 'error', title: 'Version unavailable', detail: 'That revision could not be loaded' }) }
    finally { setVerBusy('') }
  }

  // ── the diagram pane (one instance; fullscreen just repositions its wrapper) ─
  const diagramPane = () => (
    <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center gap-1 border-b border-border px-2 py-1.5">
        <span className="flex items-center gap-1.5 px-1 text-xs font-medium text-muted"><Network size={13} /> Diagram</span>
        <div className="ml-auto flex items-center gap-1">
          <IconBtn title="Zoom out" onClick={() => setScale(s => Math.max(0.3, s * 0.9))}><ZoomOut size={15} /></IconBtn>
          <IconBtn title="Zoom in" onClick={() => setScale(s => Math.min(4, s * 1.1))}><ZoomIn size={15} /></IconBtn>
          <IconBtn title="Reset view" onClick={reset}><RotateCcw size={15} /></IconBtn>
          <IconBtn title="Version history" onClick={() => setShowHistory(v => !v)} active={showHistory} busy={histBusy}><History size={15} /></IconBtn>
          <IconBtn title="Copy Mermaid" onClick={copyMermaid} busy={copyBusy}><Copy size={15} /></IconBtn>
          <IconBtn title="Export SVG" onClick={exportSvg} busy={exportBusy}><Download size={15} /></IconBtn>
          <IconBtn title={full === 'diagram' ? 'Exit fullscreen' : 'Fullscreen diagram'} onClick={() => setFull(full === 'diagram' ? null : 'diagram')} active={full === 'diagram'}>
            {full === 'diagram' ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </IconBtn>
        </div>
      </div>
      <div className="relative min-h-0 flex-1 overflow-hidden">
        {loading ? (
          <div className="grid h-full place-items-center text-muted"><Loader2 size={18} className="animate-spin" /></div>
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
            onWheel={onWheel} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}
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
            {histBusy ? (
              <p className="flex items-center gap-1.5 px-1 py-2 text-xs text-muted"><Loader2 size={12} className="animate-spin" /> Loading history…</p>
            ) : history.length === 0 ? (
              <p className="px-1 py-2 text-xs text-muted">No git history for this diagram.</p>
            ) : history.map(v => (
              <button key={v.sha} disabled={!!verBusy} onClick={() => loadVersion(v.sha)}
                className="block w-full rounded px-2 py-1.5 text-left text-xs hover:bg-accent/10 disabled:opacity-50">
                <span className="inline-flex items-center gap-1 font-mono text-accent">
                  {verBusy === v.sha && <Loader2 size={10} className="animate-spin" />}{v.short}
                </span>{' '}
                <span className="text-muted">{(v.date || '').slice(0, 10)}</span>
                <span className="block truncate text-fg/80">{v.subject}</span>
              </button>
            ))}
          </div>
        )}
        <div className="pointer-events-none absolute bottom-2 left-2 rounded-md border border-border bg-card/80 px-2 py-0.5 text-[10px] text-muted backdrop-blur">
          {Math.round(scale * 100)}%{selected && <> · <span className="text-accent">{nodeLabels.get(selected) || selected}</span></>}
        </div>
      </div>
    </div>
  )

  // ── the text pane: tabbed Guide / Map (reused in split view + fullscreen) ────
  const nodeList = useMemo(() => {
    const ids = new Set<string>([...edges.out.keys(), ...edges.inc.keys(), ...nodeLabels.keys()])
    const q = mapQuery.trim().toLowerCase()
    return [...ids]
      .map(id => ({
        id, label: nodeLabels.get(id) || id,
        degree: (edges.out.get(id)?.size || 0) + (edges.inc.get(id)?.size || 0),
      }))
      .filter(n => !q || n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q))
      .sort((a, b) => b.degree - a.degree || a.label.localeCompare(b.label))
  }, [edges, nodeLabels, mapQuery])

  const textPane = () => (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center gap-1 border-b border-border px-2 py-1.5">
        <TabBtn active={textTab === 'guide'} onClick={() => setTextTab('guide')}><FileText size={13} /> Guide</TabBtn>
        <TabBtn active={textTab === 'map'} onClick={() => setTextTab('map')}><List size={13} /> Map <span className="text-muted">{nodeList.length}</span></TabBtn>
        <div className="ml-auto">
          <IconBtn title={full === 'text' ? 'Exit fullscreen' : 'Fullscreen text'} onClick={() => setFull(full === 'text' ? null : 'text')} active={full === 'text'}>
            {full === 'text' ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </IconBtn>
        </div>
      </div>
      {textTab === 'guide' ? (
        <div ref={guideRef} className="min-h-0 flex-1 overflow-y-auto p-4">
          {diagram ? <GuidePanel guide={diagram.guide} selected={selected} /> : <p className="text-sm text-muted">No guide.</p>}
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <Search size={14} className="text-muted" />
            <input value={mapQuery} onChange={e => setMapQuery(e.target.value)} placeholder="Filter nodes…"
              className="w-full bg-transparent text-sm outline-none placeholder:text-muted" />
            {mapQuery && <button onClick={() => setMapQuery('')} className="text-muted hover:text-fg"><X size={14} /></button>}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {nodeList.length === 0 ? <p className="p-3 text-sm text-muted">No matching nodes.</p>
              : nodeList.map(n => (
                <button key={n.id} onClick={() => selectFromMap(n.id)}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition ${selected === n.id ? 'bg-accent/15 text-accent ring-1 ring-accent/40' : 'hover:bg-accent/5'}`}>
                  <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: hueFor(n.id) }} />
                  <span className="min-w-0 flex-1 truncate">{n.label}</span>
                  <span className="shrink-0 rounded-full border border-border px-1.5 text-[10px] text-muted">{n.degree} links</span>
                </button>
              ))}
          </div>
        </div>
      )}
    </div>
  )

  // fullscreen = the chosen pane becomes a fixed overlay; the other is hidden underneath.
  const paneClass = (pane: 'diagram' | 'text') =>
    full === pane ? 'fixed inset-3 z-50 flex min-h-0 flex-col rounded-xl bg-bg/95 shadow-2xl backdrop-blur'
      : full ? 'hidden'
        : 'flex min-h-0 min-w-0 flex-col'

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <Network size={20} className="text-accent" />
        <h1 className="text-lg font-semibold">Architecture</h1>
        <span className="rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] text-accent">v2</span>
        <div className="ml-2 flex gap-1 rounded-lg border border-border p-0.5">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveId(t.id)}
              className={`rounded-md px-3 py-1 text-sm transition ${activeId === t.id ? 'bg-accent/15 text-accent' : 'text-muted hover:text-fg'}`}>
              {t.title}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <IconBtn title={swapped ? 'Diagram → left' : 'Diagram → right'} onClick={() => setSwapped(s => !s)} active={swapped}><ArrowLeftRight size={16} /></IconBtn>
          <IconBtn title="Fit to view" onClick={() => { setScale(1); setPan({ x: 0, y: 0 }) }}><Crosshair size={16} /></IconBtn>
        </div>
      </header>

      <div ref={bodyRef} className="flex min-h-0 flex-1 items-stretch">
        {/* left pane */}
        <div className={paneClass(swapped ? 'text' : 'diagram')} style={full ? undefined : { flexBasis: `${split * 100}%` }}>
          {swapped ? textPane() : diagramPane()}
        </div>
        {/* draggable divider (only in split view) */}
        {!full && (
          <div onMouseDown={onDividerDown} title="Drag to resize"
            className="group flex w-3 shrink-0 cursor-col-resize items-center justify-center">
            <span className="flex h-10 w-1.5 items-center justify-center rounded-full bg-border transition group-hover:bg-accent">
              <GripVertical size={12} className="text-transparent group-hover:text-card" />
            </span>
          </div>
        )}
        {/* right pane */}
        <div className={paneClass(swapped ? 'diagram' : 'text')} style={full ? undefined : { flexBasis: `${(1 - split) * 100}%` }}>
          {swapped ? diagramPane() : textPane()}
        </div>
      </div>

      <p className="text-xs text-muted">
        Click a node (or a Map row) to trace its connections and jump to its guide section. Drag the divider to
        resize · <ArrowLeftRight size={11} className="inline" /> swaps sides · each pane has a fullscreen button.
        Diagrams are canonical sources under <code className="rounded bg-accent/10 px-1">docs/architecture/diagrams/</code>.
      </p>
    </div>
  )
}

function IconBtn({ children, title, onClick, active, busy }: {
  children: React.ReactNode; title: string; onClick: () => void; active?: boolean; busy?: boolean
}) {
  return (
    <button title={title} onClick={onClick} disabled={busy}
      className={`grid h-8 w-8 place-items-center rounded-md border border-border transition hover:text-accent disabled:opacity-60 ${active ? 'bg-accent/15 text-accent' : 'text-muted'}`}>
      {busy ? <Loader2 size={15} className="animate-spin" /> : children}
    </button>
  )
}

function TabBtn({ children, active, onClick }: { children: React.ReactNode; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition ${active ? 'bg-accent/15 text-accent' : 'text-muted hover:text-fg'}`}>
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

// Render the guide as a set of cards — one per `## <id>` section — each with a colour-matched
// icon header (the colour matches that node in the diagram) and its markdown body. The intro
// (text before the first `##`) renders as a lead block. Each card carries a scroll anchor so a
// node/Map click jumps to it, and the selected section is emphasised.
function GuidePanel({ guide, selected }: { guide: string; selected?: string }) {
  const sections = useMemo(() => {
    const parts: Array<{ id: string; title: string; body: string }> = []
    let cur = { id: '', title: '', body: '' }
    for (const line of guide.split('\n')) {
      const h2 = /^##\s+(.+)$/.exec(line)
      if (h2) { parts.push(cur); cur = { id: h2[1].trim(), title: h2[1].trim(), body: '' } }
      else cur.body += line + '\n'
    }
    parts.push(cur)
    return parts.filter(p => p.title || p.body.trim())
  }, [guide])

  return (
    <div className="space-y-2.5 text-sm">
      {sections.map((s, i) => {
        if (!s.id) {
          return (
            <div key={i} className="rounded-xl border border-accent/20 bg-accent/5 p-3.5 leading-relaxed">
              <MarkdownView content={s.body} />
            </div>
          )
        }
        const Icon = sectionIcon(s.title)
        const color = hueFor(s.id)
        const isSel = !!selected && s.id.toLowerCase() === selected.toLowerCase()
        return (
          <div key={i} data-guide-anchor={s.id.toLowerCase()}
            className={`scroll-mt-2 rounded-xl border p-3 transition ${isSel ? 'border-accent/60 bg-accent/5 shadow-sm' : 'border-border bg-card hover:border-overlay/20'}`}>
            <div className="mb-1.5 flex items-center gap-2">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md" style={{ background: `${color}1f`, color }}>
                <Icon size={14} />
              </span>
              <span className="text-sm font-semibold text-heading">{s.title}</span>
              {isSel && <span className="ml-auto rounded-full bg-accent/15 px-1.5 py-px text-[10px] text-accent">selected</span>}
            </div>
            <div className="leading-relaxed text-muted [&_code]:rounded [&_code]:bg-accent/10 [&_code]:px-1 [&_code]:text-accent [&_strong]:text-text">
              <MarkdownView content={s.body} />
            </div>
          </div>
        )
      })}
    </div>
  )
}
