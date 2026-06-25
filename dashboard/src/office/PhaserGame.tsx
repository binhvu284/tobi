import { useEffect, useRef } from 'react'
import Phaser from 'phaser'
import type { Agent, OfficeStats } from '../api'
import type { WarState } from '../hooks/useMissionStream'
import { EventBus, EV } from './EventBus'
import { accentHex } from './theme'
import Preloader from './scenes/Preloader'
import OfficeScene, { type MissionLite } from './scenes/OfficeScene'

/**
 * Mounts the Phaser office and bridges it to React via the EventBus. React owns
 * data + control flows and pushes them in (agents/mission/accent/select); the
 * scene pushes interactions out (clicked/hover). The game is created once and
 * destroyed on unmount — the only place that imports the engine into the page.
 */
export default function PhaserGame({
  agents, stats, war, selectedId, accent, performance, rightInset, onAgentClick, onAgentHover,
}: {
  agents: Agent[]
  stats: OfficeStats | null
  war: WarState
  selectedId: string | null
  accent: number
  performance: boolean
  rightInset: number
  onAgentClick: (id: string | null) => void
  onAgentHover: (id: string | null) => void
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const gameRef = useRef<Phaser.Game | null>(null)
  const readyRef = useRef(false)

  // Derive a compact mission snapshot for the scene's behavior machine.
  const mission: MissionLite = {
    activeAgentId: war.activeAgentId,
    status: war.status,
    text: war.activeSeq != null ? (war.steps[war.activeSeq]?.text || '') : '',
    done: war.done || !war.connected,
  }

  // Keep the latest props so we can flush them when the scene reports ready.
  const latest = useRef({ agents, mission, accent, selectedId, performance, rightInset })
  latest.current = { agents, mission, accent, selectedId, performance, rightInset }

  // Create the game once; wire scene→React + initial flush; destroy on unmount.
  useEffect(() => {
    if (gameRef.current || !hostRef.current) return
    const game = new Phaser.Game({
      type: Phaser.AUTO,
      parent: hostRef.current,
      transparent: true,
      scale: { mode: Phaser.Scale.RESIZE, autoCenter: Phaser.Scale.CENTER_BOTH },
      render: { antialias: true, pixelArt: false },
      scene: [Preloader, OfficeScene],
    })
    gameRef.current = game

    const onClicked = (id: string | null) => onAgentClick(id)
    const onHover = (id: string | null) => onAgentHover(id)
    const onReady = () => {
      readyRef.current = true
      const l = latest.current
      EventBus.emit(EV.ACCENT, l.accent || accentHex())
      EventBus.emit(EV.AGENTS, l.agents)
      EventBus.emit(EV.MISSION, l.mission)
      EventBus.emit(EV.SELECT, l.selectedId)
      EventBus.emit(EV.PERF, l.performance)
      EventBus.emit(EV.INSET, l.rightInset)
    }
    EventBus.on(EV.CLICKED, onClicked)
    EventBus.on(EV.HOVER, onHover)
    EventBus.on(EV.READY, onReady)

    return () => {
      readyRef.current = false
      EventBus.off(EV.CLICKED, onClicked)
      EventBus.off(EV.HOVER, onHover)
      EventBus.off(EV.READY, onReady)
      game.destroy(true)
      gameRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Push prop changes into the scene — but only once it's ready; the READY flush
  // seeds the initial state, so anything emitted before then would be a no-op.
  useEffect(() => { if (readyRef.current) EventBus.emit(EV.AGENTS, agents) }, [agents])
  useEffect(() => { if (readyRef.current) EventBus.emit(EV.MISSION, mission) }, [mission.activeAgentId, mission.text, mission.done, mission.status]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (readyRef.current) EventBus.emit(EV.ACCENT, accent) }, [accent])
  useEffect(() => { if (readyRef.current) EventBus.emit(EV.SELECT, selectedId) }, [selectedId])
  useEffect(() => { if (readyRef.current) EventBus.emit(EV.PERF, performance) }, [performance])
  useEffect(() => { if (readyRef.current) EventBus.emit(EV.INSET, rightInset) }, [rightInset])

  return <div ref={hostRef} className="absolute inset-0" />
}
