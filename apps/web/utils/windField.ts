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
}

import { isOcean } from "./landmask"

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
  }
}

/** Equal-area-ish latitude so mid-latitudes are not starved. */
export function randomLat(south = -68, north = 68) {
  const u = Math.random() * 2 - 1
  const lat = Math.asin(u) / DEG
  return Math.min(north, Math.max(south, lat))
}

export function sampleWind(grid: WindGrid, lon: number, lat: number, oceanOnly = false): [number, number] {
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

export function targetParticleCount(width: number, dpr: number) {
  if (width < 720) return 7000
  if (width < 1100) return 12000
  if (dpr > 1.6) return 16000
  return 18000
}

export function wrapLon(lon: number) {
  if (lon > 180) return lon - 360
  if (lon < -180) return lon + 360
  return lon
}
