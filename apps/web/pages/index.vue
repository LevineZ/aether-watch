<template>
  <div class="earth-root">
    <header class="earth-nav">
      <NuxtLink to="/" class="brand" style="color:#f4efe6">
        <BrandMark />
        <span>
          <span class="brand-name">AetherWatch</span>
          <span class="brand-sub" style="color:#b7aea2">{{ t("brand.earthSub") }}</span>
        </span>
      </NuxtLink>
      <nav>
        <NuxtLink v-for="item in nav" :key="item.to" :to="item.to" :class="{ active: item.to === '/' }">
          {{ t(item.key) }}
        </NuxtLink>
        <LocaleToggle earth />
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
        <div class="loading" style="color:#ddd;padding:6rem 2rem">{{ t("earth.loading") }}</div>
      </template>
    </ClientOnly>
    <aside class="earth-panel">
      <label>{{ t("earth.element") }}</label>
      <div class="chips">
        <button
          v-for="el in elements"
          :key="el.id"
          class="chip"
          :class="{ active: variable === el.id }"
          type="button"
          @click="selectVariable(el.id)"
        >
          {{ elName(el) }}
        </button>
      </div>
      <label>{{ t("earth.model") }}</label>
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
      <label>{{ t("earth.layer") }}</label>
      <div class="chips">
        <button class="chip" :class="{ active: playing }" type="button" @click="playing = !playing">
          {{ playing ? t("earth.animOn", { label: elName(activeEl) || t("earth.particles") }) : t("earth.animOff", { label: elName(activeEl) || t("earth.particles") }) }}
        </button>
      </div>
      <div class="legend" v-if="activeEl?.kind === 'vector'">
        <span>{{ elName(activeEl) }}</span>
        <i :style="{ background: legendCss }" />
        <span>{{ activeEl?.unit }}</span>
      </div>
      <div class="clock">
        {{ t("earth.clock", { time: clock }) }}
        <div class="src">{{ source }}</div>
        <div class="hint">{{ t("earth.hint") }}</div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { paletteCss, type Palette } from "~/utils/colormap"
import type { Wind } from "~/utils/windField"
import type { ScalarField } from "~/utils/rasterField"
import type { MessageKey } from "~/utils/messages"

const { t, locale } = useI18n()
useHead({ title: computed(() => `${t("earth.title")} · AetherWatch`) })
const nav: { to: string; key: MessageKey }[] = [
  { to: "/", key: "nav.earth" },
  { to: "/forecast", key: "nav.forecast" },
  { to: "/news", key: "nav.news" },
  { to: "/feeds", key: "nav.feeds" },
  { to: "/about", key: "nav.about" },
  { to: "/admin", key: "nav.admin" },
]

type GlobeEl = {
  id: string
  label: string
  label_en?: string
  kind: "vector" | "scalar"
  endpoint: string
  palette: Palette
  unit: string
}
type ModelChip = { id: string; short: string; kind?: string }

const fallbackElements: GlobeEl[] = [
  { id: "ocean_current", label: "洋流", label_en: "Currents", kind: "vector", endpoint: "currents", palette: "current", unit: "m/s" },
  { id: "wind_speed_10m", label: "风场", label_en: "Wind", kind: "vector", endpoint: "wind", palette: "wind", unit: "m/s" },
  { id: "temperature_2m", label: "气温", label_en: "Temperature", kind: "scalar", endpoint: "field", palette: "thermal", unit: "°C" },
  { id: "surface_pressure", label: "气压", label_en: "Pressure", kind: "scalar", endpoint: "field", palette: "pressure", unit: "hPa" },
  { id: "precipitation", label: "降水", label_en: "Precip", kind: "scalar", endpoint: "field", palette: "rain", unit: "mm" },
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
const srcState = ref<{
  mode: "req-current" | "req-wind" | "req-field" | "live" | "synth" | "down-current" | "down-wind" | "down-field"
  kind?: string
  src?: string
}>({ mode: "req-current" })
const globeReady = ref(false)
const clock = computed(() => beijingStamp(scalar.value?.valid_time || undefined, locale.value).clock)
const loadGen = ref(0)
const source = computed(() => {
  const s = srcState.value
  if (s.mode === "req-current") return t("earth.requestCurrent")
  if (s.mode === "req-wind") return t("earth.requestWind")
  if (s.mode === "req-field") return t("earth.requestField", { label: s.kind || "" })
  if (s.mode === "down-current") return t("earth.currentDown")
  if (s.mode === "down-wind") return t("earth.windDown")
  if (s.mode === "down-field") return t("earth.fieldDown", { label: s.kind || "" })
  if (s.mode === "synth") return t("earth.synthetic", { kind: s.kind || "" })
  return t("earth.live", { kind: s.kind || "", src: s.src || "open-meteo" })
})

const activeEl = computed(() => elements.value.find((e) => e.id === variable.value) || elements.value[0])
const flowKind = computed(() => (variable.value === "wind_speed_10m" ? "wind" : "current"))
const legendCss = computed(() => paletteCss(activeEl.value?.palette || "current"))
const modelOptions = computed(() => {
  const extra = ncModels.value
  if (activeEl.value?.endpoint === "currents") return [...marineModels, ...extra.filter((m) => m.kind === "vector")]
  if (activeEl.value?.endpoint === "wind") return [...weatherModels]
  return [...weatherModels, ...extra]
})

function elName(el?: GlobeEl | null) {
  if (!el) return ""
  return locale.value === "en" ? el.label_en || el.label : el.label
}

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
    srcState.value = { mode: "req-current" }
    scalar.value = null
    try {
      const data = await $fetch<Wind & { source?: string; fallback?: boolean }>(resolveApi("/api/currents"), {
        query: { model: mid },
      })
      if (seq !== loadGen.value) return
      flow.value = data
      srcState.value = describeSource(elName(el), data)
    } catch {
      if (seq !== loadGen.value) return
      srcState.value = { mode: "down-current" }
    }
    return
  }
  if (el.kind === "vector") {
    srcState.value = { mode: "req-wind" }
    scalar.value = null
    try {
      const data = await $fetch<Wind>(resolveApi("/api/wind"), { query: { model: mid } })
      if (seq !== loadGen.value) return
      flow.value = data
      srcState.value = describeSource(elName(el), data as { source?: string; fallback?: boolean })
    } catch {
      if (seq !== loadGen.value) return
      srcState.value = { mode: "down-wind" }
    }
    return
  }
  flow.value = null
  scalar.value = null
  srcState.value = { mode: "req-field", kind: elName(el) }
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
    srcState.value = { mode: "live", kind: elName(el), src: (data as { source?: string }).source || "open-meteo" }
  } catch {
    if (seq !== loadGen.value) return
    srcState.value = { mode: "down-field", kind: elName(el) }
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
    return { mode: "synth" as const, kind }
  }
  return { mode: "live" as const, kind, src: src || "open-meteo" }
}
</script>
