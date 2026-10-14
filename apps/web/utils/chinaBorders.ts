import type { Map as MlMap } from "maplibre-gl"

export const CHINA_PRC_GEO_URLS = ["/geo/china-prc.geojson", "/api/geo/china-prc.json"] as const

type GeoFC = { type: string; features: Array<{ properties?: Record<string, unknown> | null; geometry?: unknown }> }

let cached: GeoFC | null = null
let inflight: Promise<GeoFC | null> | null = null

/** Load vendored PRC land + ten-dash GeoJSON (public copy, then API). */
export async function loadChinaPrcGeo(): Promise<GeoFC | null> {
  if (cached) return cached
  if (inflight) return inflight
  inflight = (async () => {
    for (const url of CHINA_PRC_GEO_URLS) {
      try {
        const res = await fetch(url)
        if (!res.ok) continue
        const data = (await res.json()) as GeoFC
        if (data?.features?.length) {
          cached = data
          return data
        }
      } catch {
        /* try next */
      }
    }
    return null
  })()
  try {
    return await inflight
  } finally {
    inflight = null
  }
}

/**
 * Hide OSM/OpenFreeMap admin lines that depict Taiwan as a separate country
 * or omit the mainland standard-map dash line. Coastlines and place labels stay.
 */
export function muteOsmCountryBoundaries(map: MlMap) {
  const layers = map.getStyle()?.layers || []
  for (const layer of layers) {
    if (layer.type !== "line") continue
    const src = `${layer.id} ${(layer as { "source-layer"?: string })["source-layer"] || ""}`.toLowerCase()
    if (src.includes("bound") || src.includes("admin") || src.includes("disputed")) {
      try {
        map.setLayoutProperty(layer.id, "visibility", "none")
      } catch {
        /* optional */
      }
    }
  }
}

type BorderTheme = "paper" | "globe"

const THEME: Record<BorderTheme, { land: string; dash: string; width: number; dashWidth: number }> = {
  paper: { land: "#6b3a24", dash: "#8a3d1c", width: 1.15, dashWidth: 1.55 },
  globe: { land: "#c4b29a", dash: "#e0c39a", width: 0.9, dashWidth: 1.35 },
}

/** Draw PRC land outline (incl. Taiwan) and 南海诸岛十段线 above the field overlay. */
export async function applyChinaBorders(map: MlMap, theme: BorderTheme = "paper") {
  if (!map.isStyleLoaded()) return
  muteOsmCountryBoundaries(map)
  const data = await loadChinaPrcGeo()
  if (!data || !map.getStyle()) return
  const paint = THEME[theme]
  const land = {
    type: "FeatureCollection",
    features: data.features.filter((f) => (f.properties as { kind?: string } | null)?.kind === "land"),
  }
  const dash = {
    type: "FeatureCollection",
    features: data.features.filter((f) => (f.properties as { kind?: string } | null)?.kind === "dash"),
  }
  const ensure = (id: string, fc: object) => {
    const src = map.getSource(id) as { setData?: (d: object) => void } | undefined
    if (src?.setData) src.setData(fc)
    else if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: fc as never })
  }
  ensure("prc-land", land)
  ensure("prc-dash", dash)
  if (!map.getLayer("prc-land-line")) {
    map.addLayer({
      id: "prc-land-line",
      type: "line",
      source: "prc-land",
      paint: {
        "line-color": paint.land,
        "line-width": paint.width,
        "line-opacity": 0.92,
      },
    })
  }
  if (!map.getLayer("prc-dash-line")) {
    map.addLayer({
      id: "prc-dash-line",
      type: "line",
      source: "prc-dash",
      paint: {
        "line-color": paint.dash,
        "line-width": paint.dashWidth,
        "line-opacity": 0.95,
        "line-dasharray": [1.8, 1.15],
      },
    })
  }
}
