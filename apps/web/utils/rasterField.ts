import { colorAt, type Palette } from "~/utils/colormap"
import { sampleBicubic, sampleBilinear } from "~/utils/interp"

export { sampleBicubic, sampleBilinear }

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
  variable?: string
  source?: string
  provider?: string
  kind?: string
  nx?: number
  ny?: number
  filled?: number
  fallback?: boolean
  stale?: boolean
  degraded?: string
  error?: string
  unavailable?: boolean
}

const rasterMemo = new Map<string, string>()
const MEMO_MAX = 24

export function rasterizeField(
  field: ScalarField,
  palette: Palette,
  width = 1280,
  height = 960,
  mode: "bilinear" | "bicubic" = "bilinear",
  opts?: { signalAlpha?: boolean; opacity?: number; prefilter?: boolean },
) {
  const ny = field.values.length
  const nx = field.values[0]?.length || 0
  const signal = !!opts?.signalAlpha
  const opacity = opts?.opacity ?? 228
  const prefilter = !!opts?.prefilter
  const key = `${field.model || ""}|${field.valid_time || ""}|${nx}x${ny}|${field.min}|${field.max}|${palette}|${width}x${height}|${mode}|${signal}|${opacity}|${prefilter}`
  const hit = rasterMemo.get(key)
  if (hit) return hit

  const canvas = document.createElement("canvas")
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d", { alpha: true })
  if (!ctx) return canvas.toDataURL()
  const img = ctx.createImageData(width, height)
  const span = field.max - field.min || 1
  const grid = prefilter ? prefilterGrid(field.values) : field.values
  const sample = mode === "bicubic" ? sampleBicubic : sampleBilinear
  for (let j = 0; j < height; j++) {
    for (let i = 0; i < width; i++) {
      const x = (i / Math.max(1, width - 1)) * Math.max(0, nx - 1)
      const y = (1 - j / Math.max(1, height - 1)) * Math.max(0, ny - 1)
      const v = sample(grid, x, y)
      const o = (j * width + i) * 4
      if (v == null) {
        img.data[o + 3] = 0
        continue
      }
      const t = Math.min(1, Math.max(0, (v - field.min) / span))
      const [r, g, b] = colorAt(palette, t)
      const edge = edgeFade(i, j, width, height)
      const a = (signal ? opacity * t ** 0.68 : opacity) * edge
      img.data[o] = r
      img.data[o + 1] = g
      img.data[o + 2] = b
      img.data[o + 3] = Math.round(a)
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

function edgeFade(i: number, j: number, w: number, h: number) {
  const mx = Math.min(i, w - 1 - i) / Math.max(1, w * 0.006)
  const my = Math.min(j, h - 1 - j) / Math.max(1, h * 0.006)
  return Math.min(1, Math.max(0.72, Math.min(mx, my)))
}

/** Optional 3×3 valid-neighbor blur. Off by default so bilinear stays continuous, not blotchy. */
export function prefilterGrid(grid: (number | null)[][]): (number | null)[][] {
  const ny = grid.length
  const nx = grid[0]?.length || 0
  if (!nx || !ny) return grid
  const out: (number | null)[][] = Array.from({ length: ny }, () => Array<number | null>(nx).fill(null))
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      let acc = 0
      let w = 0
      for (let dj = -1; dj <= 1; dj++) {
        for (let di = -1; di <= 1; di++) {
          const y = j + dj
          const x = i + di
          if (y < 0 || y >= ny || x < 0 || x >= nx) continue
          const v = grid[y][x]
          if (v == null || !Number.isFinite(v)) continue
          const k = di === 0 && dj === 0 ? 4 : di === 0 || dj === 0 ? 2 : 1
          acc += v * k
          w += k
        }
      }
      out[j][i] = w ? acc / w : null
    }
  }
  return out
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
