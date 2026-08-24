// The gate.
//
// Morpheus's security model is "the gate is the defence": pass it and everything inside is shown
// in full, secrets included. So the gate is not a login form bolted on, it is the front door and
// it is built like one.
//
// Two screens: an arrival that names where you are, then verification one factor at a time. The
// owner reaches it from inside TOBI, so crossing it has to feel like crossing into somewhere
// else -- but he crosses it several times a day, so the ceremony is kept to about a second and
// the whole sequence is completable from the keyboard without ever reaching for the mouse.
//
// SHELL ONLY: `unlock()` is not authentication. Any non-empty password opens it; an empty one
// demonstrates the refusal path. Real verification replaces the submit handler and nothing else.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { ArrowRight, KeyRound, ShieldAlert, Fingerprint, Hash, X } from 'lucide-react'
import { useMorpheus, type Factor } from './MorpheusSession'
import { MORPHEUS_GATE_IMAGE } from './tokens'
import { Atmosphere, Btn } from './ui'

const OWNER_NAME = 'Thomas'

/** The Morpheus mark: a closed eye that opens. Placeholder identity, per the owner's brief. */
function EyeMark({ open, size = 68 }: { open: boolean; size?: number }) {
  const reduce = useReducedMotion()
  const lidOpen = 'M5 32C5 32 16.5 17 32 17C47.5 17 59 32 59 32C59 32 47.5 47 32 47C16.5 47 5 32 5 32Z'
  const lidShut = 'M5 32C5 32 16.5 30.6 32 30.6C47.5 30.6 59 32 59 32C59 32 47.5 33.4 32 33.4C16.5 33.4 5 32 5 32Z'
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden className="text-accent">
      <motion.path stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"
        initial={false} animate={{ d: reduce || open ? lidOpen : lidShut }}
        transition={{ duration: 1.15, ease: [0.16, 1, 0.3, 1] }} />
      <motion.circle cx="32" cy="32" r="8.5" stroke="currentColor" strokeWidth="1.25"
        style={{ transformOrigin: '32px 32px' }}
        initial={false} animate={{ opacity: open ? 1 : 0, scale: open ? 1 : 0.3 }}
        transition={{ duration: 0.8, delay: open ? 0.3 : 0, ease: [0.16, 1, 0.3, 1] }} />
      <motion.circle cx="32" cy="32" r="2.75" fill="currentColor"
        initial={false} animate={{ opacity: open ? 1 : 0 }}
        transition={{ duration: 0.5, delay: open ? 0.55 : 0 }} />
    </svg>
  )
}

/** One seal in the sequence: sealed, live, or broken open. */
function Seal({ state, Icon, label }: {
  state: 'done' | 'active' | 'waiting'; Icon: typeof KeyRound; label: string
}) {
  const reduce = useReducedMotion()
  const done = state === 'done'
  const active = state === 'active'
  return (
    <div className="flex flex-col items-center gap-2.5" aria-current={active ? 'step' : undefined}>
      <div className="relative h-11 w-11">
        <motion.span
          className={`absolute inset-0 rounded-full border ${
            done ? 'border-accent/70' : active ? 'border-accent/45' : 'border-border'}`}
          style={{ borderStyle: done ? 'solid' : 'dashed' }}
          animate={reduce || !active ? { rotate: 0 } : { rotate: 360 }}
          transition={active && !reduce
            ? { duration: 11, repeat: Infinity, ease: 'linear' }
            : { duration: 0.2 }} />
        {/* The seal itself: a hairline down the middle that parts when the step clears. */}
        <motion.span
          className={`absolute left-1/2 top-1.5 h-8 w-px -translate-x-1/2 ${done ? 'bg-accent/40' : 'bg-border'}`}
          style={{ transformOrigin: 'center' }}
          animate={{ scaleY: done ? 0 : 1 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }} />
        <span className={`absolute inset-[7px] grid place-items-center rounded-full transition-colors duration-300 ${
          done ? 'bg-accent/12 text-accent' : active ? 'bg-surface text-heading' : 'bg-panel text-muted'}`}>
          <Icon size={14} />
        </span>
      </div>
      <span className={`text-[10px] uppercase tracking-[0.14em] transition-colors duration-300 ${
        done || active ? 'text-text' : 'text-muted/70'}`}>{label}</span>
    </div>
  )
}

export default function Gate() {
  const { unlock, factors, intrusions } = useMorpheus()
  const reduce = useReducedMotion()
  const [screen, setScreen] = useState<'arrival' | 'verify'>('arrival')
  const [eyeOpen, setEyeOpen] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)
  const [value, setValue] = useState('')
  const [rejected, setRejected] = useState(false)
  const [descending, setDescending] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const t = setTimeout(() => setEyeOpen(true), reduce ? 0 : 380)
    return () => clearTimeout(t)
  }, [reduce])

  const steps = useMemo(() => {
    const s: { factor: Factor; label: string; Icon: typeof KeyRound; prompt: string; hint: string }[] = [{
      factor: 'password', label: 'Password', Icon: KeyRound,
      prompt: `Welcome back, ${OWNER_NAME}. Enter your password so I know it is you.`,
      hint: 'Master password',
    }]
    if (factors.code) s.push({
      factor: 'code', label: 'Code', Icon: Hash,
      prompt: 'Second seal. The six digits from your authenticator.', hint: 'Six-digit code',
    })
    if (factors.key) s.push({
      factor: 'key', label: 'Key', Icon: Fingerprint,
      prompt: 'Last seal. Touch your hardware key.', hint: 'Waiting for the key',
    })
    return s
  }, [factors])

  const step = steps[Math.min(stepIndex, steps.length - 1)]
  const isKeyStep = step.factor === 'key'
  const last = stepIndex === steps.length - 1

  useEffect(() => {
    if (screen === 'verify' && !isKeyStep) inputRef.current?.focus()
  }, [screen, stepIndex, isKeyStep])

  const advance = useCallback(() => {
    if (descending) return
    if (step.factor === 'password' && value.trim() === '') {
      setRejected(true)
      setTimeout(() => setRejected(false), 1000)
      return
    }
    if (!last) { setStepIndex(i => i + 1); setValue(''); return }
    setDescending(true)
    setTimeout(() => unlock(), reduce ? 0 : 900)
  }, [descending, step.factor, value, last, unlock, reduce])

  const warning = intrusions.length > 0 && !dismissed

  return (
    <div className="relative h-full w-full overflow-hidden bg-bg text-text">
      <Atmosphere image={MORPHEUS_GATE_IMAGE} />

      {/* Descent: on success the scene sinks and dissolves; on refusal it recoils upward.
          Only transform and opacity are animated. An earlier version also animated `filter`,
          which left `blur(0px)` inline on this full-viewport element forever and pushed every
          repaint of the whole screen through a filter pass -- enough to stall the compositor
          even though the main thread stayed responsive. */}
      <motion.div
        className="relative z-10 grid h-full place-items-center px-6"
        animate={
          descending && !reduce ? { y: 30, scale: 1.06, opacity: 0 }
            : rejected && !reduce ? { y: -10, scale: 0.995, opacity: 1 }
              : { y: 0, scale: 1, opacity: 1 }}
        transition={{ duration: descending ? 0.88 : 0.32, ease: [0.65, 0, 0.35, 1] }}>

        <AnimatePresence mode="wait">
          {screen === 'arrival' ? (
            <motion.div key="arrival" className="w-full max-w-md text-center"
              initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}>
              <div className="mx-auto mb-9 grid place-items-center"><EyeMark open={eyeOpen} /></div>
              <p className="text-[10.5px] uppercase tracking-[0.36em] text-muted">Private instance</p>
              <h1 className="mt-5 font-display text-[44px] font-semibold leading-[1.04] tracking-[-0.025em] text-heading">
                Welcome to Morpheus
              </h1>
              <p className="mx-auto mt-4 max-w-[19rem] text-[14.5px] leading-relaxed text-text/75">
                Everything past this door answers to you alone.
              </p>
              <div className="mt-10 flex justify-center">
                <Btn variant="primary" autoFocus onClick={() => setScreen('verify')}
                  className="group h-11 px-7 text-[14px]"
                  icon={undefined}>
                  Enter
                  <ArrowRight size={16} className="transition-transform duration-200 group-hover:translate-x-1" />
                </Btn>
              </div>
            </motion.div>
          ) : (
            <motion.div key="verify" className="w-full max-w-[26rem]"
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}>

              {warning && (
                <div className="mb-8 flex items-start gap-3 rounded-card border border-danger/35 bg-danger/[0.08] px-4 py-3">
                  <ShieldAlert size={15} className="mt-0.5 shrink-0 text-danger" />
                  <div className="min-w-0 flex-1 text-[12.5px] leading-relaxed">
                    <p className="font-medium text-heading">
                      {intrusions.length} failed {intrusions.length === 1 ? 'attempt' : 'attempts'} since you were last here.
                    </p>
                    <p className="mt-0.5 text-muted">The gate held. Full detail is in the access log.</p>
                  </div>
                  <button onClick={() => setDismissed(true)} aria-label="Dismiss"
                    className="shrink-0 rounded p-0.5 text-muted transition-colors hover:text-text">
                    <X size={13} />
                  </button>
                </div>
              )}

              <div className="mb-10 flex items-start justify-center gap-9">
                {steps.map((s, i) => (
                  <Seal key={s.factor} Icon={s.Icon} label={s.label}
                    state={i < stepIndex ? 'done' : i === stepIndex ? 'active' : 'waiting'} />
                ))}
              </div>

              <motion.div key={step.factor}
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}>
                <p className="text-center text-[14.5px] leading-relaxed text-text">{step.prompt}</p>

                <motion.div
                  animate={rejected && !reduce ? { x: [0, -8, 7, -4, 0] } : { x: 0 }}
                  transition={{ duration: 0.42 }}
                  className={`mt-7 flex items-center gap-3 rounded-card border bg-surface/70 pl-4 pr-1.5 backdrop-blur-sm
                    transition-colors duration-200 ${
                    rejected ? 'border-danger' : 'border-border focus-within:border-accent/60'}`}>
                  <step.Icon size={15} className={rejected ? 'text-danger' : 'text-muted'} />
                  {isKeyStep ? (
                    <span className="flex-1 py-3 text-[13.5px] text-muted">{step.hint}</span>
                  ) : (
                    <input ref={inputRef}
                      type={step.factor === 'password' ? 'password' : 'text'}
                      inputMode={step.factor === 'code' ? 'numeric' : undefined}
                      value={value} onChange={e => setValue(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); advance() } }}
                      aria-label={step.hint} placeholder={step.hint}
                      className="flex-1 bg-transparent py-3 text-[14px] tracking-[0.2em] text-heading outline-none
                        placeholder:tracking-normal placeholder:text-muted/70" />
                  )}
                  <Btn variant="primary" size="sm" onClick={advance} disabled={descending}>
                    {last ? 'Descend' : 'Next'}
                  </Btn>
                </motion.div>

                <p className="mt-3.5 text-center text-[11.5px] text-muted" role="status">
                  {rejected ? 'The gate refused. Every attempt is recorded.' : 'Press Enter to continue.'}
                </p>

                {/* Dev only. `import.meta.env.DEV` is a literal false in a production build, so
                    this whole block is removed by the bundler and can never ship. */}
                {import.meta.env.DEV && (
                  <div className="mt-8 border-t border-border/60 pt-4 text-center">
                    <button onClick={() => unlock()}
                      className="text-[11.5px] text-muted underline decoration-dotted underline-offset-4
                        outline-none transition-colors duration-150 hover:text-accent focus-visible:text-accent">
                      Skip the gate (development only)
                    </button>
                  </div>
                )}
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  )
}
