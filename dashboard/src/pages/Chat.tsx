import { useEffect, useRef, useState } from 'react'
import { softFail } from '../lib/report'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Sparkles, Bot, User, ShieldAlert, Check, X, Plus, Trash2, Pencil,
  Square, RotateCcw, Copy, ChevronDown, Cpu, MessageSquarePlus,
  Paperclip, Globe, Image as ImageIcon, FileText, ThumbsUp, ThumbsDown, Activity,
  GitBranch, Plug, Layers, PanelLeftClose, PanelLeftOpen, AlertTriangle, Zap, Quote,
  Terminal, Search, Briefcase, Wrench, ShieldCheck, CheckCircle2, XCircle, ListChecks, Radio, Gauge,
  ChevronUp, MessagesSquare, ChevronRight, Pin, Youtube, Loader2, MoreVertical,
} from 'lucide-react'
import { SiGithub, SiGoogle, SiNotion, SiVercel, SiSupabase, type IconType } from '@icons-pack/react-simple-icons'
import { type ChatSession, type AvailableModel, type ChatUsage, type ChatNotice, type ChatStoredMessage, type ChatAttachment, type ChatPicker, type ReaderChip, type ChatModeId, type ContextChip, type ChatArtifactEvent, type ChatArtifact, type ChatRuntimeEvent, type ChatTurnTrace, getChatSessions, createChatSession, getChatSession, patchChatSession, deleteChatSession, appendChatMessage, streamChatSession, getLlmModels, forkChatSession, setMessageFeedback, getSessionActivity, getChatConfig, commandAgentRun, getChatTurnTrace, getSessionArtifacts, getChatArtifact } from '../api.chat'
import { type ConductorAction, confirmConductorAction } from '../api.conductor'
import { compactSession } from '../api.keys'
import { getEvolution } from '../api.abilities'
import { type PendingAction, rememberFact } from '../api.brain'
import { getIntegrations } from '../api.genesis'
import { pmListProjects } from '../api.pm'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useToast } from '../context/ToastProvider'
import { useReducedMotionPref } from '../context/MotionProvider'
import MarkdownView from '../components/chat/MarkdownView'
import TierEmblem from '../components/TierEmblem'
import ModelMenu from '../components/chat/ModelMenu'
import ProcessTrace from '../components/chat/ProcessTrace'
import PickerWizard, { type PickerAnswer } from '../components/chat/PickerWizard'
import ChatAmbient, { ChatHeroMotif } from '../components/chat/ChatAmbient'
import TerminalMode from '../components/chat/TerminalMode'

import type { TierMark, Meta, Msg, ChatMode, TurnOpts, QueuedTurn } from '../components/chat/chatTypes'
import {
  YT_RE, findYouTube, DEFAULT_STARTERS, CHAT_MODES_V2, CHAT_MODES_LEGACY, MODE_MIGRATE,
  migrateStoredMode, DEFAULT_DETAIL_PICKER, shortModel, fmtTime, fmtAbsolute, fmtRelative,
  minuteKey, COLUMN, fmtBytes, attBytes, readDataURL,
} from '../components/chat/chatUtils'
import {
  type ConnectorCatalogItem, SlackLogo, CONNECTOR_CATALOG, connectorMatches, ConnectorGlyph, ConnectorMark,
} from '../components/chat/connectorCatalog'
import { ReaderChips, TurnChips, MemoryChips } from '../components/chat/ChatChips'

export default function Chat() {
  const { toast } = useToast()
  const reduced = useReducedMotionPref() !== 'full'

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const navigate = useNavigate()
  const { sessionId: urlSid } = useParams()
  const activeId = urlSid ? Number(urlSid) : null
  const [model, setModel] = useState<string | null>(null)
  const [models, setModels] = useState<AvailableModel[]>([])
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [readerChips, setReaderChips] = useState<ReaderChip[]>([])   // YouTube reader status (#14)
  const [renaming, setRenaming] = useState<number | null>(null)
  const [renameVal, setRenameVal] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(() => { try { return localStorage.getItem('tobi.chat.sidebar') !== '0' } catch { return true } })
  const [modelIssue, setModelIssue] = useState(false)
  const [tier, setTier] = useState<TierMark | null>(null)
  const [titleEditing, setTitleEditing] = useState(false)
  const [titleVal, setTitleVal] = useState('')
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const [confirmMode, setConfirmMode] = useState<'ask' | 'auto'>(() => { try { return localStorage.getItem('tobi.chat.confirmMode') === 'auto' ? 'auto' : 'ask' } catch { return 'ask' } })
  const [autoAcceptChat, setAutoAcceptChat] = useState(false)
  const [starters, setStarters] = useState<string[]>([])
  const [slashIdx, setSlashIdx] = useState(0)
  const [atBottom, setAtBottom] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)

  // attachments / tools
  const [attachments, setAttachments] = useState<ChatAttachment[]>([])
  const [plusOpen, setPlusOpen] = useState(false)
  const [plusPanel, setPlusPanel] = useState<'connectors' | 'confirmations' | null>('connectors')
  const [webResearch, setWebResearch] = useState(() => { try { return localStorage.getItem('tobi.chat.webResearch') === '1' } catch { return false } })
  const [connectors, setConnectors] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem('tobi.chat.connectors') || '[]') } catch { return [] } })
  const [connectorOpts, setConnectorOpts] = useState<{ id: string; label: string }[]>([])
  const [thinkingStartedAt, setThinkingStartedAt] = useState(0)
  const [thinkingSteps, setThinkingSteps] = useState<string[]>([])   // accumulated checkpoint timeline
  const [editing, setEditing] = useState<number | null>(null)
  const [editVal, setEditVal] = useState('')
  const [activityOpen, setActivityOpen] = useState(false)
  const [activity, setActivity] = useState<ConductorAction[]>([])
  const [compacting, setCompacting] = useState(false)
  const [picker, setPicker] = useState<ChatPicker | null>(null)  // Feature 3 wizard
  const [dragOver, setDragOver] = useState(false)                // Feature 8 drag & drop
  const [headerCollapsed, setHeaderCollapsed] = useState(() => { try { return localStorage.getItem('tobi.chat.header') === '0' } catch { return false } })
  // #16: v2 defaults on; migrate the stored legacy mode immediately (terminal→agent, …).
  const [modeV2, setModeV2] = useState(true)
  const [mode, setMode] = useState<ChatMode>(() => { try { return migrateStoredMode(localStorage.getItem('tobi.chat.mode'), true) } catch { return 'chat' } })
  const [deepResearch, setDeepResearch] = useState(false)           // one-message DR toggle (#16 D15)
  const [contextChips, setContextChips] = useState<ContextChip[]>([])  // auto project context (D20)
  const [runPaused, setRunPaused] = useState(false)                 // failed agent step → Retry/Skip/Revise (D10)
  const [pausedRunId, setPausedRunId] = useState<number | null>(null)
  const [revisionRunId, setRevisionRunId] = useState<number | null>(null)
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null)
  const [runtimeEvents, setRuntimeEvents] = useState<ChatRuntimeEvent[]>([])
  const [turnTrace, setTurnTrace] = useState<ChatTurnTrace | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)
  const [artifactOpen, setArtifactOpen] = useState<ChatArtifact | null>(null)
  const [artifactLoading, setArtifactLoading] = useState(false)
  const [terminalLines, setTerminalLines] = useState<string[]>([])   // live run_command stdout (#11)
  const [modeOpen, setModeOpen] = useState(false)
  const [objective, setObjective] = useState('')
  const [objectiveEditing, setObjectiveEditing] = useState(false)
  const [queuedTurns, setQueuedTurns] = useState<QueuedTurn[]>([])
  const [pinnedIds, setPinnedIds] = useState<number[]>(() => {
    try {
      const raw = JSON.parse(localStorage.getItem('tobi.chat.pinned') || '[]') as number[]
      return Array.isArray(raw) ? raw.filter(Number.isFinite) : []
    } catch { return [] }
  })

  const endRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const lastTurnRef = useRef<{ text: string; opts: TurnOpts }>({ text: '', opts: {} })
  const lastMetaRef = useRef<Meta>({})
  const stepsRef = useRef<string[]>([])   // mirrors thinkingSteps for persisting into message meta
  const activeIdRef = useRef<number | null>(null)
  const queuedTurnsRef = useRef<QueuedTurn[]>([])
  // streamed deltas can arrive far faster than 60fps (small chunks back-to-back) — buffer
  // them and flush once per animation frame instead of one setMessages per chunk, or a long
  // reply turns into hundreds of full-conversation re-renders and locks up the tab.
  const deltaBufRef = useRef('')
  const deltaRafRef = useRef<number | null>(null)
  const flushDelta = () => {
    deltaRafRef.current = null
    const chunk = deltaBufRef.current
    if (!chunk) return
    deltaBufRef.current = ''
    setMessages(m => { const next = [...m]; const last = next[next.length - 1]; if (last && last.role === 'assistant') next[next.length - 1] = { ...last, content: last.content + chunk }; return next })
  }
  const fileRef = useRef<HTMLInputElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const plusRef = useRef<HTMLDivElement>(null)
  const modeRef = useRef<HTMLDivElement>(null)

  const storedToMsg = (m: ChatStoredMessage, artifactMap?: Map<number, ChatArtifact>): Msg => {
    // #16: the meta column persists mode/steps/tools/chips/artifacts across reloads
    let parsed: Meta = {}
    if (m.meta) { try { parsed = JSON.parse(m.meta) as Meta } catch { /* ignore */ } }
    if (parsed.artifact_ids?.length && artifactMap) {
      parsed.artifacts = parsed.artifact_ids
        .map(id => artifactMap.get(id))
        .filter((a): a is ChatArtifact => Boolean(a))
        .map(a => ({ id: a.id, kind: a.kind, title: a.title || 'Artifact' }))
    }
    return {
      id: m.id, role: m.role, content: m.content, model: m.model, thinking: m.thinking,
      feedback: m.feedback, created_at: m.created_at, meta: { ...parsed, tokens: m.tokens ?? undefined },
    }
  }

  useEffect(() => {
    (async () => {
      // #16 feature flag: v2 (Chat/Agent) unless the backend says otherwise; on fetch
      // failure stay v2 (default-on). Flag off → restore the stored legacy mode as-is.
      try {
        const cfg = await getChatConfig()
        setModeV2(cfg.mode_v2)
        try { setMode(migrateStoredMode(localStorage.getItem('tobi.chat.mode'), cfg.mode_v2)) } catch { /* ignore */ }
      } catch { /* ignore — default v2 */ }
      try { setModels((await getLlmModels()).models) } catch { /* ignore */ }
      try {
        const ev = await getEvolution()
        const t = ev.tiers.find(x => x.id === ev.current_tier) ?? ev.tiers[ev.current_tier]
        if (t) setTier({ tier: t.id, colorKey: t.color_key, roman: t.roman, name: t.name })
      } catch (error) { softFail('chat data')(error) }
      try {
        const r = await pmListProjects()
        const active = r.items.filter(p => p.status === 'active')
        const s: string[] = []
        active.slice(0, 2).forEach(p => s.push(`How is “${p.name}” progressing?`))
        if (r.items.length) s.push('What changed across my projects recently?')
        s.push('Give me a status report of the office.')
        if (s.length) setStarters(s.slice(0, 4))
      } catch (error) { softFail('chat data')(error) }
      try {
        const r = await getIntegrations()
        setConnectorOpts(r.integrations.filter(i => i.connected && i.category === 'tools' && !['codex', 'explore'].includes(i.id)).map(i => ({ id: i.id, label: i.label })))
      } catch (error) { softFail('chat data')(error) }
      try {
        const r = await getChatSessions()
        if (r.sessions.length === 0) { const s = await createChatSession(); setSessions([s]); navigate(`/chat/${s.id}`, { replace: true }) }
        else { setSessions(r.sessions); if (activeId == null) navigate(`/chat/${r.sessions[0].id}`, { replace: true }) }
      } catch (error) { softFail('chat data')(error) }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // URL-driven session loading: when the :sessionId param changes, load that session.
  // This lets each chat session have its own workspace tab.
  useEffect(() => {
    if (activeId == null) return
    let cancelled = false
    setPending(null); setActivityOpen(false); setModelIssue(false); setAutoAcceptChat(false); setReaderChips([])
    setMessages([]); setSending(false); setStreaming(false)
    const s = sessions.find(x => x.id === activeId)
    setModel(s?.model ?? null)
    try { setInput(localStorage.getItem(`tobi.chat.draft.${activeId}`) || '') } catch { setInput('') }
    try { setObjective(localStorage.getItem(`tobi.chat.objective.${activeId}`) || '') } catch { setObjective('') }
    setObjectiveEditing(false)
    Promise.all([
      getChatSession(activeId),
      getSessionArtifacts(activeId, 200).catch(() => ({ artifacts: [] as ChatArtifact[] })),
    ]).then(([r, artifactResult]) => {
      if (cancelled) return
      setModel(r.session.model ?? null)
      const artifactMap = new Map(artifactResult.artifacts.map(a => [a.id, a]))
      setMessages(r.messages.map(m => storedToMsg(m, artifactMap)))
    }).catch(() => { if (!cancelled) setMessages([]) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId])

  // auto-scroll only when the user is already at the bottom (P2 C: pause + Jump-to-latest)
  useEffect(() => { if (atBottomRef.current) endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, sending])
  useEffect(() => { try { localStorage.setItem('tobi.chat.sidebar', sidebarOpen ? '1' : '0') } catch { /* ignore */ } }, [sidebarOpen])
  useEffect(() => { try { localStorage.setItem('tobi.chat.confirmMode', confirmMode) } catch { /* ignore */ } }, [confirmMode])
  useEffect(() => { activeIdRef.current = activeId }, [activeId])
  useEffect(() => { try { localStorage.setItem('tobi.chat.mode', mode) } catch { /* ignore */ } }, [mode])
  useEffect(() => { try { localStorage.setItem('tobi.chat.pinned', JSON.stringify(pinnedIds)) } catch { /* ignore */ } }, [pinnedIds])
  useEffect(() => { try { localStorage.setItem('tobi.chat.webResearch', webResearch ? '1' : '0') } catch { /* ignore */ } }, [webResearch])
  useEffect(() => { try { localStorage.setItem('tobi.chat.connectors', JSON.stringify(connectors)) } catch { /* ignore */ } }, [connectors])
  useEffect(() => {
    if (!plusOpen && !modeOpen) return
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node
      if (plusOpen && plusRef.current && !plusRef.current.contains(target)) { setPlusOpen(false); setPlusPanel(null) }
      if (modeOpen && modeRef.current && !modeRef.current.contains(target)) setModeOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setPlusOpen(false); setPlusPanel(null); setModeOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [modeOpen, plusOpen])
  useEffect(() => {
    if (activeId == null) return
    try { if (objective.trim()) localStorage.setItem(`tobi.chat.objective.${activeId}`, objective); else localStorage.removeItem(`tobi.chat.objective.${activeId}`) } catch { /* ignore */ }
  }, [objective, activeId])
  useEffect(() => { if (activeId == null) return; try { if (input) localStorage.setItem(`tobi.chat.draft.${activeId}`, input); else localStorage.removeItem(`tobi.chat.draft.${activeId}`) } catch { /* ignore */ } }, [input, activeId])
  const onScroll = () => {
    const el = scrollRef.current; if (!el) return
    const bottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    atBottomRef.current = bottom; setAtBottom(bottom)
  }
  const jumpToLatest = () => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); atBottomRef.current = true; setAtBottom(true) }

  // auto-grow composer to ~200px then scroll. Guard: when the textarea isn't laid out yet
  // (session switch / route transition / hidden tab) scrollHeight reads 0 — pinning inline
  // height to that collapsed the input to nothing. Fall back to natural rows={1} height,
  // and clamp to a one-line minimum otherwise (the min-h class is the hard CSS floor).
  const autoGrow = () => {
    const el = taRef.current; if (!el) return
    el.style.height = 'auto'
    if (!el.scrollHeight) { el.style.height = ''; return }
    el.style.height = `${Math.min(Math.max(el.scrollHeight, 30), 200)}px`
  }
  useEffect(() => { autoGrow(); setSlashIdx(0) }, [input])
  // re-measure after a session switch too — input '' → '' doesn't trigger the effect above
  useEffect(() => { const t = setTimeout(autoGrow, 50); return () => clearTimeout(t) }, [activeId])

  const openSession = (id: number) => { navigate(`/chat/${id}`) }

  const refreshSessions = async () => { try { setSessions((await getChatSessions()).sessions) } catch (error) { softFail('chat data')(error) } }
  const reloadMessages = async (sid: number) => {
    try {
      const [r, artifactResult] = await Promise.all([
        getChatSession(sid),
        getSessionArtifacts(sid, 200).catch(() => ({ artifacts: [] as ChatArtifact[] })),
      ])
      const artifactMap = new Map(artifactResult.artifacts.map(a => [a.id, a]))
      setMessages(r.messages.map((m, i, arr) => {
        const msg = storedToMsg(m, artifactMap)
        if (i === arr.length - 1 && m.role === 'assistant') msg.meta = { ...msg.meta, ...lastMetaRef.current }
        return msg
      }))
    } catch { /* ignore */ }
  }

  const newSession = async () => {
    try { const s = await createChatSession(model); setSessions(p => [s, ...p]); navigate(`/chat/${s.id}`) }
    catch (e) { toast({ kind: 'error', title: 'Could not create chat', detail: (e as Error).message }) }
  }
  const removeSession = async (id: number) => {
    try {
      await deleteChatSession(id)
      setPinnedIds(p => p.filter(x => x !== id))
      const next = sessions.filter(s => s.id !== id); setSessions(next)
      if (activeId === id) { if (next.length) navigate(`/chat/${next[0].id}`); else { const s = await createChatSession(); setSessions([s]); navigate(`/chat/${s.id}`) } }
    } catch (e) { toast({ kind: 'error', title: 'Delete failed', detail: (e as Error).message }) }
  }
  const togglePin = (id: number) => setPinnedIds(p => p.includes(id) ? p.filter(x => x !== id) : [id, ...p])
  const commitRename = async (id: number) => {
    const title = renameVal.trim(); setRenaming(null); if (!title) return
    setSessions(p => p.map(s => s.id === id ? { ...s, title } : s))
    try { await patchChatSession(id, { title }) } catch (error) { softFail('chat data')(error) }
  }
  const changeModel = async (val: string) => {
    const m = val || null; setModel(m); setModelIssue(false)
    if (activeId != null) { try { await patchChatSession(activeId, { model: m ?? '' }) } catch (error) { softFail('chat data')(error) } }
  }
  const syncQueuedTurns = (next: QueuedTurn[]) => {
    queuedTurnsRef.current = next
    setQueuedTurns(next)
  }
  const pushQueuedTurn = (turn: QueuedTurn) => syncQueuedTurns([...queuedTurnsRef.current, turn])
  const shiftQueuedTurn = () => {
    const [next, ...rest] = queuedTurnsRef.current
    syncQueuedTurns(rest)
    return next
  }
  const clearQueuedTurns = () => syncQueuedTurns([])

  // ── header session-title rename (click-to-edit) ──
  const activeTitle = sessions.find(s => s.id === activeId)?.title || 'New chat'
  const pinnedSessions = pinnedIds.map(id => sessions.find(s => s.id === id)).filter(Boolean) as ChatSession[]
  const recentSessions = sessions.filter(s => !pinnedIds.includes(s.id))
  const startTitleEdit = () => { if (activeId == null) return; setTitleVal(activeTitle); setTitleEditing(true) }
  const commitHeaderTitle = async () => {
    const t = titleVal.trim(); setTitleEditing(false)
    if (!t || activeId == null || t === activeTitle) return
    setSessions(p => p.map(s => s.id === activeId ? { ...s, title: t } : s))
    try { await patchChatSession(activeId, { title: t }) } catch (error) { softFail('chat data')(error) }
  }

  // ── attachments ──
  const addFiles = async (files: File[]) => {
    const out: ChatAttachment[] = []
    for (const f of files) {
      const isImg = f.type.startsWith('image/')
      const isPdf = f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
      try {
        if (isImg || isPdf) out.push({ name: f.name, mime: f.type || (isPdf ? 'application/pdf' : 'image/png'), kind: isImg ? 'image' : 'pdf', data_url: await readDataURL(f) })
        else out.push({ name: f.name, mime: f.type || 'text/plain', kind: 'text', text: (await f.text()).slice(0, 200000) })
      } catch { /* skip unreadable */ }
    }
    if (out.length) setAttachments(a => [...a, ...out])
  }
  const onPaste = (e: React.ClipboardEvent) => {
    const imgs = Array.from(e.clipboardData.items).filter(it => it.type.startsWith('image/')).map(it => it.getAsFile()).filter(Boolean) as File[]
    if (imgs.length) { e.preventDefault(); addFiles(imgs) }
  }

  // ── turn ──
  const runTurn = async (text: string, sid: number, opts: TurnOpts) => {
    lastTurnRef.current = { text, opts }; lastMetaRef.current = {}
    const tag = opts.attachments?.length ? `  📎×${opts.attachments.length}` : ''
    setMessages(m => [...m, { role: 'user', content: text + tag }])
    setSending(true); setPending(null); setModelIssue(false)
    setContextChips([]); setRunPaused(false); setPausedRunId(null)
    setRuntimeEvents([]); setTurnTrace(null)
    // YouTube reader chip (#14): show 'reading' immediately if the message has a link;
    // the backend confirms real per-link states via a `reader` notice event.
    const ytIds = findYouTube(text)
    setReaderChips(ytIds.length ? ytIds.map(id => ({ url: `https://youtu.be/${id}`, state: 'reading' })) : [])
    setThinkingStartedAt(Date.now()); setTerminalLines([])
    setThinkingSteps([]); stepsRef.current = []
    const ac = new AbortController(); abortRef.current = ac
    let streamed = false; let toolsSeen: string[] = []
    // #16: accumulated per-turn mode metadata (echoed by the backend, folded into meta)
    let modeSeen: ChatModeId | undefined
    let contextSeen: Meta['context']
    let artifactsSeen: ChatArtifactEvent[] = []
    let memoryChipsSeen: NonNullable<Meta['memoryChips']> = []
    let turnIdSeen: string | undefined
    const pushStep = (phase: string) => {
      if (phase && stepsRef.current[stepsRef.current.length - 1] !== phase) {
        stepsRef.current = [...stepsRef.current, phase]; setThinkingSteps(stepsRef.current)
      }
    }
    const startAssistant = () => {
      if (streamed) return; streamed = true; setSending(false); setStreaming(true)
      // the tools are done; log the final action so the checkpoint list shows the full arc and
      // the orb moves off the last tool onto "Composing" while the answer streams below
      pushStep('Composing the reply…')
      setMessages(m => [...m, { role: 'assistant', content: '', meta: {} }])
    }
    try {
      await streamChatSession(sid, text, model, {
        onThinking: (phase, tools) => {
          // accumulate DISTINCT phases into a stable checkpoint timeline (don't replace)
          if (phase) pushStep(phase)
          if (tools?.length) toolsSeen = tools
        },
        onDelta: (delta) => {
          startAssistant()
          deltaBufRef.current += delta
          if (deltaRafRef.current == null) deltaRafRef.current = requestAnimationFrame(flushDelta)
        },
        // Authorization is server-side. An action event always represents a real checkpoint.
        onAction: (a) => { flushDelta(); setPending(a) },
        onPicker: (p) => { flushDelta(); setPicker(p) },
        onNotice: (n) => {
          if (n.kind === 'model_issue') setModelIssue(true)
          else if (n.kind === 'model_escalated') toast({ kind: 'info', title: 'Model escalated', detail: 'The selected model returned malformed output, so TOBI retried once with the configured fallback.' })
          else if (n.kind === 'model_fallback') {
            const route = n as ChatNotice & { from_model?: string; to_model?: string; reason?: string }
            toast({
              kind: 'info',
              title: 'Fallback model used',
              detail: `${route.from_model || 'Selected model'} failed; ${route.to_model || 'the configured fallback'} completed the turn.`,
            })
          }
          else if (n.kind === 'reader' && n.items) setReaderChips(n.items)
          else if (n.kind === 'run_paused') {
            const rid = Number((n as ChatNotice & { run_id?: number }).run_id)
            if (Number.isFinite(rid) && rid > 0) setPausedRunId(rid)
            setRunPaused(true)
          }
          else if (n.kind === 'dr_images_skipped') toast({ kind: 'info', title: 'Deep Research', detail: 'Images are skipped during research — ask about them separately.' })
        },
        onMode: (m) => { modeSeen = m.mode },
        onContext: (c) => {
          setContextChips(c.projects)
          contextSeen = { projects: c.projects, resources: c.resources }
        },
        onPlan: (p) => {
          // agent-declared plan (D9) → numbered checkpoints in the orb timeline
          pushStep(`Planned ${p.steps.length} step${p.steps.length === 1 ? '' : 's'}`)
          p.steps.slice(0, 12).forEach((s, i) => pushStep(`${i + 1}. ${s}`))
        },
        onArtifact: (a) => { artifactsSeen = [...artifactsSeen, a] },
        onMemoryChips: (e) => { memoryChipsSeen = e.chips },
        onTurnStarted: (e) => { turnIdSeen = e.turn_id; setActiveTurnId(e.turn_id) },
        onRuntimeEvent: (e) => setRuntimeEvents(prev => [...prev, e].slice(-80)),
        onRecoveryRequired: (e) => {
          const rid = Number(e.data?.run_id)
          if (Number.isFinite(rid) && rid > 0) setPausedRunId(rid)
          if (e.data?.code === 'model.malformed_output') setModelIssue(true)
          else setRunPaused(true)
        },
        onTerminal: (line) => setTerminalLines(ls => [...ls, line]),
        onReset: () => {
          // a chatty model leaked a prose preamble before a tool call → drop it, show the orb again
          if (deltaRafRef.current != null) { cancelAnimationFrame(deltaRafRef.current); deltaRafRef.current = null }
          deltaBufRef.current = ''
          // that wasn't the real reply → retract the 'Composing' checkpoint we optimistically logged
          if (stepsRef.current[stepsRef.current.length - 1] === 'Composing the reply…') {
            stepsRef.current = stepsRef.current.slice(0, -1); setThinkingSteps(stepsRef.current)
          }
          streamed = false; setStreaming(false); setSending(true)
          setMessages(m => (m.length && m[m.length - 1].role === 'assistant') ? m.slice(0, -1) : m)
        },
        onUsage: (u: ChatUsage) => {
          flushDelta()
          lastMetaRef.current = {
            elapsedMs: u.latency_ms, tokens: u.completion_tokens, tools: toolsSeen, steps: stepsRef.current,
            mode: modeSeen, context: contextSeen, artifacts: artifactsSeen.length ? artifactsSeen : undefined,
            memoryChips: memoryChipsSeen.length ? memoryChipsSeen : undefined,
            turn_id: turnIdSeen,
            requestedModel: u.requested_model,
            actualModel: u.actual_model,
            fallbackReason: u.fallback_reason,
          }
          setMessages(m => { const next = [...m]; const last = next[next.length - 1]; if (last && last.role === 'assistant') next[next.length - 1] = { ...last, meta: { ...last.meta, ...lastMetaRef.current } }; return next })
        },
      }, ac.signal, opts)
    } catch (e) {
      flushDelta()
      if ((e as Error).name !== 'AbortError') {
        const msg = `⚠️ ${(e as Error).message}`
        setMessages(m => { const next = [...m]; const last = next[next.length - 1]; if (last && last.role === 'assistant' && !last.content) { next[next.length - 1] = { ...last, content: msg }; return next } return [...next, { role: 'assistant', content: msg }] })
      }
    } finally {
      if (deltaRafRef.current != null) { cancelAnimationFrame(deltaRafRef.current); deltaRafRef.current = null }
      flushDelta()
      setSending(false); setStreaming(false); abortRef.current = null
      reloadMessages(sid); refreshSessions(); if (activityOpen) loadActivity(sid)
      const queued = activeIdRef.current === sid ? shiftQueuedTurn() : undefined
      if (queued) {
        setMode(queued.mode)
        setTimeout(() => runTurn(queued.text, sid, queued.opts), 0)
      }
    }
  }

  // #16: the baseline turn options every entry point shares (branch / starter / picker),
  // so continuations keep the active mode instead of silently demoting to chat.
  const baseOpts = (): TurnOpts => ({
    connectors,
    ...(modeV2 ? { mode: (mode === 'agent' ? 'agent' : 'chat') as ChatModeId, review_mode: reviewMode } : {}),
  })

  const send = async () => {
    let text = input.trim()
    if ((!text && !attachments.length) || activeId == null) return
    const opts: TurnOpts = {
      ...baseOpts(),
      attachments,
      web_research: webResearch || mode === 'research',
      ...(modeV2 && deepResearch ? { deep_research: true } : {}),
    }
    if (revisionRunId != null) {
      try {
        const recovery = await commandAgentRun(revisionRunId, 'revise', text)
        opts.resume_run_id = revisionRunId
        text = recovery.recovery_prompt || text
        setRevisionRunId(null)
      } catch (e) {
        toast({ kind: 'error', title: 'Could not revise run', detail: (e as Error).message })
        return
      }
    }
    // Deep Research is ONE message [D15] — reset here (covers both queue + immediate
    // paths); regenerate still replays it from lastTurnRef.opts without re-arming.
    if (deepResearch) setDeepResearch(false)
    setInput(''); setAttachments([]); setPlusOpen(false)
    try { localStorage.removeItem(`tobi.chat.draft.${activeId}`) } catch { /* ignore */ }
    if (sending || streaming) {
      pushQueuedTurn({ text, opts, mode })
      toast({ kind: 'info', title: 'Queued next turn', detail: 'TOBI will continue after this answer finishes.' })
      return
    }
    runTurn(text, activeId, opts)
  }
  const stop = () => { abortRef.current?.abort(); setSending(false); setStreaming(false) }
  const regenerate = () => {
    if (sending || streaming || activeId == null || !lastTurnRef.current.text) return
    setMessages(m => (m.length && m[m.length - 1].role === 'assistant') ? m.slice(0, -1) : m)
    setMessages(m => (m.length && m[m.length - 1].role === 'user') ? m.slice(0, -1) : m)
    runTurn(lastTurnRef.current.text, activeId, lastTurnRef.current.opts)
  }

  const recoverRun = async (command: 'resume' | 'retry_step' | 'skip_step' | 'cancel') => {
    if (pausedRunId == null || activeId == null) {
      toast({ kind: 'error', title: 'Recovery unavailable', detail: 'This older run has no resumable checkpoint.' })
      return
    }
    try {
      const result = await commandAgentRun(pausedRunId, command)
      setRunPaused(false)
      if (result.requires_turn && result.recovery_prompt) {
        await runTurn(result.recovery_prompt, activeId, { ...baseOpts(), mode: 'agent', resume_run_id: pausedRunId })
      } else if (command === 'cancel') {
        toast({ kind: 'info', title: 'Run cancelled' })
      }
    } catch (e) {
      toast({ kind: 'error', title: 'Recovery failed', detail: (e as Error).message })
    }
  }

  const reviseRun = () => {
    if (pausedRunId == null) return
    setRevisionRunId(pausedRunId)
    setRunPaused(false)
    setInput(lastTurnRef.current.text)
    setTimeout(() => taRef.current?.focus(), 0)
  }

  const loadTurnTrace = async () => {
    if (!activeTurnId) return
    setTraceLoading(true)
    try { setTurnTrace(await getChatTurnTrace(activeTurnId)) }
    catch (e) { toast({ kind: 'error', title: 'Trace unavailable', detail: (e as Error).message }) }
    finally { setTraceLoading(false) }
  }

  const openArtifact = async (artifactId: number) => {
    setArtifactLoading(true)
    try { setArtifactOpen(await getChatArtifact(artifactId)) }
    catch (e) { toast({ kind: 'error', title: 'Artifact unavailable', detail: (e as Error).message }) }
    finally { setArtifactLoading(false) }
  }

  // ── edit → branch ──
  const startEdit = (m: Msg) => { if (m.id == null) return; setEditing(m.id); setEditVal(m.content.replace(/\s*📎×\d+$/, '')) }
  const saveBranch = async () => {
    if (editing == null || activeId == null) return
    const text = editVal.trim(); const mid = editing; setEditing(null)
    if (!text) return
    try {
      const nb = await forkChatSession(activeId, mid)
      setSessions(p => [nb, ...p])
      await openSession(nb.id)
      runTurn(text, nb.id, baseOpts())
      toast({ kind: 'success', title: 'Branched', detail: 'Original chat preserved in the sidebar.' })
    } catch (e) { toast({ kind: 'error', title: 'Branch failed', detail: (e as Error).message }) }
  }

  const giveFeedback = async (m: Msg, value: number) => {
    if (m.id == null) return
    const next = m.feedback === value ? null : value
    setMessages(ms => ms.map(x => x.id === m.id ? { ...x, feedback: next } : x))
    try { await setMessageFeedback(m.id, next) } catch { /* ignore */ }
  }

  const startWith = (text: string) => { if (activeId == null || sending || streaming) return; runTurn(text, activeId, baseOpts()) }
  const quoteReply = (text: string) => {
    const snippet = text.length > 280 ? `${text.slice(0, 280)}…` : text
    const q = snippet.split('\n').map(l => `> ${l}`).join('\n')
    setInput(prev => `${q}\n\n${prev}`)
    setTimeout(() => taRef.current?.focus(), 0)
  }

  const copy = (text: string) => { navigator.clipboard?.writeText(text).then(() => toast({ kind: 'success', title: 'Copied' })).catch(() => {}) }
  const [remembering, setRemembering] = useState<number | null>(null)
  const remember = async (content: string, msgId?: number) => {
    if (msgId) setRemembering(msgId)
    try {
      const r = await rememberFact(content)
      toast({ kind: 'success', title: 'Remembered', detail: r.category ? `Saved to ${r.category}` : undefined })
    } catch (e) { toast({ kind: 'error', title: 'Could not save', detail: (e as Error).message }) }
    finally { if (msgId) setRemembering(null) }
  }

  const loadActivity = async (sid: number) => { try { setActivity((await getSessionActivity(sid)).actions) } catch (error) { softFail('chat data')(error) } }
  const toggleActivity = () => { const next = !activityOpen; setActivityOpen(next); if (next && activeId != null) loadActivity(activeId) }

  const resolveAction = async (decision: 'approve' | 'reject', action?: PendingAction) => {
    const p = action ?? pending
    if (!p) return
    setPending(null)
    const items = p.items && p.items.length ? p.items : [p]   // a batch confirms/refuses together
    const label = items.length > 1 ? `${items.length} actions` : p.summary
    if (decision === 'reject') {
      for (const it of items) { try { await confirmConductorAction(it.id, 'reject') } catch { /* ignore */ } }
      const txt = items.length > 1 ? `Very good, sir — I've cancelled all ${items.length} of those.` : `Very good, sir — I've cancelled that (${p.summary}).`
      setMessages(m => [...m, { role: 'assistant', content: txt }]); if (activeId) appendChatMessage(activeId, txt).catch(() => {})
      return
    }
    setMessages(m => [...m, { role: 'assistant', content: `On it, sir — ${label}…` }])
    try {
      let okCount = 0; let lastErr = ''
      for (const it of items) {
        try { const r = await confirmConductorAction(it.id, 'approve'); if (r.ok) okCount++; else lastErr = r.error || '' }
        catch (e) { lastErr = (e as Error).message }
      }
      const done = okCount === items.length
        ? `✓ Done, sir — ${items.length > 1 ? `all ${items.length} actions completed` : p.summary}.`
        : `⚠️ Completed ${okCount} of ${items.length}${lastErr ? ` — ${lastErr}` : ''}.`
      setMessages(m => [...m.slice(0, -1), { role: 'assistant', content: done }]); if (activeId) appendChatMessage(activeId, done).catch(softFail('chat data'))
      if (activeId && activityOpen) loadActivity(activeId)
    } catch (e) { setMessages(m => [...m.slice(0, -1), { role: 'assistant', content: `⚠️ ${(e as Error).message}` }]) }
  }

  const toggleConnector = (id: string) => setConnectors(c => c.includes(id) ? c.filter(x => x !== id) : [...c, id])
  const activeFlags = (webResearch ? 1 : 0) + connectors.length + attachments.length

  // ── picker wizard (Feature 3) — answers go back to TOBI as the owner's next message ──
  const submitPicker = (answers: PickerAnswer[]) => {
    setPicker(null)
    if (activeId == null || sending || streaming || !answers.length) return
    const body = answers.map(a => `• ${a.question} — ${a.answer}`).join('\n')
    runTurn(`Here are the details you asked for:\n${body}`, activeId, baseOpts())
  }

  // ── drag & drop image/file input (Feature 8) ──
  const onDragOver = (e: React.DragEvent) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDragOver(true) } }
  const onDragLeave = (e: React.DragEvent) => { if (e.currentTarget === e.target) setDragOver(false) }
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false)
    const files = Array.from(e.dataTransfer.files || [])
    if (files.length) addFiles(files)
  }

  // ── context energy bar + Compact ──
  const estTok = (s: string) => Math.ceil((s || '').length / 4)
  const ctxLimit = models.find(m => m.id === model)?.context || 128000
  const ctxUsed = messages.reduce((a, m) => a + (m.meta?.tokens || estTok(m.content)), 0) + 400
  const ctxPct = Math.min(100, Math.round((ctxUsed / ctxLimit) * 100))
  const ctxHot = ctxPct >= 80
  const doCompact = async () => {
    if (activeId == null || compacting || messages.length < 2) return
    setCompacting(true)
    try {
      const r = await compactSession(activeId, model)
      if (r.compacted) { await reloadMessages(activeId); toast({ kind: 'success', title: 'Compacted', detail: 'Older turns summarized; recent ones kept.' }) }
      else toast({ kind: 'info', title: 'Nothing to compact', detail: r.detail })
    } catch (e) { toast({ kind: 'error', title: 'Compact failed', detail: (e as Error).message }) }
    finally { setCompacting(false) }
  }

  const busy = sending || streaming
  const CHAT_MODES = modeV2 ? CHAT_MODES_V2 : CHAT_MODES_LEGACY   // #16 flag-gated selector
  const activeMode = CHAT_MODES.find(m => m.id === mode) ?? CHAT_MODES[0]
  const activeModel = models.find(m => m.id === model)
  const runState = sending ? 'Thinking' : streaming ? 'Streaming' : queuedTurns.length ? 'Queued' : 'Idle'
  const modePlaceholder = mode === 'research'
    ? 'Research with sources...'
    : mode === 'agent'
      ? 'Tell TOBI the outcome and constraints...'
      : mode === 'terminal'
        ? 'Describe the command or local operation you want...'
        : mode === 'project'
          ? 'Ask about a project, task, owner input, or roadmap...'
          : deepResearch ? 'Deep Research: ask your research question…'
          : 'Message TOBI...'
  const objectiveLabel = objective.trim() || 'Set objective'
  const connectorRows = [
    ...CONNECTOR_CATALOG.map(item => {
      const live = connectorOpts.find(opt => connectorMatches(item, opt))
      return { item, id: live?.id ?? item.id, label: live?.label ?? item.label, connected: !!live }
    }),
    ...connectorOpts
      .filter(opt => !CONNECTOR_CATALOG.some(item => connectorMatches(item, opt)))
      .map(opt => ({
        item: { id: opt.id, label: opt.label, desc: 'Connected tool provider', match: [opt.id], color: '#58a6ff' } as ConnectorCatalogItem,
        id: opt.id,
        label: opt.label,
        connected: true,
      })),
  ]
  const reviewMode = confirmMode === 'auto' ? 'always' : autoAcceptChat ? 'session' : 'ask'
  const setReviewMode = (v: 'ask' | 'session' | 'always') => {
    if (v === 'ask') { setConfirmMode('ask'); setAutoAcceptChat(false) }
    else if (v === 'session') { setConfirmMode('ask'); setAutoAcceptChat(true) }
    else { setConfirmMode('auto'); setAutoAcceptChat(false) }
  }
  const selectMode = (id: ChatMode) => {
    setMode(id)
    if (id === 'research') setWebResearch(true)
    setModeOpen(false)
  }

  // ── slash commands — v2 (#16): /terminal folds into Agent, /research arms Deep
  // Research for one message, /project is retired (context is automatic), /chat added ──
  const slashCmds: { cmd: string; desc: string; icon: typeof Cpu; run: () => void }[] = modeV2 ? [
    { cmd: 'model', desc: 'Switch model', icon: Cpu, run: () => setModelMenuOpen(true) },
    { cmd: 'chat', desc: 'Switch to chat mode', icon: MessageSquarePlus, run: () => setMode('chat') },
    { cmd: 'agent', desc: 'Switch to agent mode', icon: Wrench, run: () => setMode('agent') },
    { cmd: 'terminal', desc: 'Commands run in Agent mode now', icon: Terminal, run: () => { setMode('agent'); toast({ kind: 'info', title: 'Terminal → Agent', detail: 'Describe the command — the safety gate still applies.' }) } },
    { cmd: 'research', desc: deepResearch ? 'Deep Research → off' : 'Deep Research → on (next message)', icon: Search, run: () => setDeepResearch(v => !v) },
    { cmd: 'web', desc: webResearch ? 'Web research → off' : 'Web research → on', icon: Globe, run: () => setWebResearch(v => !v) },
    { cmd: 'details', desc: 'Let TOBI ask you for context', icon: Sparkles, run: () => setPicker(DEFAULT_DETAIL_PICKER) },
    { cmd: 'compact', desc: 'Summarize older turns', icon: Layers, run: () => doCompact() },
    { cmd: 'new', desc: 'Start a new chat', icon: MessageSquarePlus, run: () => newSession() },
    { cmd: 'clear', desc: 'Clear the message box', icon: X, run: () => { setInput(''); setAttachments([]) } },
  ] : [
    { cmd: 'model', desc: 'Switch model', icon: Cpu, run: () => setModelMenuOpen(true) },
    { cmd: 'agent', desc: 'Switch to agent mode', icon: Wrench, run: () => setMode('agent') },
    { cmd: 'terminal', desc: 'Switch to terminal mode', icon: Terminal, run: () => setMode('terminal') },
    { cmd: 'project', desc: 'Switch to project mode', icon: Briefcase, run: () => setMode('project') },
    { cmd: 'research', desc: webResearch ? 'Web research → off' : 'Web research → on (Hermes)', icon: Globe, run: () => setWebResearch(v => !v) },
    { cmd: 'web', desc: webResearch ? 'Web research → off' : 'Web research → on', icon: Globe, run: () => setWebResearch(v => !v) },
    { cmd: 'details', desc: 'Let TOBI ask you for context', icon: Sparkles, run: () => setPicker(DEFAULT_DETAIL_PICKER) },
    { cmd: 'compact', desc: 'Summarize older turns', icon: Layers, run: () => doCompact() },
    { cmd: 'new', desc: 'Start a new chat', icon: MessageSquarePlus, run: () => newSession() },
    { cmd: 'clear', desc: 'Clear the message box', icon: X, run: () => { setInput(''); setAttachments([]) } },
  ]
  const slashQuery = input.startsWith('/') && !/\s/.test(input) ? input.slice(1).toLowerCase() : null
  const slashMatches = slashQuery !== null ? slashCmds.filter(c => c.cmd.startsWith(slashQuery)) : []
  const slashOpen = slashQuery !== null && slashMatches.length > 0
  const runSlash = (c: { run: () => void }) => { setInput(''); setSlashIdx(0); c.run() }
  const onComposerKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (slashOpen) {
      const sel = Math.min(slashIdx, slashMatches.length - 1)
      if (e.key === 'ArrowDown') { e.preventDefault(); setSlashIdx(i => Math.min(i + 1, slashMatches.length - 1)); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSlashIdx(i => Math.max(i - 1, 0)); return }
      if (e.key === 'Tab') { e.preventDefault(); setInput(`/${slashMatches[sel].cmd} `); return }
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runSlash(slashMatches[sel]); return }
      if (e.key === 'Escape') { e.preventDefault(); setInput(''); return }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const toggleHeader = () => setHeaderCollapsed(c => { const n = !c; try { localStorage.setItem('tobi.chat.header', n ? '0' : '1') } catch { /* ignore */ } return n })

  // TOBI's avatar = his evolving tier emblem (falls back to a bot glyph until tier loads)
  const tobiMark = (size: number, state: 'normal' | 'current' = 'normal') => tier
    ? <TierEmblem tier={tier.tier} colorKey={tier.colorKey} size={size} state={state} className="shrink-0" />
    : <span className="flex shrink-0 items-center justify-center rounded-full border border-purple/30 bg-purple/10 text-purple" style={{ width: size, height: size }}><Bot size={Math.round(size * 0.5)} /></span>

  const renderSessionRow = (s: ChatSession) => {
    const pinned = pinnedIds.includes(s.id)
    return (
      <div key={s.id} className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm transition-colors ${activeId === s.id ? 'bg-accent/10 text-text' : 'text-muted hover:bg-surface/60'}`}>
        {renaming === s.id ? (
          <input autoFocus value={renameVal} onChange={e => setRenameVal(e.target.value)} onBlur={() => commitRename(s.id)}
            onKeyDown={e => { if (e.key === 'Enter') commitRename(s.id); if (e.key === 'Escape') setRenaming(null) }}
            className="w-full rounded border border-accent/40 bg-bg px-1.5 py-0.5 text-xs text-text outline-none" />
        ) : (
          <>
            <button onClick={() => openSession(s.id)} className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
              {pinned ? <Pin size={13} className="shrink-0 text-accent" /> : s.title?.startsWith('\u21b3') ? <GitBranch size={13} className="shrink-0 opacity-60" /> : <MessageSquarePlus size={13} className="shrink-0 opacity-60" />}
              <span className="truncate">{s.title || 'New chat'}</span>
            </button>
            <button onClick={() => togglePin(s.id)} title={pinned ? 'Unpin chat' : 'Pin chat'} className={`shrink-0 transition-opacity hover:text-accent ${pinned ? 'text-accent opacity-100' : 'opacity-0 group-hover:opacity-100'}`}><Pin size={11} /></button>
            <SessionMenu onRename={() => { setRenaming(s.id); setRenameVal(s.title || '') }} onDelete={() => removeSession(s.id)} />
          </>
        )}
      </div>
  )
}

// ── Session 3-dot menu (rename + delete) ─────────────────────────────────────
function SessionMenu({ onRename, onDelete }: { onRename: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc); document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div className="relative shrink-0" ref={ref}>
      <button onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        className="opacity-0 transition-opacity hover:text-text group-hover:opacity-100">
        <MoreVertical size={14} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, scale: 0.95, y: -4 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.12 }}
            onClick={e => e.stopPropagation()}
            className="absolute right-0 top-full z-50 mt-1 w-32 overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-2xl backdrop-blur-xl">
            <button onClick={() => { setOpen(false); onRename() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-text hover:bg-bg/60">
              <Pencil size={13} className="text-muted" /> Rename
            </button>
            <button onClick={() => { setOpen(false); onDelete() }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-danger hover:bg-danger/10">
              <Trash2 size={13} /> Delete
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

  return (
    <div className="relative flex h-full" onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}>
      <AnimatePresence>
        {(artifactLoading || artifactOpen) && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[180] flex items-center justify-center bg-black/60 p-3 backdrop-blur-sm sm:p-8"
            onMouseDown={(e) => { if (e.target === e.currentTarget && !artifactLoading) setArtifactOpen(null) }}>
            <motion.section initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.98 }}
              className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl">
              <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border px-4">
                <FileText size={16} className="text-success" />
                <h2 className="min-w-0 flex-1 truncate text-sm font-semibold text-text">{artifactOpen?.title || 'Loading artifact…'}</h2>
                <button onClick={() => setArtifactOpen(null)} disabled={artifactLoading} title="Close artifact"
                  className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-bg/60 hover:text-text disabled:opacity-40"><X size={16} /></button>
              </header>
              <div className="scroll-subtle overflow-y-auto p-4 sm:p-6">
                {artifactLoading ? <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={15} className="animate-spin" /> Loading…</div>
                  : <MarkdownView content={artifactOpen?.content || 'This artifact has no content.'} />}
              </div>
            </motion.section>
          </motion.div>
        )}
      </AnimatePresence>
      {/* drag & drop overlay (Feature 8) */}
      <AnimatePresence>
        {dragOver && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="pointer-events-none absolute inset-0 z-[150] flex items-center justify-center bg-accent/10 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-accent/60 bg-surface/90 px-8 py-6 text-accent shadow-2xl">
              <ImageIcon size={28} />
              <span className="text-sm font-semibold">Drop images or files to attach</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* sessions sidebar — collapsible icon rail (persisted, default open) */}
      {sidebarOpen ? (
        <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-surface/30 sm:flex">
          <div className="flex items-center justify-between px-3 py-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Chats</span>
            <div className="flex items-center gap-1">
              <button onClick={newSession} title="New chat" className="flex h-6 w-6 items-center justify-center rounded-md border border-border text-muted hover:border-accent/50 hover:text-accent"><Plus size={13} /></button>
              <button onClick={() => setSidebarOpen(false)} title="Collapse sidebar" className="flex h-6 w-6 items-center justify-center rounded-md border border-border text-muted hover:border-accent/50 hover:text-accent"><PanelLeftClose size={13} /></button>
            </div>
          </div>
          <div className="scroll-subtle flex-1 space-y-1.5 overflow-y-auto px-2 pb-3">
            {pinnedSessions.length > 0 && (
              <div className="space-y-0.5">
                <div className="px-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted/70">Pinned</div>
                {pinnedSessions.map(renderSessionRow)}
              </div>
            )}
            <div className="px-1.5 pt-1 text-[10px] font-semibold uppercase tracking-wide text-muted/70">Recent</div>
            {recentSessions.map(renderSessionRow)}
          </div>
        </aside>
      ) : (
        <aside className="hidden w-12 shrink-0 flex-col items-center gap-2 border-r border-border bg-surface/30 py-3 sm:flex">
          <button onClick={() => setSidebarOpen(true)} title="Open chats" className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted hover:border-accent/50 hover:text-accent"><PanelLeftOpen size={15} /></button>
          <button onClick={newSession} title="New chat" className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted hover:border-accent/50 hover:text-accent"><Plus size={15} /></button>
          <div className="mt-1 text-[10px] font-mono text-muted/60">{sessions.length}</div>
        </aside>
      )}

      {/* conversation */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* Per-theme ambient ornaments (#13 M2.5) — behind everything, Chat-only. */}
        <ChatAmbient />
        {/* ── collapsible HUD header — collapse control on the LEFT; closes fully ── */}
        {!headerCollapsed && (
        <div className="relative border-b border-border bg-bg/80 px-4 py-2 backdrop-blur sm:px-5">
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-accent/25 to-transparent" />
          <div className="flex min-w-0 items-center gap-2.5">
            {/* collapse — left edge, hides the header completely */}
            <button onClick={toggleHeader} title="Collapse header"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-muted transition-colors hover:border-accent/40 hover:text-accent">
              <ChevronUp size={16} />
            </button>
            <span title={tier ? `TOBI - Tier ${tier.roman} - ${tier.name}` : 'TOBI'} className="leading-none">{tobiMark(36, 'current')}</span>
            <div className="min-w-0 flex-1">
              <div className="flex min-w-0 items-center gap-2">
                {titleEditing ? (
                  <input autoFocus value={titleVal} onChange={e => setTitleVal(e.target.value)} onBlur={commitHeaderTitle}
                    onKeyDown={e => { if (e.key === 'Enter') commitHeaderTitle(); if (e.key === 'Escape') setTitleEditing(false) }}
                    className="w-64 max-w-[52vw] rounded-lg border border-accent/40 bg-bg px-2.5 py-1 text-sm font-semibold text-text outline-none" />
                ) : (
                  <button onClick={startTitleEdit} title="Click to rename"
                    className="group/title flex min-w-0 items-center gap-1.5 rounded-lg py-0.5 pr-2 transition-colors hover:text-accent">
                    <span className="truncate text-sm font-bold text-heading">{activeTitle}</span>
                    <Pencil size={11} className="shrink-0 text-muted opacity-0 transition-opacity group-hover/title:opacity-100" />
                  </button>
                )}
                <span className={`hidden items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium sm:flex ${busy ? 'border-accent/40 bg-accent/10 text-accent' : queuedTurns.length ? 'border-warning/40 bg-warning/10 text-warning' : 'border-border text-muted'}`}>
                  <Radio size={10} className={busy ? 'animate-pulse' : ''} /> {runState}
                </span>
              </div>
              <div className="mt-1 flex min-w-0 items-center gap-2">
                <activeMode.Icon size={12} className="shrink-0 text-accent" />
                {objectiveEditing ? (
                  <input autoFocus value={objective} onChange={e => setObjective(e.target.value)} onBlur={() => setObjectiveEditing(false)}
                    onKeyDown={e => { if (e.key === 'Enter') setObjectiveEditing(false); if (e.key === 'Escape') setObjectiveEditing(false) }}
                    placeholder="Set this chat's mission objective"
                    className="min-w-0 flex-1 rounded-md border border-accent/40 bg-surface px-2 py-0.5 text-xs text-text outline-none" />
                ) : (
                  <button onClick={() => setObjectiveEditing(true)} className="min-w-0 truncate text-left text-xs text-muted hover:text-text">
                    <span className="text-accent">{activeMode.label}</span>
                    <span className="mx-1.5 text-muted/50">/</span>
                    <span>{objectiveLabel}</span>
                  </button>
                )}
              </div>
            </div>

            {/* right cluster — status chips · context meter · run inspector */}
            <div className="flex shrink-0 items-center gap-2">
              {(webResearch || connectors.length > 0) && (
                <div className="hidden items-center gap-1 lg:flex">
                  {webResearch && <span className="flex items-center gap-1 rounded-full border border-accent/35 bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent"><Globe size={10} /> Web</span>}
                  {connectors.length > 0 && <span className="flex items-center gap-1 rounded-full border border-success/35 bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success"><Plug size={10} /> {connectors.length}</span>}
                </div>
              )}
              {messages.length > 1 && (
                <div className={`hidden items-center gap-2 rounded-full border bg-surface/70 px-2.5 py-1 sm:flex ${ctxHot ? 'border-warning/40' : 'border-border'}`}
                  title={`Context ~${ctxPct}% of ${(ctxLimit / 1000).toFixed(0)}K tokens`}>
                  <div className="relative h-1.5 w-14 overflow-hidden rounded-full bg-bg/60">
                    <div className={`h-full rounded-full transition-all ${ctxHot ? 'bg-warning' : 'bg-accent/60'}`} style={{ width: `${ctxPct}%` }} />
                    {compacting && <div className="absolute inset-0 animate-pulse rounded-full bg-accent/30" />}
                  </div>
                  <span className={`text-[10px] tabular-nums ${ctxHot ? 'text-warning' : 'text-muted'}`}>{ctxPct}%</span>
                  <span className="h-3 w-px bg-border" />
                  <button onClick={doCompact} disabled={compacting}
                    className={`flex items-center gap-1 text-[10px] disabled:opacity-50 ${ctxHot ? 'text-warning hover:opacity-80' : 'text-muted hover:text-accent'}`}>
                    <Layers size={11} /> {compacting ? 'Compacting…' : 'Compact'}
                  </button>
                </div>
              )}
              <button onClick={toggleActivity} title="Run inspector" className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${activityOpen ? 'border-accent/50 bg-accent/10 text-accent' : 'border-border text-muted hover:text-accent'}`}><Activity size={16} /></button>
            </div>
          </div>
        </div>
        )}

        {/* floating restore chip — chat-specific glyph, distinct from the main header's */}
        {headerCollapsed && (
          <button onClick={toggleHeader} title="Show chat header"
            className="absolute left-3 top-2 z-30 flex h-7 items-center gap-1 rounded-full border border-accent/30 bg-surface/85 px-2.5 text-muted shadow-lg backdrop-blur transition-colors hover:border-accent/50 hover:text-accent">
            <MessagesSquare size={14} className="text-accent" />
            <ChevronDown size={12} />
          </button>
        )}

        <div className="relative flex min-h-0 flex-1">
          <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
            <div className={`${COLUMN} space-y-6`}>
              {models.length === 0 && (
                <div className="mx-auto max-w-md rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-center text-xs text-muted">
                  No models configured yet. <Link to="/models" className="font-medium text-accent underline">Set up providers →</Link>
                </div>
              )}
              {messages.length === 0 && (
                <div className="relative isolate mx-auto mt-12 max-w-md text-center">
                  <ChatHeroMotif />
                  <div className="mb-3 flex justify-center">{tobiMark(46, 'current')}</div>
                  <div className="text-base font-semibold text-heading">How can I help, sir?</div>
                  <p className="mt-1 text-xs text-muted">Ask anything, attach a file, or pick a starter below.</p>
                  <div className="mt-4 flex flex-wrap justify-center gap-2">
                    {(starters.length ? starters : DEFAULT_STARTERS).map(s => (
                      <button key={s} onClick={() => startWith(s)}
                        className="rounded-full border border-border bg-surface/70 px-3 py-1.5 text-xs text-text transition-colors hover:border-accent/50 hover:text-accent">{s}</button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((m, i) => {
                const mine = m.role === 'user'; const isLast = i === messages.length - 1
                if (m.role === 'summary') return (
                  <div key={m.id ?? i} className="mx-auto max-w-lg rounded-lg border border-border bg-bg/40 px-3 py-2">
                    <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted"><Layers size={11} /> Earlier conversation compacted</div>
                    <div className="text-xs text-muted"><MarkdownView content={m.content} /></div>
                  </div>
                )
                if (mine) return (
                  <motion.div key={m.id ?? i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="group flex flex-row-reverse gap-2.5">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-accent/30 bg-accent/10 text-accent"><User size={13} /></div>
                    <div className="max-w-[80%]">
                      {editing === m.id ? (
                        <div className="rounded-2xl border border-accent/40 bg-bg p-2">
                          <textarea autoFocus value={editVal} onChange={e => setEditVal(e.target.value)} rows={2} className="w-full resize-none bg-transparent text-sm text-text outline-none" />
                          <div className="mt-1 flex justify-end gap-2">
                            <button onClick={() => setEditing(null)} className="text-[11px] text-muted hover:text-text">Cancel</button>
                            <button onClick={saveBranch} className="flex items-center gap-1 rounded border border-accent/50 bg-accent/15 px-2 py-0.5 text-[11px] text-accent hover:bg-accent/25"><GitBranch size={11} /> Save & branch</button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="rounded-2xl rounded-tr-sm border border-accent/20 bg-accent/10 px-4 py-2.5 text-[15px] text-text"><div className="whitespace-pre-wrap leading-relaxed">{m.content}</div></div>
                          {m.created_at && <div className="mt-0.5 flex justify-end"><span title={fmtAbsolute(m.created_at)} className="cursor-default text-[10px] text-muted/50">{fmtRelative(m.created_at)}</span></div>}
                          <div className="mt-1 flex justify-end gap-3 opacity-0 transition-opacity group-hover:opacity-100">
                            <button onClick={() => copy(m.content.replace(/\s*📎×\d+$/, ''))} className="flex items-center gap-1 text-[10px] text-muted hover:text-accent"><Copy size={10} /> Copy</button>
                            <button onClick={() => startWith(m.content.replace(/\s*📎×\d+$/, ''))} className="flex items-center gap-1 text-[10px] text-muted hover:text-accent"><RotateCcw size={10} /> Resend</button>
                            <button onClick={() => remember(m.content.replace(/\s*📎×\d+$/, ''), m.id)} disabled={remembering === m.id} className="flex items-center gap-1 text-[10px] text-muted hover:text-accent disabled:opacity-50">
                              {remembering === m.id ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />} Remember
                            </button>
                            {m.id != null && <button onClick={() => startEdit(m)} className="flex items-center gap-1 text-[10px] text-muted hover:text-accent"><Pencil size={10} /> Edit → branch</button>}
                          </div>
                        </>
                      )}
                    </div>
                  </motion.div>
                )
                return (
                  <motion.div key={m.id ?? i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="group flex gap-3">
                    <div className="pt-0.5">{tobiMark(28)}</div>
                    <div className="min-w-0 flex-1">
                      {/* process trace: live checkpoints while working, collapsed "Worked for Xs" once done */}
                      {isLast && busy
                        ? <ProcessTrace active steps={thinkingSteps} startedAt={thinkingStartedAt} />
                        : <ProcessTrace steps={m.meta?.steps} tools={m.meta?.tools} thinking={m.thinking} elapsedMs={m.meta?.elapsedMs} tokens={m.meta?.tokens} />}
                      {/* #16: mode / project-context / artifact chips (live for the running turn, meta afterwards) */}
                      {isLast && busy
                        ? <TurnChips mode={mode === 'agent' ? 'agent' : undefined} context={contextChips.length ? { projects: contextChips } : undefined} onOpenArtifact={openArtifact} />
                        : <TurnChips mode={m.meta?.mode} context={m.meta?.context} artifacts={m.meta?.artifacts} onOpenArtifact={openArtifact} />}
                      <div className="tobi-answer max-w-none text-[15px] leading-relaxed">
                        {m.content ? <MarkdownView content={m.content} /> : (isLast && busy ? null : <span className="text-sm text-muted">…</span>)}
                        {streaming && isLast && <span className={`ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] bg-accent align-middle ${reduced ? '' : 'chat-caret'}`} />}
                      </div>
                      {/* #20 review P1: per-memory feedback chips for this turn (empty until meta folds in) */}
                      <MemoryChips chips={m.meta?.memoryChips} turnRef={m.meta?.turn_id} />
                      {m.created_at && !(streaming && isLast) && (
                        <div className="mt-0.5"><span title={fmtAbsolute(m.created_at)} className="cursor-default text-[10px] text-muted/50">{fmtRelative(m.created_at)}</span></div>
                      )}
                      {m.content && !(streaming && isLast) && (
                        <div className="mt-1.5 flex items-center gap-3 opacity-0 transition-opacity group-hover:opacity-100">
                          <button onClick={() => copy(m.content)} className="flex items-center gap-1 text-[10px] text-muted hover:text-accent"><Copy size={10} /> Copy</button>
                          {isLast && <button onClick={regenerate} className="flex items-center gap-1 text-[10px] text-muted hover:text-accent"><RotateCcw size={10} /> Regenerate</button>}
                          <button onClick={() => quoteReply(m.content)} className="flex items-center gap-1 text-[10px] text-muted hover:text-accent"><Quote size={10} /> Quote</button>
                          <button onClick={() => remember(m.content, m.id)} disabled={remembering === m.id} className="flex items-center gap-1 text-[10px] text-muted hover:text-accent disabled:opacity-50">
                            {remembering === m.id ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />} Remember
                          </button>
                          {m.id != null && <>
                            <button onClick={() => giveFeedback(m, 1)} className={`flex items-center gap-1 text-[10px] hover:text-success ${m.feedback === 1 ? 'text-success' : 'text-muted'}`}><ThumbsUp size={10} /></button>
                            <button onClick={() => giveFeedback(m, -1)} className={`flex items-center gap-1 text-[10px] hover:text-danger ${m.feedback === -1 ? 'text-danger' : 'text-muted'}`}><ThumbsDown size={10} /></button>
                          </>}
                          {(m.model || m.meta?.tokens || m.created_at) && (
                            <span className="ml-auto flex items-center gap-1.5 font-mono text-[10px] text-muted/60">
                              {m.model && <span>{shortModel(m.model)}</span>}
                              {m.meta?.tokens ? <span>· {m.meta.tokens} tok</span> : null}
                              {m.created_at && <span>· {fmtTime(m.created_at)}</span>}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </motion.div>
                )
              })}

              {/* live process trace before the answer bubble exists (avatar-aligned so it
                  stays put when the streamed answer appears beneath it) */}
              <AnimatePresence>
                {sending && (
                  // exit is instant so the trace hands off seamlessly to the in-message trace when
                  // the streamed answer appears beneath it (no brief double "Working" panel)
                  <motion.div key="proc" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0 } }} className="flex gap-3">
                    <div className="pt-0.5">{tobiMark(28)}</div>
                    <div className="min-w-0 flex-1"><ProcessTrace active steps={thinkingSteps} startedAt={thinkingStartedAt} /></div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* #16 [D10]: a failed agent step paused the run — offer Retry / Skip / Revise */}
              {runPaused && !busy && (
                <motion.div initial={{ opacity: 0, y: reduced ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-warning/40 bg-warning/5 p-3.5">
                  <div className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-warning"><AlertTriangle size={15} /> The run paused on a failed step</div>
                  <div className="mb-3 text-[13px] text-text">TOBI stopped rather than guessing, sir — the report above says exactly what happened. How shall we proceed?</div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button onClick={() => recoverRun('retry_step')}
                      className="flex items-center gap-1.5 rounded-lg border border-warning/50 bg-warning/15 px-3 py-1.5 text-xs font-medium text-warning hover:bg-warning/25"><RotateCcw size={13} /> Retry</button>
                    <button onClick={() => recoverRun('skip_step')}
                      className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-text"><ChevronRight size={13} /> Skip</button>
                    <button onClick={reviseRun}
                      className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-text"><Pencil size={13} /> Revise</button>
                    <button onClick={() => recoverRun('cancel')}
                      className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-danger"><X size={13} /> Stop</button>
                    {activeTurnId && <button onClick={loadTurnTrace}
                      className="ml-auto flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-text"><Activity size={13} /> {traceLoading ? 'Loading…' : 'Details'}</button>}
                  </div>
                  {turnTrace && (
                    <div className="mt-3 border-t border-border/70 pt-2.5">
                      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted">
                        <span>Route: {turnTrace.route || 'legacy'}</span>
                        <span>First event: {turnTrace.first_event_ms ?? '-'}ms</span>
                        <span>First token: {turnTrace.first_token_ms ?? '-'}ms</span>
                        <span>Total: {turnTrace.total_ms ?? '-'}ms</span>
                      </div>
                      <div className="max-h-36 space-y-1 overflow-y-auto font-mono text-[10px] text-muted">
                        {turnTrace.events.map(e => <div key={e.seq} className="flex gap-2"><span className="w-5 text-right text-muted/60">{e.seq}</span><span className="w-24 text-accent">{e.stage}</span><span className="truncate">{e.event_type}</span></div>)}
                      </div>
                    </div>
                  )}
                </motion.div>
              )}

              {/* model-issue notice — one-tap switch */}
              {modelIssue && !busy && (
                <motion.div initial={{ opacity: 0, y: reduced ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-warning/40 bg-warning/5 p-3.5">
                  <div className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-warning"><AlertTriangle size={15} /> The current model is struggling</div>
                  <div className="mb-3 text-[13px] text-text">It kept returning incomplete output, sir. Switch to a stronger model and I’ll pick this straight back up.</div>
                  <div className="flex flex-wrap items-center gap-2">
                    <ModelMenu models={models} value={model} onChange={changeModel} />
                    <button onClick={() => { setModelIssue(false); pausedRunId != null ? recoverRun('retry_step') : regenerate() }} className="flex items-center gap-1.5 rounded-lg border border-warning/50 bg-warning/15 px-3 py-1.5 text-xs font-medium text-warning hover:bg-warning/25"><Zap size={13} /> Retry</button>
                  </div>
                </motion.div>
              )}

              {pending && !sending && (
                <motion.div initial={{ opacity: 0, y: reduced ? 0 : 8 }} animate={{ opacity: 1, y: 0 }} className="mx-auto w-full max-w-md rounded-xl border border-warning/40 bg-warning/5 p-3.5">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-warning"><ShieldAlert size={14} /> Confirm action{pending.items && pending.items.length > 1 ? 's' : ''} · <span className="uppercase tracking-wide">{pending.risk} risk</span></div>
                  {pending.items && pending.items.length > 1 ? (
                    <div className="mb-3">
                      <div className="mb-1.5 text-sm text-text">TOBI wants to perform <span className="font-medium">{pending.items.length} high-risk actions</span>:</div>
                      <ul className="space-y-1">
                        {pending.items.map(it => (
                          <li key={it.id} className="flex items-start gap-2 text-[13px] text-text"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warning/70" />{it.summary}</li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div className="mb-3 text-sm text-text">TOBI wants to <span className="font-medium">{pending.summary}</span>.</div>
                  )}
                  <div className="flex flex-col gap-2">
                    <div className="flex gap-2">
                      <button onClick={() => resolveAction('approve')} className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-success/50 bg-success/15 py-1.5 text-xs font-medium text-success hover:bg-success/25"><Check size={13} /> Accept</button>
                      <button onClick={() => resolveAction('reject')} className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border py-1.5 text-xs text-muted hover:text-text"><X size={13} /> Refuse</button>
                    </div>
                    <button onClick={() => { setAutoAcceptChat(true); resolveAction('approve') }}
                      className="flex items-center justify-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 py-1.5 text-[11px] font-medium text-accent hover:bg-accent/20"><Zap size={12} /> Accept &amp; auto-accept the rest of this chat</button>
                  </div>
                  <div className="mt-2 text-[10px] text-muted">Or type “yes” / “no”. Set a default in the <span className="text-text">+</span> menu → Confirmations.</div>
                </motion.div>
              )}
              <div ref={endRef} />
            </div>
          </div>

          {/* activity panel */}
          {activityOpen && (
            <aside className="hidden w-80 shrink-0 flex-col border-l border-border bg-surface/40 lg:flex">
              <div className="flex items-center justify-between border-b border-border px-3 py-3">
                <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><Gauge size={13} /> Run Inspector</span>
                <button onClick={() => setActivityOpen(false)} className="text-muted hover:text-text"><X size={13} /></button>
              </div>
              <div className="scroll-subtle flex-1 space-y-3 overflow-y-auto px-3 py-3">
                <div className="rounded-lg border border-border bg-bg/45 p-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-xs font-semibold text-heading"><activeMode.Icon size={13} className="text-accent" /> {activeMode.label}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${busy ? 'bg-accent/15 text-accent' : queuedTurns.length ? 'bg-warning/15 text-warning' : 'bg-border/60 text-muted'}`}>{runState}</span>
                  </div>
                  <div className="space-y-1.5 text-[11px] text-muted">
                    <div className="flex items-center justify-between gap-2"><span>Objective</span><span className="max-w-[170px] truncate text-right text-text">{objective.trim() || 'Unset'}</span></div>
                    <div className="flex items-center justify-between gap-2"><span>Model</span><span className="max-w-[170px] truncate text-right text-text">{activeModel ? activeModel.model : 'Auto default'}</span></div>
                    <div className="flex items-center justify-between gap-2"><span>Context</span><span className={ctxHot ? 'text-warning' : 'text-text'}>{ctxPct}% of {(ctxLimit / 1000).toFixed(0)}K</span></div>
                    <div className="flex items-center justify-between gap-2"><span>Tools</span><span className="text-text">{activeFlags || 'None'}</span></div>
                  </div>
                </div>

                {pending && (
                  <div className="rounded-lg border border-warning/40 bg-warning/5 p-3">
                    <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-warning"><ShieldAlert size={13} /> Approval waiting</div>
                    <p className="text-[12px] leading-relaxed text-text">{pending.items?.length ? `${pending.items.length} actions queued for approval` : pending.summary}</p>
                    <div className="mt-2 flex gap-2">
                      <button onClick={() => resolveAction('approve')} className="flex flex-1 items-center justify-center gap-1 rounded-md border border-success/50 bg-success/15 py-1 text-[11px] font-medium text-success hover:bg-success/25"><CheckCircle2 size={12} /> Accept</button>
                      <button onClick={() => resolveAction('reject')} className="flex flex-1 items-center justify-center gap-1 rounded-md border border-border py-1 text-[11px] text-muted hover:text-text"><XCircle size={12} /> Refuse</button>
                    </div>
                  </div>
                )}

                {queuedTurns.length > 0 && (
                  <div className="rounded-lg border border-warning/35 bg-warning/5 p-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-xs font-semibold text-warning"><ListChecks size={13} /> Queue</span>
                      <button onClick={clearQueuedTurns} className="text-[10px] text-muted hover:text-warning">Clear</button>
                    </div>
                    <div className="space-y-1.5">
                      {queuedTurns.slice(0, 3).map((q, i) => (
                        <div key={`${q.mode}-${i}`} className="rounded-md border border-border bg-bg/45 px-2 py-1.5">
                          <div className="text-[10px] uppercase tracking-wide text-muted">{CHAT_MODES.find(m => m.id === q.mode)?.label || q.mode}</div>
                          <div className="truncate text-xs text-text">{q.text}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted"><Activity size={12} /> Action History</div>
                {activity.length === 0 && <p className="px-1 text-[11px] text-muted">No actions yet in this chat.</p>}
                {(() => {
                  let lastMinKey = ''
                  return activity.map(a => {
                    const mk = minuteKey(a.created_at)
                    const showStamp = mk !== lastMinKey
                    lastMinKey = mk
                    return (
                      <div key={a.id}>
                        {showStamp && a.created_at && (
                          <div className="px-1 py-0.5 text-[9px] text-muted/50">{fmtTime(a.created_at)}</div>
                        )}
                        <div className="rounded-lg border border-border bg-bg/40 px-2.5 py-1.5">
                          <div className="flex items-center justify-between gap-1">
                            <span className="truncate text-xs text-text">{a.summary}</span>
                            <span className={`shrink-0 rounded px-1 py-0.5 text-[9px] uppercase ${a.status === 'executed' ? 'bg-success/15 text-success' : a.status === 'failed' ? 'bg-danger/15 text-danger' : a.status === 'rejected' ? 'bg-border text-muted' : 'bg-warning/15 text-warning'}`}>{a.status}</span>
                          </div>
                          <div className="mt-0.5 flex items-center gap-1.5 text-[9px] text-muted"><span className="rounded bg-surface px-1">{a.tool}</span><span className="uppercase">{a.risk}</span></div>
                        </div>
                      </div>
                    )
                  })
                })()}
              </div>
            </aside>
          )}

          {/* jump-to-latest pill (appears when scrolled up) */}
          <AnimatePresence>
            {!atBottom && messages.length > 0 && (
              <motion.button initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}
                onClick={jumpToLatest}
                className="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-border bg-surface/95 px-3 py-1.5 text-[11px] font-medium text-text shadow-lg backdrop-blur hover:border-accent/50 hover:text-accent">
                <ChevronDown size={13} /> Jump to latest
              </motion.button>
            )}
          </AnimatePresence>
        </div>

        {/* attachment thumbnail cards + grid */}
        {attachments.length > 0 && (
          <div className="border-t border-border px-3 pt-2.5 sm:px-4">
            <div className={`${COLUMN} flex flex-wrap gap-2`}>
              {attachments.map((a, i) => (
                <div key={i} className="group/att relative flex items-center gap-2 rounded-xl border border-border bg-surface/70 p-1.5 pr-3">
                  {a.kind === 'image' && a.data_url
                    ? <img src={a.data_url} alt={a.name} className="h-11 w-11 rounded-lg border border-border object-cover" />
                    : <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-bg/60 text-accent">{a.kind === 'image' ? <ImageIcon size={18} /> : <FileText size={18} />}</span>}
                  <div className="min-w-0">
                    <div className="max-w-[140px] truncate text-xs font-medium text-text">{a.name}</div>
                    <div className="text-[10px] uppercase tracking-wide text-muted">{a.kind} · {fmtBytes(attBytes(a))}</div>
                  </div>
                  <button onClick={() => setAttachments(x => x.filter((_, k) => k !== i))}
                    className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-border bg-surface text-muted opacity-0 transition-opacity hover:text-danger group-hover/att:opacity-100"><X size={11} /></button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* auto-accept indicator — visible whenever confirmations are being bypassed */}
        {(confirmMode === 'auto' || autoAcceptChat) && (
          <div className="px-3 pt-2 sm:px-4">
            <div className={`${COLUMN} flex justify-end`}>
              <button onClick={() => { setConfirmMode('ask'); setAutoAcceptChat(false) }} title="Turn auto-accept off"
                className="flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/10 px-2.5 py-1 text-[10px] font-medium text-accent hover:bg-accent/20">
                <Zap size={11} /> Auto-accept {confirmMode === 'auto' ? 'always' : 'this chat'} · turn off
              </button>
            </div>
          </div>
        )}

        {/* composer — one unified HUD card: mode strip · textarea · toolbar */}
        <div className="p-3 sm:p-4">
          <div className={`${COLUMN}`}>
            {/* picker wizard (Feature 3) — floats directly above the input, Claude-style */}
            <AnimatePresence>
              {picker && <PickerWizard key="picker" picker={picker} onSubmit={submitPicker} onCancel={() => setPicker(null)} />}
            </AnimatePresence>
            {queuedTurns.length > 0 && (
              <div className="mb-2 flex items-center justify-between gap-2 rounded-lg border border-warning/35 bg-warning/5 px-3 py-1.5">
                <span className="flex min-w-0 items-center gap-1.5 text-[11px] text-warning"><ListChecks size={12} /> <span className="truncate">{queuedTurns.length} follow-up{queuedTurns.length > 1 ? 's' : ''} queued</span></span>
                <button onClick={clearQueuedTurns} className="text-[10px] text-muted hover:text-warning">Clear</button>
              </div>
            )}
            {/* Terminal merged into Agent (#16 D11/D13): the console panel appears in Agent
                mode once a command actually produces output (legacy terminal mode keeps it) */}
            {(mode === 'terminal' || (modeV2 && mode === 'agent' && terminalLines.length > 0)) &&
              <TerminalMode lines={terminalLines} active={busy} />}
            <input ref={fileRef} type="file" multiple hidden onChange={e => { if (e.target.files) addFiles(Array.from(e.target.files)); e.target.value = '' }} />
            <div className="relative rounded-2xl border border-border bg-surface/70 shadow-[0_-18px_60px_rgb(0_0_0/0.16)] transition-all focus-within:border-accent/45 focus-within:shadow-[0_0_0_1px_rgb(var(--accent)/0.22),0_-18px_70px_rgb(0_0_0/0.22)]">
              {/* HUD energy hairline across the top edge */}
              <div className="pointer-events-none absolute inset-x-4 top-0 h-px bg-gradient-to-r from-transparent via-accent/45 to-transparent" />

              {/* selected connectors — removable chips above the textarea */}
              <AnimatePresence>
                {connectors.length > 0 && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.18 }}
                    className="overflow-hidden">
                    <div className="flex flex-wrap items-center gap-1.5 px-3 pt-2.5">
                      {connectors.map(cid => {
                        const row = connectorRows.find(r => r.id === cid)
                          ?? connectorRows.find(r => connectorMatches(r.item, { id: cid, label: cid }))
                        const item = row?.item ?? { id: cid, label: cid, desc: '', color: '#58a6ff' } as ConnectorCatalogItem
                        const label = row?.label ?? cid
                        return (
                          <motion.span key={cid} layout initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }}
                            transition={{ duration: 0.16 }}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-bg/50 py-1 pl-1 pr-1.5 text-xs text-text">
                            <span className="flex h-5 w-5 items-center justify-center rounded-md bg-bg/60"><ConnectorGlyph item={item} size={12} /></span>
                            <span className="font-medium">{label}</span>
                            <button onClick={() => toggleConnector(cid)} aria-label={`Remove ${label}`} title={`Remove ${label}`}
                              className="ml-0.5 flex h-4 w-4 items-center justify-center rounded text-muted transition-colors hover:bg-overlay/10 hover:text-danger"><X size={11} /></button>
                          </motion.span>
                        )
                      })}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* YouTube reader chips (#14): compact status — detected before Send,
                  reading/ready/unavailable during & after the turn */}
              <ReaderChips chips={readerChips} draftIds={findYouTube(input)} />

              {/* textarea — transparent, the card is the surface */}
              <div className="relative px-3 pt-2.5">
                <AnimatePresence>
                  {slashOpen && (
                    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 6 }} transition={{ duration: 0.12 }}
                      className="absolute bottom-full left-2 z-20 mb-2 w-64 overflow-hidden rounded-xl border border-border bg-surface p-1.5 shadow-xl">
                      <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted">Commands</div>
                      {slashMatches.map((c, i) => (
                        <button key={c.cmd} onMouseEnter={() => setSlashIdx(i)} onClick={() => runSlash(c)}
                          className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm ${i === Math.min(slashIdx, slashMatches.length - 1) ? 'bg-accent/10 text-accent' : 'text-text hover:bg-bg/60'}`}>
                          <c.icon size={14} className="shrink-0 opacity-70" />
                          <span className="font-medium">/{c.cmd}</span>
                          <span className="ml-auto text-[10px] text-muted">{c.desc}</span>
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
                <textarea ref={taRef} value={input} onChange={e => setInput(e.target.value)} onPaste={onPaste}
                  onKeyDown={onComposerKey}
                  rows={1} placeholder={`${modePlaceholder}  (Enter to send - / for commands)`}
                  className="block min-h-[30px] max-h-[200px] w-full resize-none overflow-y-auto bg-transparent py-1 text-sm leading-relaxed text-text outline-none placeholder:text-muted/55" />
              </div>

              {/* bottom toolbar — tools left · model + send right */}
              <div className="flex items-center justify-between gap-2 px-2 pb-2 pt-1">
                <div className="flex items-center gap-0.5">
                  <div className="relative" ref={plusRef}>
                    <button onClick={() => setPlusOpen(o => !o)} title="Tools & attachments"
                      className={`relative flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${plusOpen ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-overlay/5 hover:text-text'}`}>
                      <Plus size={18} className={`transition-transform ${plusOpen ? 'rotate-45' : ''}`} />
                      {connectors.length > 0 && !plusOpen && <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[9px] font-bold text-bg">{connectors.length}</span>}
                    </button>
                    <AnimatePresence>
                      {plusOpen && (
                        <motion.div initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 6, scale: 0.97 }} transition={{ duration: 0.14 }}
                          className="absolute bottom-11 left-0 z-20 w-60 rounded-xl border border-border bg-surface p-1.5 shadow-xl">
                          <button onClick={() => { fileRef.current?.click(); setPlusOpen(false) }} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-text hover:bg-bg/60"><Paperclip size={15} className="text-muted" /> Upload file</button>
                          <button onClick={() => { fileRef.current?.click(); setPlusOpen(false) }} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-text hover:bg-bg/60"><ImageIcon size={15} className="text-muted" /> Attach image <span className="ml-auto text-[10px] text-muted">or paste</span></button>
                          <button onClick={() => setWebResearch(v => !v)} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-text hover:bg-bg/60"><Globe size={15} className={webResearch ? 'text-accent' : 'text-muted'} /> Web research <span className={`ml-auto text-[10px] ${webResearch ? 'text-accent' : 'text-muted'}`}>{webResearch ? 'On' : 'Off'}</span></button>
                          {modeV2 && (
                            <button onClick={() => setDeepResearch(v => !v)} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-text hover:bg-bg/60" title="One-message cited research report">
                              <Search size={15} className={deepResearch ? 'text-purple' : 'text-muted'} /> Deep Research
                              <span className={`ml-auto text-[10px] ${deepResearch ? 'text-purple' : 'text-muted'}`}>{deepResearch ? 'Next msg' : 'Off'}</span>
                            </button>
                          )}
                          <button onMouseEnter={() => setPlusPanel('connectors')} onClick={() => setPlusPanel('connectors')} className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-bg/60 ${plusPanel === 'connectors' ? 'bg-accent/10 text-accent' : 'text-text'}`}><Plug size={15} className="text-muted" /> Connectors <span className="ml-auto flex items-center gap-1 text-[10px] text-muted">{connectors.length || 'Live'} <ChevronRight size={12} /></span></button>
                          <button onMouseEnter={() => setPlusPanel('confirmations')} onClick={() => setPlusPanel('confirmations')} className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-bg/60 ${plusPanel === 'confirmations' ? 'bg-accent/10 text-accent' : 'text-text'}`}><ShieldCheck size={15} className="text-muted" /> Human review <span className="ml-auto flex items-center gap-1 text-[10px] text-muted">{reviewMode} <ChevronRight size={12} /></span></button>
                          <button onClick={() => { setPicker(DEFAULT_DETAIL_PICKER); setPlusOpen(false) }} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-text hover:bg-bg/60"><Sparkles size={15} className="text-muted" /> Tell TOBI about you <span className="ml-auto text-[10px] text-muted">picker</span></button>
                          <button disabled className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted/60"><FileText size={15} /> Choose from Drive <span className="ml-auto text-[10px]">soon</span></button>
                          {connectorOpts.length > 0 && <div className="hidden">
                            <div className="px-2.5 py-1 text-[10px] uppercase tracking-wide text-muted">Connectors → live tools</div>
                            {connectorOpts.map(c => (
                              <button key={c.id} onClick={() => toggleConnector(c.id)} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm text-text hover:bg-bg/60"><Plug size={14} className={connectors.includes(c.id) ? 'text-accent' : 'text-muted'} /> {c.label} <span className={`ml-auto text-[10px] ${connectors.includes(c.id) ? 'text-accent' : 'text-muted'}`}>{connectors.includes(c.id) ? 'On' : 'Off'}</span></button>
                            ))}
                          </div>}
                          <div className="hidden">
                            <div className="px-2.5 py-1 text-[10px] uppercase tracking-wide text-muted">Confirmations · when TOBI acts</div>
                            {([
                              { v: 'ask', label: 'Ask every time', Icon: ShieldAlert },
                              { v: 'session', label: 'Auto-accept this chat', Icon: Check },
                              { v: 'always', label: 'Always auto-accept', Icon: Zap },
                            ] as const).map(({ v, label, Icon }) => {
                              const active = confirmMode === 'auto' ? v === 'always' : autoAcceptChat ? v === 'session' : v === 'ask'
                              return (
                                <button key={v} onClick={() => {
                                  if (v === 'ask') { setConfirmMode('ask'); setAutoAcceptChat(false) }
                                  else if (v === 'session') { setConfirmMode('ask'); setAutoAcceptChat(true) }
                                  else { setConfirmMode('auto'); setAutoAcceptChat(false) }
                                }} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm text-text hover:bg-bg/60">
                                  <Icon size={14} className={active ? 'text-accent' : 'text-muted'} /> {label}
                                  <span className={`ml-auto h-2 w-2 rounded-full ${active ? 'bg-accent' : 'border border-border'}`} />
                                </button>
                              )
                            })}
                          </div>
                          <AnimatePresence mode="wait">
                            {plusPanel === 'connectors' && (
                              <motion.div key="connectors" initial={{ opacity: 0, x: -6, scale: 0.98 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, x: -6, scale: 0.98 }} transition={{ duration: 0.13 }}
                                className="absolute bottom-0 left-[calc(100%+8px)] w-72 rounded-xl border border-border bg-surface p-2 shadow-xl">
                                <div className="mb-1 px-1 text-[10px] uppercase tracking-wide text-muted">Connectors</div>
                                <div className="space-y-1">
                                  {connectorRows.map(({ item, id, label, connected }) => {
                                    const active = connectors.includes(id)
                                    return (
                                      <button key={item.id} disabled={!connected} onClick={() => connected && toggleConnector(id)}
                                        className={`flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors ${connected ? 'text-text hover:bg-bg/60' : 'cursor-not-allowed text-muted/50'} ${active ? 'bg-accent/10' : ''}`}>
                                        <ConnectorMark item={item} />
                                        <span className="min-w-0 flex-1">
                                          <span className="block truncate text-sm font-medium">{label}</span>
                                          <span className="block truncate text-[11px] text-muted">{item.desc}</span>
                                        </span>
                                        <span className={`text-[10px] ${active ? 'text-accent' : connected ? 'text-muted' : 'text-muted/50'}`}>{active ? 'On' : connected ? 'Off' : 'Soon'}</span>
                                      </button>
                                    )
                                  })}
                                </div>
                              </motion.div>
                            )}
                            {plusPanel === 'confirmations' && (
                              <motion.div key="confirmations" initial={{ opacity: 0, x: -6, scale: 0.98 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, x: -6, scale: 0.98 }} transition={{ duration: 0.13 }}
                                className="absolute bottom-0 left-[calc(100%+8px)] w-72 rounded-xl border border-border bg-surface p-2 shadow-xl">
                                <div className="mb-1 px-1 text-[10px] uppercase tracking-wide text-muted">Human review checkpoints</div>
                                {([
                                  { v: 'ask', label: 'Ask before action', desc: 'Review every tool action first.', Icon: ShieldAlert },
                                  { v: 'session', label: 'Trust this chat', desc: 'Auto-accept only until this chat changes.', Icon: Check },
                                  { v: 'always', label: 'Autonomous approval', desc: 'Let TOBI proceed without prompts.', Icon: Zap },
                                ] as const).map(({ v, label, desc, Icon }) => {
                                  const active = reviewMode === v
                                  return (
                                    <button key={v} onClick={() => setReviewMode(v)}
                                      className={`flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors ${active ? 'bg-accent/10 text-accent' : 'text-text hover:bg-bg/60'}`}>
                                      <Icon size={15} className="shrink-0" />
                                      <span className="min-w-0 flex-1">
                                        <span className="block text-sm font-medium">{label}</span>
                                        <span className="block truncate text-[11px] text-muted">{desc}</span>
                                      </span>
                                      {active && <Check size={14} className="shrink-0" />}
                                    </button>
                                  )
                                })}
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                  {/* quick per-turn toggles — light up when active */}
                  <button onClick={() => setWebResearch(v => !v)} title="Web research"
                    className={`flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${webResearch ? 'bg-accent/15 text-accent shadow-[0_0_14px_rgb(var(--accent)/0.15)]' : 'text-muted hover:bg-overlay/5 hover:text-text'}`}><Globe size={16} /></button>
                  {modeV2 && (
                    <button onClick={() => setDeepResearch(v => !v)} title="Deep Research — one cited report for the next message"
                      className={`flex h-9 items-center gap-1 rounded-lg px-2 transition-colors ${deepResearch ? 'bg-purple/15 text-purple shadow-[0_0_14px_rgb(var(--purple)/0.15)]' : 'text-muted hover:bg-overlay/5 hover:text-text'}`}>
                      <Search size={16} />{deepResearch && <span className="text-[10px] font-medium">Deep</span>}
                    </button>
                  )}
                  {attachments.length > 0 && (
                    <span className="ml-0.5 flex items-center gap-1 rounded-md bg-accent/10 px-1.5 py-1.5 text-[10px] font-medium text-accent"><Paperclip size={11} /> {attachments.length}</span>
                  )}
                </div>

                <div className="flex items-center gap-1.5">
                  <div className="relative" ref={modeRef}>
                    <button onClick={() => setModeOpen(o => !o)} title="Message mode"
                      className={`flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium transition-colors ${modeOpen ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-overlay/5 hover:text-text'}`}>
                      <activeMode.Icon size={15} />
                      <span className="hidden sm:inline">{activeMode.label}</span>
                      <ChevronDown size={12} className={`transition-transform ${modeOpen ? 'rotate-180' : ''}`} />
                    </button>
                    <AnimatePresence>
                      {modeOpen && (
                        <motion.div initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 6, scale: 0.97 }} transition={{ duration: 0.14 }}
                          className="fixed inset-x-0 bottom-0 z-30 w-full rounded-t-2xl border-t border-border bg-surface p-2 pb-4 shadow-2xl sm:absolute sm:inset-x-auto sm:bottom-11 sm:right-0 sm:w-72 sm:rounded-xl sm:border sm:p-1.5 sm:pb-1.5 sm:shadow-xl">
                          <div className="px-2.5 py-1 text-[10px] uppercase tracking-wide text-muted">Mode for next message</div>
                          {CHAT_MODES.map(({ id, label, hint, Icon }) => {
                            const selected = mode === id
                            return (
                              <button key={id} onClick={() => selectMode(id)}
                                className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition-colors ${selected ? 'bg-accent/10 text-accent' : 'text-text hover:bg-bg/60'}`}>
                                <Icon size={15} className="shrink-0" />
                                <span className="min-w-0 flex-1">
                                  <span className="block text-sm font-medium">{label}</span>
                                  <span className="block truncate text-[11px] text-muted">{hint}</span>
                                </span>
                                {selected && <Check size={14} className="shrink-0" />}
                              </button>
                            )
                          })}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                  <ModelMenu models={models} value={model} onChange={changeModel} open={modelMenuOpen} onOpenChange={setModelMenuOpen} direction="up" />
                  {busy && (
                    <button onClick={send} disabled={!input.trim() && !attachments.length} title="Queue next turn" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-warning/45 bg-warning/10 text-warning hover:bg-warning/20 disabled:opacity-40"><ListChecks size={15} /></button>
                  )}
                  {busy ? (
                    <button onClick={stop} title="Stop" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-danger/50 bg-danger/15 text-danger hover:bg-danger/25"><Square size={15} /></button>
                  ) : (
                    <button onClick={send} disabled={!input.trim() && !attachments.length} title="Send" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-accent/50 bg-accent/15 text-accent shadow-[0_0_18px_rgb(var(--accent)/0.18)] transition-colors hover:bg-accent/25 disabled:opacity-40 disabled:shadow-none"><Send size={16} /></button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
