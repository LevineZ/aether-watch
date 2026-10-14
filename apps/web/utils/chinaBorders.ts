import type { Map as MlMap } from "maplibre-gl"

export const CHINA_PRC_GEO_URLS = ["/geo/china-prc.geojson", "/api/geo/china-prc.json"] as const

export const PRC_LAYER_IDS = [
  "prc-land-fill",
  "prc-land-case",
  "prc-dash-case",
  "prc-land-line",
  "prc-dash-line",
] as const

type GeoFC = { type: string; features: Array<{ properties?: Record<string, unknown> | null; geometry?: unknown }> }

let cached: GeoFC | null = null
let inflight: Promise<GeoFC | null> | null = null
let loadFailures = 0

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

type ThemePaint = {
  fill: string
  fillOpacity: number
  case: string
  land: string
  dash: string
  landWidth: unknown
  dashWidth: unknown
  caseWidth: unknown
  dashCaseWidth: unknown
  dasharray: number[]
}

const zoomWidth = (z1: number, z3: number, z6: number) =>
  ["interpolate", ["linear"], ["zoom"], 1, z1, 3, z3, 6, z6] as unknown

const THEME: Record<BorderTheme, ThemePaint> = {
  paper: {
    fill: "#c1440e",
    fillOpacity: 0.07,
    case: "#fff6e4",
    land: "#c1440e",
    dash: "#e07a14",
    landWidth: zoomWidth(2.15, 3.15, 4.4),
    dashWidth: zoomWidth(2.55, 3.7, 5.1),
    caseWidth: zoomWidth(4.4, 6.2, 8.2),
    dashCaseWidth: zoomWidth(5.0, 7.0, 9.2),
    dasharray: [2.6, 1.35],
  },
  globe: {
    fill: "#f6d27a",
    fillOpacity: 0.1,
    case: "#1a0c04",
    land: "#ffd56a",
    dash: "#ffe9a8",
    landWidth: zoomWidth(2.4, 3.4, 4.8),
    dashWidth: zoomWidth(2.9, 4.1, 5.6),
    caseWidth: zoomWidth(5.0, 6.8, 9.0),
    dashCaseWidth: zoomWidth(5.6, 7.6, 10.2),
    dasharray: [2.4, 1.2],
  },
}

export function firstPrcLayerId(map: MlMap): string | undefined {
  return PRC_LAYER_IDS.find((id) => map.getLayer(id))
}

/** Keep the highlighted PRC outline + 十段线 above heatmaps / particles. */
export function raiseChinaBorders(map: MlMap) {
  for (const id of PRC_LAYER_IDS) {
    if (map.getLayer(id)) {
      try {
        map.moveLayer(id)
      } catch {
        /* already top or style busy */
      }
    }
  }
}

function setLinePaint(
  map: MlMap,
  id: string,
  color: string,
  width: unknown,
  opacity: number,
  dasharray?: number[],
) {
  try {
    map.setPaintProperty(id, "line-color", color)
    map.setPaintProperty(id, "line-width", width as never)
    map.setPaintProperty(id, "line-opacity", opacity)
    if (dasharray) map.setPaintProperty(id, "line-dasharray", dasharray)
    try {
      map.setPaintProperty(id, "line-emissive-strength", 1)
    } catch {
      /* mercator / older paint */
    }
  } catch {
    /* layer missing */
  }
}

function addLine(
  map: MlMap,
  id: string,
  source: string,
  color: string,
  width: unknown,
  opacity: number,
  dasharray?: number[],
) {
  if (map.getLayer(id)) {
    setLinePaint(map, id, color, width, opacity, dasharray)
    return
  }
  const paint: Record<string, unknown> = {
    "line-color": color,
    "line-width": width,
    "line-opacity": opacity,
  }
  if (dasharray) paint["line-dasharray"] = dasharray
  try {
    map.addLayer({
      id,
      type: "line",
      source,
      layout: {
        "line-cap": "round",
        "line-join": "round",
        visibility: "visible",
      },
      paint: paint as never,
    })
    try {
      map.setPaintProperty(id, "line-emissive-strength", 1)
    } catch {
      /* globe-only paint */
    }
  } catch {
    /* style busy */
  }
}

/** Draw PRC land outline (incl. Taiwan) and 南海诸岛十段线 above the field overlay. */
export async function applyChinaBorders(map: MlMap, theme: BorderTheme = "paper") {
  if (!map.getStyle()) return
  if (!map.isStyleLoaded()) {
    map.once("idle", () => {
      void applyChinaBorders(map, theme)
    })
    return
  }
  muteOsmCountryBoundaries(map)
  const data = await loadChinaPrcGeo()
  if (!data) {
    if (loadFailures < 4) {
      loadFailures += 1
      window.setTimeout(() => {
        void applyChinaBorders(map, theme)
      }, 1200)
    }
    return
  }
  loadFailures = 0
  if (!map.getStyle()) return
  const paint = THEME[theme]
  const land = {
    type: "FeatureCollection",
    features: data.features.filter((f) => (f.properties as { kind?: string } | null)?.kind === "land"),
  }
  const dash = {
    type: "FeatureCollection",
    features: data.features.filter((f) => (f.properties as { kind?: string } | null)?.kind === "dash"),
  }
  if (!land.features.length && !dash.features.length) return

  const ensure = (id: string, fc: object) => {
    const src = map.getSource(id) as { setData?: (d: object) => void } | undefined
    if (src?.setData) src.setData(fc)
    else if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: fc as never })
  }
  ensure("prc-land", land)
  ensure("prc-dash", dash)

  if (!map.getLayer("prc-land-fill")) {
    try {
      map.addLayer({
        id: "prc-land-fill",
        type: "fill",
        source: "prc-land",
        paint: {
          "fill-color": paint.fill,
          "fill-opacity": paint.fillOpacity,
        },
      })
    } catch {
      /* style busy */
    }
  } else {
    try {
      map.setPaintProperty("prc-land-fill", "fill-color", paint.fill)
      map.setPaintProperty("prc-land-fill", "fill-opacity", paint.fillOpacity)
    } catch {
      /* optional */
    }
  }

  addLine(map, "prc-land-case", "prc-land", paint.case, paint.caseWidth, 0.92)
  addLine(map, "prc-dash-case", "prc-dash", paint.case, paint.dashCaseWidth, 0.88, paint.dasharray)
  addLine(map, "prc-land-line", "prc-land", paint.land, paint.landWidth, 1)
  addLine(map, "prc-dash-line", "prc-dash", paint.dash, paint.dashWidth, 1, paint.dasharray)
  raiseChinaBorders(map)
}
