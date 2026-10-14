import type { CustomLayerInterface, Map as MlMap } from "maplibre-gl"
import { isOcean } from "./landmask"
import {
  mercatorX,
  mercatorY,
  packWind,
  randomCurrentPoint,
  randomLat,
  sampleWind,
  targetParticleCount,
  wrapLon,
  type Wind,
  type WindGrid,
} from "./windField"

export type FlowKind = "wind" | "current"

type RenderArgs = {
  shaderData?: { variantName: string; vertexShaderPrelude: string; define: string }
  defaultProjectionData: {
    mainMatrix: Float32Array | number[]
    fallbackMatrix: Float32Array | number[]
    tileMercatorCoords: [number, number, number, number]
    clippingPlane: [number, number, number, number]
    projectionTransition: number
  }
  modelViewProjectionMatrix?: Float32Array | number[]
}

const TRAIL = 10
const STRIDE = 4
const MAX_PARTICLES = 36000
const VERTS_PER_PARTICLE = (TRAIL - 1) * 2
/** Degrees per 16.67ms at 1 m/s. Currents must stay calm vs wind. */
const CURRENT_STEP = 0.038
const WIND_STEP = 0.034

function compile(gl: WebGL2RenderingContext, type: number, source: string) {
  const sh = gl.createShader(type)
  if (!sh) return null
  gl.shaderSource(sh, source)
  gl.compileShader(sh)
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    console.warn("[flow] shader", gl.getShaderInfoLog(sh))
    gl.deleteShader(sh)
    return null
  }
  return sh
}

function link(gl: WebGL2RenderingContext, vsSrc: string, fsSrc: string) {
  const vs = compile(gl, gl.VERTEX_SHADER, vsSrc)
  const fs = compile(gl, gl.FRAGMENT_SHADER, fsSrc)
  if (!vs || !fs) return null
  const prog = gl.createProgram()
  if (!prog) return null
  gl.attachShader(prog, vs)
  gl.attachShader(prog, fs)
  gl.linkProgram(prog)
  gl.deleteShader(vs)
  gl.deleteShader(fs)
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    console.warn("[flow] program", gl.getProgramInfoLog(prog))
    gl.deleteProgram(prog)
    return null
  }
  return prog
}

type ShaderBundle = {
  program: WebGLProgram
  aPos: number
  aSpeed: number
  aAlpha: number
  uMatrix: WebGLUniformLocation | null
  uFallback: WebGLUniformLocation | null
  uTile: WebGLUniformLocation | null
  uClip: WebGLUniformLocation | null
  uTrans: WebGLUniformLocation | null
  uKind: WebGLUniformLocation | null
  uVmax: WebGLUniformLocation | null
}

/**
 * MapLibre custom layer: CPU advection + one GPU line draw.
 * Globe projection is MapLibre's `projectTile` (no per-particle project/unproject).
 */
export class WindParticleLayer implements CustomLayerInterface {
  id = "aether-flow"
  type = "custom" as const
  renderingMode = "2d" as const

  playing = true
  interacting = false
  kind: FlowKind = "current"

  private map: MlMap | null = null
  private gl: WebGL2RenderingContext | null = null
  private buffer: WebGLBuffer | null = null
  private vao: WebGLVertexArrayObject | null = null
  private shaders = new Map<string, ShaderBundle>()
  private grid: WindGrid | null = null

  private count = 0
  private lon = new Float32Array(MAX_PARTICLES)
  private lat = new Float32Array(MAX_PARTICLES)
  private age = new Uint16Array(MAX_PARTICLES)
  private histX = new Float32Array(MAX_PARTICLES * TRAIL)
  private histY = new Float32Array(MAX_PARTICLES * TRAIL)
  private verts = new Float32Array(MAX_PARTICLES * VERTS_PER_PARTICLE * STRIDE)
  private usedVerts = 0

  private raf = 0
  private lastT = 0
  private visible = true
  private pageHidden = false
  private reduced = false
  private dropped = 0
  private observer: IntersectionObserver | null = null
  private gen = 0

  setField(wind: Wind | null, kind: FlowKind = this.kind) {
    this.kind = kind
    this.grid = wind ? packWind(wind) : null
    this.gen++
    if (this.count) this.seed(this.count)
  }

  setPlaying(v: boolean) {
    this.playing = v
    if (v) this.kick()
  }

  setVisible(v: boolean) {
    this.visible = v
    if (v) this.kick()
  }

  resize(width: number, dpr: number) {
    const next = Math.min(MAX_PARTICLES, Math.max(6000, Math.round(this.baseCount(width, dpr) * this.quality())))
    if (next !== this.count) this.seed(next)
  }

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    this.map = map
    this.gl = gl
    this.buffer = gl.createBuffer()
    this.vao = gl.createVertexArray()
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer)
    gl.bufferData(gl.ARRAY_BUFFER, this.verts.byteLength, gl.DYNAMIC_DRAW)

    this.reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false
    this.pageHidden = document.hidden
    const w = map.getContainer().clientWidth || window.innerWidth
    if (!this.count) this.seed(this.baseCount(w, Math.min(window.devicePixelRatio || 1, 2)))

    const onVis = () => {
      this.pageHidden = document.hidden
      if (!document.hidden) this.kick()
    }
    document.addEventListener("visibilitychange", onVis)
    this._onVis = onVis

    map.on("movestart", this._onMoveStart)
    map.on("moveend", this._onMoveEnd)

    this.observer = new IntersectionObserver(
      (entries) => {
        this.visible = entries[0]?.isIntersecting !== false
        if (this.visible) this.kick()
      },
      { threshold: 0.05 },
    )
    this.observer.observe(map.getContainer())
    this.kick()
  }

  onRemove(map: MlMap, gl: WebGL2RenderingContext) {
    cancelAnimationFrame(this.raf)
    this.raf = 0
    map.off("movestart", this._onMoveStart)
    map.off("moveend", this._onMoveEnd)
    if (this._onVis) document.removeEventListener("visibilitychange", this._onVis)
    this.observer?.disconnect()
    this.observer = null
    if (this.buffer) gl.deleteBuffer(this.buffer)
    if (this.vao) gl.deleteVertexArray(this.vao)
    for (const s of this.shaders.values()) gl.deleteProgram(s.program)
    this.shaders.clear()
    this.buffer = null
    this.vao = null
    this.gl = null
    this.map = null
  }

  render(gl: WebGL2RenderingContext, args: RenderArgs) {
    if (!this.visible || !this.playing || !this.grid || this.usedVerts < 2) return
    const bundle = this.getShader(gl, args)
    if (!bundle) return

    const proj = args.defaultProjectionData
    gl.useProgram(bundle.program)
    gl.uniformMatrix4fv(bundle.uMatrix, false, proj.mainMatrix as Float32Array)
    gl.uniformMatrix4fv(bundle.uFallback, false, proj.fallbackMatrix as Float32Array)
    gl.uniform4f(bundle.uTile, ...proj.tileMercatorCoords)
    gl.uniform4f(bundle.uClip, ...proj.clippingPlane)
    gl.uniform1f(bundle.uTrans, proj.projectionTransition)
    gl.uniform1f(bundle.uKind, this.kind === "current" ? 1 : 0)
    gl.uniform1f(bundle.uVmax, this.kind === "current" ? 1.35 : 16)

    if (this.vao) gl.bindVertexArray(this.vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer)
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.verts.subarray(0, this.usedVerts * STRIDE))

    gl.enableVertexAttribArray(bundle.aPos)
    gl.enableVertexAttribArray(bundle.aSpeed)
    gl.enableVertexAttribArray(bundle.aAlpha)
    const stride = STRIDE * 4
    gl.vertexAttribPointer(bundle.aPos, 2, gl.FLOAT, false, stride, 0)
    gl.vertexAttribPointer(bundle.aSpeed, 1, gl.FLOAT, false, stride, 8)
    gl.vertexAttribPointer(bundle.aAlpha, 1, gl.FLOAT, false, stride, 12)

    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE)
    gl.disable(gl.DEPTH_TEST)
    gl.drawArrays(gl.LINES, 0, this.usedVerts)
    if (this.vao) gl.bindVertexArray(null)
  }

  private _onVis: (() => void) | null = null
  private _onMoveStart = () => {
    this.interacting = true
  }
  private _onMoveEnd = () => {
    this.interacting = false
  }

  private baseCount(width: number, dpr: number) {
    if (this.reduced) return this.kind === "current" ? 4000 : 3200
    return Math.min(MAX_PARTICLES, targetParticleCount(width, dpr, this.kind))
  }

  private quality() {
    if (this.dropped > 8) return 0.55
    if (this.dropped > 3) return 0.75
    return 1
  }

  private seed(n: number) {
    this.count = Math.min(MAX_PARTICLES, n)
    for (let i = 0; i < this.count; i++) this.spawn(i, true)
    this.usedVerts = 0
  }

  private spawn(i: number, randomAge = false) {
    let lon = Math.random() * 360 - 180
    let lat = randomLat()
    if (this.kind === "current") {
      ;[lon, lat] = randomCurrentPoint()
      if (this.grid) {
        for (let t = 0; t < 8; t++) {
          ;[lon, lat] = randomCurrentPoint()
          const [u, v] = sampleWind(this.grid, lon, lat, true)
          if (Math.hypot(u, v) > 0.008 && isOcean(lon, lat)) break
        }
      }
    }
    this.lon[i] = lon
    this.lat[i] = lat
    this.age[i] = randomAge ? (Math.random() * 80) | 0 : 0
    const x = mercatorX(lon)
    const y = mercatorY(lat)
    const o = i * TRAIL
    for (let k = 0; k < TRAIL; k++) {
      this.histX[o + k] = x
      this.histY[o + k] = y
    }
  }

  private kick() {
    if (this.raf) return
    this.lastT = performance.now()
    const loop = (now: number) => {
      this.raf = 0
      if (!this.map) return
      const hidden = this.pageHidden || !this.visible
      if (!hidden) {
        const dt = Math.min(48, now - this.lastT)
        this.lastT = now
        if (dt > 26) this.dropped = Math.min(12, this.dropped + 1)
        else if (dt < 15) this.dropped = Math.max(0, this.dropped - 1)
        if (this.playing && this.grid) this.advect(dt)
        this.map.triggerRepaint()
      }
      if (!this.map) return
      this.raf = requestAnimationFrame(loop)
    }
    this.raf = requestAnimationFrame(loop)
  }

  private advect(dt: number) {
    const grid = this.grid
    if (!grid) return
    const current = this.kind === "current"
    const step = (current ? CURRENT_STEP : WIND_STEP) * (dt / 16.67)
    const dead = current ? 0.01 : 0.1
    const interacting = this.interacting
    const n = interacting ? (this.count * 0.55) | 0 : this.count
    const cam = this.map?.getCenter()
    const camLon = cam?.lng ?? 0
    const camLat = cam?.lat ?? 0
    const sinCam = Math.sin(camLat * (Math.PI / 180))
    const cosCam = Math.cos(camLat * (Math.PI / 180))
    const maxAge = interacting ? 80 : current ? 280 : 120
    let w = 0
    const verts = this.verts
    const minCos = 0.02

    for (let i = 0; i < n; i++) {
      let lon = this.lon[i]
      let lat = this.lat[i]
      const [u, v] = sampleWind(grid, lon, lat, current)
      const spd = Math.hypot(u, v)
      lon = wrapLon(lon + u * step)
      lat += v * step
      this.age[i]++
      if (this.age[i] > maxAge || lat > 76 || lat < -76 || spd < dead || (current && !isOcean(lon, lat))) {
        this.spawn(i)
        continue
      }
      this.lon[i] = lon
      this.lat[i] = lat

      const o = i * TRAIL
      for (let k = 0; k < TRAIL - 1; k++) {
        this.histX[o + k] = this.histX[o + k + 1]
        this.histY[o + k] = this.histY[o + k + 1]
      }
      this.histX[o + TRAIL - 1] = mercatorX(lon)
      this.histY[o + TRAIL - 1] = mercatorY(lat)

      if (this.age[i] < 2) continue

      const φ = lat * (Math.PI / 180)
      const dλ = (lon - camLon) * (Math.PI / 180)
      const cosc = Math.sin(φ) * sinCam + Math.cos(φ) * cosCam * Math.cos(dλ)
      if (cosc < minCos) continue

      const segs = interacting ? 4 : TRAIL - 1
      const start = TRAIL - 1 - segs
      for (let k = start; k < TRAIL - 1; k++) {
        const x0 = this.histX[o + k]
        const y0 = this.histY[o + k]
        const x1 = this.histX[o + k + 1]
        const y1 = this.histY[o + k + 1]
        if (Math.abs(x1 - x0) > 0.45) continue
        const a0 = ((k - start + 1) / (segs + 1)) * 0.55
        const a1 = ((k - start + 2) / (segs + 1)) * 0.95
        let p = w * STRIDE
        verts[p++] = x0
        verts[p++] = y0
        verts[p++] = spd
        verts[p++] = a0
        verts[p++] = x1
        verts[p++] = y1
        verts[p++] = spd
        verts[p++] = a1
        w += 2
      }
    }
    this.usedVerts = w
  }

  private getShader(gl: WebGL2RenderingContext, args: RenderArgs): ShaderBundle | null {
    const desc = args.shaderData
    const key = desc?.variantName || "default"
    const hit = this.shaders.get(key)
    if (hit) return hit

    const prelude = desc?.vertexShaderPrelude || ""
    const define = desc?.define || ""
    const project = prelude.includes("projectTile")
      ? "gl_Position = projectTile(a_pos);"
      : "gl_Position = u_projection_matrix * vec4(a_pos, 0.0, 1.0);"
    const vs = `#version 300 es
${prelude}
${define}
in vec2 a_pos;
in float a_speed;
in float a_alpha;
out float v_speed;
out float v_alpha;
void main() {
  ${project}
  v_speed = a_speed;
  v_alpha = a_alpha;
}`
    const fs = `#version 300 es
precision highp float;
in float v_speed;
in float v_alpha;
uniform float u_kind;
uniform float u_vmax;
out vec4 fragColor;
void main() {
  float t = clamp(v_speed / max(u_vmax, 0.05), 0.0, 1.0);
  vec3 col;
  if (u_kind > 0.5) {
    vec3 c1 = vec3(0.10, 0.55, 0.72);
    vec3 c2 = vec3(0.28, 0.90, 0.82);
    vec3 c3 = vec3(0.85, 0.98, 0.92);
    vec3 c4 = vec3(0.96, 0.78, 0.42);
    col = t < 0.4 ? mix(c1, c2, t / 0.4)
        : t < 0.75 ? mix(c2, c3, (t - 0.4) / 0.35)
        : mix(c3, c4, (t - 0.75) / 0.25);
  } else {
    vec3 c1 = vec3(0.45, 0.82, 1.00);
    vec3 c2 = vec3(0.58, 0.94, 0.78);
    vec3 c3 = vec3(0.98, 0.80, 0.38);
    vec3 c4 = vec3(0.91, 0.36, 0.10);
    col = t < 0.33 ? mix(c1, c2, t / 0.33)
        : t < 0.66 ? mix(c2, c3, (t - 0.33) / 0.33)
        : mix(c3, c4, (t - 0.66) / 0.34);
  }
  float a = v_alpha * (0.28 + 0.72 * t);
  fragColor = vec4(col * a, a);
}`
    const program = link(gl, vs, fs)
    if (!program) return null
    const bundle: ShaderBundle = {
      program,
      aPos: gl.getAttribLocation(program, "a_pos"),
      aSpeed: gl.getAttribLocation(program, "a_speed"),
      aAlpha: gl.getAttribLocation(program, "a_alpha"),
      uMatrix: gl.getUniformLocation(program, "u_projection_matrix"),
      uFallback: gl.getUniformLocation(program, "u_projection_fallback_matrix"),
      uTile: gl.getUniformLocation(program, "u_projection_tile_mercator_coords"),
      uClip: gl.getUniformLocation(program, "u_projection_clipping_plane"),
      uTrans: gl.getUniformLocation(program, "u_projection_transition"),
      uKind: gl.getUniformLocation(program, "u_kind"),
      uVmax: gl.getUniformLocation(program, "u_vmax"),
    }
    this.shaders.set(key, bundle)
    return bundle
  }
}
