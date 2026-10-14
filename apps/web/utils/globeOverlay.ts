import type { Palette } from "~/utils/colormap"
import type { ScalarField } from "~/utils/rasterField"

/** Globe scalar grid. Matches Earth /api/field −180…180/−70…70 and API globe_field_nx/ny. */
export const GLOBE_FIELD_NX = 16
export const GLOBE_FIELD_NY = 10

const WEATHER_MODELS = new Set([
  "gfs_seamless",
  "ecmwf_ifs025",
  "ecmwf_aifs025_single",
  "icon_seamless",
  "ukmo_seamless",
])

export function weatherModelId(model: string | null | undefined): string {
  const raw = (model || "").trim()
  if (WEATHER_MODELS.has(raw) || raw.startsWith("nc:")) return raw
  return "gfs_seamless"
}

export function fieldHasSignal(field: ScalarField | null | undefined): boolean {
  const rows = field?.values
  if (!rows?.length) return false
  for (const row of rows) {
    for (const v of row) {
      if (v != null && Number.isFinite(v)) return true
    }
  }
  return false
}

/** Nullschool-like fill opacity: color field reads first, particles sit on top. */
export function overlayOpacity(palette: Palette, kind?: "wind" | "current"): number {
  if (palette === "rain" || palette === "cloud") return 0.88
  if (palette === "waves") return 0.84
  if (palette === "wind") return 0.7
  if (palette === "thermal" || palette === "pressure") return 0.78
  if (kind === "current") return 0.55
  return 0.62
}
