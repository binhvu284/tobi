/**
 * Isometric grid math for the office floor. A 2:1 "diamond" projection: each
 * grid cell (col,row) maps to a screen point; depth (for back-to-front draw
 * ordering) is simply col+row — larger = nearer the viewer = drawn on top.
 */

export const TILE_W = 64 // full diamond width
export const TILE_H = 32 // full diamond height (2:1)
export const HALF_W = TILE_W / 2
export const HALF_H = TILE_H / 2

/** Grid (col,row) → screen (x,y) in scene/world space, before camera offset. */
export function gridToScreen(col: number, row: number): { x: number; y: number } {
  return {
    x: (col - row) * HALF_W,
    y: (col + row) * HALF_H,
  }
}

/** Screen (x,y) → fractional grid (col,row). Inverse of gridToScreen. */
export function screenToGrid(x: number, y: number): { col: number; row: number } {
  const col = (x / HALF_W + y / HALF_H) / 2
  const row = (y / HALF_H - x / HALF_W) / 2
  return { col, row }
}

/** Back-to-front draw depth for a grid cell. */
export function isoDepth(col: number, row: number): number {
  return col + row
}
