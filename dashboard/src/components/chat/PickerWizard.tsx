import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, ChevronLeft, ChevronRight, Check, SkipForward, Sparkles } from 'lucide-react'
import type { ChatPicker } from '../../api.chat'
import { useReducedMotionPref } from '../../context/MotionProvider'

export type PickerAnswer = { question: string; answer: string }

/**
 * Multi-step wizard TOBI raises when he needs context (or the owner asks him to
 * "ask me for my details"). One question per screen + progress indicator; option
 * questions are **multi-select** (pick any number, plus a free-text add). Answers
 * are session-scoped — on submit they go back to TOBI as the owner's next message.
 *
 * Rendered as a floating card that sits directly above the chat composer (Claude
 * style) — the parent positions it; this component owns no page overlay.
 */
export default function PickerWizard({ picker, onSubmit, onCancel }: {
  picker: ChatPicker
  onSubmit: (answers: PickerAnswer[]) => void
  onCancel: () => void
}) {
  const reduced = useReducedMotionPref() !== 'full'
  const questions = picker.questions
  const [step, setStep] = useState(0)
  const [chosen, setChosen] = useState<string[][]>(() => questions.map(() => []))  // selected options per q
  const [typed, setTyped] = useState<string[]>(() => questions.map(() => ''))      // free-text per q
  const [dir, setDir] = useState(1)

  const q = questions[step]
  const last = step === questions.length - 1
  const hasOptions = !!(q.options && q.options.length)

  const toggle = (opt: string) => setChosen(c => c.map((arr, i) =>
    i === step ? (arr.includes(opt) ? arr.filter(x => x !== opt) : [...arr, opt]) : arr))
  const setTypedAt = (v: string) => setTyped(t => t.map((x, i) => (i === step ? v : x)))
  const answerFor = (i: number) => [...chosen[i], typed[i].trim()].filter(Boolean).join(', ')

  const go = (delta: number) => { setDir(delta); setStep(s => Math.min(Math.max(s + delta, 0), questions.length - 1)) }
  const finish = () => onSubmit(questions.map((qq, i) => ({ question: qq.question, answer: answerFor(i) })).filter(a => a.answer))
  const next = () => (last ? finish() : go(1))

  const variants = reduced
    ? { enter: { opacity: 0 }, center: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        enter: (d: number) => ({ opacity: 0, x: d > 0 ? 20 : -20 }),
        center: { opacity: 1, x: 0 },
        exit: (d: number) => ({ opacity: 0, x: d > 0 ? -20 : 20 }),
      }

  return (
    <motion.div
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 14, scale: 0.985 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={reduced ? { opacity: 0 } : { opacity: 0, y: 10, scale: 0.985 }}
      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
      className="mb-2 overflow-hidden rounded-2xl border border-accent/25 bg-surface/95 shadow-2xl shadow-black/30 ring-1 ring-accent/10 backdrop-blur"
    >
      {/* HUD energy hairline */}
      <div className="pointer-events-none h-px bg-gradient-to-r from-transparent via-accent/45 to-transparent" />

      {/* Header + progress */}
      <div className="flex items-center justify-between px-4 pt-3">
        <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-heading">
          <Sparkles size={15} className="shrink-0 text-accent" /> <span className="truncate">{picker.topic}</span>
        </div>
        <button onClick={onCancel} className="shrink-0 rounded-md p-1 text-muted hover:text-text" aria-label="Close"><X size={16} /></button>
      </div>
      <div className="flex items-center gap-1.5 px-4 pt-2.5">
        {questions.map((_, i) => (
          <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${i < step ? 'bg-accent' : i === step ? 'bg-accent/60' : 'bg-border'}`} />
        ))}
      </div>
      <div className="flex items-center justify-between px-4 pt-1 text-[10px] uppercase tracking-wider text-muted">
        <span>Step {step + 1} of {questions.length}</span>
        {hasOptions && <span className="text-muted/70">Select any that apply</span>}
      </div>

      {/* Question */}
      <div className="px-4 pb-3 pt-3">
        <AnimatePresence mode="wait" custom={dir}>
          <motion.div key={step} custom={dir} variants={variants} initial="enter" animate="center" exit="exit" transition={{ duration: 0.16 }}>
            <div className="mb-2.5 text-[15px] font-medium leading-snug text-text">{q.question}</div>
            {hasOptions ? (
              <div className="flex flex-col gap-1.5">
                <div className="flex flex-wrap gap-1.5">
                  {q.options!.map(opt => {
                    const on = chosen[step].includes(opt)
                    return (
                      <button key={opt} onClick={() => toggle(opt)}
                        className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ${on ? 'border-accent bg-accent/15 text-accent' : 'border-border text-muted hover:border-accent/40 hover:text-text'}`}>
                        <span className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[4px] border transition-colors ${on ? 'border-accent bg-accent text-bg' : 'border-border'}`}>
                          {on && <Check size={10} strokeWidth={3} />}
                        </span>
                        {opt}
                      </button>
                    )
                  })}
                </div>
                <input
                  value={typed[step]}
                  onChange={e => setTypedAt(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); next() } }}
                  placeholder="Add your own…"
                  className="mt-0.5 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent"
                />
              </div>
            ) : (
              <textarea
                autoFocus
                value={typed[step]}
                onChange={e => setTypedAt(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); next() } }}
                rows={3}
                placeholder="Your answer…"
                className="w-full resize-none rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent"
              />
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-border px-3 py-2.5">
        <button onClick={() => go(-1)} disabled={step === 0}
          className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm text-muted transition-colors hover:text-text disabled:opacity-30">
          <ChevronLeft size={15} /> Back
        </button>
        <div className="flex items-center gap-1">
          <button onClick={next} className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm text-muted hover:text-text" title="Skip this one">
            <SkipForward size={14} /> Skip
          </button>
          <button onClick={next}
            className="flex items-center gap-1.5 rounded-lg border border-accent/50 bg-accent/15 px-3 py-1.5 text-sm font-medium text-accent shadow-[0_0_18px_rgb(var(--accent)/0.18)] transition-colors hover:bg-accent/25">
            {last ? <><Check size={15} /> Send to TOBI</> : <>Next <ChevronRight size={15} /></>}
          </button>
        </div>
      </div>
    </motion.div>
  )
}
