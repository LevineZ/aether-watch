import type { Map as MlMap } from "maplibre-gl"
import { classifyBoundaryLayer } from "~/utils/chinaBorders"
import { applyPlaceLabels, isPlaceLabelLayer, type LabelLang } from "~/utils/mapLabels"

/** Strip streets/POIs and darken water so the globe reads as space + ocean. */
export function restyleGlobe(map: MlMap, lang: LabelLang = "zh") {
  try {
    map.setProjection({ type: "globe" })
  } catch {
    /* mercator fallback */
  }
  try {
    map.setSky({
      "sky-color": "#02040c",
      "horizon-color": "#24506e",
      "fog-color": "#08141e",
      "sky-horizon-blend": 0.88,
      "horizon-fog-blend": 0.62,
      "fog-ground-blend": 0.28,
      "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.95, 3, 0.72, 6, 0.14, 8, 0],
    } as never)
  } catch {
    try {
      map.setSky({
        "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.85, 5, 0.35, 7, 0],
      } as never)
    } catch {
      /* optional */
    }
  }
  try {
    map.setLight({ anchor: "viewport", position: [1.4, 205, 42], intensity: 0.5 } as never)
  } catch {
    /* optional */
  }

  const layers = map.getStyle()?.layers || []
  for (const layer of layers) {
    const id = layer.id
    const type = layer.type
    const src = `${id} ${(layer as { "source-layer"?: string })["source-layer"] || ""}`.toLowerCase()
    try {
      if (type === "symbol") {
        const keep = isPlaceLabelLayer(id, src)
        map.setLayoutProperty(id, "visibility", keep ? "visible" : "none")
        if (keep) {
          try {
            map.setPaintProperty(id, "text-color", "#d7cfc3")
            map.setPaintProperty(id, "text-halo-color", "#05070d")
            map.setPaintProperty(id, "text-halo-width", 1.15)
            map.setPaintProperty(id, "text-opacity", 0.82)
          } catch {
            /* optional */
          }
        }
        continue
      }
      if (type === "background") {
        map.setPaintProperty(id, "background-color", "#05070d")
        continue
      }
      if (type === "fill" || type === "fill-extrusion") {
        if (src.includes("water") || src.includes("ocean") || src.includes("sea")) {
          map.setPaintProperty(id, "fill-color", "#071624")
          if (type === "fill") map.setPaintProperty(id, "fill-opacity", 1)
        } else if (src.includes("building")) {
          map.setLayoutProperty(id, "visibility", "none")
        } else if (src.includes("landcover") || src.includes("landuse") || src.includes("park")) {
          map.setPaintProperty(id, "fill-color", "#223244")
          map.setPaintProperty(id, "fill-opacity", 0.9)
        } else if (src.includes("land")) {
          map.setPaintProperty(id, "fill-color", "#2a3b4e")
          if (type === "fill") map.setPaintProperty(id, "fill-opacity", 1)
        }
      }
      if (type === "line") {
        if (
          src.includes("road") ||
          src.includes("street") ||
          src.includes("transit") ||
          src.includes("rail") ||
          src.includes("path") ||
          src.includes("aeroway") ||
          src.includes("transport")
        ) {
          map.setLayoutProperty(id, "visibility", "none")
        } else if (src.includes("bound") || src.includes("admin") || src.includes("country") || src.includes("disput")) {
          const role = classifyBoundaryLayer(id, src)
          if (role === "province") {
            /* applyChinaBorders restyles these to solid 观潮 orange */
            map.setLayoutProperty(id, "visibility", "visible")
          } else {
            map.setLayoutProperty(id, "visibility", "none")
          }
        } else if (src.includes("water") || src.includes("coast")) {
          map.setPaintProperty(id, "line-color", "#4a86a0")
          map.setPaintProperty(id, "line-opacity", 0.82)
          map.setPaintProperty(id, "line-width", 0.95)
          map.setLayoutProperty(id, "visibility", "visible")
        } else {
          map.setLayoutProperty(id, "visibility", "none")
        }
      }
    } catch {
      /* layer paint mismatch is fine */
    }
  }
  applyPlaceLabels(map, lang)
}

export function paintStars(canvas: HTMLCanvasElement, w: number, h: number) {
  const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
  canvas.width = Math.max(1, Math.floor(w * dpr))
  canvas.height = Math.max(1, Math.floor(h * dpr))
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`
  const ctx = canvas.getContext("2d")
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)
  const n = Math.round((w * h) / 2800)
  for (let i = 0; i < n; i++) {
    const x = Math.random() * w
    const y = Math.random() * h
    const r = Math.random() ** 2 * 1.3 + 0.25
    const warm = Math.random() > 0.82
    ctx.fillStyle = warm ? `rgba(244, 196, 160, ${0.35 + Math.random() * 0.5})` : `rgba(220, 230, 255, ${0.25 + Math.random() * 0.55})`
    ctx.beginPath()
    ctx.arc(x, y, r, 0, Math.PI * 2)
    ctx.fill()
  }
}
