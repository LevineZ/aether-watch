<template>
  <AppShell title="预报" kicker="AetherWatch · Model Forecast">
    <div class="f-toolbar">
      <div class="f-row" role="group" aria-label="要素选择">
        <span class="f-label">要素</span>
        <button
          v-for="el in elements"
          :key="el.id"
          class="tab"
          :class="{ active: variable === el.id }"
          type="button"
          @click="variable = el.id"
        >
          {{ el.label }}
        </button>
      </div>
      <div class="f-row" role="group" aria-label="模式选择">
        <span class="f-label">模式</span>
        <button
          v-for="m in modelOptions"
          :key="m.id"
          class="chip"
          :class="{ active: selected.includes(m.id) }"
          type="button"
          @click="toggle(m.id)"
        >
          <i class="dot" :style="{ background: m.color }" />
          {{ m.short }}
        </button>
        <button class="ghost" type="button" title="全选" @click="selectPreview">✓ 全选</button>
        <button class="ghost" type="button" @click="selected = selected.slice(0, 1)">清空</button>
      </div>
    </div>
    <p v-if="note" class="banner">{{ note }}</p>

    <section class="panel fsec">
      <header class="fsec-head">
        <h2 class="section-title">
          空间分布对比
          <small>{{ currentElement?.label }} {{ unit }} · 真实模式预报场</small>
        </h2>
        <span v-if="fieldLoading" class="fbusy" role="status">{{ busyLine }}</span>
      </header>
      <div class="tax">
        <div class="tax-top">
          <span>预报时效</span>
          <strong class="tax-now">{{ validStamp }}</strong>
          <span class="tax-hint">+0h ~ +120h · 北京时</span>
          <button class="play" type="button" :aria-pressed="playing" @click="togglePlay">
            {{ playing ? "暂停" : "播放" }}
          </button>
        </div>
        <input
          class="tax-range"
          type="range"
          :min="0"
          :max="leads.length - 1"
          step="1"
          v-model.number="leadIndex"
          :aria-label="`预报时效 +${lead}h`"
        />
        <div class="tax-ticks">
          <span v-for="h in leads" :key="h" :class="{ on: h === lead }">+{{ h }}h</span>
        </div>
      </div>
      <div class="map-grid" :class="{ solo: mapsToShow.length === 1 }">
        <ClientOnly v-for="id in mapsToShow" :key="id">
          <FieldMap
            :map-id="id"
            :title="labelOf(id)"
            :field="(fields[id] as never) || null"
            :palette="palette"
            :color="colorOf(id)"
            :loading="fieldLoading && !fields[id]"
            :camera="camera"
            :driver-id="cameraDriver"
            :pick="{ lat, lon }"
            @camera="onCamera(id, $event)"
            @camera-end="onCameraEnd(id)"
            @pick="onPick"
            @zoom-by="zoomBy"
            @reset="resetCamera"
            @reload-view="reloadAtView"
          />
        </ClientOnly>
      </div>
      <p v-if="fieldError" class="error">{{ fieldError }}</p>
    </section>

    <section class="panel fsec">
      <header class="fsec-head">
        <h2 class="section-title">
          指定格点 · 多模式演变
          <small>{{ currentElement?.label }} {{ unit }} · 横轴为有效时刻（北京时）</small>
        </h2>
        <span v-if="seriesLoading" class="fbusy" role="status">序列加载中…</span>
      </header>
      <div class="coord-row">
        <span class="f-label">格点坐标</span>
        <label>纬度 <input v-model="latText" type="number" step="0.1" aria-label="纬度" /></label>
        <label>经度 <input v-model="lonText" type="number" step="0.1" aria-label="经度" /></label>
        <button class="ghost" type="button" @click="commitCoords">定位</button>
        <button class="ghost" type="button" @click="beijing">北京</button>
        <button class="ghost" type="button" @click="shanghai">上海</button>
        <span class="coord-hint">或直接在空间图上点选格点</span>
      </div>
      <SeriesChart v-if="chartTimes.length" :times="chartTimes" :series="chartSeries" :unit="unit" />
      <p v-else class="empty">{{ seriesError || "等待 Open-Meteo 返回…" }}</p>
    </section>
  </AppShell>
</template>

<script setup lang="ts">
import {
  CHINA_BBOX,
  CHINA_CAMERA,
  LEAD_HOURS,
  beijingShort,
  clampZoom,
  type GeoBbox,
  type MapCamera,
} from "~/composables/useLinkedCamera"

useHead({ title: "预报 · AetherWatch" })
type Model = { id: string; short: string; color: string; kind?: string; status?: string }
type Element = { id: string; label: string; label_en: string; unit: string; palette: string }

const elements = ref<Element[]>([])
const preview = ref<Model[]>([])
const datasets = ref<Model[]>([])
const selected = ref<string[]>(["gfs_seamless", "ecmwf_ifs025", "ecmwf_aifs025_single"])
const variable = ref("temperature_2m")
const leads = LEAD_HOURS
const leadIndex = ref(0)
const lat = ref(39.9)
const lon = ref(116.4)
const latText = ref("39.90")
const lonText = ref("116.40")
const fields = ref<Record<string, unknown>>({})
const fieldError = ref("")
const fieldLoading = ref(false)
const seriesLoading = ref(false)
const seriesError = ref("")
const chartTimes = ref<string[]>([])
const chartSeries = ref<{ id: string; name: string; color: string; values: (number | null)[] }[]>([])
const note = ref("")
const playing = ref(false)
const camera = ref<MapCamera>({ ...CHINA_CAMERA })
const cameraDriver = ref<string | null>(null)
const viewBbox = ref<GeoBbox | null>(null)
let playTimer: ReturnType<typeof setInterval> | null = null

const lead = computed(() => leads[leadIndex.value] ?? 0)
const unit = computed(() => currentElement.value?.unit || "°C")
const palette = computed(() => (currentElement.value?.palette as never) || "thermal")
const currentElement = computed(() => elements.value.find((e) => e.id === variable.value))
const modelOptions = computed(() => [
  ...preview.value,
  ...datasets.value.filter((d) => d.status === "ready"),
])
const mapsToShow = computed(() => selected.value.slice(0, 4))
const busyLine = computed(
  () => `正在加载 ${currentElement.value?.label || variable.value} · ${mapsToShow.value.length} 个模式 · +${lead.value}h`,
)
const validStamp = computed(() => {
  const first = mapsToShow.value.map((id) => fields.value[id] as { valid_time?: string } | undefined).find((f) => f?.valid_time)
  return first?.valid_time ? beijingShort(first.valid_time) : `+${lead.value}h`
})

function labelOf(id: string) {
  return modelOptions.value.find((m) => m.id === id)?.short || id
}
function colorOf(id: string) {
  return modelOptions.value.find((m) => m.id === id)?.color || "#c1440e"
}
function toggle(id: string) {
  if (selected.value.includes(id)) {
    if (selected.value.length > 1) selected.value = selected.value.filter((x) => x !== id)
  } else {
    selected.value = [...selected.value, id].slice(0, 4)
  }
}
function selectPreview() {
  selected.value = preview.value.map((m) => m.id).slice(0, 4)
}
function setPoint(nextLat: number, nextLon: number) {
  lat.value = Number(nextLat.toFixed(2))
  lon.value = Number(nextLon.toFixed(2))
  latText.value = lat.value.toFixed(2)
  lonText.value = lon.value.toFixed(2)
}
function beijing() {
  setPoint(39.9, 116.4)
}
function shanghai() {
  setPoint(31.23, 121.47)
}
function commitCoords() {
  const la = parseFloat(latText.value)
  const lo = parseFloat(lonText.value)
  if (Number.isNaN(la) || Number.isNaN(lo)) return
  setPoint(Math.max(-85, Math.min(85, la)), ((lo + 540) % 360) - 180)
}
function onPick(pt: { lat: number; lon: number }) {
  setPoint(pt.lat, pt.lon)
}
function onCamera(id: string, cam: MapCamera) {
  cameraDriver.value = id
  camera.value = cam
}
function onCameraEnd(id: string) {
  if (cameraDriver.value === id) cameraDriver.value = null
}
function zoomBy(delta: number) {
  cameraDriver.value = null
  camera.value = { ...camera.value, zoom: clampZoom(camera.value.zoom + delta) }
}
function resetCamera() {
  cameraDriver.value = null
  camera.value = { ...CHINA_CAMERA }
  viewBbox.value = null
  loadFields()
}
function reloadAtView(bbox: GeoBbox) {
  const west = Math.min(bbox.west, bbox.east)
  const east = Math.max(bbox.west, bbox.east)
  const south = Math.min(bbox.south, bbox.north)
  const north = Math.max(bbox.south, bbox.north)
  viewBbox.value = {
    west: Math.max(-180, west),
    south: Math.max(-85, south),
    east: Math.min(180, east),
    north: Math.min(85, north),
  }
  loadFields()
}
function togglePlay() {
  if (playing.value) stopPlay()
  else startPlay()
}
function startPlay() {
  playing.value = true
  playTimer = setInterval(() => {
    leadIndex.value = leadIndex.value >= leads.length - 1 ? 0 : leadIndex.value + 1
  }, 1400)
}
function stopPlay() {
  playing.value = false
  if (playTimer) clearInterval(playTimer)
  playTimer = null
}

async function loadCatalog() {
  try {
    const cat = await $fetch<{ models: Model[]; elements: Element[]; datasets: Model[] }>(resolveApi("/api/catalog"))
    preview.value = cat.models
    elements.value = cat.elements
    datasets.value = cat.datasets
  } catch {
    elements.value = [{ id: "temperature_2m", label: "2 米气温", label_en: "2 m temperature", unit: "°C", palette: "thermal" }]
    preview.value = [
      { id: "gfs_seamless", short: "GFS", color: "#c1440e" },
      { id: "ecmwf_ifs025", short: "IFS", color: "#1d4e89" },
      { id: "ecmwf_aifs025_single", short: "AIFS", color: "#b45309" },
      { id: "icon_seamless", short: "ICON", color: "#3f6f4e" },
    ]
  }
}

async function loadSeries() {
  seriesLoading.value = true
  seriesError.value = ""
  try {
    const models = selected.value.filter((id) => !id.startsWith("nc:")).join(",")
    const data = await $fetch<{
      times: string[]
      unit: string
      models: Record<string, { name: string; color: string; values: (number | null)[] }>
      errors: Record<string, string>
    }>(resolveApi("/api/series"), {
      query: { lat: lat.value, lon: lon.value, variable: variable.value, models, forecast_days: 5 },
    })
    chartTimes.value = data.times
    chartSeries.value = Object.entries(data.models).map(([id, m]) => ({
      id,
      name: m.name,
      color: m.color,
      values: m.values,
    }))
    const missing = Object.keys(data.errors || {})
    note.value = missing.length ? `部分模式缺 ${currentElement.value?.label}：${missing.join(", ")}` : ""
  } catch (e: unknown) {
    seriesError.value = e instanceof Error ? e.message : "序列请求失败"
  } finally {
    seriesLoading.value = false
  }
}

async function loadFields() {
  fieldError.value = ""
  fieldLoading.value = true
  const next: Record<string, unknown> = { ...fields.value }
  const bbox = viewBbox.value || CHINA_BBOX
  await Promise.all(
    mapsToShow.value.map(async (id) => {
      try {
        next[id] = await $fetch(resolveApi("/api/field"), {
          query: {
            model: id,
            variable: variable.value,
            step: lead.value,
            west: bbox.west,
            south: bbox.south,
            east: bbox.east,
            north: bbox.north,
          },
        })
      } catch (e: unknown) {
        fieldError.value = e instanceof Error ? e.message : "场数据失败"
      }
    }),
  )
  fields.value = next
  fieldLoading.value = false
}

let seriesTimer: ReturnType<typeof setTimeout> | null = null
function debounceSeries() {
  if (seriesTimer) clearTimeout(seriesTimer)
  seriesTimer = setTimeout(loadSeries, 250)
}

onMounted(async () => {
  await loadCatalog()
  await Promise.all([loadSeries(), loadFields()])
})
onBeforeUnmount(stopPlay)
watch([variable, selected], () => {
  debounceSeries()
  loadFields()
})
watch(leadIndex, loadFields)
watch([lat, lon], debounceSeries)
</script>
