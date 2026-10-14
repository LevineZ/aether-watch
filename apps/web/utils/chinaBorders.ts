import type { Map as MlMap } from "maplibre-gl"

export const CHINA_PRC_GEO_URLS = ["/geo/china-prc.geojson", "/api/geo/china-prc.json"] as const

/** Visible PRC overlays. Legacy case/fill ids are hidden if a prior style left them. */
export const PRC_LAYER_IDS = ["prc-land-line", "prc-dash-line"] as const
const LEGACY_PRC_IDS = ["prc-land-fill", "prc-land-case", "prc-dash-case"] as const

/** 观潮 earth.css `boundary-nation` — solid orange, not a CSS dasharray. */
export const GLOBE_NATION = "rgba(255,186,92,0.95)"
export const GLOBE_PROVINCE = "rgba(255,186,92,0.88)"
/** Forecast panels: thick dark solid national stroke. */
export const PAPER_NATION = "#161616"
export const PAPER_PROVINCE = "#3a3a3a"

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

export type BoundaryRole = "mute" | "province" | null

/** Country / disputed OSM lines are muted; admin-1+ stay for 观潮-like province mesh. */
export function classifyBoundaryLayer(id: string, sourceLayer = ""): BoundaryRole {
  const s = `${id} ${sourceLayer}`.toLowerCase()
  if (!s.includes("bound") && !s.includes("admin") && !s.includes("disput")) return null
  if (s.includes("disput") || s.includes("claimed")) return "mute"
  if (s.includes("country") || /boundary_2([^0-9]|$)/.test(s) || s.includes("admin_0") || s.includes("admin0")) {
    return "mute"
  }
  if (
    s.includes("boundary_3") ||
    s.includes("boundary_state") ||
    s.includes("province") ||
    s.includes("boundary_4") ||
    s.includes("admin_1") ||
    s.includes("admin1")
  ) {
    return "province"
  }
  if (s.includes("bound") || s.includes("admin")) return "mute"
  return null
}

/**
 * Hide OSM/OpenFreeMap country lines that depict Taiwan as a separate country
 * or omit the mainland standard-map dash line. Province / prefecture lines stay.
 */
export function muteOsmCountryBoundaries(map: MlMap) {
  const layers = map.getStyle()?.layers || []
  for (const layer of layers) {
    if (layer.type !== "line") continue
    const src = (layer as { "source-layer"?: string })["source-layer"] || ""
    const role = classifyBoundaryLayer(layer.id, src)
    if (role === "mute") {
      try {
        map.setLayoutProperty(layer.id, "visibility", "none")
      } catch {
        /* optional */
      }
    }
  }
}

type BorderTheme = "paper" | "globe"

const zoomWidth = (stops: Array<[number, number]>) =>
  ["interpolate", ["linear"], ["zoom"], ...stops.flat()] as unknown

const THEME = {
  paper: {
    land: PAPER_NATION,
    dash: PAPER_NATION,
    province: PAPER_PROVINCE,
    landWidth: zoomWidth([
      [2, 1.85],
      [3, 2.05],
      [6, 2.45],
    ]),
    dashWidth: zoomWidth([
      [2, 1.7],
      [3, 1.95],
      [6, 2.3],
    ]),
    provinceWidth: zoomWidth([
      [2, 0.55],
      [3.2, 0.75],
      [6, 1.05],
      [8, 1.25],
    ]),
    landOpacity: 1,
    dashOpacity: 1,
    provinceOpacity: 0.88,
    provinceMinZoom: 1.9,
  },
  globe: {
    land: GLOBE_NATION,
    dash: GLOBE_NATION,
    province: GLOBE_PROVINCE,
    landWidth: zoomWidth([
      [1, 1.25],
      [3, 1.4],
      [6, 1.7],
    ]),
    dashWidth: zoomWidth([
      [1, 1.25],
      [3, 1.4],
      [6, 1.65],
    ]),
    provinceWidth: zoomWidth([
      [1.4, 0.7],
      [3, 1.15],
      [5, 1.65],
      [6, 1.85],
    ]),
    landOpacity: 0.95,
    dashOpacity: 0.95,
    provinceOpacity: 0.9,
    provinceMinZoom: 2.05,
  },
} as const

export function firstPrcLayerId(map: MlMap): string | undefined {
  return PRC_LAYER_IDS.find((id) => map.getLayer(id))
}

/** Keep the solid PRC outline + 十段线 above heatmaps / particles. */
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

function clearDasharray(map: MlMap, id: string) {
  try {
    map.setPaintProperty(id, "line-dasharray", undefined as never)
  } catch {
    try {
      map.setPaintProperty(id, "line-dasharray", [1, 0] as never)
    } catch {
      /* some styles reject both */
    }
  }
}

function setLinePaint(map: MlMap, id: string, color: string, width: unknown, opacity: number) {
  try {
    map.setPaintProperty(id, "line-color", color)
    map.setPaintProperty(id, "line-width", width as never)
    map.setPaintProperty(id, "line-opacity", opacity)
    clearDasharray(map, id)
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
  cap: "butt" | "round",
) {
  if (map.getLayer(id)) {
    setLinePaint(map, id, color, width, opacity)
    try {
      map.setLayoutProperty(id, "line-cap", cap)
      map.setLayoutProperty(id, "visibility", "visible")
    } catch {
      /* optional */
    }
    return
  }
  try {
    map.addLayer({
      id,
      type: "line",
      source,
      layout: {
        "line-cap": cap,
        "line-join": cap === "butt" ? "miter" : "round",
        visibility: "visible",
      },
      paint: {
        "line-color": color,
        "line-width": width,
        "line-opacity": opacity,
      } as never,
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

function hideLegacy(map: MlMap) {
  for (const id of LEGACY_PRC_IDS) {
    if (!map.getLayer(id)) continue
    try {
      map.setLayoutProperty(id, "visibility", "none")
    } catch {
      /* optional */
    }
  }
}

/** Restyle OpenFreeMap province / prefecture lines: solid, 观潮 color, visible at China overview zoom. */
export function styleProvinceBoundaries(map: MlMap, theme: BorderTheme = "paper") {
  const paint = THEME[theme]
  const layers = map.getStyle()?.layers || []
  for (const layer of layers) {
    if (layer.type !== "line") continue
    const src = (layer as { "source-layer"?: string })["source-layer"] || ""
    if (classifyBoundaryLayer(layer.id, src) !== "province") continue
    try {
      map.setLayoutProperty(layer.id, "visibility", "visible")
      map.setLayoutProperty(layer.id, "line-cap", "butt")
      map.setLayoutProperty(layer.id, "line-join", "miter")
    } catch {
      /* optional */
    }
    try {
      map.setLayerZoomRange(layer.id, paint.provinceMinZoom, 24)
    } catch {
      /* optional */
    }
    setLinePaint(map, layer.id, paint.province, paint.provinceWidth, paint.provinceOpacity)
    try {
      map.setPaintProperty(layer.id, "line-blur", 0)
    } catch {
      /* optional */
    }
  }
}

/** Draw solid PRC land outline (incl. Taiwan) and 南海诸岛十段线 as geometry segments. */
export async function applyChinaBorders(map: MlMap, theme: BorderTheme = "paper") {
  if (!map.getStyle()) return
  if (!map.isStyleLoaded()) {
    map.once("idle", () => {
      void applyChinaBorders(map, theme)
    })
    return
  }
  muteOsmCountryBoundaries(map)
  styleProvinceBoundaries(map, theme)
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
  hideLegacy(map)

  // National outline: solid (butt/round). 十段线: same color, solid stroke of short GeoJSON segments.
  addLine(map, "prc-land-line", "prc-land", paint.land, paint.landWidth, paint.landOpacity, "round")
  addLine(map, "prc-dash-line", "prc-dash", paint.dash, paint.dashWidth, paint.dashOpacity, "butt")
  raiseChinaBorders(map)
}
