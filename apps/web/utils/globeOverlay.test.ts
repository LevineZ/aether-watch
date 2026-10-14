import assert from "node:assert/strict"
import test from "node:test"
import { fieldHasSignal, overlayOpacity, weatherModelId } from "./globeOverlay.ts"

test("weatherModelId remaps marine chips onto GFS", () => {
  assert.equal(weatherModelId("best_match"), "gfs_seamless")
  assert.equal(weatherModelId("oscar_v2"), "gfs_seamless")
  assert.equal(weatherModelId("cmems_glo_phy"), "gfs_seamless")
  assert.equal(weatherModelId("gfs_seamless"), "gfs_seamless")
  assert.equal(weatherModelId("ecmwf_ifs025"), "ecmwf_ifs025")
  assert.equal(weatherModelId("nc:abc"), "nc:abc")
})

test("fieldHasSignal rejects empty and all-null grids", () => {
  assert.equal(fieldHasSignal(null), false)
  assert.equal(fieldHasSignal({ lats: [], lons: [], values: [], min: 0, max: 1 }), false)
  assert.equal(
    fieldHasSignal({
      lats: [0],
      lons: [0],
      values: [[null, null], [null, null]],
      min: 0,
      max: 1,
    }),
    false,
  )
  assert.equal(
    fieldHasSignal({
      lats: [0],
      lons: [0],
      values: [[null, 12.5]],
      min: 0,
      max: 20,
    }),
    true,
  )
})

test("overlayOpacity keeps rain/waves readable", () => {
  assert.ok(overlayOpacity("waves") > 0.75)
  assert.ok(overlayOpacity("thermal") > 0.7)
  assert.ok(overlayOpacity("rain") > overlayOpacity("wind"))
})
