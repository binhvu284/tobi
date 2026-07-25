// Extracted from Office.tsx (pre-#21 refactor) — verbatim move.

import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence, useDragControls } from 'framer-motion'
import { getAgents, getOfficeStats, getMissions, getMission, createMission, runMission, patchMission, createAgent, updateAgent, deleteAgent, pauseMission, resumeMission, cancelMission, injectMission, type Agent, type OfficeStats, type Mission, type AgentUpsert } from '../../api.office'


// ── Typography ──────────────────────────────────────────────────────
// Rajdhani is now bundled self-hosted (src/theme/fonts.ts) — no runtime CDN link.

// ── Pixel-art characters (unchanged sprites, selected by agent.sprite) ──
export function TobiCharacter({ working }: { working: boolean }) {
  const c = '#58a6ff', e = '#0d1117'
  return (
    <svg width="64" height="80" viewBox="0 0 8 10" className={`pixel-art ${working ? 'char-working' : 'char-idle'}`}>
      <rect x="3" y="0" width="2" height="1" fill={c} /><rect x="3" y="0" width="1" height="1" fill="#f0f6fc" />
      <rect x="1" y="1" width="6" height="4" fill={c} /><rect x="2" y="2" width="1" height="1" fill="white" />
      <rect x="5" y="2" width="1" height="1" fill="white" /><rect x="2" y="2" width="1" height="1" fill={e} style={{ opacity: 0.7 }} />
      <rect x="5" y="2" width="1" height="1" fill={e} style={{ opacity: 0.7 }} /><rect x="3" y="4" width="2" height="1" fill={e} />
      <rect x="2" y="5" width="4" height="3" fill={c} /><rect x="1" y="5" width="1" height="2" fill={c} />
      <rect x="6" y="5" width="1" height="2" fill={c} /><rect x="2" y="8" width="1" height="2" fill={c} /><rect x="5" y="8" width="1" height="2" fill={c} />
    </svg>
  )
}
export function ResearchCharacter({ working }: { working: boolean }) {
  return (
    <svg width="64" height="80" viewBox="0 0 8 10" className={`pixel-art ${working ? 'char-working' : 'char-idle'}`}>
      <rect x="1" y="0" width="6" height="2" fill="#d29922" /><rect x="1" y="1" width="6" height="4" fill="#f4a261" />
      <rect x="1" y="2" width="2" height="1" fill="#3fb950" /><rect x="4" y="2" width="2" height="1" fill="#3fb950" />
      <rect x="3" y="2" width="1" height="1" fill="#3fb950" style={{ opacity: 0.5 }} /><rect x="2" y="2" width="1" height="1" fill="#0d1117" />
      <rect x="5" y="2" width="1" height="1" fill="#0d1117" /><rect x="3" y="4" width="2" height="1" fill="#0d1117" />
      <rect x="1" y="5" width="6" height="3" fill="#e5e7eb" /><rect x="3" y="5" width="2" height="3" fill="#3fb950" style={{ opacity: 0.3 }} />
      <rect x="0" y="5" width="1" height="2" fill="#e5e7eb" /><rect x="7" y="5" width="1" height="2" fill="#e5e7eb" />
      <rect x="2" y="8" width="1" height="2" fill="#30363d" /><rect x="5" y="8" width="1" height="2" fill="#30363d" />
    </svg>
  )
}
export function CoderCharacter({ working }: { working: boolean }) {
  return (
    <svg width="64" height="80" viewBox="0 0 8 10" className={`pixel-art ${working ? 'char-working' : 'char-idle'}`}>
      <rect x="0" y="0" width="8" height="3" fill="#8b5cf6" /><rect x="2" y="1" width="4" height="3" fill="#f4a261" />
      <rect x="2" y="2" width="1" height="1" fill="#0d1117" /><rect x="5" y="2" width="1" height="1" fill="#0d1117" />
      <rect x="1" y="4" width="6" height="4" fill="#8b5cf6" /><rect x="3" y="6" width="2" height="1" fill="black" style={{ opacity: 0.3 }} />
      <rect x="0" y="4" width="1" height="3" fill="#8b5cf6" /><rect x="7" y="4" width="1" height="3" fill="#8b5cf6" />
      <rect x="2" y="8" width="1" height="2" fill="#30363d" /><rect x="5" y="8" width="1" height="2" fill="#30363d" />
    </svg>
  )
}
export function CeoCharacter({ working }: { working: boolean }) {
  return (
    <svg width="64" height="80" viewBox="0 0 8 10" className={`pixel-art ${working ? 'char-working' : 'char-idle'}`}>
      <rect x="2" y="0" width="4" height="1" fill="#30363d" /><rect x="1" y="1" width="6" height="4" fill="#f4a261" />
      <rect x="2" y="2" width="1" height="1" fill="#0d1117" /><rect x="5" y="2" width="1" height="1" fill="#0d1117" />
      <rect x="3" y="4" width="1" height="1" fill="#0d1117" /><rect x="4" y="4" width="1" height="1" fill="#0d1117" />
      <rect x="1" y="5" width="6" height="3" fill="#21262d" /><rect x="3" y="5" width="2" height="3" fill="#d29922" />
      <rect x="3" y="7" width="2" height="1" fill="#d29922" style={{ opacity: 0.7 }} /><rect x="0" y="5" width="1" height="3" fill="#21262d" />
      <rect x="7" y="5" width="1" height="3" fill="#21262d" /><rect x="2" y="8" width="1" height="2" fill="#21262d" /><rect x="5" y="8" width="1" height="2" fill="#21262d" />
    </svg>
  )
}
export const SPRITES: Record<string, React.FC<{ working: boolean }>> = {
  tobi: TobiCharacter, research: ResearchCharacter, coder: CoderCharacter, ceo: CeoCharacter,
}
export const SPRITE_KEYS = Object.keys(SPRITES)
export const spriteOf = (a: Agent) => SPRITES[a.sprite || 'tobi'] || TobiCharacter

// ── Scene FX ────────────────────────────────────────────────────────
export const CodeRain = ({ color }: { color?: string }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = canvasRef.current; if (!canvas) return
    const ctx = canvas.getContext('2d'); if (!ctx) return
    const resize = () => { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight }
    resize(); window.addEventListener('resize', resize)
    const letters = '01$#!%&*+-'.split(''); const fontSize = 14
    const columns = Math.floor(canvas.width / fontSize)
    const drops: number[] = new Array(columns).fill(0).map(() => Math.random() * -100)
    const draw = () => {
      ctx.fillStyle = 'rgba(5, 5, 5, 0.15)'; ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = color || '#22c55e'; ctx.font = `600 ${fontSize}px "Rajdhani", monospace`
      for (let i = 0; i < drops.length; i++) {
        ctx.fillText(letters[Math.floor(Math.random() * letters.length)], i * fontSize, drops[i] * fontSize)
        if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0
        drops[i]++
      }
    }
    const interval = setInterval(draw, 40)
    return () => { clearInterval(interval); window.removeEventListener('resize', resize) }
  }, [color])
  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full opacity-[0.2] pointer-events-none" />
}
export function Scanlines() { return <div className="absolute inset-0 pointer-events-none z-50 opacity-[0.03] scanlines" /> }

// ── 2D cyberpunk base: Tobi core (hub) + sub-agents on a ring (hub-and-spoke, D68) ──
export function StatusDot({ status }: { status: string }) {
  const c = status === 'working' ? 'bg-accent' : status === 'online' ? 'bg-success' : 'bg-gray-500'
  return <span className={`inline-block h-2 w-2 rounded-full ${c} ${status === 'working' ? 'animate-pulse' : ''}`} />
}

export function CoreGlow({ color }: { color: string }) {
  return (
    <motion.div className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-44 w-44 -translate-x-1/2 -translate-y-1/2 rounded-full blur-2xl"
      style={{ background: color }} animate={{ opacity: [0.14, 0.28, 0.14], scale: [1, 1.12, 1] }} transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }} />
  )
}
