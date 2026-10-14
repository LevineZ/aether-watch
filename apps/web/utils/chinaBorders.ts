import type { Map as MlMap } from "maplibre-gl"

export type ChinaBorderTheme = "light" | "dark"

const SOURCE_ID = "china-bounds"
const LAND_ID = "china-bounds-land"
const DASH_ID = "china-bounds-dash"

type BoundsGeo = {
  type: string
  features?: unknown[]
}

const cache: { url: string; data: BoundsGeo | null; inflight: Promise<BoundsGeo | null> | null } = {
  url: "",
  data: null,
  inflight: null,
}

const THEMES: Record<
  ChinaBorderTheme,
  { land: string; dash: string; halo: string; width: number }
> = {
  // 观潮 forecast overlays: dark ink, dashed national stroke + 十段线 segments.
  light: { land: "#1f1d17", dash: "#1f1d17", halo: "#fffdf8", width: 1.55 },
  dark: { land: "#e4d2b8", dash: "#f0e0c8", halo: "#05070d", width: 1.7 },
}

async function loadBounds(url: string): Promise<BoundsGeo | null> {
  if (cache.url === url && cache.data) return cache.data
  if (cache.inflight) return cache.inflight
  cache.inflight = (async () => {
    try {
      const res = await fetch(url)
      if (!res.ok) return null
      const data = (await res.json()) as BoundsGeo
      cache.url = url
      cache.data = data
      return data
    } catch {
      return null
    } finally {
      cache.inflight = null
    }
  })()
  return cache.inflight
}

function moveToTop(map: MlMap, id: string) {
  if (map.getLayer(id)) {
    try {
      map.moveLayer(id)
    } catch {
      /* already top or missing */
    }
  }
}

/** PRC land outline + 十段线 as dashed MapLibre lines. Idempotent. */
export async function addChinaBorders(
  map: MlMap,
  opts: { url: string; theme?: ChinaBorderTheme },
) {
  const theme = THEMES[opts.theme || "light"]
  const data = await loadBounds(opts.url)
  if (!data?.features?.length) return

  if (!map.getSource(SOURCE_ID)) {
    map.addSource(SOURCE_ID, { type: "geojson", data: data as never })
  }

  const dasharray: [number, number] = [2.4, 1.7]
  const width = [
    "interpolate",
    ["linear"],
    ["zoom"],
    0,
    theme.width,
    2,
    theme.width + 0.25,
    4,
    theme.width + 0.55,
    6,
    theme.width + 0.85,
  ]

  if (!map.getLayer(LAND_ID)) {
    map.addLayer({
      id: `${LAND_ID}-halo`,
      type: "line",
      source: SOURCE_ID,
      filter: ["==", ["get", "kind"], "land"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": theme.halo,
        "line-opacity": 0.55,
        "line-width": ["+", width, 1.15] as never,
        "line-dasharray": dasharray,
      },
    })
    map.addLayer({
      id: LAND_ID,
      type: "line",
      source: SOURCE_ID,
      filter: ["==", ["get", "kind"], "land"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": theme.land,
        "line-opacity": 0.92,
        "line-width": width as never,
        "line-dasharray": dasharray,
      },
    })
  }

  if (!map.getLayer(DASH_ID)) {
    // 十段线: geometry is already short segments; keep them readable at globe zoom.
    map.addLayer({
      id: `${DASH_ID}-halo`,
      type: "line",
      source: SOURCE_ID,
      filter: ["==", ["get", "kind"], "dash"],
      layout: { "line-cap": "butt", "line-join": "round" },
      paint: {
        "line-color": theme.halo,
        "line-opacity": 0.5,
        "line-width": ["+", width, 1.3] as never,
      },
    })
    map.addLayer({
      id: DASH_ID,
      type: "line",
      source: SOURCE_ID,
      filter: ["==", ["get", "kind"], "dash"],
      layout: { "line-cap": "butt", "line-join": "round" },
      paint: {
        "line-color": theme.dash,
        "line-opacity": 0.95,
        "line-width": ["+", width, 0.35] as never,
      },
    })
  }

  for (const id of [`${LAND_ID}-halo`, LAND_ID, `${DASH_ID}-halo`, DASH_ID]) {
    moveToTop(map, id)
  }
}

export function raiseChinaBorders(map: MlMap) {
  for (const id of [`${LAND_ID}-halo`, LAND_ID, `${DASH_ID}-halo`, DASH_ID]) {
    moveToTop(map, id)
  }
}
