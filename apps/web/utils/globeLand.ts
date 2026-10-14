/** Ocean / space-adjacent water. OpenFreeMap dark paints land as background, so this must not be near-black. */
export const GLOBE_OCEAN = "#071624"
export const GLOBE_LAND_FILL = "#2a3b4e"
export const GLOBE_LAND_SOURCE = "aw-globe-land"
export const GLOBE_LAND_LAYER = "aw-globe-land-fill"
export const GLOBE_LAND_GEO_URLS = ["/geo/ne-110m-land.geojson", "/api/geo/ne-110m-land.json"] as const

export type GlobeStyleJson = {
  version?: number
  sources?: Record<string, unknown>
  layers?: Array<{
    id: string
    type: string
    source?: string
    "source-layer"?: string
    paint?: Record<string, unknown>
    layout?: Record<string, unknown>
    filter?: unknown
    minzoom?: number
    maxzoom?: number
  }>
  sprite?: string
  glyphs?: string
  [key: string]: unknown
}

export type LayerHint = { id: string; type: string; "source-layer"?: string }

function isWaterFill(layer: LayerHint) {
  if (layer.type !== "fill" && layer.type !== "fill-extrusion") return false
  const src = `${layer.id} ${layer["source-layer"] || ""}`.toLowerCase()
  return src.includes("water") || src.includes("ocean") || src.includes("sea")
}

/** Place the local land fill under OFM water so lakes/coasts still cut inland. */
export function landInsertBeforeId(layers: LayerHint[]): string | undefined {
  for (const layer of layers) {
    if (layer.id === GLOBE_LAND_LAYER) continue
    if (isWaterFill(layer)) return layer.id
  }
  return layers.find((layer) => layer.type === "symbol")?.id
}

export function globeLandLayerSpec() {
  return {
    id: GLOBE_LAND_LAYER,
    type: "fill" as const,
    source: GLOBE_LAND_SOURCE,
    paint: {
      "fill-color": GLOBE_LAND_FILL,
      "fill-opacity": 1,
    },
  }
}

/**
 * OpenFreeMap dark uses background as land. Rewrite to ocean + a vendored NE 110m fill
 * so missing vector tiles (or our space-black restyle) cannot punch continent-sized holes.
 */
export function applyGlobeBasemap(style: GlobeStyleJson): GlobeStyleJson {
  const sources = { ...(style.sources || {}) }
  sources[GLOBE_LAND_SOURCE] = {
    type: "geojson",
    data: GLOBE_LAND_GEO_URLS[0],
  }
  const layers = [...(style.layers || [])]
  for (const layer of layers) {
    if (layer.type === "background") {
      layer.paint = { ...(layer.paint || {}), "background-color": GLOBE_OCEAN }
    } else if (isWaterFill(layer)) {
      layer.paint = { ...(layer.paint || {}), "fill-color": GLOBE_OCEAN }
      if (layer.type === "fill") layer.paint["fill-opacity"] = 1
    }
  }
  if (!layers.some((layer) => layer.id === GLOBE_LAND_LAYER)) {
    const before = landInsertBeforeId(layers)
    const spec = globeLandLayerSpec()
    const at = before ? layers.findIndex((layer) => layer.id === before) : 1
    layers.splice(at < 0 ? layers.length : at, 0, spec)
  }
  return { ...style, sources, layers }
}

/** Offline globe: ocean background + local land polygons, no OpenFreeMap tiles. */
export function globeFallbackStyle(): GlobeStyleJson {
  return applyGlobeBasemap({
    version: 8,
    sources: {},
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": GLOBE_OCEAN },
      },
    ],
  })
}
