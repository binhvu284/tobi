import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useReducedMotion } from 'framer-motion'
import type { MotionLevel } from '../lib/motion'

// User-chosen motion setting. The *effective* level merges this with the OS
// `prefers-reduced-motion` flag (the more restrictive of the two wins), so a
// machine that asks for less motion is always honoured even on "Full".
export type MotionSetting = 'full' | 'reduced' | 'off'
const KEY = 'tobi.motion'
const RANK: Record<MotionSetting, number> = { full: 0, reduced: 1, off: 2 }

type Ctx = { setting: MotionSetting; level: MotionLevel; setSetting: (s: MotionSetting) => void }
const MotionCtx = createContext<Ctx>({ setting: 'full', level: 'full', setSetting: () => {} })

export function MotionProvider({ children }: { children: ReactNode }) {
  const [setting, setSettingState] = useState<MotionSetting>(() => {
    try {
      const v = localStorage.getItem(KEY)
      return v === 'reduced' || v === 'off' || v === 'full' ? v : 'full'
    } catch { return 'full' }
  })
  const osReduced = useReducedMotion() // boolean | null
  const osLevel: MotionSetting = osReduced ? 'reduced' : 'full'
  const level: MotionLevel = RANK[setting] >= RANK[osLevel] ? setting : osLevel

  // Expose the active level on <html> so pure-CSS decorative animation can be
  // neutralized by the `[data-motion]` guards in index.css.
  useEffect(() => { document.documentElement.setAttribute('data-motion', level) }, [level])

  const setSetting = (s: MotionSetting) => {
    setSettingState(s)
    try { localStorage.setItem(KEY, s) } catch { /* ignore */ }
  }

  return <MotionCtx.Provider value={{ setting, level, setSetting }}>{children}</MotionCtx.Provider>
}

export function useMotion() { return useContext(MotionCtx) }
/** The effective motion level ('full' | 'reduced' | 'off') after merging OS + in-app prefs. */
export function useReducedMotionPref(): MotionLevel { return useContext(MotionCtx).level }
