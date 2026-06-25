import Phaser from 'phaser'
import type { Agent } from '../../api'
import { EventBus, EV } from '../EventBus'
import { gridToScreen, isoDepth, TILE_W, TILE_H, HALF_H } from '../iso'
import ChibiAgent, { type Behavior } from '../objects/ChibiAgent'
import { accentHex, cssColorToInt } from '../theme'
import { PathGrid, type Cell } from '../pathfinding'
import { applyDayNight } from '../fx'

const SLEEP_MS = 45000 // calm office: agents doze after this much inactivity

export type MissionLite = {
  activeAgentId: string | null
  status: string
  text: string
  done: boolean
}

const DESK_COLS = [2, 5, 8] // 3 desks per row → up to 15 agents over 5 rows

/** Room grid sized to the roster: just enough rows for the desks used, so the
 * floor isn't mostly empty for small teams. Columns are fixed (3 desk columns
 * + side margins). */
function layoutFor(n: number): { cols: number; rows: number } {
  const deskRows = Math.max(1, Math.ceil(Math.max(n, 1) / DESK_COLS.length))
  const lastDeskRow = 1 + (deskRows - 1) * 2
  return { cols: Math.max(...DESK_COLS) + 2, rows: lastDeskRow + 3 }
}

// Only the newest scene instance handles EventBus traffic. React keeps the bus
// alive across (re)mounts/HMR, so a torn-down or duplicate scene must never run
// a handler — calling the GameObject factory after its display list is gone is
// what throws "Cannot read properties of null (reading 'add')".
let ACTIVE: OfficeScene | null = null

/** Per-agent desk cell + the floor tile the chibi stands on (one tile toward camera). */
function deskCell(i: number): { col: number; row: number } {
  const col = DESK_COLS[i % DESK_COLS.length]
  const row = 1 + Math.floor(i / DESK_COLS.length) * 2
  return { col, row }
}

/**
 * The isometric open-plan office. Floor + themed desks are static; one ChibiAgent
 * per live agent runs a behavior state machine fed by the mission stream over the
 * EventBus. Fixed camera fits the whole room and recenters on resize.
 */
export default class OfficeScene extends Phaser.Scene {
  private agents: Agent[] = []
  private mission: MissionLite = { activeAgentId: null, status: 'planned', text: '', done: true }
  private accent = accentHex()
  private selectedId: string | null = null
  private chibis = new Map<string, ChibiAgent>()
  private deskGlows: Phaser.GameObjects.Image[] = []
  private rim?: Phaser.GameObjects.Graphics
  private bounds = new Phaser.Geom.Rectangle(0, 0, 1, 1)
  private blinkTimer?: Phaser.Time.TimerEvent
  private roomCols = 10
  private roomRows = 6
  private rightInset = 0 // px reserved on the right for HUD panels (camera shifts left)
  // ── M3 motion/choreography ──
  private pathGrid?: PathGrid
  private deskCells = new Map<string, Cell>() // agent id → desk tile (courier targets)
  private spots: Cell[] = []                   // shared walkable spots (coffee / whiteboard)
  private lastActivityAt = Date.now()          // drives idle→sleep
  private prevActiveId: string | null = null   // handoff detection
  private microTimer?: Phaser.Time.TimerEvent
  private sleepTimer?: Phaser.Time.TimerEvent
  private perf = false
  // ── M4 juice/FX ──
  private monitors: Phaser.GameObjects.Image[] = []
  private motes?: Phaser.GameObjects.Particles.ParticleEmitter
  private steam?: Phaser.GameObjects.Particles.ParticleEmitter
  private bloom?: Phaser.FX.Bloom
  private dayCM?: Phaser.FX.ColorMatrix
  private dayTimer?: Phaser.Time.TimerEvent
  private wasActive = false

  constructor() { super('OfficeScene') }

  create() {
    ACTIVE = this
    this.wireBus()
    this.wireInput()
    this.buildWorld()

    this.scale.on('resize', this.fitCamera, this)
    this.blinkTimer = this.time.addEvent({ delay: 1400, loop: true, callback: this.randomBlink, callbackScope: this })
    this.sleepTimer = this.time.addEvent({ delay: 5000, loop: true, callback: () => this.guard('sleepTick', () => this.refresh()), callbackScope: this })
    this.microTimer = this.time.addEvent({ delay: 9000, loop: true, callback: this.microEvent, callbackScope: this })
    this.dayTimer = this.time.addEvent({ delay: 60000, loop: true, callback: () => this.guard('dayNight', () => this.applyDayNight()), callbackScope: this })

    this.events.once(Phaser.Scenes.Events.SHUTDOWN, this.teardown, this)
    EventBus.emit(EV.READY) // ask React to flush current props
  }

  /** True only for the live scene whose systems/display list are still up.
   * (`displayList` is nulled on shutdown — that's the real "torn down" signal;
   * we deliberately don't require RUNNING status so the create-time flush works.) */
  private alive(): boolean {
    return ACTIVE === this && !!this.sys && !!this.sys.displayList
  }

  // ── World ──────────────────────────────────────────────────────────
  /** Wipe and rebuild the floor + desks sized to the current roster, then fit. */
  private buildWorld() {
    // clear chibis then everything else on the display list (floor, rim, desks…)
    this.chibis.forEach(c => c.destroy()); this.chibis.clear()
    this.deskGlows = []
    this.sys.displayList.list.slice().forEach(o => o.destroy())
    const { cols, rows } = layoutFor(this.agents.length)
    this.roomCols = cols; this.roomRows = rows
    this.deskCells.clear()
    this.monitors = []
    this.motes = undefined; this.steam = undefined // destroyed with the display list above
    this.buildFloor()
    this.agents.forEach((a, i) => this.placeDesk(a, i))
    this.buildPaths()
    this.refresh()
    this.fitCamera()
    this.setupFx()
  }

  // ── M4 FX: glow / bloom / particles / day-night ────────────────────
  private setupFx() {
    this.guard('setupFx', () => {
      const cam = this.cameras?.main
      if (cam?.postFX && !this.dayCM) this.dayCM = cam.postFX.addColorMatrix()
      this.applyDayNight()
      this.applyFx()
    })
  }

  private applyDayNight() {
    if (this.dayCM) applyDayNight(this.dayCM)
  }

  /** (Re)build perf-gated FX: a soft per-monitor neon glow + particle motes/steam.
   * No camera bloom — it washed the whole scene out; the per-object glow gives the
   * neon pop while keeping the dark floor and agent colors crisp. */
  private applyFx() {
    try {
      // clear any prior camera-wide bloom from earlier builds
      const cam = this.cameras?.main
      if (this.bloom && cam?.postFX) { cam.postFX.remove(this.bloom); this.bloom = undefined }
      this.monitors.forEach(m => {
        m.postFX?.clear()
        if (!this.perf && m.postFX) m.postFX.addGlow(m.getData('glow') as number, 1.6, 0)
      })
      this.motes?.destroy(); this.motes = undefined
      this.steam?.destroy(); this.steam = undefined
      if (!this.perf) this.buildParticles()
    } catch (e) { console.warn('[Office] applyFx failed', e) }
  }

  private buildParticles() {
    const b = this.bounds
    this.motes = this.add.particles(b.centerX, b.bottom, 'dot', {
      x: { min: -b.width / 2, max: b.width / 2 },
      y: { min: -b.height, max: 0 },
      lifespan: 4500, frequency: 500, quantity: 1,
      speedY: { min: -14, max: -5 }, scale: { start: 0.5, end: 0 },
      alpha: { start: 0.3, end: 0 }, tint: this.accent, blendMode: 'ADD',
    }).setDepth(95000)
    const spot = this.spots[0]
    if (spot) {
      const s = gridToScreen(spot.col, spot.row)
      this.steam = this.add.particles(s.x, s.y + HALF_H - 8, 'dot', {
        lifespan: 1600, frequency: 300, speedY: { min: -18, max: -8 },
        scale: { start: 0.32, end: 0 }, alpha: { start: 0.4, end: 0 }, tint: 0xcfd8e3, blendMode: 'ADD',
      }).setDepth(95000)
    }
  }

  /** Walkable grid (desks blocked) + shared spots + a coffee prop, for M3 motion. */
  private buildPaths() {
    const blocked = new Set<string>()
    this.deskCells.forEach(({ col, row }) => blocked.add(`${col},${row}`))
    this.pathGrid = new PathGrid(this.roomCols, this.roomRows, blocked)
    // a couple of free corners as wander targets (coffee + lounge)
    const cand: Cell[] = [
      { col: 1, row: this.roomRows - 2 },
      { col: this.roomCols - 2, row: this.roomRows - 2 },
      { col: 1, row: 1 },
    ]
    this.spots = cand.filter(c => c.col >= 0 && c.row >= 0 && !blocked.has(`${c.col},${c.row}`))
    // little coffee station at the first spot
    if (this.spots[0]) {
      const s = gridToScreen(this.spots[0].col, this.spots[0].row)
      this.add.image(s.x, s.y + HALF_H, 'prop-coffee').setOrigin(0.5, 1).setDepth(isoDepth(this.spots[0].col, this.spots[0].row) * 10)
    }
  }

  private buildFloor() {
    const xs: number[] = [], ys: number[] = []
    for (let r = 0; r < this.roomRows; r++) {
      for (let c = 0; c < this.roomCols; c++) {
        const { x, y } = gridToScreen(c, r)
        const tile = this.add.image(x, y, (c + r) % 2 ? 'floor-a' : 'floor-b').setOrigin(0.5, 0)
        tile.setDepth(-1000 + isoDepth(c, r))
        xs.push(x - TILE_W / 2, x + TILE_W / 2); ys.push(y, y + TILE_H)
      }
    }
    this.bounds = new Phaser.Geom.Rectangle(
      Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys),
    )
    // neon room rim (accent-tinted) drawn around the floor diamond
    this.rim = this.add.graphics().setDepth(-1100)
    this.drawRim()
  }

  private drawRim() {
    if (!this.rim) return
    const g = this.rim; g.clear()
    const corners = [gridToScreen(0, 0), gridToScreen(this.roomCols - 1, 0), gridToScreen(this.roomCols - 1, this.roomRows - 1), gridToScreen(0, this.roomRows - 1)]
      .map(p => ({ x: p.x, y: p.y + TILE_H / 2 }))
    g.lineStyle(3, this.accent, 0.5); g.strokePoints(corners, true)
    g.lineStyle(8, this.accent, 0.08); g.strokePoints(corners, true)
  }

  private placeDesk(agent: Agent, i: number) {
    const { col, row } = deskCell(i)
    const d = gridToScreen(col, row)
    const baseDepth = isoDepth(col, row) * 10
    // accent footprint glow
    const glow = this.add.image(d.x, d.y, 'floor-glow').setOrigin(0.5, 0).setTint(this.accent).setAlpha(0.5).setDepth(baseDepth - 1)
    this.deskGlows.push(glow)
    // desk + tinted monitor (glow added in applyFx)
    this.add.image(d.x, d.y - 6, 'desk').setOrigin(0.5, 0.5).setDepth(baseDepth)
    const mon = this.add.image(d.x, d.y - 14, 'monitor').setOrigin(0.5, 1).setTint(this.colorOf(agent)).setDepth(baseDepth + 1)
    mon.setData('glow', this.colorOf(agent))
    this.monitors.push(mon)
    // a role prop beside the desk
    const prop = this.propFor(agent)
    if (prop) this.add.image(d.x - 24, d.y - 4, prop).setOrigin(0.5, 1).setDepth(baseDepth + 1)
    // chibi stands one tile toward the camera (south), facing the desk
    const feet = gridToScreen(col, row + 1)
    const chibi = new ChibiAgent(this, agent)
    chibi.setPosition(feet.x, feet.y + 4).setDepth(isoDepth(col, row + 1) * 10 + 5)
    chibi.setHome(col, row + 1)
    chibi.on('pointerover', () => { EventBus.emit(EV.HOVER, agent.id); this.input.setDefaultCursor('pointer') })
    chibi.on('pointerout', () => { EventBus.emit(EV.HOVER, null); this.input.setDefaultCursor('default') })
    chibi.on('pointerdown', () => EventBus.emit(EV.CLICKED, agent.id))
    this.chibis.set(agent.id, chibi)
    this.deskCells.set(agent.id, { col, row })
  }

  /** Feet position (with depth) for a grid cell — the point a chibi stands on. */
  private feetPoint(cell: Cell): { x: number; y: number; depth: number } {
    const s = gridToScreen(cell.col, cell.row)
    return { x: s.x, y: s.y + 4, depth: isoDepth(cell.col, cell.row) * 10 + 5 }
  }

  private colorOf(a: Agent): number { return cssColorToInt(a.color) }

  private propFor(a: Agent): string | null {
    const k = `${a.role || ''} ${a.sprite || ''}`.toLowerCase()
    if (k.includes('research')) return 'prop-whiteboard'
    if (k.includes('ceo') || a.is_head) return 'prop-plant'
    if (k.includes('cod') || k.includes('dev') || k.includes('engineer')) return 'prop-coffee'
    return 'prop-plant'
  }

  // ── EventBus (React → scene) ───────────────────────────────────────
  private wireBus() {
    EventBus.on(EV.AGENTS, this.onAgents, this)
    EventBus.on(EV.MISSION, this.onMission, this)
    EventBus.on(EV.ACCENT, this.onAccent, this)
    EventBus.on(EV.SELECT, this.onSelect, this)
    EventBus.on(EV.INSET, this.onInset, this)
    EventBus.on(EV.PERF, this.onPerf, this)
  }

  private onInset(px: number) { this.guard('onInset', () => { this.rightInset = Math.max(0, px || 0); this.fitCamera() }) }
  private onPerf(on: boolean) { this.guard('onPerf', () => { this.perf = !!on; this.applyFx() }) }

  /** Run a bus handler only on the live scene, and never let a scene error blank
   * the page — log it (sourcemaps make it precise) and degrade gracefully. */
  private guard(label: string, fn: () => void) {
    if (!this.alive()) return
    try { fn() } catch (e) { console.warn(`[Office] ${label} failed`, e) }
  }

  private onAgents(agents: Agent[]) {
    this.guard('onAgents', () => {
      const next = Array.isArray(agents) ? agents.slice(0, 15) : []
      const sameRoster = next.length === this.chibis.size && next.every(a => this.chibis.has(a.id))
      this.agents = next
      if (!sameRoster) this.buildWorld() // room is sized to the roster → full rebuild
      else this.refresh()
    })
  }

  private onMission(m: MissionLite) {
    this.guard('onMission', () => {
      const prev = this.prevActiveId
      this.mission = m || this.mission
      const active = this.mission.activeAgentId
      const running = !!active && !this.mission.done
      if (running) {
        this.lastActivityAt = Date.now()
        // handoff: the work moved to a new agent → send a courier between desks
        if (prev && prev !== active) this.sendCourier(prev, active)
      }
      // mission start/finish pops
      const cam = this.cameras?.main
      if (running && !this.wasActive) cam?.shake(160, 0.004)             // kickoff jolt
      if (!running && this.wasActive) cam?.flash(260, 40, 90, 140)        // finish glow
      this.wasActive = running
      this.prevActiveId = running ? active : null
      this.refresh()
    })
  }
  private onAccent(hex: number) {
    this.guard('onAccent', () => {
      this.accent = hex
      this.drawRim()
      this.deskGlows.forEach(g => g.setTint(hex))
    })
  }
  private onSelect(id: string | null) {
    this.guard('onSelect', () => {
      this.selectedId = id
      this.chibis.forEach((c, cid) => { c.setSelected(cid === id); c.setDimmed(id != null) })
      if (id) this.chibis.get(id)?.setDepth(99999)
    })
  }

  /** Recompute every agent's behavior + bubble from the latest data. */
  private refresh() {
    for (const a of this.agents) {
      const c = this.chibis.get(a.id); if (!c) continue
      if (c.walking) continue // don't yank a wandering agent off its path
      c.setBehavior(this.behaviorFor(a))
      const active = this.mission.activeAgentId === a.id && !this.mission.done
      c.setBubble(active ? this.mission.text : null)
    }
  }

  private behaviorFor(a: Agent): Behavior {
    if (this.mission.activeAgentId === a.id && !this.mission.done) return 'working'
    const s = a.live?.status
    if (s === 'working') return 'working'
    if (s === 'offline') return 'sleeping'
    // calm resting office: doze when nothing's happened for a while
    const calm = !(this.mission.activeAgentId && !this.mission.done)
    if (calm && Date.now() - this.lastActivityAt > SLEEP_MS) return 'sleeping'
    return 'idle'
  }

  // ── Choreography (M3): handoff couriers + idle wandering ───────────
  /** Send a glowing data-packet walking from one agent's desk to another's. */
  private sendCourier(fromId: string, toId: string) {
    const from = this.deskCells.get(fromId), to = this.deskCells.get(toId)
    if (!from || !to || !this.pathGrid) return
    const color = cssColorToInt(this.agents.find(a => a.id === toId)?.color)
    this.pathGrid.find({ col: from.col, row: from.row + 1 }, { col: to.col, row: to.row + 1 }).then(path => {
      if (!this.alive() || !path || path.length === 0) return
      const pts = path.map(c => { const s = gridToScreen(c.col, c.row); return { x: s.x, y: s.y + HALF_H } })
      const dot = this.add.image(pts[0].x, pts[0].y, 'dot').setTint(color).setScale(1.8).setDepth(99998)
      let i = 0
      const step = () => {
        if (!this.alive() || !dot.active) { dot.destroy(); return }
        if (i >= pts.length) { this.tweens.add({ targets: dot, scale: 0, alpha: 0, duration: 180, onComplete: () => dot.destroy() }); return }
        const p = pts[i++]
        this.tweens.add({ targets: dot, x: p.x, y: p.y, duration: 110, ease: 'Linear', onComplete: step })
      }
      step()
    })
  }

  /** Occasionally a calm, idle agent gets up, walks to a spot, pauses, returns. */
  private microEvent() {
    this.guard('microEvent', () => {
      if (this.perf || !this.pathGrid || this.spots.length === 0) return
      if (this.mission.activeAgentId && !this.mission.done) return // only when calm
      const idle = [...this.chibis.values()].filter(c => !c.walking && c.behaviorState() === 'idle')
      if (idle.length === 0) return
      const c = idle[Math.floor(Math.random() * idle.length)]
      const spot = this.spots[Math.floor(Math.random() * this.spots.length)]
      const home = { col: c.homeCol, row: c.homeRow }
      this.pathGrid.find(home, spot).then(out => {
        if (!this.alive() || !out) return
        c.walkAlong(out.map(p => this.feetPoint(p)), () => {
          this.time.delayedCall(1600, () => {
            this.pathGrid?.find(spot, home).then(back => {
              if (this.alive() && back) c.walkAlong(back.map(p => this.feetPoint(p)))
            })
          })
        })
      })
    })
  }

  // ── Input (scene → React) ──────────────────────────────────────────
  private wireInput() {
    this.input.on('pointerdown', (_p: Phaser.Input.Pointer, over: Phaser.GameObjects.GameObject[]) => {
      if (!over.length) EventBus.emit(EV.CLICKED, null) // background click = deselect
    })
  }

  private randomBlink() {
    if (!this.alive()) return
    const arr = [...this.chibis.values()]
    if (arr.length) arr[Math.floor(Math.random() * arr.length)].blink()
  }

  // ── Camera ─────────────────────────────────────────────────────────
  private fitCamera() {
    const cam = this.cameras?.main
    if (!cam) return
    const pad = 1.12
    // Reserve the right inset for HUD panels: fit into the remaining width and
    // shift the room left so no desk hides behind the panel.
    const availW = Math.max(120, cam.width - this.rightInset)
    const zoom = Phaser.Math.Clamp(Math.min(availW / (this.bounds.width * pad), cam.height / (this.bounds.height * pad)), 0.4, 2)
    cam.setZoom(zoom)
    cam.centerOn(this.bounds.centerX + this.rightInset / (2 * zoom), this.bounds.centerY)
  }

  private teardown() {
    if (ACTIVE === this) ACTIVE = null
    EventBus.off(EV.AGENTS, this.onAgents, this)
    EventBus.off(EV.MISSION, this.onMission, this)
    EventBus.off(EV.ACCENT, this.onAccent, this)
    EventBus.off(EV.SELECT, this.onSelect, this)
    EventBus.off(EV.INSET, this.onInset, this)
    EventBus.off(EV.PERF, this.onPerf, this)
    this.scale.off('resize', this.fitCamera, this)
    this.blinkTimer?.remove()
    this.sleepTimer?.remove()
    this.microTimer?.remove()
    this.dayTimer?.remove()
    this.motes?.destroy(); this.steam?.destroy()
  }
}
