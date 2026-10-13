<template>
  <article class="map-card">
    <header>
      <h3 class="map-name">
        <i class="dot" :style="{ background: color }" />
        {{ title }}
      </h3>
      <span v-if="field?.valid_time" class="map-valid" :title="validTitle">{{ validLabel }}</span>
      <div class="map-tools" role="group" aria-label="视图缩放">
        <button type="button" class="mtool" title="缩小" aria-label="缩小" @click="emit('zoom-by', -0.7)">−</button>
        <button type="button" class="mtool" title="放大" aria-label="放大" @click="emit('zoom-by', 0.7)">+</button>
        <button type="button" class="mtool" title="复位（双击地图同样复位）" aria-label="复位" @click="emit('reset')">↺</button>
        <button
          type="button"
          class="mtool mtool-wide"
          title="按当前联动视野向 Open-Meteo 重新取场"
          @click="requestView"
        >
          按视野取数
        </button>
      </div>
    </header>
    <div class="map-stage">
      <div ref="host" class="map-host" title="单击选格点 · 滚轮缩放 · 拖动平移 · 双击复位"></div>
      <p class="map-hint">单击选格点 · 滚轮缩放 · 拖动平移 · 双击复位</p>
      <div v-if="loading" class="map-busy"><span class="apanel-spin" />加载中…</div>
    </div>
    <div class="scale">
      <span>{{ minLabel }}</span>
      <div class="scale-bar" :style="{ background: bar }" />
      <span>{{ maxLabel }}</span>
    </div>
  </article>
</template>

<script setup lang="ts">
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { paletteCss, type Palette } from "~/utils/colormap"
import { fieldCorners, rasterizeField, type ScalarField } from "~/utils/rasterField"
import {
  beijingShort,
  camerasClose,
  type GeoBbox,
  type MapCamera,
} from "~/composables/useLinkedCamera"

const props = withDefaults(
  defineProps<{
    mapId: string
    title: string
    field: ScalarField | null
    palette?: Palette
    color?: string
    loading?: boolean
    camera: MapCamera
    driverId: string | null
    pick: { lat: number; lon: number }
  }>(),
  { palette: "thermal", color: "#c1440e", loading: false },
)

const emit = defineEmits<{
  camera: [cam: MapCamera]
  "camera-end": []
  pick: [pt: { lat: number; lon: number }]
  "zoom-by": [delta: number]
  reset: []
  "reload-view": [bbox: GeoBbox]
}>()

const host = ref<HTMLDivElement | null>(null)
let map: maplibregl.Map | null = null
let marker: maplibregl.Marker | null = null
let ro: ResizeObserver | null = null
let applying = false

const bar = computed(() => paletteCss(props.palette || "thermal"))
const minLabel = computed(() => (props.field ? `${props.field.min.toFixed(1)}${props.field.unit || ""}` : "—"))
const maxLabel = computed(() => (props.field ? `${props.field.max.toFixed(1)}${props.field.unit || ""}` : "—"))
const validLabel = computed(() => beijingShort(props.field?.valid_time))
const validTitle = computed(() =>
  props.field?.valid_time ? `有效时刻 ${beijingShort(props.field.valid_time)} 北京时` : "Open-Meteo",
)

function snapshot(): MapCamera {
  if (!map) return props.camera
  const c = map.getCenter()
  return {
    center: [c.lng, c.lat],
    zoom: map.getZoom(),
    bearing: map.getBearing(),
    pitch: map.getPitch(),
  }
}

function applyCamera(cam: MapCamera) {
  if (!map) return
  const cur = snapshot()
  if (camerasClose(cur, cam)) return
  applying = true
  map.jumpTo({
    center: cam.center,
    zoom: cam.zoom,
    bearing: cam.bearing,
    pitch: cam.pitch,
  })
  applying = false
}

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

function placeMarker() {
  if (!map || !marker) return
  marker.setLngLat([props.pick.lon, props.pick.lat])
}

function currentBbox(): GeoBbox {
  if (!map) {
    return { west: 73, south: 18, east: 135, north: 54 }
  }
  const b = map.getBounds()
  return {
    west: Number(b.getWest().toFixed(3)),
    south: Number(b.getSouth().toFixed(3)),
    east: Number(b.getEast().toFixed(3)),
    north: Number(b.getNorth().toFixed(3)),
  }
}

function requestView() {
  emit("reload-view", currentBbox())
}

onMounted(() => {
  if (!host.value) return
  map = new maplibregl.Map({
    container: host.value,
    style: "https://tiles.openfreemap.org/styles/positron",
    center: props.camera.center,
    zoom: props.camera.zoom,
    bearing: props.camera.bearing,
    pitch: 0,
    minZoom: 2.15,
    maxZoom: 8.2,
    attributionControl: false,
    interactive: true,
    fadeDuration: 0,
    dragRotate: false,
    pitchWithRotate: false,
    renderWorldCopies: false,
  })
  map.dragRotate.disable()
  map.touchPitch.disable()
  map.touchZoomRotate.disableRotation()
  map.keyboard.disableRotation()
  map.doubleClickZoom.disable()
  map.getCanvas().style.cursor = "crosshair"

  marker = new maplibregl.Marker({ color: "#c1440e", scale: 0.72 })
    .setLngLat([props.pick.lon, props.pick.lat])
    .addTo(map)

  map.on("load", () => {
    applyCamera(props.camera)
    paint()
    placeMarker()
    map?.resize()
  })
  map.on("move", () => {
    if (applying) return
    emit("camera", snapshot())
  })
  map.on("moveend", () => {
    if (applying) return
    emit("camera-end")
  })
  map.on("click", (ev) => {
    emit("pick", {
      lat: Number(ev.lngLat.lat.toFixed(2)),
      lon: Number(ev.lngLat.lng.toFixed(2)),
    })
  })
  map.on("dblclick", (ev) => {
    ev.preventDefault()
    emit("reset")
  })

  ro = new ResizeObserver(() => map?.resize())
  ro.observe(host.value)
})

watch(
  () => [props.field, props.palette] as const,
  () => paint(),
)

watch(
  () => props.camera,
  (cam) => {
    if (props.driverId === props.mapId) return
    applyCamera(cam)
  },
  { deep: true },
)

watch(
  () => [props.pick.lat, props.pick.lon],
  () => placeMarker(),
)

onBeforeUnmount(() => {
  ro?.disconnect()
  marker?.remove()
  marker = null
  map?.remove()
  map = null
})
</script>

<style scoped>
.map-card header {
  gap: 0.4rem;
  flex-wrap: wrap;
}
.map-name {
  margin: 0;
  font-size: 0.86rem;
  font-weight: 650;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.map-valid {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--ink-faint);
  margin-right: auto;
}
.map-tools {
  display: inline-flex;
  align-items: center;
  gap: 0.22rem;
}
.mtool {
  width: 1.55rem;
  height: 1.55rem;
  border-radius: 999px;
  border: 1px solid var(--rule);
  background: #fff;
  color: var(--accent);
  font-size: 0.82rem;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}
.mtool-wide {
  width: auto;
  padding: 0 0.55rem;
  font-size: 0.68rem;
  font-weight: 600;
}
.mtool:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.map-stage {
  position: relative;
  flex: 1;
  min-height: 260px;
}
.map-host {
  min-height: 260px;
  height: 100%;
}
.map-hint {
  position: absolute;
  left: 0.45rem;
  bottom: 0.4rem;
  margin: 0;
  z-index: 2;
  pointer-events: none;
  font-size: 0.62rem;
  color: #5e554c;
  background: rgba(255, 253, 248, 0.82);
  padding: 0.12rem 0.4rem;
  border-radius: 6px;
}
.map-busy {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: grid;
  place-items: center;
  gap: 0.4rem;
  background: rgba(255, 253, 248, 0.45);
  color: var(--ink-soft);
  font-size: 0.78rem;
}
.apanel-spin {
  width: 1rem;
  height: 1rem;
  border: 2px solid var(--rule);
  border-top-color: var(--accent);
  border-radius: 99px;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.scale {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.45rem;
  padding: 0.28rem 0.55rem 0.4rem;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  color: var(--ink-faint);
}
.scale-bar { height: 7px; border-radius: 99px; }
</style>
