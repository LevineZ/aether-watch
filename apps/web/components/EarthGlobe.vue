<template>
  <div class="globe-wrap">
    <div ref="host" class="globe-el" />
    <canvas ref="cv" class="wind-cv" />
  </div>
</template>

<script setup lang="ts">
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"

type Wind = {
  width: number
  height: number
  west: number
  south: number
  east: number
  north: number
  u: number[]
  v: number[]
}

const props = defineProps<{ wind: Wind | null; playing?: boolean }>()
const host = ref<HTMLDivElement | null>(null)
const cv = ref<HTMLCanvasElement | null>(null)

let map: maplibregl.Map | null = null
let raf = 0
let particles: { lon: number; lat: number; age: number }[] = []

function sample(lon: number, lat: number): [number, number] {
  const w = props.wind
  if (!w) return [0, 0]
  let x = ((lon - w.west) / (w.east - w.west)) * (w.width - 1)
  if (x < 0) x += w.width - 1
  const y = ((w.north - lat) / (w.north - w.south)) * (w.height - 1)
  const x0 = Math.max(0, Math.min(w.width - 1, Math.floor(x)))
  const y0 = Math.max(0, Math.min(w.height - 1, Math.floor(y)))
  const x1 = Math.min(w.width - 1, x0 + 1)
  const y1 = Math.min(w.height - 1, y0 + 1)
  const fx = x - x0
  const fy = y - y0
  const idx = (yy: number, xx: number) => yy * w.width + xx
  const u =
    w.u[idx(y0, x0)] * (1 - fx) * (1 - fy) +
    w.u[idx(y0, x1)] * fx * (1 - fy) +
    w.u[idx(y1, x0)] * (1 - fx) * fy +
    w.u[idx(y1, x1)] * fx * fy
  const v =
    w.v[idx(y0, x0)] * (1 - fx) * (1 - fy) +
    w.v[idx(y0, x1)] * fx * (1 - fy) +
    w.v[idx(y1, x0)] * (1 - fx) * fy +
    w.v[idx(y1, x1)] * fx * fy
  return [u, v]
}

function seed(n: number) {
  particles = Array.from({ length: n }, () => ({
    lon: Math.random() * 360 - 180,
    lat: Math.random() * 140 - 70,
    age: Math.floor(Math.random() * 90),
  }))
}

function resize() {
  const canvas = cv.value
  const el = host.value
  if (!canvas || !el) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = el.clientWidth * dpr
  canvas.height = el.clientHeight * dpr
  canvas.style.width = `${el.clientWidth}px`
  canvas.style.height = `${el.clientHeight}px`
}

function visible(lon: number, lat: number, w: number, h: number) {
  if (!map) return false
  const p = map.project([lon, lat])
  if (p.x < -20 || p.x > w + 20 || p.y < -20 || p.y > h + 20) return false
  const inv = map.unproject([p.x, p.y])
  const dlon = Math.abs((((inv.lng - lon + 540) % 360) - 180))
  return dlon < 12 && Math.abs(inv.lat - lat) < 12
}

function tick() {
  const canvas = cv.value
  const ctx = canvas?.getContext("2d")
  if (!canvas || !ctx || !map) {
    raf = requestAnimationFrame(tick)
    return
  }
  const dpr = canvas.width / (host.value?.clientWidth || canvas.width)
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  const w = host.value?.clientWidth || 1
  const h = host.value?.clientHeight || 1
  ctx.globalCompositeOperation = "destination-out"
  ctx.fillStyle = "rgba(0,0,0,0.18)"
  ctx.fillRect(0, 0, w, h)
  ctx.globalCompositeOperation = "lighter"
  if (props.playing !== false && props.wind) {
    ctx.lineWidth = 1.2
    ctx.lineCap = "round"
    for (const p of particles) {
      const [u, v] = sample(p.lon, p.lat)
      const spd = Math.hypot(u, v)
      p.lon += u * 0.045
      p.lat += v * 0.045
      if (p.lon > 180) p.lon -= 360
      if (p.lon < -180) p.lon += 360
      p.age++
      if (p.age > 110 || p.lat > 78 || p.lat < -78) {
        p.lon = Math.random() * 360 - 180
        p.lat = Math.random() * 140 - 70
        p.age = 0
        continue
      }
      if (!visible(p.lon, p.lat, w, h)) continue
      const a = map.project([p.lon, p.lat])
      const b = map.project([p.lon - u * 0.18, p.lat - v * 0.18])
      const t = Math.min(1, spd / 18)
      const r = Math.round(90 + 150 * t)
      const g = Math.round(180 + 60 * t)
      const bl = Math.round(255 - 140 * t)
      ctx.strokeStyle = `rgba(${r},${g},${bl},${0.22 + 0.55 * t})`
      ctx.beginPath()
      ctx.moveTo(b.x, b.y)
      ctx.lineTo(a.x, a.y)
      ctx.stroke()
    }
  }
  raf = requestAnimationFrame(tick)
}

onMounted(() => {
  if (!host.value) return
  seed(window.innerWidth < 800 ? 2800 : 6500)
  map = new maplibregl.Map({
    container: host.value,
    style: "https://tiles.openfreemap.org/styles/dark",
    center: [112, 18],
    zoom: 1.55,
    attributionControl: false,
    canvasContextAttributes: { antialias: true },
  })
  map.on("style.load", () => {
    try {
      map?.setProjection({ type: "globe" })
    } catch {
      /* 2d fallback */
    }
    try {
      map?.setSky({
        "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.8, 5, 0.3, 7, 0],
      } as never)
    } catch {
      /* optional */
    }
  })
  resize()
  window.addEventListener("resize", resize)
  raf = requestAnimationFrame(tick)
})

watch(
  () => props.wind,
  () => {
    if (props.wind && particles.length === 0) seed(5000)
  },
)

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  window.removeEventListener("resize", resize)
  map?.remove()
  map = null
})
</script>

<style scoped>
.globe-wrap, .globe-el, .wind-cv { position: absolute; inset: 0; }
.wind-cv { pointer-events: none; z-index: 2; }
.globe-el { z-index: 1; }
</style>
