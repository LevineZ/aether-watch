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
import { paletteCss, type Palette } from "~/utils/colormap"
import { fieldCorners, rasterizeField, type ScalarField } from "~/utils/rasterField"

const props = defineProps<{
  title: string
  field: ScalarField | null
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

function paint() {
  if (!map || !props.field) return
  const ny = props.field.values.length
  const nx = props.field.values[0]?.length || 0
  const url = rasterizeField(
    props.field,
    props.palette || "thermal",
    nx >= 24 ? 512 : 256,
    ny >= 18 ? 384 : 192,
  )
  const coordinates = fieldCorners(props.field)
  const src = map.getSource("field") as maplibregl.ImageSource | undefined
  if (src) {
    src.updateImage({ url, coordinates })
  } else if (map.isStyleLoaded()) {
    map.addSource("field", { type: "image", url, coordinates })
    map.addLayer({
      id: "field",
      type: "raster",
      source: "field",
      paint: { "raster-opacity": 0.84, "raster-fade-duration": 0 },
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
    fadeDuration: 0,
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

watch(
  () => [props.field, props.palette] as const,
  () => paint(),
)

onBeforeUnmount(() => {
  map?.remove()
  map = null
})
</script>
