import assert from "node:assert/strict"
import test from "node:test"
import {
  applyGlobeBasemap,
  GLOBE_LAND_FILL,
  GLOBE_LAND_GEO_URLS,
  GLOBE_LAND_LAYER,
  GLOBE_LAND_SOURCE,
  GLOBE_OCEAN,
  globeFallbackStyle,
  globeLandLayerSpec,
  landInsertBeforeId,
} from "./globeLand.ts"

test("land fill sits under water, not above labels", () => {
  const before = landInsertBeforeId([
    { id: "background", type: "background" },
    { id: "water", type: "fill", "source-layer": "water" },
    { id: "place_city", type: "symbol" },
  ])
  assert.equal(before, "water")
  assert.equal(landInsertBeforeId([{ id: "background", type: "background" }, { id: "place_city", type: "symbol" }]), "place_city")
})

test("applyGlobeBasemap rewrites OFM dark background-as-land", () => {
  const style = applyGlobeBasemap({
    version: 8,
    sources: { openmaptiles: { type: "vector" } },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "rgb(12,12,12)" } },
      { id: "water", type: "fill", source: "openmaptiles", "source-layer": "water", paint: { "fill-color": "rgb(27,27,29)" } },
      { id: "place_city", type: "symbol" },
    ],
  })
  assert.equal(style.layers?.[0]?.paint?.["background-color"], GLOBE_OCEAN)
  assert.equal(style.layers?.[1]?.id, GLOBE_LAND_LAYER)
  assert.equal(style.layers?.[1]?.paint?.["fill-color"], GLOBE_LAND_FILL)
  assert.equal(style.layers?.[2]?.id, "water")
  assert.equal(style.layers?.[2]?.paint?.["fill-color"], GLOBE_OCEAN)
  assert.equal((style.sources as Record<string, { data?: string }>)[GLOBE_LAND_SOURCE]?.data, GLOBE_LAND_GEO_URLS[0])
  assert.equal(GLOBE_OCEAN, "#071624")
  assert.notEqual(GLOBE_OCEAN, "#05070d")
})

test("globeFallbackStyle is local ocean + land with no remote tiles", () => {
  const style = globeFallbackStyle()
  assert.equal(style.version, 8)
  const sourceIds = Object.keys(style.sources || {})
  assert.deepEqual(sourceIds, [GLOBE_LAND_SOURCE])
  assert.ok(style.layers?.some((layer) => layer.id === "background"))
  assert.ok(style.layers?.some((layer) => layer.id === GLOBE_LAND_LAYER))
  assert.equal(globeLandLayerSpec().source, GLOBE_LAND_SOURCE)
  assert.ok(GLOBE_LAND_GEO_URLS[1].includes("/api/geo/ne-110m-land.json"))
})
