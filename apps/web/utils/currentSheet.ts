/**
 * Nullschool / cambecc/earth sheet parameters.
 * Silk comes from short strokes + a destination-in fade buffer, not long ribbons.
 */

/** Degrees per 16.67ms at 1 m/s. Calm China-globe drift; keep ≤ ~0.22. */
export const CURRENT_STEP = 0.22

/** Per-frame multiply for the trail buffer (cambecc/earth destination-in 0.97). */
export const CURRENT_FADE = 0.97

/** GPU segments per particle; history lives in the fade buffer, not a 40-pt strip. */
export const CURRENT_STROKE_SEGS = 3

/** Gaussian k in exp(-side² · k). Vertex side is -1..1; GLSL must match. */
export const SHEET_EDGE_K = 1.85

/** Fast drain of screen-space trails while the globe camera moves. */
export const CURRENT_FADE_INTERACTING = 0.55

export function sheetFade(dtMs: number, interacting: boolean) {
  const perFrame = interacting ? CURRENT_FADE_INTERACTING : CURRENT_FADE
  return Math.pow(perFrame, Math.max(0.35, dtMs) / 16.67)
}

/** Soft falloff across ribbon width so edges do not read as line walls. */
export function sheetEdge(side: number) {
  const s = Math.min(1, Math.max(-1, side))
  return Math.exp(-s * s * SHEET_EDGE_K)
}

/**
 * Per-stroke alpha. One dash is a dim flake; additive overlap + fade → sheet.
 * Keep this low: fade equilibrium is a/(1-f). Opaque heads become spaghetti.
 */
export function sheetAlpha(trailT: number, speed01: number) {
  const along = 0.72 + 0.28 * Math.min(1, Math.max(0, trailT))
  const speed = 0.14 + 0.12 * Math.min(1, Math.max(0, speed01))
  return along * speed
}
