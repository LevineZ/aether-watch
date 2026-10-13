import { colorAt, type Palette } from "~/utils/colormap"

export type ScalarField = {
  lats: number[]
  lons: number[]
  values: (number | null)[][]
  min: number
  max: number
  unit?: string
  valid_time?: string | null
  bbox?: { west: number; south: number; east: number; north: number }
}

export function rasterizeField(field: ScalarField, palette: Palette, width = 256, height = 192) {
  const canvas = document.createElement("canvas")
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d")
  if (!ctx) return canvas.toDataURL()
  const img = ctx.createImageData(width, height)
  const ny = field.values.length
  const nx = field.values[0]?.length || 0
  const span = field.max - field.min || 1
  for (let j = 0; j < height; j++) {
    for (let i = 0; i < width; i++) {
      const x = (i / Math.max(1, width - 1)) * Math.max(0, nx - 1)
      const y = (1 - j / Math.max(1, height - 1)) * Math.max(0, ny - 1)
      const v = sampleBilinear(field.values, x, y)
      const o = (j * width + i) * 4
      if (v == null) {
        img.data[o + 3] = 0
        continue
      }
      const [r, g, b] = colorAt(palette, (v - field.min) / span)
      img.data[o] = r
      img.data[o + 1] = g
      img.data[o + 2] = b
      img.data[o + 3] = 210
    }
  }
  ctx.putImageData(img, 0, 0)
  return canvas.toDataURL("image/png")
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

function sampleBilinear(grid: (number | null)[][], x: number, y: number) {
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
  if (v00 == null || v10 == null || v01 == null || v11 == null) {
    return v00 ?? v10 ?? v01 ?? v11
  }
  return v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) + v01 * (1 - fx) * fy + v11 * fx * fy
}
