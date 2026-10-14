export type Palette = "thermal" | "wind" | "rain" | "humidity" | "pressure" | "cloud" | "current" | "waves"

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "")
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

const STOPS: Record<Palette, string[]> = {
  thermal: ["#1b2a4a", "#2f5f86", "#4f93b8", "#98d0d4", "#f3f6e8", "#f6c07a", "#d96a28", "#9a2f0c"],
  wind: ["#081428", "#0c3f9a", "#1488c8", "#14b45a", "#c8dc14", "#f0c020", "#e05018"],
  current: ["#041828", "#0a4a78", "#14a0b0", "#3ee0c8", "#a8fff0"],
  waves: ["#08143c", "#0c4aa8", "#1490c0", "#1ab050", "#c8d414", "#f08a14", "#d42818", "#8a1030"],
  rain: ["#f7f4ee", "#dceee4", "#9dcec2", "#4e9aa0", "#1c6274", "#0b3b4a"],
  humidity: ["#f4e4c1", "#d5dda8", "#8fbe90", "#4a8a7a", "#2a5c58", "#1b3b40"],
  pressure: ["#4a1f5c", "#6d5aa4", "#c8c4dc", "#f7f4ee", "#e8b56a", "#b85a1c"],
  cloud: ["#1c1915", "#4a433c", "#8a8176", "#cfc4b4", "#f7f4ee"],
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
