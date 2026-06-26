import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Loader2, Sparkles, Bot, User } from 'lucide-react'
import { type ChatMessage, streamBrainChat, getChatHistory, rememberFact } from '../api'
import { useToast } from '../context/ToastProvider'
import { useReducedMotionPref } from '../context/MotionProvider'

const THINK_PHASES = ['Recalling memories…', 'Connecting context…', 'Thinking…']

/** Pulsing orb + cycling status phases that mirror TOBI's memory-first pipeline. */
function ThinkingOrb() {
  const reduced = useReducedMotionPref() !== 'full'
  const [pi, setPi] = useState(0)
  useEffect(() => {
    if (pi >= THINK_PHASES.length - 1) return
    const t = setTimeout(() => setPi(p => Math.min(p + 1, THINK_PHASES.length - 1)), reduced ? 500 : 850)
    return () => clearTimeout(t)
  }, [pi, reduced])
  return (
    <div className="flex gap-2.5">
      <div className="flex h-7 w-7 items-center justify-center rounded-full border border-purple/30 bg-purple/10 text-purple"><Bot size={13} /></div>
      <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm border border-border bg-surface px-3.5 py-2.5">
        <motion.span className="h-2.5 w-2.5 rounded-full"
          style={{ background: 'rgb(var(--purple))', boxShadow: '0 0 8px rgb(var(--purple) / 0.7)' }}
          animate={reduced ? {} : { scale: [1, 1.4, 1], opacity: [0.6, 1, 0.6] }}
          transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut' }} />
        <AnimatePresence mode="wait">
          <motion.span key={pi} initial={{ opacity: 0, y: reduced ? 0 : 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduced ? 0 : -4 }}
            transition={{ duration: 0.2 }} className="text-xs text-muted">{THINK_PHASES[pi]}</motion.span>
        </AnimatePresence>
      </div>
    </div>
  )
}

export default function Chat() {
  const { toast } = useToast()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const reduced = useReducedMotionPref() !== 'full'
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { getChatHistory().then(r => setMessages(r.items)).catch(() => {}) }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, sending])

  const send = async () => {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setMessages(m => [...m, { role: 'user', content: text }])
    setSending(true)
    // Reserve the assistant bubble; it fills in as deltas stream.
    let streamed = false
    const startAssistant = () => {
      if (streamed) return
      streamed = true
      setSending(false)
      setStreaming(true)
      setMessages(m => [...m, { role: 'assistant', content: '' }])
    }
    try {
      await streamBrainChat(text, (delta) => {
        startAssistant()
        setMessages(m => {
          const next = [...m]
          const last = next[next.length - 1]
          if (last && last.role === 'assistant') next[next.length - 1] = { ...last, content: last.content + delta }
          return next
        })
      })
    } catch (e) {
      const msg = `⚠️ ${(e as Error).message}`
      if (streamed) {
        setMessages(m => {
          const next = [...m]
          const last = next[next.length - 1]
          if (last && last.role === 'assistant' && !last.content) next[next.length - 1] = { ...last, content: msg }
          return next
        })
      } else {
        setMessages(m => [...m, { role: 'assistant', content: msg }])
      }
    } finally { setSending(false); setStreaming(false) }
  }

  const remember = async (content: string) => {
    try {
      const r = await rememberFact(content)
      toast({ kind: 'success', title: 'Remembered', detail: r.category ? `Saved to ${r.category}` : undefined })
    } catch (e) { toast({ kind: 'error', title: 'Could not save', detail: (e as Error).message }) }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 border-b border-border px-5 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/30 bg-accent/10 text-accent"><Bot size={16} /></div>
        <div>
          <h1 className="text-sm font-bold text-heading">Chat with TOBI</h1>
          <p className="text-[11px] text-muted">Talk naturally — TOBI learns about you as you go</p>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-6">
        {messages.length === 0 && (
          <div className="mx-auto mt-10 max-w-sm text-center text-sm text-muted">
            <Sparkles size={22} className="mx-auto mb-2 text-accent/70" />
            Say hello. Anything you share that's worth remembering gets saved to your <span className="text-text">Brain</span>.
          </div>
        )}
        {messages.map((m, i) => {
          const mine = m.role === 'user'
          return (
            <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              className={`group flex gap-2.5 ${mine ? 'flex-row-reverse' : ''}`}>
              <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${mine ? 'border-accent/30 bg-accent/10 text-accent' : 'border-purple/30 bg-purple/10 text-purple'}`}>
                {mine ? <User size={13} /> : <Bot size={13} />}
              </div>
              <div className={`max-w-[78%] rounded-2xl border px-3.5 py-2 text-sm ${mine ? 'rounded-tr-sm border-accent/20 bg-accent/10 text-text' : 'rounded-tl-sm border-border bg-surface text-text'}`}>
                <div className="whitespace-pre-wrap leading-relaxed">
                  {m.content}
                  {!mine && streaming && i === messages.length - 1 && (
                    <span className={`ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] bg-accent align-middle ${reduced ? '' : 'chat-caret'}`} />
                  )}
                </div>
                {!mine && (
                  <button onClick={() => remember(m.content)}
                    className="mt-1 flex items-center gap-1 text-[10px] text-muted opacity-0 transition-opacity hover:text-accent group-hover:opacity-100">
                    <Sparkles size={10} /> Remember this
                  </button>
                )}
              </div>
            </motion.div>
          )
        })}
        {sending && <ThinkingOrb />}
        <div ref={endRef} />
      </div>

      <div className="border-t border-border p-3 sm:p-4">
        <div className="flex items-end gap-2">
          <textarea value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            rows={1} placeholder="Message TOBI…  (Enter to send, Shift+Enter for newline)"
            className="max-h-32 flex-1 resize-none rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm text-text outline-none focus:border-accent/50" />
          <button onClick={send} disabled={sending || !input.trim()}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-accent/50 bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-40">
            {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  )
}
