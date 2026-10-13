<template>
  <div class="earth-root">
    <header class="earth-nav">
      <NuxtLink to="/" class="brand" style="color:#f4efe6">
        <BrandMark />
        <span>
          <span class="brand-name">AetherWatch</span>
          <span class="brand-sub" style="color:#b7aea2">Earth Observatory</span>
        </span>
      </NuxtLink>
      <nav>
        <NuxtLink v-for="item in nav" :key="item.to" :to="item.to" :class="{ active: item.to === '/' }">
          {{ item.cn }}
        </NuxtLink>
      </nav>
    </header>
    <ClientOnly>
      <EarthGlobe
        :flow="flow"
        :kind="flowKind"
        :playing="playing"
        :field="scalar"
        :palette="activeEl?.palette || 'current'"
        @ready="globeReady = true"
      />
      <template #fallback>
        <div class="loading" style="color:#ddd;padding:6rem 2rem">正在装载地球…</div>
      </template>
    </ClientOnly>
    <aside class="earth-panel">
      <label>要素</label>
      <div class="chips">
        <button
          v-for="el in elements"
          :key="el.id"
          class="chip"
          :class="{ active: variable === el.id }"
          type="button"
          @click="selectVariable(el.id)"
        >
          {{ el.label }}
        </button>
      </div>
      <label>模式</label>
      <div class="chips">
        <button
          v-for="m in modelOptions"
          :key="m.id"
          class="chip"
          :class="{ active: model === m.id }"
          type="button"
          @click="selectModel(m.id)"
        >
          {{ m.short }}
        </button>
      </div>
      <label>图层</label>
      <div class="chips">
        <button class="chip" :class="{ active: playing }" type="button" @click="playing = !playing">
          {{ playing ? `${activeEl?.label || "粒子"}动画 开` : `${activeEl?.label || "粒子"}动画 停` }}
        </button>
      </div>
      <div class="legend" v-if="activeEl?.kind === 'vector'">
        <span>{{ activeEl?.label }}</span>
        <i :style="{ background: legendCss }" />
        <span>{{ activeEl?.unit }}</span>
      </div>
      <div class="clock">
        {{ clock }}
        <div class="src">{{ source }}</div>
        <div class="hint">拖动旋转 · 滚轮缩放 · 切换即重载场</div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { paletteCss, type Palette } from "~/utils/colormap"
import type { Wind } from "~/utils/windField"
import type { ScalarField } from "~/utils/rasterField"

useHead({ title: "地球 · AetherWatch" })
const nav = [
  { to: "/", cn: "地球" },
  { to: "/forecast", cn: "预报" },
  { to: "/news", cn: "资讯" },
  { to: "/feeds", cn: "动态" },
  { to: "/about", cn: "关于" },
  { to: "/admin", cn: "管理" },
]

type GlobeEl = {
  id: string
  label: string
  kind: "vector" | "scalar"
  endpoint: string
  palette: Palette
  unit: string
}
type ModelChip = { id: string; short: string; kind?: string }

const fallbackElements: GlobeEl[] = [
  { id: "ocean_current", label: "洋流", kind: "vector", endpoint: "currents", palette: "current", unit: "m/s" },
  { id: "wind_speed_10m", label: "风场", kind: "vector", endpoint: "wind", palette: "wind", unit: "m/s" },
  { id: "temperature_2m", label: "气温", kind: "scalar", endpoint: "field", palette: "thermal", unit: "°C" },
  { id: "surface_pressure", label: "气压", kind: "scalar", endpoint: "field", palette: "pressure", unit: "hPa" },
  { id: "precipitation", label: "降水", kind: "scalar", endpoint: "field", palette: "rain", unit: "mm" },
]
const weatherModels: ModelChip[] = [
  { id: "gfs_seamless", short: "GFS" },
  { id: "ecmwf_ifs025", short: "IFS" },
  { id: "ecmwf_aifs025_single", short: "AIFS" },
  { id: "icon_seamless", short: "ICON" },
]
const marineModels: ModelChip[] = [
  { id: "best_match", short: "Marine" },
  { id: "meteofrance_currents", short: "SMOC" },
]

const elements = ref<GlobeEl[]>(fallbackElements)
const ncModels = ref<ModelChip[]>([])
const variable = ref("ocean_current")
const model = ref("best_match")
const playing = ref(true)
const flow = ref<Wind | null>(null)
const scalar = ref<ScalarField | null>(null)
const source = ref("正在请求 Open-Meteo 洋流…")
const globeReady = ref(false)
const clock = beijingStamp().clock
const loadGen = ref(0)

const activeEl = computed(() => elements.value.find((e) => e.id === variable.value) || elements.value[0])
const flowKind = computed(() => (variable.value === "wind_speed_10m" ? "wind" : "current"))
const legendCss = computed(() => paletteCss(activeEl.value?.palette || "current"))
const modelOptions = computed(() => {
  const extra = ncModels.value
  if (activeEl.value?.endpoint === "currents") return [...marineModels, ...extra.filter((m) => m.kind === "vector")]
  if (activeEl.value?.endpoint === "wind") return [...weatherModels]
  return [...weatherModels, ...extra]
})

function selectVariable(id: string) {
  if (variable.value === id) return
  variable.value = id
  const opts = modelOptions.value
  if (!opts.some((m) => m.id === model.value)) {
    model.value = opts[0]?.id || (id === "ocean_current" ? "best_match" : "gfs_seamless")
  }
}

function selectModel(id: string) {
  if (model.value === id) return
  model.value = id
}

async function loadCatalog() {
  try {
    const cat = await $fetch<{
      globe_elements?: GlobeEl[]
      current_models?: ModelChip[]
      datasets?: { id: string; short: string; status: string; has_vector?: boolean }[]
    }>(resolveApi("/api/catalog"))
    if (cat.globe_elements?.length) elements.value = cat.globe_elements as GlobeEl[]
    if (cat.current_models?.length) {
      marineModels.splice(0, marineModels.length, ...cat.current_models)
    }
    ncModels.value = (cat.datasets || [])
      .filter((d) => d.status === "ready")
      .map((d) => ({ id: d.id, short: d.short, kind: d.has_vector ? "vector" : "scalar" }))
  } catch {
    /* hardcoded fallbacks */
  }
}

async function load() {
  const el = activeEl.value
  if (!el) return
  const seq = ++loadGen.value
  const mid = model.value
  if (el.kind === "vector" && el.endpoint === "currents") {
    source.value = "正在请求 Open-Meteo 洋流…"
    scalar.value = null
    try {
      const data = await $fetch<Wind & { source?: string; fallback?: boolean }>(resolveApi("/api/currents"), {
        query: { model: mid },
      })
      if (seq !== loadGen.value) return
      flow.value = data
      source.value = describeSource("洋流", data)
    } catch {
      if (seq !== loadGen.value) return
      source.value = "洋流暂不可用，将显示合成场"
    }
    return
  }
  if (el.kind === "vector") {
    source.value = "正在请求 Open-Meteo 10 m 风场…"
    scalar.value = null
    try {
      const data = await $fetch<Wind>(resolveApi("/api/wind"), { query: { model: mid } })
      if (seq !== loadGen.value) return
      flow.value = data
      source.value = describeSource("风场", data as { source?: string; fallback?: boolean })
    } catch {
      if (seq !== loadGen.value) return
      source.value = "风场暂不可用，将显示合成场"
    }
    return
  }
  flow.value = null
  source.value = `正在请求 ${el.label} 场…`
  try {
    const data = await $fetch<ScalarField>(resolveApi("/api/field"), {
      query: {
        model: mid,
        variable: el.id,
        west: -180,
        south: -70,
        east: 180,
        north: 70,
        nx: 16,
        ny: 10,
        step: 0,
      },
    })
    if (seq !== loadGen.value) return
    scalar.value = data
    source.value = `${el.label} · ${(data as { source?: string }).source || "open-meteo"}`
  } catch {
    if (seq !== loadGen.value) return
    source.value = `${el.label} 暂不可用`
  }
}

onMounted(async () => {
  await loadCatalog()
  await load()
})
watch([variable, model], load)

function describeSource(kind: string, data: { source?: string; fallback?: boolean }) {
  const src = data.source || ""
  if (data.fallback || src.startsWith("synthetic")) {
    return `${kind} · 合成场（Open-Meteo 暂不可用）`
  }
  return `${kind} · ${src || "open-meteo"}`
}
</script>
