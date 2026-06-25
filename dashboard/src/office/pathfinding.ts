import * as EasyStar from 'easystarjs'

export type Cell = { col: number; row: number }

/**
 * Thin promise wrapper over easystar for the office floor. Built fresh whenever
 * the room is rebuilt: desk tiles are blocked (1), everything else walkable (0).
 * Couriers and wandering agents path tile-to-tile across this grid.
 */
export class PathGrid {
  private es = new EasyStar.js()

  constructor(public cols: number, public rows: number, blocked: Set<string>) {
    const grid: number[][] = []
    for (let r = 0; r < rows; r++) {
      const row: number[] = []
      for (let c = 0; c < cols; c++) row.push(blocked.has(`${c},${r}`) ? 1 : 0)
      grid.push(row)
    }
    this.es.setGrid(grid)
    this.es.setAcceptableTiles([0])
  }

  /** Resolve to a tile path (inclusive of both ends) or null if unreachable. */
  find(a: Cell, b: Cell): Promise<Cell[] | null> {
    return new Promise(resolve => {
      this.es.findPath(a.col, a.row, b.col, b.row, (path) => {
        resolve(path && path.length ? path.map(p => ({ col: p.x, row: p.y })) : null)
      })
      this.es.calculate()
    })
  }
}
