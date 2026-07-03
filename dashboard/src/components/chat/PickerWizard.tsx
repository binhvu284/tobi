import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, ChevronLeft, ChevronRight, Check, SkipForward, Sparkles } from 'lucide-react'
import type { ChatPicker } from '../../api'
import { useReducedMotionPref } from '../../context/MotionProvider'

export type PickerAnswer = { question: string; answer: string }

/**
 * Multi-step wizard TOBI raises when he needs context (or the owner asks him to
 * "ask me for my details"). One question per screen + progress indicator; each
 * question is free-text or a set of option chips. Answers are session-scoped —
 * on submit they go back to TOBI as the owner's next message.
 */
export default function PickerWizard({ picker, onSubmit, onCancel }: {
  picker: ChatPicker
  onSubmit: (answers: PickerAnswer[]) => void
  onCancel: () => void
}) {
  const reduced = useReducedMotionPref() !== 'full'
  const questions = picker.questions
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<string[]>(() => questions.map(() => ''))
  const [dir, setDir] = useState(1)

  const q = questions[step]
  const last = step === questions.length - 1
  const setAnswer = (v: string) => setAnswers(a => a.map((x, i) => (i === step ? v : x)))

  const go = (delta: number) => { setDir(delta); setStep(s => Math.min(Math.max(s + delta, 0), questions.length - 1)) }
  const finish = () => onSubmit(questions.map((qq, i) => ({ question: qq.question, answer: answers[i].trim() })).filter(a => a.answer))
  const next = () => (last ? finish() : go(1))

  const variants = reduced
    ? { enter: { opacity: 0 }, center: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        enter: (d: number) => ({ opacity: 0, x: d > 0 ? 24 : -24 }),
        center: { opacity: 1, x: 0 },
        exit: (d: number) => ({ opacity: 0, x: d > 0 ? -24 : 24 }),
      }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onCancel} />
      <motion.div
        initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 340, damping: 28 }}
        className="relative w-full max-w-md overflow-hidden rounded-2xl border border-accent/25 bg-surface shadow-2xl ring-1 ring-accent/10"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-heading">
            <Sparkles size={15} className="text-accent" /> {picker.topic}
          </div>
          <button onClick={onCancel} className="rounded-md p-1 text-muted hover:text-text" aria-label="Close"><X size={16} /></button>
        </div>

        {/* Progress */}
        <div className="flex items-center gap-1.5 px-4 pt-3">
          {questions.map((_, i) => (
            <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${i < step ? 'bg-accent' : i === step ? 'bg-accent/60' : 'bg-border'}`} />
          ))}
        </div>
        <div className="px-4 pt-1 text-[10px] uppercase tracking-wider text-muted">Step {step + 1} of {questions.length}</div>

        {/* Question */}
        <div className="min-h-[150px] px-4 py-4">
          <AnimatePresence mode="wait" custom={dir}>
            <motion.div key={step} custom={dir} variants={variants} initial="enter" animate="center" exit="exit" transition={{ duration: 0.18 }}>
              <div className="mb-3 text-[15px] font-medium text-text">{q.question}</div>
              {q.options && q.options.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {q.options.map(opt => (
                    <button key={opt} onClick={() => setAnswer(opt)}
                      className={`rounded-lg border px-3 py-2 text-sm transition-colors ${answers[step] === opt ? 'border-accent bg-accent/15 text-accent' : 'border-border text-muted hover:border-accent/40 hover:text-text'}`}>
                      {opt}
                    </button>
                  ))}
                  <input
                    value={q.options.includes(answers[step]) ? '' : answers[step]}
                    onChange={e => setAnswer(e.target.value)}
                    placeholder="or type your own…"
                    className="mt-1 w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-accent"
                  />
                </div>
              ) : (
                <textarea
                  autoFocus
                  value={answers[step]}
                  onChange={e => setAnswer(e.target.value)}
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
        <div className="flex items-center justify-between border-t border-border px-4 py-3">
          <button onClick={() => go(-1)} disabled={step === 0}
            className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm text-muted transition-colors hover:text-text disabled:opacity-30">
            <ChevronLeft size={15} /> Back
          </button>
          <div className="flex items-center gap-2">
            <button onClick={next} className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm text-muted hover:text-text" title="Skip this one">
              <SkipForward size={14} /> Skip
            </button>
            <button onClick={next}
              className="flex items-center gap-1.5 rounded-lg border border-accent/50 bg-accent/15 px-3 py-1.5 text-sm font-medium text-accent transition-colors hover:bg-accent/25">
              {last ? <><Check size={15} /> Send to TOBI</> : <>Next <ChevronRight size={15} /></>}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
