import type { CustomLayerInterface, Map as MlMap } from "maplibre-gl"
import { colorAt, type Palette } from "~/utils/colormap"
import { sampleBilinear } from "~/utils/interp"
import { mercatorX, mercatorY } from "~/utils/windField"
import type { ScalarField } from "~/utils/rasterField"

type RenderArgs = {
  shaderData?: { variantName: string; vertexShaderPrelude: string; define: string }
  defaultProjectionData: {
    mainMatrix: Float32Array | number[]
    fallbackMatrix: Float32Array | number[]
    tileMercatorCoords: [number, number, number, number]
    clippingPlane: [number, number, number, number]
    projectionTransition: number
  }
}

function compile(gl: WebGL2RenderingContext, type: number, source: string) {
  const sh = gl.createShader(type)
  if (!sh) return null
  gl.shaderSource(sh, source)
  gl.compileShader(sh)
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    console.warn("[scalar] shader", gl.getShaderInfoLog(sh))
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
    console.warn("[scalar] program", gl.getProgramInfoLog(prog))
    gl.deleteProgram(prog)
    return null
  }
  return prog
}

type Bundle = {
  program: WebGLProgram
  aPos: number
  aUv: number
  uMatrix: WebGLUniformLocation | null
  uFallback: WebGLUniformLocation | null
  uTile: WebGLUniformLocation | null
  uClip: WebGLUniformLocation | null
  uTrans: WebGLUniformLocation | null
  uGrid: WebGLUniformLocation | null
  uCmap: WebGLUniformLocation | null
  uOpacity: WebGLUniformLocation | null
  uSignal: WebGLUniformLocation | null
}

function buildMesh(west: number, south: number, east: number, north: number, tx: number, ty: number) {
  const verts: number[] = []
  const dx = (east - west) / tx
  const dy = (north - south) / ty
  for (let j = 0; j < ty; j++) {
    for (let i = 0; i < tx; i++) {
      const lon0 = west + i * dx
      const lon1 = west + (i + 1) * dx
      if (Math.abs(lon1 - lon0) > 40) continue
      const lat0 = south + j * dy
      const lat1 = south + (j + 1) * dy
      const u0 = i / tx
      const u1 = (i + 1) / tx
      const v0 = j / ty
      const v1 = (j + 1) / ty
      const quad = [
        [lon0, lat0, u0, v0],
        [lon1, lat0, u1, v0],
        [lon1, lat1, u1, v1],
        [lon0, lat0, u0, v0],
        [lon1, lat1, u1, v1],
        [lon0, lat1, u0, v1],
      ]
      for (const [lon, lat, u, v] of quad) {
        verts.push(mercatorX(lon), mercatorY(lat), u, v)
      }
    }
  }
  return new Float32Array(verts)
}

/** Render-side bilinear densification. 16× turns a 16×10 live grid into a 256×160 texture. */
export const SCALAR_UPSAMPLE = 16

function packGrid(field: ScalarField, scale = SCALAR_UPSAMPLE) {
  const srcNy = field.values.length
  const srcNx = field.values[0]?.length || 0
  const span = field.max - field.min || 1
  const nx = Math.max(2, (srcNx - 1) * scale + 1)
  const ny = Math.max(2, (srcNy - 1) * scale + 1)
  const pix = new Uint8Array(nx * ny * 4)
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const x = (i / Math.max(1, nx - 1)) * Math.max(0, srcNx - 1)
      const y = (j / Math.max(1, ny - 1)) * Math.max(0, srcNy - 1)
      const v = sampleBilinear(field.values, x, y)
      const o = (j * nx + i) * 4
      if (v == null || !Number.isFinite(v)) {
        pix[o + 3] = 0
        continue
      }
      const t = Math.min(1, Math.max(0, (v - field.min) / span))
      pix[o] = Math.round(t * 255)
      pix[o + 1] = pix[o]
      pix[o + 2] = pix[o]
      pix[o + 3] = 255
    }
  }
  return { pix, nx, ny }
}

function packCmap(palette: Palette) {
  const pix = new Uint8Array(256 * 4)
  for (let i = 0; i < 256; i++) {
    const [r, g, b] = colorAt(palette, i / 255)
    pix[i * 4] = r
    pix[i * 4 + 1] = g
    pix[i * 4 + 2] = b
    pix[i * 4 + 3] = 255
  }
  return pix
}

/**
 * Globe-safe scalar overlay: tessellated mercator mesh + GPU bilinear field texture.
 * Nulls stay transparent; precip-like palettes fade with signal so coastlines remain.
 */
export class ScalarFieldLayer implements CustomLayerInterface {
  id = "aether-scalar"
  type = "custom" as const
  renderingMode = "2d" as const

  visible = false
  opacity = 0.52
  signalAlpha = false

  private map: MlMap | null = null
  private gl: WebGL2RenderingContext | null = null
  private buffer: WebGLBuffer | null = null
  private vao: WebGLVertexArrayObject | null = null
  private gridTex: WebGLTexture | null = null
  private cmapTex: WebGLTexture | null = null
  private shaders = new Map<string, Bundle>()
  private verts = new Float32Array(0)
  private vertCount = 0

  setField(field: ScalarField | null, palette: Palette, opts?: { signalAlpha?: boolean; opacity?: number }) {
    this.signalAlpha = opts?.signalAlpha ?? false
    this.opacity = opts?.opacity ?? (this.signalAlpha ? 0.82 : 0.48)
    this.visible = !!field
    const gl = this.gl
    if (!gl) {
      this._pending = field && palette ? { field, palette } : null
      this.map?.triggerRepaint()
      return
    }
    if (!field) {
      this.vertCount = 0
      this.map?.triggerRepaint()
      return
    }
    const west = field.bbox?.west ?? field.lons[0]
    const east = field.bbox?.east ?? field.lons[field.lons.length - 1]
    const south = field.bbox?.south ?? field.lats[0]
    const north = field.bbox?.north ?? field.lats[field.lats.length - 1]
    const spanX = Math.max(24, Math.min(220, Math.round((east - west) / 1.5)))
    const spanY = Math.max(16, Math.min(120, Math.round((north - south) / 1.5)))
    this.verts = buildMesh(west, south, east, north, spanX, spanY)
    this.vertCount = this.verts.length / 4
    if (this.buffer) {
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer)
      gl.bufferData(gl.ARRAY_BUFFER, this.verts, gl.DYNAMIC_DRAW)
    }
    const { pix, nx, ny } = packGrid(field, SCALAR_UPSAMPLE)
    this.upload(gl, this.gridTex, nx, ny, pix, gl.LINEAR)
    this.upload(gl, this.cmapTex, 256, 1, packCmap(palette), gl.LINEAR)
    this.map?.triggerRepaint()
  }

  private _pending: { field: ScalarField; palette: Palette } | null = null

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    this.map = map
    this.gl = gl
    this.buffer = gl.createBuffer()
    this.vao = gl.createVertexArray()
    this.gridTex = gl.createTexture()
    this.cmapTex = gl.createTexture()
    if (this._pending) {
      this.setField(this._pending.field, this._pending.palette)
      this._pending = null
    }
  }

  onRemove(_map: MlMap, gl: WebGL2RenderingContext) {
    if (this.buffer) gl.deleteBuffer(this.buffer)
    if (this.vao) gl.deleteVertexArray(this.vao)
    if (this.gridTex) gl.deleteTexture(this.gridTex)
    if (this.cmapTex) gl.deleteTexture(this.cmapTex)
    for (const s of this.shaders.values()) gl.deleteProgram(s.program)
    this.shaders.clear()
    this.buffer = null
    this.vao = null
    this.gridTex = null
    this.cmapTex = null
    this.gl = null
    this.map = null
  }

  render(gl: WebGL2RenderingContext, args: RenderArgs) {
    if (!this.visible || this.vertCount < 3) return
    const bundle = this.getShader(gl, args)
    if (!bundle) return
    const proj = args.defaultProjectionData
    gl.useProgram(bundle.program)
    gl.uniformMatrix4fv(bundle.uMatrix, false, proj.mainMatrix as Float32Array)
    gl.uniformMatrix4fv(bundle.uFallback, false, proj.fallbackMatrix as Float32Array)
    gl.uniform4f(bundle.uTile, ...proj.tileMercatorCoords)
    gl.uniform4f(bundle.uClip, ...proj.clippingPlane)
    gl.uniform1f(bundle.uTrans, proj.projectionTransition)
    gl.uniform1f(bundle.uOpacity, this.opacity)
    gl.uniform1f(bundle.uSignal, this.signalAlpha ? 1 : 0)
    gl.uniform1i(bundle.uGrid, 0)
    gl.uniform1i(bundle.uCmap, 1)

    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, this.gridTex)
    gl.activeTexture(gl.TEXTURE1)
    gl.bindTexture(gl.TEXTURE_2D, this.cmapTex)

    if (this.vao) gl.bindVertexArray(this.vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer)
    gl.enableVertexAttribArray(bundle.aPos)
    gl.enableVertexAttribArray(bundle.aUv)
    gl.vertexAttribPointer(bundle.aPos, 2, gl.FLOAT, false, 16, 0)
    gl.vertexAttribPointer(bundle.aUv, 2, gl.FLOAT, false, 16, 8)

    gl.enable(gl.BLEND)
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
    gl.disable(gl.DEPTH_TEST)
    gl.drawArrays(gl.TRIANGLES, 0, this.vertCount)
    if (this.vao) gl.bindVertexArray(null)
  }

  private upload(
    gl: WebGL2RenderingContext,
    tex: WebGLTexture | null,
    w: number,
    h: number,
    pix: Uint8Array,
    filter: number,
  ) {
    if (!tex) return
    gl.bindTexture(gl.TEXTURE_2D, tex)
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, pix)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
  }

  private getShader(gl: WebGL2RenderingContext, args: RenderArgs): Bundle | null {
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
in vec2 a_uv;
out vec2 v_uv;
void main() {
  ${project}
  v_uv = a_uv;
}`
    const fs = `#version 300 es
precision highp float;
in vec2 v_uv;
uniform sampler2D u_grid;
uniform sampler2D u_cmap;
uniform float u_opacity;
uniform float u_signal;
out vec4 fragColor;
void main() {
  vec4 g = texture(u_grid, v_uv);
  if (g.a < 0.05) discard;
  float t = g.r;
  vec3 col = texture(u_cmap, vec2(t, 0.5)).rgb;
  float a = u_opacity;
  if (u_signal > 0.5) a *= pow(clamp(t, 0.0, 1.0), 0.68);
  if (a < 0.02) discard;
  fragColor = vec4(col, a);
}`
    const program = link(gl, vs, fs)
    if (!program) return null
    const bundle: Bundle = {
      program,
      aPos: gl.getAttribLocation(program, "a_pos"),
      aUv: gl.getAttribLocation(program, "a_uv"),
      uMatrix: gl.getUniformLocation(program, "u_projection_matrix"),
      uFallback: gl.getUniformLocation(program, "u_projection_fallback_matrix"),
      uTile: gl.getUniformLocation(program, "u_projection_tile_mercator_coords"),
      uClip: gl.getUniformLocation(program, "u_projection_clipping_plane"),
      uTrans: gl.getUniformLocation(program, "u_projection_transition"),
      uGrid: gl.getUniformLocation(program, "u_grid"),
      uCmap: gl.getUniformLocation(program, "u_cmap"),
      uOpacity: gl.getUniformLocation(program, "u_opacity"),
      uSignal: gl.getUniformLocation(program, "u_signal"),
    }
    this.shaders.set(key, bundle)
    return bundle
  }
}

export function signalPalette(palette: Palette) {
  return palette === "rain" || palette === "cloud"
}
