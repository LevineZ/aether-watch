import assert from "node:assert/strict"
import { test } from "node:test"
import { currentSegmentOk, frontCosc, mercatorLat, MIN_COSC_CURRENT } from "./flowSegment.ts"

function mercatorY(lat: number) {
  const s = Math.sin((Math.min(78, Math.max(-78, lat)) * Math.PI) / 180)
  return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)
}

test("mercatorLat inverts mercatorY near China seas", () => {
  const lat = 22.5
  const y = mercatorY(lat)
  assert.ok(Math.abs(mercatorLat(y) - lat) < 0.05)
})

test("frontCosc is high at camera and low on the far side", () => {
  const camLat = 30
  const sinCam = Math.sin((camLat * Math.PI) / 180)
  const cosCam = Math.cos((camLat * Math.PI) / 180)
  const onAxis = frontCosc(110, 30, 110, sinCam, cosCam)
  const farSide = frontCosc(-70, -30, 110, sinCam, cosCam)
  assert.ok(onAxis > 0.95)
  assert.ok(farSide < 0)
})

test("currentSegmentOk keeps a short Kuroshio step and rejects a date-line wrap", () => {
  const x0 = (130 + 180) / 360
  const x1 = (131 + 180) / 360
  const y = mercatorY(28)
  assert.equal(currentSegmentOk(x0, y, x1, y, 110, 30), true)

  const wrap0 = (179 + 180) / 360
  const wrap1 = (-179 + 180) / 360
  assert.equal(currentSegmentOk(wrap0, y, wrap1, y, 110, 30), false)
})

test("currentSegmentOk rejects a silhouette pair behind the China globe camera", () => {
  const x0 = (-70 + 180) / 360
  const x1 = (-69 + 180) / 360
  const y = mercatorY(-20)
  assert.equal(currentSegmentOk(x0, y, x1, y, 110, 30, MIN_COSC_CURRENT), false)
})
