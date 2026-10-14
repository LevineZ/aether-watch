/** Shared bilinear / bicubic sampling and render-side grid densification. */

export function sampleBilinear(grid: (number | null)[][], x: number, y: number): number | null {
  const ny = grid.length
  const nx = grid[0]?.length || 0
  if (!nx || !ny) return null
  const x0 = Math.max(0, Math.min(nx - 1, Math.floor(x)))
  const y0 = Math.max(0, Math.min(ny - 1, Math.floor(y)))
  const x1 = Math.min(nx - 1, x0 + 1)
  const y1 = Math.min(ny - 1, y0 + 1)
  const fx = x - x0
  const fy = y - y0
  const v00 = grid[y0][x0]
  const v10 = grid[y0][x1]
  const v01 = grid[y1][x0]
  const v11 = grid[y1][x1]
  const w00 = v00 == null || !Number.isFinite(v00) ? 0 : (1 - fx) * (1 - fy)
  const w10 = v10 == null || !Number.isFinite(v10) ? 0 : fx * (1 - fy)
  const w01 = v01 == null || !Number.isFinite(v01) ? 0 : (1 - fx) * fy
  const w11 = v11 == null || !Number.isFinite(v11) ? 0 : fx * fy
  const w = w00 + w10 + w01 + w11
  if (w <= 1e-6) return pickValid([v00, v10, v01, v11])
  return ((v00 || 0) * w00 + (v10 || 0) * w10 + (v01 || 0) * w01 + (v11 || 0) * w11) / w
}

export function sampleBicubic(grid: (number | null)[][], x: number, y: number): number | null {
  const ny = grid.length
  const nx = grid[0]?.length || 0
  if (!nx || !ny) return null
  const x0 = Math.floor(x)
  const y0 = Math.floor(y)
  const fx = x - x0
  const fy = y - y0
  const cols: number[] = []
  for (let jj = -1; jj <= 2; jj++) {
    const row: number[] = []
    for (let ii = -1; ii <= 2; ii++) {
      const v = at(grid, x0 + ii, y0 + jj)
      if (v == null) return sampleBilinear(grid, x, y)
      row.push(v)
    }
    cols.push(cubic(row[0], row[1], row[2], row[3], fx))
  }
  return cubic(cols[0], cols[1], cols[2], cols[3], fy)
}

/** Bilinear upsample of a coarse scalar grid (render-side densification). */
export function upsampleScalarGrid(grid: (number | null)[][], scale: number): (number | null)[][] {
  const srcNy = grid.length
  const srcNx = grid[0]?.length || 0
  if (!srcNx || !srcNy) return grid
  const s = Math.max(1, Math.round(scale))
  if (s === 1) return grid
  const nx = Math.max(2, (srcNx - 1) * s + 1)
  const ny = Math.max(2, (srcNy - 1) * s + 1)
  const out: (number | null)[][] = Array.from({ length: ny }, () => Array<number | null>(nx).fill(null))
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const x = (i / Math.max(1, nx - 1)) * Math.max(0, srcNx - 1)
      const y = (j / Math.max(1, ny - 1)) * Math.max(0, srcNy - 1)
      out[j][i] = sampleBilinear(grid, x, y)
    }
  }
  return out
}

export type VectorPatch = {
  u: Float32Array
  v: Float32Array
  width: number
  height: number
  mask: Uint8Array | null
}

/** Bilinear upsample of a packed u/v field so particles follow smooth interpolated vectors. */
export function upsampleVectorField(
  u: Float32Array,
  v: Float32Array,
  width: number,
  height: number,
  scale: number,
  mask: Uint8Array | null = null,
): VectorPatch {
  const s = Math.max(1, Math.round(scale))
  if (s === 1 || width < 2 || height < 2) {
    return { u, v, width, height, mask }
  }
  const nw = Math.max(2, (width - 1) * s + 1)
  const nh = Math.max(2, (height - 1) * s + 1)
  const ou = new Float32Array(nw * nh)
  const ov = new Float32Array(nw * nh)
  const om = mask ? new Uint8Array(nw * nh) : null
  for (let j = 0; j < nh; j++) {
    for (let i = 0; i < nw; i++) {
      const x = (i / Math.max(1, nw - 1)) * (width - 1)
      const y = (j / Math.max(1, nh - 1)) * (height - 1)
      const [uu, vv, mm] = samplePackedBilinear(u, v, width, height, x, y, mask)
      const o = j * nw + i
      ou[o] = uu
      ov[o] = vv
      if (om) om[o] = mm
    }
  }
  return { u: ou, v: ov, width: nw, height: nh, mask: om }
}

export function samplePackedBilinear(
  u: Float32Array,
  v: Float32Array,
  width: number,
  height: number,
  x: number,
  y: number,
  mask: Uint8Array | null = null,
): [number, number, number] {
  const x0 = Math.max(0, Math.min(width - 1, Math.floor(x)))
  const y0 = Math.max(0, Math.min(height - 1, Math.floor(y)))
  const x1 = Math.min(width - 1, x0 + 1)
  const y1 = Math.min(height - 1, y0 + 1)
  const fx = x - x0
  const fy = y - y0
  const i00 = y0 * width + x0
  const i10 = y0 * width + x1
  const i01 = y1 * width + x0
  const i11 = y1 * width + x1
  const w00 = (1 - fx) * (1 - fy)
  const w10 = fx * (1 - fy)
  const w01 = (1 - fx) * fy
  const w11 = fx * fy
  const uu = u[i00] * w00 + u[i10] * w10 + u[i01] * w01 + u[i11] * w11
  const vv = v[i00] * w00 + v[i10] * w10 + v[i01] * w01 + v[i11] * w11
  if (!mask) return [uu, vv, 1]
  const m = (mask[i00] || 0) * w00 + (mask[i10] || 0) * w10 + (mask[i01] || 0) * w01 + (mask[i11] || 0) * w11
  return [uu, vv, m > 0.25 ? 1 : 0]
}

function pickValid(vals: Array<number | null | undefined>) {
  for (const v of vals) {
    if (v != null && Number.isFinite(v)) return v
  }
  return null
}

function at(grid: (number | null)[][], ix: number, iy: number) {
  const ny = grid.length
  const nx = grid[0]?.length || 0
  const x = Math.max(0, Math.min(nx - 1, ix))
  const y = Math.max(0, Math.min(ny - 1, iy))
  const v = grid[y][x]
  return v != null && Number.isFinite(v) ? v : null
}

function cubic(p0: number, p1: number, p2: number, p3: number, t: number) {
  return (
    p1 +
    0.5 *
      t *
      (p2 - p0 + t * (2 * p0 - 5 * p1 + 4 * p2 - p3 + t * (3 * (p1 - p2) + p3 - p0)))
  )
}
