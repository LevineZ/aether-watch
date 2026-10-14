export type Palette = "thermal" | "wind" | "rain" | "humidity" | "pressure" | "cloud" | "current"

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "")
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

const STOPS: Record<Palette, string[]> = {
  thermal: ["#1d3557", "#457b9d", "#a8dadc", "#f1faee", "#f4a261", "#c1440e", "#6d2b0a"],
  wind: ["#0b1d2a", "#1b4d6b", "#3f8f7a", "#d9c56e", "#f3f0e6"],
  current: ["#03141c", "#0a3a4a", "#1c8a9a", "#5ad0c8", "#e7fff6"],
  rain: ["#f7f4ee", "#cde4d6", "#6db3a8", "#1d6a7a", "#0b3b4a"],
  humidity: ["#f4e4c1", "#c4d6a0", "#6aa88a", "#2f6f6a", "#1b3b40"],
  pressure: ["#5b2c6f", "#7b6bb0", "#f7f4ee", "#e0a454", "#9a3412"],
  cloud: ["#1c1915", "#6b6258", "#cfc4b4", "#f7f4ee"],
}

export function colorAt(palette: Palette, t: number): [number, number, number] {
  const stops = STOPS[palette] || STOPS.thermal
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1)
  const i = Math.min(stops.length - 2, Math.floor(x))
  const f = x - i
  const a = hexToRgb(stops[i])
  const b = hexToRgb(stops[i + 1])
  return [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)]
}

export function paletteCss(palette: Palette) {
  return `linear-gradient(90deg, ${(STOPS[palette] || STOPS.thermal).join(",")})`
}
