/** Shared current-sheet segment tests. Kept out of windLayer so Node tests skip MapLibre. */

export const MAX_MERCATOR_WRAP = 0.12
export const MAX_MERCATOR_SEG = 0.032
export const MIN_COSC_CURRENT = 0.14
export const MIN_COSC_WIND = 0.05
export const DEG = Math.PI / 180

export function mercatorLat(y: number) {
  const n = Math.PI * (1 - 2 * y)
  return (2 * Math.atan(Math.exp(n)) - Math.PI / 2) / DEG
}

/** Spherical visibility vs camera; low values are the globe silhouette / far side. */
export function frontCosc(lon: number, lat: number, camLon: number, sinCam: number, cosCam: number) {
  const φ = lat * DEG
  const dλ = (lon - camLon) * DEG
  return Math.sin(φ) * sinCam + Math.cos(φ) * cosCam * Math.cos(dλ)
}

/** CPU reject for date-line wraps, jumps, and silhouette points that become NDC slabs. */
export function currentSegmentOk(
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  camLon: number,
  camLat: number,
  minCos = MIN_COSC_CURRENT,
) {
  const dx = x1 - x0
  const dy = y1 - y0
  if (Math.abs(dx) > MAX_MERCATOR_WRAP) return false
  if (dx * dx + dy * dy > MAX_MERCATOR_SEG * MAX_MERCATOR_SEG) return false
  const sinCam = Math.sin(camLat * DEG)
  const cosCam = Math.cos(camLat * DEG)
  const a = frontCosc(x0 * 360 - 180, mercatorLat(y0), camLon, sinCam, cosCam)
  const b = frontCosc(x1 * 360 - 180, mercatorLat(y1), camLon, sinCam, cosCam)
  return a >= minCos && b >= minCos
}
