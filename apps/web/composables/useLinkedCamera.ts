export type MapCamera = {
  center: [number, number]
  zoom: number
  bearing: number
  pitch: number
}

export type GeoBbox = {
  west: number
  south: number
  east: number
  north: number
}

/** Default China frame used by every linked forecast map. */
export const CHINA_CAMERA: MapCamera = {
  center: [104.0, 35.6],
  zoom: 3.15,
  bearing: 0,
  pitch: 0,
}

export const CHINA_BBOX: GeoBbox = { west: 73, south: 18, east: 135, north: 54 }

export const LEAD_HOURS = [0, 6, 12, 18, 24, 36, 48, 60, 72, 96, 120] as const

export function camerasClose(a: MapCamera, b: MapCamera) {
  return (
    Math.abs(a.center[0] - b.center[0]) < 1e-7 &&
    Math.abs(a.center[1] - b.center[1]) < 1e-7 &&
    Math.abs(a.zoom - b.zoom) < 1e-5 &&
    Math.abs(a.bearing - b.bearing) < 1e-5 &&
    Math.abs(a.pitch - b.pitch) < 1e-5
  )
}

export function clampZoom(z: number) {
  return Math.min(8.2, Math.max(2.15, z))
}

export function beijingShort(iso?: string | null) {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso).replace("T", " ").slice(5, 16)
  const fmt = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
  const parts = Object.fromEntries(fmt.formatToParts(d).map((p) => [p.type, p.value]))
  return `${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`
}
