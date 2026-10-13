<template>
  <div class="map-card">
    <header>
      <strong>{{ title }}</strong>
      <span>{{ validLabel }}</span>
    </header>
    <div ref="host" class="map-host"></div>
    <div class="scale">
      <div class="scale-bar" :style="{ background: bar }" />
      <div class="scale-labels">
        <span>{{ minLabel }}</span>
        <span>{{ maxLabel }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { colorAt, paletteCss, sampleBilinear, type Palette } from "~/utils/colormap"

type Field = {
  lats: number[]
  lons: number[]
  values: (number | null)[][]
  min: number
  max: number
  unit?: string
  valid_time?: string | null
  bbox?: { west: number; south: number; east: number; north: number }
}

const props = defineProps<{
  title: string
  field: Field | null
  palette?: Palette
  loading?: boolean
}>()

const host = ref<HTMLDivElement | null>(null)
let map: maplibregl.Map | null = null
const bar = computed(() => paletteCss(props.palette || "thermal"))
const minLabel = computed(() => (props.field ? `${props.field.min.toFixed(1)}${props.field.unit || ""}` : "—"))
const maxLabel = computed(() => (props.field ? `${props.field.max.toFixed(1)}${props.field.unit || ""}` : "—"))
const validLabel = computed(() => {
  if (!props.field?.valid_time) return "Open-Meteo"
  return String(props.field.valid_time).replace("T", " ").slice(0, 16)
})

function rasterize(field: Field) {
  const W = 256
  const H = 192
  const canvas = document.createElement("canvas")
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext("2d")
  if (!ctx) return canvas.toDataURL()
  const img = ctx.createImageData(W, H)
  const ny = field.values.length
  const nx = field.values[0]?.length || 0
  const span = field.max - field.min || 1
  const pal = props.palette || "thermal"
  for (let j = 0; j < H; j++) {
    for (let i = 0; i < W; i++) {
      const x = (i / (W - 1)) * (nx - 1)
      const y = (1 - j / (H - 1)) * (ny - 1)
      const v = sampleBilinear(field.values, x, y)
      const o = (j * W + i) * 4
      if (v == null) {
        img.data[o + 3] = 0
        continue
      }
      const [r, g, b] = colorAt(pal, (v - field.min) / span)
      img.data[o] = r
      img.data[o + 1] = g
      img.data[o + 2] = b
      img.data[o + 3] = 210
    }
  }
  ctx.putImageData(img, 0, 0)
  return canvas.toDataURL("image/png")
}

function boundsOf(field: Field): [[number, number], [number, number], [number, number], [number, number]] {
  const west = field.bbox?.west ?? field.lons[0]
  const east = field.bbox?.east ?? field.lons[field.lons.length - 1]
  const south = field.bbox?.south ?? field.lats[0]
  const north = field.bbox?.north ?? field.lats[field.lats.length - 1]
  return [
    [west, north],
    [east, north],
    [east, south],
    [west, south],
  ]
}

function paint() {
  if (!map || !props.field) return
  const url = rasterize(props.field)
  const coordinates = boundsOf(props.field)
  const src = map.getSource("field") as maplibregl.ImageSource | undefined
  if (src) {
    src.updateImage({ url, coordinates })
  } else if (map.isStyleLoaded()) {
    map.addSource("field", { type: "image", url, coordinates })
    map.addLayer({
      id: "field",
      type: "raster",
      source: "field",
      paint: { "raster-opacity": 0.82, "raster-fade-duration": 0 },
    })
  }
}

onMounted(() => {
  if (!host.value) return
  map = new maplibregl.Map({
    container: host.value,
    style: "https://tiles.openfreemap.org/styles/positron",
    center: [104.0, 36.5],
    zoom: 2.6,
    attributionControl: false,
    interactive: true,
  })
  map.scrollZoom.disable()
  map.on("load", () => {
    map?.fitBounds(
      [
        [73, 18],
        [135, 54],
      ],
      { padding: 12, duration: 0 },
    )
    paint()
  })
})

watch(() => props.field, () => paint(), { deep: false })

onBeforeUnmount(() => {
  map?.remove()
  map = null
})
</script>
