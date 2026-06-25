import Phaser from 'phaser'
import { TILE_W, TILE_H } from '../iso'

/**
 * Procedural art factory. Instead of shipping external sprite packs we draw every
 * texture once with Phaser Graphics → generateTexture. Everything is kept neutral
 * (white/grey) where it should be recolorable so the scene can `tint` it to each
 * agent's color or the live theme accent. Runs once, then boots OfficeScene.
 */
export default class Preloader extends Phaser.Scene {
  constructor() { super('Preloader') }

  create() {
    const g = this.add.graphics()
    const make = (key: string, w: number, h: number, draw: (g: Phaser.GameObjects.Graphics) => void) => {
      g.clear()
      draw(g)
      g.generateTexture(key, w, h)
    }

    // ── Iso floor tiles (two shades → subtle checker) ──
    const diamond = (g: Phaser.GameObjects.Graphics, fill: number, edge: number) => {
      const pts = [
        { x: TILE_W / 2, y: 0 }, { x: TILE_W, y: TILE_H / 2 },
        { x: TILE_W / 2, y: TILE_H }, { x: 0, y: TILE_H / 2 },
      ]
      g.fillStyle(fill, 1); g.fillPoints(pts, true)
      g.lineStyle(1, edge, 0.5); g.strokePoints(pts, true)
    }
    make('floor-a', TILE_W, TILE_H, g => diamond(g, 0x0c1320, 0x1e2c44))
    make('floor-b', TILE_W, TILE_H, g => diamond(g, 0x0e1726, 0x223352))
    // a bright (tintable→accent) diamond used for desk footprints / selection ring
    make('floor-glow', TILE_W, TILE_H, g => {
      const pts = [
        { x: TILE_W / 2, y: 0 }, { x: TILE_W, y: TILE_H / 2 },
        { x: TILE_W / 2, y: TILE_H }, { x: 0, y: TILE_H / 2 },
      ]
      g.lineStyle(2, 0xffffff, 1); g.strokePoints(pts, true)
    })

    // ── Iso desk (fixed dark steel cuboid; agent color goes on the monitor) ──
    make('desk', 60, 50, g => {
      const cx = 30, top = 4, hw = 22, hh = 11, H = 14
      const T = { t: { x: cx, y: top }, r: { x: cx + hw, y: top + hh }, b: { x: cx, y: top + 2 * hh }, l: { x: cx - hw, y: top + hh } }
      // left face
      g.fillStyle(0x141c2b, 1); g.fillPoints([T.l, T.b, { x: T.b.x, y: T.b.y + H }, { x: T.l.x, y: T.l.y + H }], true)
      // right face
      g.fillStyle(0x1b2740, 1); g.fillPoints([T.b, T.r, { x: T.r.x, y: T.r.y + H }, { x: T.b.x, y: T.b.y + H }], true)
      // top surface
      g.fillStyle(0x24324f, 1); g.fillPoints([T.t, T.r, T.b, T.l], true)
      g.lineStyle(1, 0x3b557f, 0.7); g.strokePoints([T.t, T.r, T.b, T.l], true)
    })

    // ── Monitor (tintable → agent color; the glowing screen) ──
    make('monitor', 24, 22, g => {
      g.fillStyle(0x0a0f18, 1); g.fillRoundedRect(2, 1, 20, 14, 2)  // bezel
      g.fillStyle(0xffffff, 1); g.fillRoundedRect(4, 3, 16, 10, 1)  // screen (tinted)
      g.fillStyle(0x0a0f18, 1); g.fillRect(10, 15, 4, 4)            // stand
      g.fillRect(7, 19, 10, 2)                                      // base
    })

    // ── Props ──
    make('prop-whiteboard', 30, 26, g => {
      g.fillStyle(0x0a0f18, 1); g.fillRect(1, 1, 28, 18)
      g.fillStyle(0xe9eef7, 1); g.fillRect(3, 3, 24, 14)
      g.lineStyle(1, 0x58a6ff, 0.8); g.lineBetween(6, 8, 14, 8); g.lineBetween(6, 12, 22, 12)
      g.fillStyle(0x0a0f18, 1); g.fillRect(7, 19, 3, 6); g.fillRect(20, 19, 3, 6) // legs
    })
    make('prop-plant', 16, 22, g => {
      g.fillStyle(0x6b4a2f, 1); g.fillRect(5, 15, 6, 6)          // pot
      g.fillStyle(0x3fb950, 1); g.fillCircle(8, 10, 6)           // leaves
      g.fillStyle(0x4fd964, 1); g.fillCircle(5, 8, 3); g.fillCircle(11, 8, 3)
    })
    make('prop-coffee', 12, 12, g => {
      g.fillStyle(0xe9eef7, 1); g.fillRoundedRect(2, 4, 7, 7, 1) // cup
      g.lineStyle(1.5, 0xe9eef7, 1); g.strokeCircle(10, 7, 2)    // handle
    })

    // ── Chibi parts (body tintable → agent color; head a soft skin tone) ──
    make('chibi-shadow', 26, 12, g => { g.fillStyle(0x000000, 0.35); g.fillEllipse(13, 6, 24, 9) })
    make('chibi-body', 26, 22, g => {
      g.fillStyle(0xffffff, 1); g.fillRoundedRect(4, 2, 18, 18, 7)   // torso (tinted)
      g.fillStyle(0x000000, 0.18); g.fillRoundedRect(4, 12, 18, 8, 6) // soft shade at base
    })
    make('chibi-head', 20, 20, g => {
      g.fillStyle(0xf3d2b3, 1); g.fillCircle(10, 10, 9)             // head
      g.fillStyle(0x000000, 0.10); g.fillCircle(10, 13, 8)         // chin shade
    })

    // ── Face expressions (drawn dark on transparent, sized to the head) ──
    const eye = (g: Phaser.GameObjects.Graphics, x: number, y: number) => g.fillCircle(x, y, 1.4)
    make('face-idle', 20, 20, g => { g.fillStyle(0x1a1a1a, 1); eye(g, 7, 9); eye(g, 13, 9); g.lineStyle(1.4, 0x1a1a1a, 1); g.beginPath(); g.arc(10, 12, 2.5, 0.1 * Math.PI, 0.9 * Math.PI); g.strokePath() })
    make('face-work', 20, 20, g => { g.fillStyle(0x1a1a1a, 1); g.fillRect(6, 8.5, 2.4, 1.6); g.fillRect(11.6, 8.5, 2.4, 1.6); g.fillRect(8.5, 12.5, 3, 1.4) })
    make('face-sleep', 20, 20, g => { g.lineStyle(1.4, 0x1a1a1a, 1); g.lineBetween(6, 9, 9, 9); g.lineBetween(11, 9, 14, 9); g.fillStyle(0x1a1a1a, 1); g.fillCircle(10, 12.5, 1) })
    make('face-think', 20, 20, g => { g.fillStyle(0x1a1a1a, 1); eye(g, 7, 8); eye(g, 13, 8); g.fillRect(8.5, 12.5, 3, 1.4) })
    make('face-talk', 20, 20, g => { g.fillStyle(0x1a1a1a, 1); eye(g, 7, 9); eye(g, 13, 9); g.fillStyle(0x1a1a1a, 1); g.fillCircle(10, 12.5, 2) })
    make('face-error', 20, 20, g => { g.lineStyle(1.6, 0xff6b6b, 1); g.lineBetween(5.5, 7.5, 8.5, 10.5); g.lineBetween(8.5, 7.5, 5.5, 10.5); g.lineBetween(11.5, 7.5, 14.5, 10.5); g.lineBetween(14.5, 7.5, 11.5, 10.5); g.lineStyle(1.4, 0x1a1a1a, 1); g.beginPath(); g.arc(10, 14, 2.5, 1.1 * Math.PI, 1.9 * Math.PI); g.strokePath() })

    // small particle dot (tintable) for FX/bubbles
    make('dot', 6, 6, g => { g.fillStyle(0xffffff, 1); g.fillCircle(3, 3, 3) })

    g.destroy()
    this.scene.start('OfficeScene') // OfficeScene emits READY once it's live
  }
}
