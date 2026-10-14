import { isOcean, randomOceanPoint, randomOceanPointIn } from "./landmask"

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

export function packWind(wind: Wind): WindGrid {
  return {
    width: wind.width,
    height: wind.height,
    west: wind.west,
    south: wind.south,
    east: wind.east,
    north: wind.north,
    u: wind.u instanceof Float32Array ? wind.u : new Float32Array(wind.u),
    v: wind.v instanceof Float32Array ? wind.v : new Float32Array(wind.v),
    mask: wind.mask ? (wind.mask instanceof Uint8Array ? wind.mask : Uint8Array.from(wind.mask)) : null,
    nest: wind.nest ? packWind(wind.nest) : null,
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

export function targetParticleCount(width: number, dpr: number, kind: "wind" | "current" = "wind") {
  const bias = kind === "current" ? 1.2 : 1
  if (width < 720) return Math.round(11000 * bias)
  if (width < 1100) return Math.round(18000 * bias)
  if (dpr > 1.6) return Math.round(24000 * bias)
  return Math.round(28000 * bias)
}

export function wrapLon(lon: number) {
  if (lon > 180) return lon - 360
  if (lon < -180) return lon + 360
  return lon
}

/** Bias current seeds into SCS / China seas so the default globe is not empty there. */
export function randomCurrentPoint(): [number, number] {
  const r = Math.random()
  if (r < 0.3) return randomOceanPointIn(105.2, 3.4, 121.0, 23.2)
  if (r < 0.44) return randomOceanPointIn(118.0, 22.0, 131.0, 41.0)
  return randomOceanPoint()
}
