import { upsampleVectorField } from "./interp"
import { isOcean, randomOceanPoint } from "./landmask"
import type { ScalarField } from "./rasterField"

export const FLOW_VMAX = { current: 1.35, wind: 16 } as const

/** Render-side densification of the coarse Open-Meteo u/v grid. */
export const VECTOR_UPSAMPLE = 4

export type Wind = {
  width: number
  height: number
  west: number
  south: number
  east: number
  north: number
  u: number[] | Float32Array
  v: number[] | Float32Array
  mask?: number[] | Uint8Array
  kind?: string
  nest?: Wind | null
}

export type WindGrid = {
  width: number
  height: number
  west: number
  south: number
  east: number
  north: number
  u: Float32Array
  v: Float32Array
  mask: Uint8Array | null
  nest: WindGrid | null
}

const DEG = Math.PI / 180
const MAX_LAT = 78

export function packWind(wind: Wind, upsample = VECTOR_UPSAMPLE): WindGrid {
  const u = wind.u instanceof Float32Array ? wind.u : new Float32Array(wind.u)
  const v = wind.v instanceof Float32Array ? wind.v : new Float32Array(wind.v)
  const mask = wind.mask ? (wind.mask instanceof Uint8Array ? wind.mask : Uint8Array.from(wind.mask)) : null
  const dense = upsampleVectorField(u, v, wind.width, wind.height, upsample, mask)
  return {
    width: dense.width,
    height: dense.height,
    west: wind.west,
    south: wind.south,
    east: wind.east,
    north: wind.north,
    u: dense.u,
    v: dense.v,
    mask: dense.mask,
    nest: wind.nest ? packWind(wind.nest, upsample) : null,
  }
}

/** Equal-area-ish latitude so mid-latitudes are not starved. */
export function randomLat(south = -68, north = 68) {
  const u = Math.random() * 2 - 1
  const lat = Math.asin(u) / DEG
  return Math.min(north, Math.max(south, lat))
}

function inPatch(grid: WindGrid, lon: number, lat: number) {
  return lon >= grid.west && lon <= grid.east && lat >= grid.south && lat <= grid.north
}

export function sampleWind(grid: WindGrid, lon: number, lat: number, oceanOnly = false): [number, number] {
  if (grid.nest && inPatch(grid.nest, lon, lat)) {
    const nested = sampleWind(grid.nest, lon, lat, oceanOnly)
    if (Math.hypot(nested[0], nested[1]) > 1e-4) return nested
  }
  if (oceanOnly && !isOcean(lon, lat)) return [0, 0]
  const { width: w, height: h } = grid
  if (w < 2 || h < 2) return [0, 0]
  let x = ((lon - grid.west) / (grid.east - grid.west)) * (w - 1)
  if (x < 0) x += w - 1
  if (x >= w - 1) x -= w - 1
  const y = ((grid.north - lat) / (grid.north - grid.south)) * (h - 1)
  if (y < 0 || y > h - 1) return [0, 0]
  const x0 = Math.floor(x)
  const y0 = Math.max(0, Math.min(h - 2, Math.floor(y)))
  const x1 = x0 + 1
  const y1 = y0 + 1
  const fx = x - x0
  const fy = y - y0
  const i00 = y0 * w + x0
  const i10 = y0 * w + x1
  const i01 = y1 * w + x0
  const i11 = y1 * w + x1
  if (grid.mask) {
    const m =
      (grid.mask[i00] || 0) + (grid.mask[i10] || 0) + (grid.mask[i01] || 0) + (grid.mask[i11] || 0)
    if (m === 0) return [0, 0]
  }
  const u =
    grid.u[i00] * (1 - fx) * (1 - fy) +
    grid.u[i10] * fx * (1 - fy) +
    grid.u[i01] * (1 - fx) * fy +
    grid.u[i11] * fx * fy
  const v =
    grid.v[i00] * (1 - fx) * (1 - fy) +
    grid.v[i10] * fx * (1 - fy) +
    grid.v[i01] * (1 - fx) * fy +
    grid.v[i11] * fx * fy
  return [u, v]
}

export function mercatorX(lon: number) {
  return (lon + 180) / 360
}

export function mercatorY(lat: number) {
  const clamped = Math.min(MAX_LAT, Math.max(-MAX_LAT, lat))
  const s = Math.sin(clamped * DEG)
  const y = 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)
  return Math.min(0.9999, Math.max(0.0001, y))
}

/**
 * Sheet coverage for thin faded trails. Currents want more overlap so the field
 * reads as nullschool streamlines rather than sparse tubes; wind stays a bit sparser.
 */
export function targetParticleCount(width: number, dpr: number, kind: "wind" | "current" = "wind") {
  const bias = kind === "current" ? 1.55 : 1.05
  if (width < 720) return Math.round(9000 * bias)
  if (width < 1100) return Math.round(12000 * bias)
  if (dpr > 1.6) return Math.round(14000 * bias)
  return Math.round(16000 * bias)
}

/** Client-side speed scalar from the same u/v grid (no extra Open-Meteo fetch). */
export function windSpeedField(
  wind: Wind,
  opts?: { oceanOnly?: boolean; vmax?: number },
): ScalarField {
  const grid = packWind(wind)
  const oceanOnly = !!opts?.oceanOnly
  const vmax = opts?.vmax ?? (oceanOnly ? FLOW_VMAX.current : FLOW_VMAX.wind)
  const nx = grid.width
  const ny = grid.height
  const lons = Array.from({ length: nx }, (_, i) => grid.west + (i / Math.max(1, nx - 1)) * (grid.east - grid.west))
  const lats = Array.from({ length: ny }, (_, j) => grid.south + (j / Math.max(1, ny - 1)) * (grid.north - grid.south))
  const values: (number | null)[][] = []
  for (let j = 0; j < ny; j++) {
    const lat = lats[j]
    const row: (number | null)[] = []
    for (let i = 0; i < nx; i++) {
      const lon = lons[i]
      if (oceanOnly && !isOcean(lon, lat)) {
        row.push(null)
        continue
      }
      const [u, v] = sampleWind(grid, lon, lat, oceanOnly)
      row.push(Math.hypot(u, v))
    }
    values.push(row)
  }
  return {
    lats,
    lons,
    values,
    min: 0,
    max: vmax,
    unit: "m/s",
    bbox: { west: grid.west, south: grid.south, east: grid.east, north: grid.north },
  }
}

export function wrapLon(lon: number) {
  if (lon > 180) return lon - 360
  if (lon < -180) return lon + 360
  return lon
}

/** Ocean basins for current seeds. Weights are global-first; China seas are a modest nest, not SCS-only. */
export const CURRENT_BASINS: { name: string; weight: number; west: number; south: number; east: number; north: number }[] = [
  { name: "n-pacific", weight: 0.2, west: 128, south: 0, east: 240, north: 52 },
  { name: "s-pacific", weight: 0.14, west: 150, south: -52, east: 290, north: 0 },
  { name: "n-atlantic", weight: 0.16, west: -80, south: 0, east: 8, north: 64 },
  { name: "s-atlantic", weight: 0.1, west: -70, south: -52, east: 18, north: 0 },
  { name: "indian", weight: 0.12, west: 38, south: -48, east: 108, north: 24 },
  { name: "southern", weight: 0.14, west: -180, south: -70, east: 180, north: -42 },
  { name: "arctic", weight: 0.04, west: -180, south: 68, east: 180, north: 80 },
  { name: "china-seas", weight: 0.08, west: 105, south: 3, east: 132, north: 41 },
  { name: "scs", weight: 0.02, west: 105.2, south: 3.4, east: 121, north: 23.2 },
]

const BASIN_WEIGHT_SUM = CURRENT_BASINS.reduce((s, b) => s + b.weight, 0)

export function randomOceanPointWrapped(west: number, south: number, east: number, north: number): [number, number] {
  const span = east - west
  for (let t = 0; t < 28; t++) {
    const lon = wrapLon(west + Math.random() * span)
    const lat = south + Math.random() * (north - south)
    if (isOcean(lon, lat)) return [lon, lat]
  }
  return randomOceanPoint()
}

/** Distributed current seeds: global oceans first, light China-seas nest, no SCS-only pile-up. */
export function randomCurrentPoint(): [number, number] {
  const r = Math.random() * BASIN_WEIGHT_SUM
  let acc = 0
  for (const basin of CURRENT_BASINS) {
    acc += basin.weight
    if (r <= acc) return randomOceanPointWrapped(basin.west, basin.south, basin.east, basin.north)
  }
  return randomOceanPoint()
}
