import Phaser from 'phaser'
import type { Agent } from '../../api'
import { cssColorToInt } from '../theme'

export type Behavior = 'working' | 'idle' | 'sleeping' | 'thinking' | 'talking' | 'error' | 'walking'

const FONT = 'Rajdhani, system-ui, sans-serif'
const FACE: Record<Behavior, string> = {
  working: 'face-work', idle: 'face-idle', sleeping: 'face-sleep',
  thinking: 'face-think', talking: 'face-talk', error: 'face-error', walking: 'face-idle',
}

/**
 * A cute chibi office worker built from procedural parts (shadow, tinted body,
 * head, swappable face, nameplate, status pip, speech bubble). The container's
 * origin is the character's *feet* (its floor anchor), so the scene positions it
 * by the desk's front tile. `setBehavior` swaps look + idle animation; `setBubble`
 * streams the active step text. Recolored to the agent's color via tint.
 */
export default class ChibiAgent extends Phaser.GameObjects.Container {
  agentId: string
  color: number
  private torso: Phaser.GameObjects.Image
  private head: Phaser.GameObjects.Image
  private face: Phaser.GameObjects.Image
  private plate: Phaser.GameObjects.Text
  private pip: Phaser.GameObjects.Arc
  private bubble?: Phaser.GameObjects.Container
  private bubbleBg?: Phaser.GameObjects.Graphics
  private bubbleTxt?: Phaser.GameObjects.Text
  private zzz?: Phaser.GameObjects.Text
  private anim?: Phaser.Tweens.Tween
  private walkTween?: Phaser.Tweens.Tween
  private behavior: Behavior = 'idle'
  private selected = false
  // home = the floor tile in front of this agent's desk (set by the scene)
  homeCol = 0
  homeRow = 0
  walking = false

  constructor(scene: Phaser.Scene, agent: Agent) {
    super(scene, 0, 0)
    this.agentId = agent.id
    this.color = cssColorToInt(agent.color)

    const shadow = scene.add.image(0, 0, 'chibi-shadow').setOrigin(0.5, 0.5)
    this.torso = scene.add.image(0, -13, 'chibi-body').setOrigin(0.5, 1).setTint(this.color)
    this.head = scene.add.image(0, -29, 'chibi-head').setOrigin(0.5, 0.5)
    this.face = scene.add.image(0, -29, 'face-idle').setOrigin(0.5, 0.5)
    this.plate = scene.add.text(0, -46, agent.name, { fontFamily: FONT, fontSize: '11px', color: '#e6edf3' })
      .setOrigin(0.5, 1).setShadow(0, 1, '#000', 3)
    this.pip = scene.add.circle(this.plate.width / 2 + 8, -50, 3, 0x3fb950)

    this.add([shadow, this.torso, this.head, this.face, this.plate, this.pip])
    this.setSize(48, 72)
    this.setInteractive(new Phaser.Geom.Rectangle(-24, -60, 48, 64), Phaser.Geom.Rectangle.Contains)
    scene.add.existing(this)
    this.applyAnim('idle') // behavior field already starts at 'idle'; kick off its loop
  }

  /** Status pip color from a live status string. */
  private pipColor(b: Behavior): number {
    if (b === 'working' || b === 'talking' || b === 'thinking') return this.color
    if (b === 'error') return 0xff6b6b
    if (b === 'sleeping') return 0x6b7280
    return 0x3fb950
  }

  setBehavior(b: Behavior) {
    if (b === this.behavior) return
    this.behavior = b
    this.face.setTexture(FACE[b])
    this.pip.setFillStyle(this.pipColor(b))
    this.applyAnim(b)
    if (b !== 'sleeping') this.hideZzz()
    if (b === 'sleeping') this.showZzz()
  }

  /** Drive the idle/ambient motion for a state (kills the prior loop). */
  private applyAnim(b: Behavior) {
    this.anim?.stop(); this.anim = undefined
    this.torso.setScale(1, 1); this.torso.y = -13; this.x = Math.round(this.x)
    const s = this.scene
    if (!s) return
    if (b === 'working' || b === 'talking') {
      this.anim = s.tweens.add({ targets: this.torso, y: -15, duration: 220, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
    } else if (b === 'idle' || b === 'walking') {
      this.anim = s.tweens.add({ targets: this.torso, scaleY: 1.05, duration: 1600, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
    } else if (b === 'thinking') {
      this.anim = s.tweens.add({ targets: this.head, angle: 6, duration: 1400, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
    } else if (b === 'sleeping') {
      this.anim = s.tweens.add({ targets: this.torso, scaleY: 1.04, duration: 2600, yoyo: true, repeat: -1, ease: 'Sine.easeInOut' })
    } else if (b === 'error') {
      this.anim = s.tweens.add({ targets: this, x: { from: this.x - 2, to: this.x + 2 }, duration: 70, yoyo: true, repeat: 5, ease: 'Sine.easeInOut' })
    }
  }

  /** Brief eye-blink — only when not asleep/erroring. */
  blink() {
    if (this.behavior === 'sleeping' || this.behavior === 'error') return
    const prev = this.face.texture.key
    this.face.setTexture('face-sleep')
    this.scene?.time.delayedCall(120, () => this.face?.setTexture(prev))
  }

  private showZzz() {
    if (this.zzz || !this.scene) return
    this.zzz = this.scene.add.text(10, -40, 'z', { fontFamily: FONT, fontSize: '12px', color: '#9aa4b2' }).setOrigin(0.5)
    this.add(this.zzz)
    this.scene.tweens.add({ targets: this.zzz, y: -56, alpha: { from: 0.9, to: 0 }, duration: 2200, repeat: -1, ease: 'Sine.easeOut' })
  }
  private hideZzz() { this.zzz?.destroy(); this.zzz = undefined }

  /** Show/stream the active step text in a speech bubble (null hides it). */
  setBubble(text: string | null) {
    const s = this.scene
    if (!s) return
    if (!text) { this.bubble?.setVisible(false); return }
    const tail = text.replace(/\s+/g, ' ').trim().slice(-52)
    if (!this.bubble) {
      this.bubbleBg = s.add.graphics()
      this.bubbleTxt = s.add.text(0, 0, '', { fontFamily: FONT, fontSize: '10px', color: '#0a0f18', wordWrap: { width: 124 } }).setOrigin(0.5, 1)
      this.bubble = s.add.container(0, -58, [this.bubbleBg, this.bubbleTxt])
      this.add(this.bubble)
    }
    this.bubbleTxt!.setText(tail)
    const w = Math.min(140, this.bubbleTxt!.width + 14)
    const h = this.bubbleTxt!.height + 10
    this.bubbleTxt!.setPosition(0, -4)
    this.bubbleBg!.clear()
    this.bubbleBg!.fillStyle(0xffffff, 0.95); this.bubbleBg!.fillRoundedRect(-w / 2, -h - 6, w, h, 5)
    this.bubbleBg!.fillTriangle(-4, -6, 4, -6, 0, 0) // tail
    this.bubble.setVisible(true)
  }

  /** Current behavior (read-only) so the scene can skip walking agents. */
  behaviorState(): Behavior { return this.behavior }
  setHome(col: number, row: number) { this.homeCol = col; this.homeRow = row }

  /** Walk through screen waypoints, tweening tile-to-tile (interpolation). */
  walkAlong(points: { x: number; y: number; depth: number }[], onArrive?: () => void) {
    if (!this.scene || points.length === 0) { onArrive?.(); return }
    this.walkTween?.stop()
    this.walking = true
    this.setBehavior('walking')
    let i = 0
    const step = () => {
      if (!this.scene || !this.active) { this.walking = false; return }
      if (i >= points.length) { this.walking = false; this.setBehavior('idle'); onArrive?.(); return }
      const p = points[i++]
      this.setDepth(p.depth)
      this.walkTween = this.scene.tweens.add({ targets: this, x: p.x, y: p.y, duration: 300, ease: 'Linear', onComplete: step })
    }
    step()
  }

  setSelected(v: boolean) {
    this.selected = v
    this.setScale(v ? 1.12 : 1)
    this.plate.setColor(v ? '#ffffff' : '#e6edf3')
  }
  setDimmed(v: boolean) { this.setAlpha(v && !this.selected ? 0.35 : 1) }

  destroy(fromScene?: boolean) { this.anim?.stop(); this.walkTween?.stop(); super.destroy(fromScene) }
}
