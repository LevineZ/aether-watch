import type { CustomLayerInterface, Map as MlMap } from "maplibre-gl"
import {
  CURRENT_STEP,
  CURRENT_STROKE_SEGS,
  SHEET_EDGE_K,
  sheetAlpha,
  sheetFade,
} from "./currentSheet"
import { currentSegmentOk, frontCosc, MIN_COSC_CURRENT, MIN_COSC_WIND } from "./flowSegment"
import { isOcean } from "./landmask"
import {
  FLOW_VMAX,
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

/**
 * History points per particle.
 * Wind still redraws a CPU trail each frame. Currents only emit CURRENT_STROKE_SEGS;
 * the silk body lives in the destination-in fade buffer.
 */
const TRAIL = 36
/** pos.xy, other.xy, side, speed, alpha, trailT */
const STRIDE = 8
const MAX_PARTICLES = 22000
/** Two verts per history point + a few degenerates to join strips. */
const VERTS_PER_PARTICLE = TRAIL * 2 + 16
const WIND_STEP = 0.03

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
  aOther: number
  aSide: number
  aSpeed: number
  aAlpha: number
  aTrail: number
  uMatrix: WebGLUniformLocation | null
  uFallback: WebGLUniformLocation | null
  uTile: WebGLUniformLocation | null
  uClip: WebGLUniformLocation | null
  uTrans: WebGLUniformLocation | null
  uKind: WebGLUniformLocation | null
  uVmax: WebGLUniformLocation | null
  uWidth: WebGLUniformLocation | null
  uPixel: WebGLUniformLocation | null
}

type ScreenBundle = {
  fade: WebGLProgram
  blit: WebGLProgram
  uFade: WebGLUniformLocation | null
  uBlit: WebGLUniformLocation | null
  aFade: number
  aBlit: number
}

type GlSnap = {
  fbo: WebGLFramebuffer | null
  vao: WebGLVertexArrayObject | null
  arrayBuf: WebGLBuffer | null
  program: WebGLProgram | null
  activeTex: number
  tex0: WebGLTexture | null
  viewport: Int32Array
  blend: boolean
  blendSrc: number
  blendDst: number
  blendSrcA: number
  blendDstA: number
  blendColor: Float32Array
  depth: boolean
  stencil: boolean
  scissor: boolean
  cull: boolean
  depthMask: boolean
  colorMask: boolean[]
}

function snapGl(gl: WebGL2RenderingContext): GlSnap {
  const activeTex = gl.getParameter(gl.ACTIVE_TEXTURE)
  gl.activeTexture(gl.TEXTURE0)
  const tex0 = gl.getParameter(gl.TEXTURE_BINDING_2D)
  gl.activeTexture(activeTex)
  return {
    fbo: gl.getParameter(gl.FRAMEBUFFER_BINDING),
    vao: gl.getParameter(gl.VERTEX_ARRAY_BINDING),
    arrayBuf: gl.getParameter(gl.ARRAY_BUFFER_BINDING),
    program: gl.getParameter(gl.CURRENT_PROGRAM),
    activeTex,
    tex0,
    viewport: gl.getParameter(gl.VIEWPORT),
    blend: gl.isEnabled(gl.BLEND),
    blendSrc: gl.getParameter(gl.BLEND_SRC_RGB),
    blendDst: gl.getParameter(gl.BLEND_DST_RGB),
    blendSrcA: gl.getParameter(gl.BLEND_SRC_ALPHA),
    blendDstA: gl.getParameter(gl.BLEND_DST_ALPHA),
    blendColor: gl.getParameter(gl.BLEND_COLOR),
    depth: gl.isEnabled(gl.DEPTH_TEST),
    stencil: gl.isEnabled(gl.STENCIL_TEST),
    scissor: gl.isEnabled(gl.SCISSOR_TEST),
    cull: gl.isEnabled(gl.CULL_FACE),
    depthMask: gl.getParameter(gl.DEPTH_WRITEMASK),
    colorMask: gl.getParameter(gl.COLOR_WRITEMASK),
  }
}

function restoreGl(gl: WebGL2RenderingContext, s: GlSnap) {
  gl.bindFramebuffer(gl.FRAMEBUFFER, s.fbo)
  gl.viewport(s.viewport[0], s.viewport[1], s.viewport[2], s.viewport[3])
  gl.bindVertexArray(s.vao)
  gl.bindBuffer(gl.ARRAY_BUFFER, s.arrayBuf)
  gl.useProgram(s.program)
  gl.activeTexture(gl.TEXTURE0)
  gl.bindTexture(gl.TEXTURE_2D, s.tex0)
  gl.activeTexture(s.activeTex)
  s.blend ? gl.enable(gl.BLEND) : gl.disable(gl.BLEND)
  gl.blendFuncSeparate(s.blendSrc, s.blendDst, s.blendSrcA, s.blendDstA)
  gl.blendColor(s.blendColor[0], s.blendColor[1], s.blendColor[2], s.blendColor[3])
  s.depth ? gl.enable(gl.DEPTH_TEST) : gl.disable(gl.DEPTH_TEST)
  s.stencil ? gl.enable(gl.STENCIL_TEST) : gl.disable(gl.STENCIL_TEST)
  s.scissor ? gl.enable(gl.SCISSOR_TEST) : gl.disable(gl.SCISSOR_TEST)
  s.cull ? gl.enable(gl.CULL_FACE) : gl.disable(gl.CULL_FACE)
  gl.depthMask(s.depthMask)
  gl.colorMask(s.colorMask[0], s.colorMask[1], s.colorMask[2], s.colorMask[3])
}

/**
 * MapLibre custom layer: CPU advection + GPU triangle-strip ribbons.
 * WebGL lineWidth is 1px on most GPUs, so GL_LINES read as dots at globe scale.
 *
 * Currents: short gaussian flakes drawn into a persistent FBO that is faded
 * each tick with a destination-in multiply (cambecc/earth 0.97 fill). Overlap
 * reads as silk sheets, not a spaghetti of 40-point ribbons. Wind stays a
 * thicker, faster yellow-green ribbon so the two modes stay distinct.
 * Clip-space extrusion MUST skip long NDC / wrap segments or they become horizontal slabs.
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
  private screen: ScreenBundle | null = null
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
  private frameDt = 16.67
  private visible = true
  private pageHidden = false
  private reduced = false
  private dropped = 0
  private observer: IntersectionObserver | null = null
  private gen = 0

  private trailFbo: WebGLFramebuffer | null = null
  private trailTex: WebGLTexture | null = null
  private trailW = 0
  private trailH = 0
  private quadVao: WebGLVertexArrayObject | null = null
  private quadBuf: WebGLBuffer | null = null
  private mustClearTrail = true
  private trailStamp = -1

  setField(wind: Wind | null, kind: FlowKind = this.kind) {
    this.kind = kind
    this.grid = wind ? packWind(wind) : null
    this.gen++
    this.mustClearTrail = true
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
    const next = Math.min(MAX_PARTICLES, Math.max(4500, Math.round(this.baseCount(width, dpr) * this.quality())))
    if (next !== this.count) this.seed(next)
  }

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    this.map = map
    this.gl = gl
    this.buffer = gl.createBuffer()
    this.vao = gl.createVertexArray()
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer)
    gl.bufferData(gl.ARRAY_BUFFER, this.verts.byteLength, gl.DYNAMIC_DRAW)
    this.initQuad(gl)
    this.mustClearTrail = true

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
    if (this.quadBuf) gl.deleteBuffer(this.quadBuf)
    if (this.quadVao) gl.deleteVertexArray(this.quadVao)
    this.destroyTrail(gl)
    if (this.screen) {
      gl.deleteProgram(this.screen.fade)
      gl.deleteProgram(this.screen.blit)
    }
    for (const s of this.shaders.values()) gl.deleteProgram(s.program)
    this.shaders.clear()
    this.screen = null
    this.buffer = null
    this.vao = null
    this.quadBuf = null
    this.quadVao = null
    this.gl = null
    this.map = null
  }

  /** Update the screen-space fade buffer before MapLibre composites this layer. */
  prerender(gl: WebGL2RenderingContext, args: RenderArgs) {
    if (this.kind !== "current" || !this.visible || !this.playing || !this.grid) return
    this.paintTrail(gl, args)
  }

  render(gl: WebGL2RenderingContext, args: RenderArgs) {
    if (!this.visible || !this.playing || !this.grid || this.usedVerts < 4) return
    if (this.kind === "current") {
      this.paintTrail(gl, args)
      if (this.trailTex) {
        this.blitTrail(gl)
        return
      }
    }
    this.drawStrips(gl, args, false)
  }

  private _onVis: (() => void) | null = null
  private _onMoveStart = () => {
    this.interacting = true
    this.mustClearTrail = true
  }
  private _onMoveEnd = () => {
    this.interacting = false
  }

  private baseCount(width: number, dpr: number) {
    if (this.reduced) return this.kind === "current" ? 4200 : 2200
    return Math.min(MAX_PARTICLES, targetParticleCount(width, dpr, this.kind))
  }

  private quality() {
    if (this.dropped > 8) return 0.55
    if (this.dropped > 3) return 0.75
    return 1
  }

  /**
   * Pixel width at default China globe framing (~zoom 1.7).
   * cambecc/earth uses PARTICLE_LINE_WIDTH = 1.0; currents stay near that so overlaps
   * read as sheets. Wind stays a distinct thicker ribbon.
   */
  private ribbonWidth() {
    const z = this.map?.getZoom() ?? 1.7
    if (this.kind === "current") {
      const zoomMul = z < 2.15 ? 1.12 : z < 3.4 ? 1.0 : 0.9
      return 1.95 * zoomMul
    }
    const zoomMul = z < 2.15 ? 1.22 : z < 3.4 ? 1.0 : 0.85
    return 2.2 * zoomMul
  }

  private seed(n: number) {
    this.count = Math.min(MAX_PARTICLES, n)
    for (let i = 0; i < this.count; i++) this.spawn(i, true)
    this.usedVerts = 0
    this.mustClearTrail = true
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
    const current = this.kind === "current"
    const step = current ? CURRENT_STEP : WIND_STEP
    const dead = current ? 0.01 : 0.1
    const o = i * TRAIL
    const xs = new Float32Array(TRAIL)
    const ys = new Float32Array(TRAIL)
    let filled = 0
    const pre = randomAge && this.grid ? TRAIL - 1 : 0
    for (let s = 0; s <= pre; s++) {
      xs[filled] = mercatorX(lon)
      ys[filled] = mercatorY(lat)
      filled++
      if (!this.grid || s === pre) break
      const [u, v] = sampleWind(this.grid, lon, lat, current)
      const spd = Math.hypot(u, v)
      lon = wrapLon(lon + u * step)
      lat += v * step
      if (spd < dead || lat > 76 || lat < -76 || (current && !isOcean(lon, lat))) break
    }
    this.lon[i] = lon
    this.lat[i] = lat
    this.age[i] = randomAge ? (TRAIL + ((Math.random() * 80) | 0)) : filled
    const x0 = xs[0]
    const y0 = ys[0]
    const pad = TRAIL - filled
    for (let k = 0; k < TRAIL; k++) {
      if (k < pad) {
        this.histX[o + k] = x0
        this.histY[o + k] = y0
      } else {
        this.histX[o + k] = xs[k - pad]
        this.histY[o + k] = ys[k - pad]
      }
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
        this.frameDt = dt
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
    const maxAge = interacting ? 90 : current ? 460 : 150
    let w = 0
    const verts = this.verts
    const minCos = current ? MIN_COSC_CURRENT : MIN_COSC_WIND
    const segs = interacting
      ? current
        ? Math.min(2, CURRENT_STROKE_SEGS)
        : 10
      : current
        ? CURRENT_STROKE_SEGS
        : Math.min(TRAIL - 1, 22)
    const start = TRAIL - 1 - segs
    const vmax = current ? FLOW_VMAX.current : FLOW_VMAX.wind

    const cap = this.verts.length / STRIDE - 8
    const emit = (x: number, y: number, ox: number, oy: number, side: number, spd: number, alpha: number, t: number) => {
      if (w >= cap) return
      let p = w * STRIDE
      verts[p++] = x
      verts[p++] = y
      verts[p++] = ox
      verts[p++] = oy
      verts[p++] = side
      verts[p++] = spd
      verts[p++] = alpha
      verts[p++] = t
      w++
    }
    const dupLast = () => {
      if (w === 0) return
      const b = (w - 1) * STRIDE
      const p = w * STRIDE
      for (let k = 0; k < STRIDE; k++) verts[p + k] = verts[b + k]
      w++
    }
    const emitPair = (x: number, y: number, ox: number, oy: number, spd: number, alpha: number, t: number) => {
      emit(x, y, ox, oy, -1, spd, alpha, t)
      emit(x, y, ox, oy, 1, spd, alpha, t)
    }
    const beginStrip = (x: number, y: number, ox: number, oy: number, spd: number, alpha: number, t: number) => {
      if (w > 0) {
        dupLast()
        emit(x, y, ox, oy, -1, spd, alpha, t)
        dupLast()
        emit(x, y, ox, oy, 1, spd, alpha, t)
      } else {
        emitPair(x, y, ox, oy, spd, alpha, t)
      }
    }
    const segOk = (x0: number, y0: number, x1: number, y1: number) =>
      currentSegmentOk(x0, y0, x1, y1, camLon, camLat, minCos)

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

      if (this.age[i] < 3) continue
      if (frontCosc(lon, lat, camLon, sinCam, cosCam) < minCos) continue

      let open = false
      for (let k = start; k < TRAIL; k++) {
        const x = this.histX[o + k]
        const y = this.histY[o + k]
        const other = k < TRAIL - 1 ? k + 1 : k - 1
        const ox = this.histX[o + other]
        const oy = this.histY[o + other]
        const t = (k - start + 1) / (segs + 1)
        const alpha = current ? sheetAlpha(t, spd / vmax) : Math.pow(t, 0.72)
        const linked = k > start && segOk(this.histX[o + k - 1], this.histY[o + k - 1], x, y)
        if (!linked) {
          if (k === TRAIL - 1 || !segOk(x, y, ox, oy)) {
            open = false
            continue
          }
          beginStrip(x, y, ox, oy, spd, alpha, t)
          open = true
          continue
        }
        if (!open) {
          beginStrip(x, y, ox, oy, spd, alpha, t)
          open = true
        } else {
          emitPair(x, y, ox, oy, spd, alpha, t)
        }
      }
    }
    this.usedVerts = w
  }

  private initQuad(gl: WebGL2RenderingContext) {
    this.quadVao = gl.createVertexArray()
    this.quadBuf = gl.createBuffer()
    gl.bindVertexArray(this.quadVao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    gl.bindVertexArray(null)
  }

  private destroyTrail(gl: WebGL2RenderingContext) {
    if (this.trailFbo) gl.deleteFramebuffer(this.trailFbo)
    if (this.trailTex) gl.deleteTexture(this.trailTex)
    this.trailFbo = null
    this.trailTex = null
    this.trailW = 0
    this.trailH = 0
  }

  private ensureTrail(gl: WebGL2RenderingContext) {
    // Slightly undersize + linear upsample so short strokes blur into silk.
    const w = Math.max(1, Math.round(gl.drawingBufferWidth * 0.62))
    const h = Math.max(1, Math.round(gl.drawingBufferHeight * 0.62))
    if (this.trailTex && this.trailFbo && this.trailW === w && this.trailH === h) return true
    this.destroyTrail(gl)
    const tex = gl.createTexture()
    const fbo = gl.createFramebuffer()
    if (!tex || !fbo) return false
    gl.bindTexture(gl.TEXTURE_2D, tex)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null)
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo)
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0)
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE
    gl.bindFramebuffer(gl.FRAMEBUFFER, null)
    if (!ok) {
      gl.deleteTexture(tex)
      gl.deleteFramebuffer(fbo)
      return false
    }
    this.trailTex = tex
    this.trailFbo = fbo
    this.trailW = w
    this.trailH = h
    this.mustClearTrail = true
    return true
  }

  private ensureScreen(gl: WebGL2RenderingContext): ScreenBundle | null {
    if (this.screen) return this.screen
    const vs = `#version 300 es
in vec2 a_pos;
out vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`
    const fadeFs = `#version 300 es
precision highp float;
uniform float u_fade;
out vec4 fragColor;
void main() {
  fragColor = vec4(u_fade);
}`
    const blitFs = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
in vec2 v_uv;
out vec4 fragColor;
void main() {
  fragColor = texture(u_tex, v_uv);
}`
    const fade = link(gl, vs, fadeFs)
    const blit = link(gl, vs, blitFs)
    if (!fade || !blit) return null
    this.screen = {
      fade,
      blit,
      uFade: gl.getUniformLocation(fade, "u_fade"),
      uBlit: gl.getUniformLocation(blit, "u_tex"),
      aFade: gl.getAttribLocation(fade, "a_pos"),
      aBlit: gl.getAttribLocation(blit, "a_pos"),
    }
    return this.screen
  }

  private bindQuad(gl: WebGL2RenderingContext, loc: number) {
    gl.bindVertexArray(this.quadVao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuf)
    gl.enableVertexAttribArray(loc)
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
  }

  /**
   * destination-in equivalent: multiply the trail FBO by fade, then add short
   * current flakes. Skips extra MapLibre passes in the same animation tick.
   */
  private paintTrail(gl: WebGL2RenderingContext, args: RenderArgs) {
    if (this.trailStamp === this.lastT && !this.mustClearTrail) return
    if (!this.ensureTrail(gl) || !this.trailFbo || !this.trailTex) return
    const screen = this.ensureScreen(gl)
    if (!screen) return
    const snap = snapGl(gl)
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.trailFbo)
    gl.viewport(0, 0, this.trailW, this.trailH)
    gl.disable(gl.DEPTH_TEST)
    gl.disable(gl.STENCIL_TEST)
    gl.disable(gl.SCISSOR_TEST)
    gl.disable(gl.CULL_FACE)
    gl.depthMask(false)
    gl.colorMask(true, true, true, true)

    if (this.mustClearTrail) {
      gl.clearColor(0, 0, 0, 0)
      gl.clear(gl.COLOR_BUFFER_BIT)
      this.mustClearTrail = false
    } else {
      const fade = sheetFade(this.frameDt, this.interacting)
      gl.enable(gl.BLEND)
      gl.blendColor(fade, fade, fade, fade)
      gl.blendFunc(gl.ZERO, gl.CONSTANT_COLOR)
      gl.useProgram(screen.fade)
      gl.uniform1f(screen.uFade, fade)
      this.bindQuad(gl, screen.aFade)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
    }

    if (this.usedVerts >= 4) {
      gl.enable(gl.BLEND)
      // Premultiplied over (not additive): jets saturate to silk, not white lines.
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
      this.drawStrips(gl, args, false, false)
    }
    restoreGl(gl, snap)
    this.trailStamp = this.lastT
  }

  private blitTrail(gl: WebGL2RenderingContext) {
    const screen = this.ensureScreen(gl)
    if (!screen || !this.trailTex) return
    const snap = snapGl(gl)
    gl.disable(gl.DEPTH_TEST)
    gl.disable(gl.CULL_FACE)
    gl.depthMask(false)
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    gl.useProgram(screen.blit)
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, this.trailTex)
    gl.uniform1i(screen.uBlit, 0)
    this.bindQuad(gl, screen.aBlit)
    gl.drawArrays(gl.TRIANGLES, 0, 3)
    restoreGl(gl, snap)
  }

  private drawStrips(gl: WebGL2RenderingContext, args: RenderArgs, additive: boolean, restore = true) {
    const bundle = this.getShader(gl, args)
    if (!bundle) return
    const snap = restore ? snapGl(gl) : null
    const proj = args.defaultProjectionData
    gl.useProgram(bundle.program)
    gl.uniformMatrix4fv(bundle.uMatrix, false, proj.mainMatrix as Float32Array)
    gl.uniformMatrix4fv(bundle.uFallback, false, proj.fallbackMatrix as Float32Array)
    gl.uniform4f(bundle.uTile, ...proj.tileMercatorCoords)
    gl.uniform4f(bundle.uClip, ...proj.clippingPlane)
    gl.uniform1f(bundle.uTrans, proj.projectionTransition)
    gl.uniform1f(bundle.uKind, this.kind === "current" ? 1 : 0)
    gl.uniform1f(bundle.uVmax, this.kind === "current" ? FLOW_VMAX.current : FLOW_VMAX.wind)
    gl.uniform1f(bundle.uWidth, this.ribbonWidth())
    gl.uniform2f(bundle.uPixel, 2 / Math.max(1, gl.drawingBufferWidth), 2 / Math.max(1, gl.drawingBufferHeight))

    if (this.vao) gl.bindVertexArray(this.vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer)
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.verts.subarray(0, this.usedVerts * STRIDE))

    gl.enableVertexAttribArray(bundle.aPos)
    gl.enableVertexAttribArray(bundle.aOther)
    gl.enableVertexAttribArray(bundle.aSide)
    gl.enableVertexAttribArray(bundle.aSpeed)
    gl.enableVertexAttribArray(bundle.aAlpha)
    if (bundle.aTrail >= 0) gl.enableVertexAttribArray(bundle.aTrail)
    const stride = STRIDE * 4
    gl.vertexAttribPointer(bundle.aPos, 2, gl.FLOAT, false, stride, 0)
    gl.vertexAttribPointer(bundle.aOther, 2, gl.FLOAT, false, stride, 8)
    gl.vertexAttribPointer(bundle.aSide, 1, gl.FLOAT, false, stride, 16)
    gl.vertexAttribPointer(bundle.aSpeed, 1, gl.FLOAT, false, stride, 20)
    gl.vertexAttribPointer(bundle.aAlpha, 1, gl.FLOAT, false, stride, 24)
    if (bundle.aTrail >= 0) gl.vertexAttribPointer(bundle.aTrail, 1, gl.FLOAT, false, stride, 28)

    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, additive ? gl.ONE : gl.ONE_MINUS_SRC_ALPHA)
    gl.disable(gl.DEPTH_TEST)
    gl.disable(gl.CULL_FACE)
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, this.usedVerts)
    if (this.vao) gl.bindVertexArray(null)
    if (snap) restoreGl(gl, snap)
  }

  private getShader(gl: WebGL2RenderingContext, args: RenderArgs): ShaderBundle | null {
    const desc = args.shaderData
    const key = desc?.variantName || "default"
    const hit = this.shaders.get(key)
    if (hit) return hit

    const prelude = desc?.vertexShaderPrelude || ""
    const define = desc?.define || ""
    const clipPos = prelude.includes("projectTile")
      ? "vec4 clipPos(vec2 p) { return projectTile(p); }"
      : "vec4 clipPos(vec2 p) { return u_projection_matrix * vec4(p, 0.0, 1.0); }"
    const vs = `#version 300 es
${prelude}
${define}
in vec2 a_pos;
in vec2 a_other;
in float a_side;
in float a_speed;
in float a_alpha;
in float a_trail;
uniform vec2 u_pixel;
uniform float u_width;
uniform float u_kind;
out float v_speed;
out float v_alpha;
out float v_side;
out float v_keep;
${clipPos}
void main() {
  vec4 a = clipPos(a_pos);
  vec4 b = clipPos(a_other);
  // Long NDC spans (silhouette / date-line / behind-camera) become giant bars.
  float keep = (a.w > 0.02 && b.w > 0.02) ? 1.0 : 0.0;
  vec2 ndcA = a.xy / max(abs(a.w), 1e-6);
  vec2 ndcB = b.xy / max(abs(b.w), 1e-6);
  vec2 dir = ndcB - ndcA;
  float len = length(dir);
  const float MAX_NDC = 0.08;
  if (len < 1e-7 || len > MAX_NDC || abs(ndcA.x) > 1.25 || abs(ndcA.y) > 1.25) keep = 0.0;
  vec2 n = len > 1e-7 ? vec2(-dir.y, dir.x) / len : vec2(0.0, 1.0);
  // No mid-trail flake bulge — that still read as a tapered line.
  float slim = 1.0 - smoothstep(0.028, MAX_NDC, len);
  vec2 offset = keep > 0.5 ? n * a_side * u_width * u_pixel * slim : vec2(0.0);
  gl_Position = vec4((ndcA + offset) * a.w, a.z, a.w);
  v_speed = a_speed;
  v_alpha = a_alpha;
  v_side = a_side;
  v_keep = keep;
}`
    const fs = `#version 300 es
precision highp float;
in float v_speed;
in float v_alpha;
in float v_side;
in float v_keep;
uniform float u_kind;
uniform float u_vmax;
out vec4 fragColor;
void main() {
  if (v_keep < 0.99) discard;
  float t = clamp(v_speed / max(u_vmax, 0.05), 0.0, 1.0);
  vec3 col;
  if (u_kind > 0.5) {
    vec3 c1 = vec3(0.10, 0.52, 0.70);
    vec3 c2 = vec3(0.20, 0.82, 0.88);
    vec3 c3 = vec3(0.55, 0.96, 0.92);
    vec3 c4 = vec3(0.82, 0.99, 0.96);
    col = t < 0.4 ? mix(c1, c2, t / 0.4)
        : t < 0.75 ? mix(c2, c3, (t - 0.4) / 0.35)
        : mix(c3, c4, (t - 0.75) / 0.25);
  } else {
    vec3 c1 = vec3(0.22, 0.72, 0.38);
    vec3 c2 = vec3(0.62, 0.92, 0.28);
    vec3 c3 = vec3(0.97, 0.92, 0.30);
    vec3 c4 = vec3(1.00, 0.78, 0.22);
    col = t < 0.33 ? mix(c1, c2, t / 0.33)
        : t < 0.66 ? mix(c2, c3, (t - 0.33) / 0.33)
        : mix(c3, c4, (t - 0.66) / 0.34);
  }
  float edge = u_kind > 0.5
    ? exp(-v_side * v_side * ${SHEET_EDGE_K.toFixed(2)})
    : (1.0 - smoothstep(0.55, 1.0, abs(v_side)));
  float sheet = u_kind > 0.5 ? 1.0 : (0.58 + 0.42 * t);
  float a = v_alpha * edge * sheet;
  fragColor = vec4(col * a, a);
}`
    const program = link(gl, vs, fs)
    if (!program) return null
    const bundle: ShaderBundle = {
      program,
      aPos: gl.getAttribLocation(program, "a_pos"),
      aOther: gl.getAttribLocation(program, "a_other"),
      aSide: gl.getAttribLocation(program, "a_side"),
      aSpeed: gl.getAttribLocation(program, "a_speed"),
      aAlpha: gl.getAttribLocation(program, "a_alpha"),
      aTrail: gl.getAttribLocation(program, "a_trail"),
      uMatrix: gl.getUniformLocation(program, "u_projection_matrix"),
      uFallback: gl.getUniformLocation(program, "u_projection_fallback_matrix"),
      uTile: gl.getUniformLocation(program, "u_projection_tile_mercator_coords"),
      uClip: gl.getUniformLocation(program, "u_projection_clipping_plane"),
      uTrans: gl.getUniformLocation(program, "u_projection_transition"),
      uKind: gl.getUniformLocation(program, "u_kind"),
      uVmax: gl.getUniformLocation(program, "u_vmax"),
      uWidth: gl.getUniformLocation(program, "u_width"),
      uPixel: gl.getUniformLocation(program, "u_pixel"),
    }
    this.shaders.set(key, bundle)
    return bundle
  }
}
