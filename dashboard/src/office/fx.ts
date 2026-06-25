import Phaser from 'phaser'

/**
 * Visual juice helpers (M4). Phaser's built-in WebGL FX (postFX glow/bloom,
 * camera ColorMatrix) do the heavy lifting — these are no-ops on the Canvas
 * fallback, so everything is feature-detected and wrapped by the caller.
 */

/** Subtle time-of-day feel via a camera ColorMatrix. Deliberately gentle — just a
 * faint brightness ramp so the neon-on-dark look stays crisp and agent colors read
 * clearly. No heavy blue "night" tint (that washed the whole scene out). */
export function applyDayNight(cm: Phaser.FX.ColorMatrix, date = new Date()) {
  const h = date.getHours() + date.getMinutes() / 60
  cm.reset()
  if (h < 6 || h >= 21) cm.brightness(0.9)    // night — barely dimmer
  else if (h < 8) cm.brightness(0.95)         // dawn
  else if (h >= 19) cm.brightness(0.94)       // dusk
  // 08:00–19:00 → neutral daylight (reset only)
}

/** A short label for the current lighting phase (for the HUD, optional). */
export function dayPhase(date = new Date()): 'night' | 'dawn' | 'day' | 'dusk' {
  const h = date.getHours()
  if (h < 6 || h >= 21) return 'night'
  if (h < 8) return 'dawn'
  if (h >= 19) return 'dusk'
  return 'day'
}
