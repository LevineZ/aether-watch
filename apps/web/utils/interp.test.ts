import assert from "node:assert/strict"
import { test } from "node:test"
import { sampleBilinear, upsampleScalarGrid, upsampleVectorField } from "./interp.ts"

test("bilinear midpoint is the mean of a 2×2 cell", () => {
  const grid = [
    [0, 10],
    [20, 30],
  ]
  const v = sampleBilinear(grid, 0.5, 0.5)
  assert.equal(v, 15)
})

test("bilinear ignores a missing corner and renormalizes", () => {
  const grid = [
    [0, null],
    [10, 20],
  ]
  const v = sampleBilinear(grid, 0.5, 0.5)
  assert.ok(v != null)
  assert.ok(Math.abs((v as number) - 10) < 1e-6)
})

test("upsampleScalarGrid densifies without inventing block edges", () => {
  const src = [
    [0, 4],
    [8, 12],
  ]
  const up = upsampleScalarGrid(src, 4)
  assert.equal(up.length, 5)
  assert.equal(up[0].length, 5)
  assert.equal(up[0][0], 0)
  assert.equal(up[4][4], 12)
  const mid = up[2][2]
  assert.ok(mid != null)
  assert.ok(Math.abs((mid as number) - 6) < 1e-6)
  // interior samples are strictly between neighbors (no nearest-neighbor steps)
  assert.ok((up[0][1] as number) > 0 && (up[0][1] as number) < 4)
  assert.ok((up[0][2] as number) === 2)
})

test("upsampleVectorField bilinear-smooths packed u/v", () => {
  const u = new Float32Array([0, 4, 8, 12])
  const v = new Float32Array([0, 0, 2, 2])
  const out = upsampleVectorField(u, v, 2, 2, 2)
  assert.equal(out.width, 3)
  assert.equal(out.height, 3)
  assert.equal(out.u[0], 0)
  assert.equal(out.u[out.width * 2 + 2], 12)
  const mid = out.u[out.width + 1]
  assert.ok(Math.abs(mid - 6) < 1e-6)
  assert.ok(Math.abs(out.v[out.width + 1] - 1) < 1e-6)
})
