<template>
  <div class="globe-wrap" ref="wrap">
    <canvas ref="stars" class="star-cv" aria-hidden="true" />
    <div ref="host" class="globe-el" />
    <div class="globe-vignette" aria-hidden="true" />
    <div v-if="!ready" class="globe-boot">{{ t("earth.loading") }}</div>
  </div>
</template>

<script setup lang="ts">
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { restyleGlobe, paintStars } from "~/utils/globeStyle"
import { fieldCorners, rasterizeField, type ScalarField } from "~/utils/rasterField"
import { WindParticleLayer, type FlowKind } from "~/utils/windLayer"
import type { Wind } from "~/utils/windField"
import type { Palette } from "~/utils/colormap"
import { applyPlaceLabels, loadOpenFreeMapStyle, OPENFREEMAP_DARK } from "~/utils/mapLabels"
import { addChinaBorders, raiseChinaBorders } from "~/utils/chinaBorders"

const props = defineProps<{
  flow: Wind | null
  kind?: FlowKind
  playing?: boolean
  field?: ScalarField | null
  palette?: Palette
}>()

const emit = defineEmits<{ ready: [] }>()
const { t, locale } = useI18n()
const wrap = ref<HTMLDivElement | null>(null)
const host = ref<HTMLDivElement | null>(null)
const stars = ref<HTMLCanvasElement | null>(null)
const ready = ref(false)

let map: maplibregl.Map | null = null
let layer: WindParticleLayer | null = null
let ro: ResizeObserver | null = null

function paintOverlay() {
  if (!map?.isStyleLoaded()) return
  const field = props.field
  if (!field) {
    if (map.getLayer("scalar")) map.setLayoutProperty("scalar", "visibility", "none")
    return
  }
  const url = rasterizeField(field, props.palette || "thermal", 512, 256)
  const coordinates = fieldCorners(field)
  const src = map.getSource("scalar") as maplibregl.ImageSource | undefined
  if (src) {
    src.updateImage({ url, coordinates })
  } else {
    map.addSource("scalar", { type: "image", url, coordinates })
    map.addLayer({
      id: "scalar",
      type: "raster",
      source: "scalar",
      paint: { "raster-opacity": 0.72, "raster-fade-duration": 0 },
    })
  }
  if (map.getLayer("scalar")) map.setLayoutProperty("scalar", "visibility", "visible")
  raiseChinaBorders(map)
}

function onResize() {
  const el = wrap.value
  if (!el) return
  if (stars.value) paintStars(stars.value, el.clientWidth, el.clientHeight)
  layer?.resize(el.clientWidth, Math.min(window.devicePixelRatio || 1, 1.75))
  map?.resize()
}

onMounted(async () => {
  if (!host.value || !wrap.value) return
  paintStars(stars.value!, wrap.value.clientWidth, wrap.value.clientHeight)
  layer = new WindParticleLayer()
  layer.kind = props.kind || "current"
  layer.playing = props.playing !== false
  // Currents seed/advect only in water (0.5° land mask). Wind is allowed over land.
  if (props.flow) layer.setField(props.flow, props.kind || "current")

  let style: string | object = OPENFREEMAP_DARK
  try {
    style = await loadOpenFreeMapStyle("dark", locale.value)
  } catch {
    /* URL fallback */
  }

  map = new maplibregl.Map({
    container: host.value,
    style: style as never,
    center: [132, 18],
    zoom: 1.62,
    minZoom: 0.7,
    maxZoom: 5.8,
    pitch: 0,
    maxPitch: 35,
    attributionControl: false,
    fadeDuration: 0,
    pixelRatio: Math.min(window.devicePixelRatio || 1, 1.6),
    canvasContextAttributes: { antialias: true },
    renderWorldCopies: false,
  })
  map.touchPitch.disable()
  map.on("style.load", () => {
    if (!map || !layer) return
    restyleGlobe(map, locale.value)
    if (!map.getLayer(layer.id)) map.addLayer(layer)
    paintOverlay()
    void addChinaBorders(map, { url: resolveApi("/api/geo/china-bounds.json"), theme: "dark" }).then(() => {
      if (map) raiseChinaBorders(map)
    })
    ready.value = true
    emit("ready")
  })
  ro = new ResizeObserver(onResize)
  ro.observe(wrap.value)
  window.addEventListener("resize", onResize)
})

watch(
  () => [props.flow, props.kind] as const,
  () => {
    layer?.setField(props.flow, props.kind || "current")
  },
)

watch(
  () => props.playing,
  (v) => {
    layer?.setPlaying(v !== false)
  },
)

watch(
  () => [props.field, props.palette] as const,
  () => paintOverlay(),
)

watch(locale, (lang) => {
  if (map?.isStyleLoaded()) {
    restyleGlobe(map, lang)
    raiseChinaBorders(map)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize)
  ro?.disconnect()
  if (map && layer && map.getLayer(layer.id)) {
    try {
      map.removeLayer(layer.id)
    } catch {
      /* already gone */
    }
  }
  map?.remove()
  map = null
  layer = null
})
</script>

<style scoped>
.globe-wrap,
.globe-el,
.star-cv,
.globe-vignette {
  position: absolute;
  inset: 0;
}
.star-cv {
  z-index: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse 70% 55% at 50% 46%, #12203a 0%, #070b14 42%, #020308 78%);
}
.globe-el {
  z-index: 1;
  background: transparent;
}
.globe-vignette {
  z-index: 3;
  pointer-events: none;
  background:
    radial-gradient(circle at 50% 48%, transparent 34%, rgba(2, 4, 10, 0.28) 58%, rgba(2, 3, 8, 0.78) 100%);
}
.globe-boot {
  position: absolute;
  z-index: 4;
  inset: 0;
  display: grid;
  place-items: center;
  color: #c9c0b4;
  font-family: var(--font-mono);
  letter-spacing: 0.12em;
  font-size: 0.78rem;
  pointer-events: none;
}
:deep(.maplibregl-canvas) {
  background: transparent;
}
</style>
