// Tiny WebAudio UI ticks — no assets, no deps. Respects the persisted sound pref.
let ctx: AudioContext | null = null
function soundOn(): boolean {
  try { return JSON.parse(localStorage.getItem('tobi.prefs') || '{}').sound === true } catch { return false }
}
function blip(freq: number, dur = 0.05, gain = 0.04) {
  if (!soundOn()) return
  try {
    ctx = ctx || new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
    const o = ctx.createOscillator(); const g = ctx.createGain()
    o.type = 'triangle'; o.frequency.value = freq
    g.gain.value = gain
    o.connect(g); g.connect(ctx.destination)
    const t = ctx.currentTime
    o.start(t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur); o.stop(t + dur)
  } catch { /* ignore */ }
}

export const sfx = {
  tick: () => blip(660, 0.04, 0.03),
  select: () => blip(880, 0.06, 0.04),
  success: () => { blip(660, 0.06); setTimeout(() => blip(990, 0.08), 60) },
  error: () => blip(180, 0.12, 0.05),
  tierUp: () => {
    const notes = [523, 659, 784, 1047, 1319, 1568]
    const delays = [0, 100, 200, 320, 460, 620]
    notes.forEach((f, i) => setTimeout(() => blip(f, 0.18, 0.07), delays[i]))
  },
}
export function useSound() { return sfx }
