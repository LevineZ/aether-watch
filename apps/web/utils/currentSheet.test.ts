import assert from "node:assert/strict"
import { test } from "node:test"
import {
  CURRENT_FADE,
  CURRENT_STEP,
  CURRENT_STROKE_SEGS,
  sheetAlpha,
  sheetEdge,
  sheetFade,
} from "./currentSheet.ts"

test("CURRENT_STEP stays a calm China-globe drift", () => {
  assert.ok(CURRENT_STEP <= 0.22)
  assert.ok(CURRENT_STEP >= 0.18)
})

test("fade is destination-in-like and drains fast while interacting", () => {
  assert.ok(CURRENT_FADE >= 0.94 && CURRENT_FADE <= 0.98)
  const still = sheetFade(16.67, false)
  const drag = sheetFade(16.67, true)
  assert.ok(Math.abs(still - CURRENT_FADE) < 1e-6)
  assert.ok(drag < 0.7)
  assert.ok(drag < still)
})

test("strokes are short flakes, not 40-point ribbons", () => {
  assert.ok(CURRENT_STROKE_SEGS <= 4)
  assert.ok(CURRENT_STROKE_SEGS >= 1)
})

test("sheetEdge is a gaussian, not a hard wall", () => {
  const core = sheetEdge(0)
  const mid = sheetEdge(0.5)
  const rim = sheetEdge(1)
  assert.equal(core, 1)
  assert.ok(mid < core * 0.65)
  assert.ok(rim < 0.18)
  assert.ok(mid > rim)
})

test("sheetAlpha stays dim so a single dash is not a line", () => {
  const head = sheetAlpha(1, 1)
  const tail = sheetAlpha(0, 0)
  assert.ok(head < 0.32)
  assert.ok(tail < head)
  assert.ok(tail > 0.06)
})
