import { colorAt, type Palette } from "~/utils/colormap"

export type ScalarField = {
  lats: number[]
  lons: number[]
  values: (number | null)[][]
  min: number
  max: number
  unit?: string
  valid_time?: string | null
  init_time?: string | null
  lead_hours?: number
  step?: number
  bbox?: { west: number; south: number; east: number; north: number }
  model?: string
  model_id?: string
  source?: string
  provider?: string
  kind?: string
  nx?: number
  ny?: number
}

const rasterMemo = new Map<string, string>()
const MEMO_MAX = 24

export function rasterizeField(
  field: ScalarField,
  palette: Palette,
  width = 1024,
  height = 768,
  mode: "bilinear" | "bicubic" = "bicubic",
  opts?: { signalAlpha?: boolean; opacity?: number },
) {
  const ny = field.values.length
  const nx = field.values[0]?.length || 0
  const signal = !!opts?.signalAlpha
  const opacity = opts?.opacity ?? 208
  const key = `${field.model || ""}|${field.valid_time || ""}|${nx}x${ny}|${field.min}|${field.max}|${palette}|${width}x${height}|${mode}|${signal}|${opacity}`
  const hit = rasterMemo.get(key)
  if (hit) return hit

  const canvas = document.createElement("canvas")
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d", { alpha: true })
  if (!ctx) return canvas.toDataURL()
  const img = ctx.createImageData(width, height)
  const span = field.max - field.min || 1
  const sample = mode === "bicubic" ? sampleBicubic : sampleBilinear
  for (let j = 0; j < height; j++) {
    for (let i = 0; i < width; i++) {
      const x = (i / Math.max(1, width - 1)) * Math.max(0, nx - 1)
      const y = (1 - j / Math.max(1, height - 1)) * Math.max(0, ny - 1)
      const v = sample(field.values, x, y)
      const o = (j * width + i) * 4
      if (v == null) {
        img.data[o + 3] = 0
        continue
      }
      const t = Math.min(1, Math.max(0, (v - field.min) / span))
      const [r, g, b] = colorAt(palette, t)
      img.data[o] = r
      img.data[o + 1] = g
      img.data[o + 2] = b
      img.data[o + 3] = signal ? Math.round(opacity * t ** 0.72) : opacity
    }
  }
  ctx.putImageData(img, 0, 0)
  const url = canvas.toDataURL("image/png")
  rasterMemo.set(key, url)
  if (rasterMemo.size > MEMO_MAX) {
    const first = rasterMemo.keys().next().value
    if (first) rasterMemo.delete(first)
  }
  return url
}

export function fieldCorners(field: ScalarField): [[number, number], [number, number], [number, number], [number, number]] {
  const west = field.bbox?.west ?? field.lons[0]
  const east = field.bbox?.east ?? field.lons[field.lons.length - 1]
  const south = field.bbox?.south ?? field.lats[0]
  const north = field.bbox?.north ?? field.lats[field.lats.length - 1]
  return [
    [west, north],
    [east, north],
    [east, south],
    [west, south],
  ]
}

function pickValid(vals: Array<number | null | undefined>) {
  for (const v of vals) {
    if (v != null && Number.isFinite(v)) return v
  }
  return null
}

export function sampleBilinear(grid: (number | null)[][], x: number, y: number) {
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
  const known = [v00, v10, v01, v11].filter((v): v is number => v != null && Number.isFinite(v))
  if (known.length === 0) return null
  if (known.length < 4) {
    const w00 = (v00 == null ? 0 : (1 - fx) * (1 - fy))
    const w10 = (v10 == null ? 0 : fx * (1 - fy))
    const w01 = (v01 == null ? 0 : (1 - fx) * fy)
    const w11 = (v11 == null ? 0 : fx * fy)
    const w = w00 + w10 + w01 + w11
    if (w <= 1e-6) return pickValid([v00, v10, v01, v11])
    return ((v00 || 0) * w00 + (v10 || 0) * w10 + (v01 || 0) * w01 + (v11 || 0) * w11) / w
  }
  return v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) + v01 * (1 - fx) * fy + v11 * fx * fy
}

function cubic(p0: number, p1: number, p2: number, p3: number, t: number) {
  return (
    p1 +
    0.5 *
      t *
      (p2 - p0 + t * (2 * p0 - 5 * p1 + 4 * p2 - p3 + t * (3 * (p1 - p2) + p3 - p0)))
  )
}

function at(grid: (number | null)[][], ix: number, iy: number) {
  const ny = grid.length
  const nx = grid[0]?.length || 0
  const x = Math.max(0, Math.min(nx - 1, ix))
  const y = Math.max(0, Math.min(ny - 1, iy))
  const v = grid[y][x]
  return v != null && Number.isFinite(v) ? v : null
}

export function sampleBicubic(grid: (number | null)[][], x: number, y: number) {
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
      if (v == null) {
        return sampleBilinear(grid, x, y)
      }
      row.push(v)
    }
    cols.push(cubic(row[0], row[1], row[2], row[3], fx))
  }
  return cubic(cols[0], cols[1], cols[2], cols[3], fy)
}
