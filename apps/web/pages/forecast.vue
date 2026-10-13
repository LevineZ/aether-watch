<template>
  <AppShell title="预报">
    <div class="tabs" style="margin-bottom: 0.7rem">
      <button
        v-for="el in elements"
        :key="el.id"
        class="tab"
        :class="{ active: variable === el.id }"
        @click="variable = el.id"
      >
        {{ el.label }}
      </button>
    </div>
    <p v-if="note" class="banner">{{ note }}</p>
    <div class="chips" style="margin: 0.4rem 0 1rem">
      <button
        v-for="m in modelOptions"
        :key="m.id"
        class="chip"
        :class="{ active: selected.includes(m.id) }"
        @click="toggle(m.id)"
      >
        <i class="dot" :style="{ background: m.color }" />
        {{ m.short }}
      </button>
      <button class="ghost" type="button" @click="selectPreview">全选预览</button>
      <button class="ghost" type="button" @click="selected = selected.slice(0, 1)">清空</button>
    </div>

    <section class="panel" style="margin-bottom: 1rem">
      <h2 class="section-title">
        空间分布对比
        <small>{{ currentElement?.label_en }} · 真实模式预报场</small>
      </h2>
      <div class="slider-row">
        <span>预报时效</span>
        <input type="range" min="0" max="8" step="1" v-model.number="step" />
        <strong>+{{ step * 6 }}h</strong>
      </div>
      <div class="map-grid">
        <ClientOnly v-for="id in mapsToShow" :key="`${id}:${variable}:${step}`">
          <FieldMap
            :key="`${id}:${variable}:${step}`"
            :title="labelOf(id)"
            :field="(fields[id] as never) || null"
            :palette="palette"
          />
        </ClientOnly>
      </div>
      <p v-if="fieldError" class="error">{{ fieldError }}</p>
    </section>

    <section class="panel">
      <h2 class="section-title">
        多模式时间序列
        <small>Open-Meteo 实况网络请求 · {{ lat.toFixed(2) }}°N {{ lon.toFixed(2) }}°E</small>
      </h2>
      <div class="coord-row">
        <label>纬度 <input v-model.number="lat" type="number" step="0.1" /></label>
        <label>经度 <input v-model.number="lon" type="number" step="0.1" /></label>
        <button class="ghost" type="button" @click="beijing">北京</button>
        <button class="ghost" type="button" @click="shanghai">上海</button>
        <span v-if="seriesLoading" class="loading">拉取序列…</span>
      </div>
      <SeriesChart v-if="chartTimes.length" :times="chartTimes" :series="chartSeries" :unit="unit" />
      <p v-else class="empty">{{ seriesError || "等待 Open-Meteo 返回…" }}</p>
    </section>
  </AppShell>
</template>

<script setup lang="ts">
useHead({ title: "预报 · AetherWatch" })
type Model = { id: string; short: string; color: string; kind?: string; status?: string }
type Element = { id: string; label: string; label_en: string; unit: string; palette: string }

const elements = ref<Element[]>([])
const preview = ref<Model[]>([])
const datasets = ref<Model[]>([])
const selected = ref<string[]>(["gfs_seamless", "ecmwf_ifs025", "ecmwf_aifs025_single"])
const variable = ref("temperature_2m")
const step = ref(0)
const lat = ref(39.9)
const lon = ref(116.4)
const fields = ref<Record<string, unknown>>({})
const fieldError = ref("")
const seriesLoading = ref(false)
const seriesError = ref("")
const chartTimes = ref<string[]>([])
const chartSeries = ref<{ id: string; name: string; color: string; values: (number | null)[] }[]>([])
const note = ref("")
const unit = computed(() => currentElement.value?.unit || "°C")
const palette = computed(() => (currentElement.value?.palette as never) || "thermal")
const currentElement = computed(() => elements.value.find((e) => e.id === variable.value))
const modelOptions = computed(() => [
  ...preview.value,
  ...datasets.value.filter((d) => d.status === "ready"),
])
const mapsToShow = computed(() => selected.value.slice(0, 4))

function labelOf(id: string) {
  return modelOptions.value.find((m) => m.id === id)?.short || id
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
function beijing() {
  lat.value = 39.9
  lon.value = 116.4
}
function shanghai() {
  lat.value = 31.23
  lon.value = 121.47
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
  const next: Record<string, unknown> = {}
  await Promise.all(
    mapsToShow.value.map(async (id) => {
      try {
        next[id] = await $fetch(resolveApi("/api/field"), {
          query: { model: id, variable: variable.value, step: step.value * 6 },
        })
      } catch (e: unknown) {
        fieldError.value = e instanceof Error ? e.message : "场数据失败"
      }
    }),
  )
  fields.value = next
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
watch([variable, selected], () => {
  debounceSeries()
  loadFields()
})
watch(step, loadFields)
watch([lat, lon], debounceSeries)
</script>
