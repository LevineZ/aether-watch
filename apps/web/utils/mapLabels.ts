import type { Map as MlMap } from "maplibre-gl"

export type LabelLang = "zh" | "en"

type StyleJson = {
  layers?: Array<{
    id: string
    type: string
    layout?: Record<string, unknown>
  }>
}

export const OPENFREEMAP_POSITRON = "https://tiles.openfreemap.org/styles/positron"
export const OPENFREEMAP_DARK = "https://tiles.openfreemap.org/styles/dark"

/** Prefer Chinese OSM names; fall back to local / latin. */
export const ZH_TEXT_FIELD: unknown = [
  "coalesce",
  ["get", "name:zh-Hans"],
  ["get", "name:zh"],
  ["get", "name:nonlatin"],
  ["get", "name"],
  ["get", "name:latin"],
  ["get", "name_en"],
  ["get", "name:en"],
]

export const EN_TEXT_FIELD: unknown = [
  "coalesce",
  ["get", "name:en"],
  ["get", "name_en"],
  ["get", "name:latin"],
  ["get", "name"],
  ["get", "name:nonlatin"],
]

function isRefShield(textField: unknown) {
  return JSON.stringify(textField || "").includes('"ref"')
}

export function patchStyleLabels(style: StyleJson, lang: LabelLang) {
  const field = lang === "zh" ? ZH_TEXT_FIELD : EN_TEXT_FIELD
  for (const layer of style.layers || []) {
    if (layer.type !== "symbol") continue
    const layout = layer.layout as Record<string, unknown> | undefined
    if (!layout || layout["text-field"] == null) continue
    if (isRefShield(layout["text-field"])) continue
    layout["text-field"] = field
    if (lang === "zh") layout["text-transform"] = "none"
  }
  return style
}

export async function loadOpenFreeMapStyle(kind: "positron" | "dark", lang: LabelLang) {
  const url = kind === "dark" ? OPENFREEMAP_DARK : OPENFREEMAP_POSITRON
  const res = await fetch(url)
  if (!res.ok) throw new Error(`style ${res.status}`)
  const style = (await res.json()) as StyleJson
  return patchStyleLabels(style, lang)
}

export function applyPlaceLabels(map: MlMap, lang: LabelLang) {
  const field = lang === "zh" ? ZH_TEXT_FIELD : EN_TEXT_FIELD
  const layers = map.getStyle()?.layers || []
  for (const layer of layers) {
    if (layer.type !== "symbol") continue
    const layout = layer.layout as Record<string, unknown> | undefined
    if (!layout || layout["text-field"] == null) continue
    if (isRefShield(layout["text-field"])) continue
    try {
      map.setLayoutProperty(layer.id, "text-field", field as never)
      if (lang === "zh") map.setLayoutProperty(layer.id, "text-transform", "none")
    } catch {
      /* layout mismatch */
    }
  }
}

export function isPlaceLabelLayer(id: string, sourceLayer = "") {
  const s = `${id} ${sourceLayer}`.toLowerCase()
  if (s.includes("highway") || s.includes("road") || s.includes("transport") || s.includes("shield") || s.includes("airport") || s.includes("aerodrome") || s.includes("oneway")) {
    return false
  }
  return s.includes("place") || s.includes("country") || s.includes("city") || s.includes("town") || s.includes("village") || s.includes("state") || s.includes("water_name") || s.includes("water-name")
}
