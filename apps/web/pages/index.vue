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
        :palette="activeEl?.palette || 'waves'"
        @ready="globeReady = true"
      />
      <template #fallback>
        <div class="loading" style="color:#ddd;padding:6rem 2rem">{{ t("earth.loading") }}</div>
      </template>
    </ClientOnly>
    <button
      class="earth-dock"
      type="button"
      :aria-expanded="panelOpen"
      aria-controls="earth-panel"
      :title="t('earth.togglePanel')"
      @click="togglePanel"
    >
      earth
    </button>
    <aside id="earth-panel" class="earth-panel" :hidden="!panelOpen">
      <button class="earth-panel-close" type="button" :title="t('earth.hidePanel')" @click="panelOpen = false">
        ×
      </button>
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
        <button
          v-if="activeEl?.kind === 'vector'"
          class="chip"
          :class="{ active: playing }"
          type="button"
          @click="playing = !playing"
        >
          {{ playing ? t("earth.animOn", { label: elName(activeEl) || t("earth.particles") }) : t("earth.animOff", { label: elName(activeEl) || t("earth.particles") }) }}
        </button>
        <span v-else class="chip quiet">{{ t("earth.overlayOnly") }}</span>
      </div>
      <div class="legend">
        <span>{{ legendLabel }}</span>
        <i :style="{ background: legendCss }" />
        <span>{{ legendUnit }}</span>
      </div>
      <div class="clock">
        {{ t("earth.clock", { time: clock }) }}
        <div class="src">{{ source }}</div>
        <div class="hint">{{ overlayHint }}</div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { paletteCss, type Palette } from "~/utils/colormap"
import { fieldHasSignal, weatherModelId } from "~/utils/globeOverlay"
import type { Wind } from "~/utils/windField"
import { windSpeedField } from "~/utils/windField"
import type { ScalarField } from "~/utils/rasterField"
import type { MessageKey } from "~/utils/messages"

const PANEL_KEY = "aetherwatch:earth-panel"

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
  overlay?: string
  overlay_unit?: string
  overlay_label?: string
  overlay_label_en?: string
}
type ModelChip = { id: string; short: string; kind?: string }

const fallbackElements: GlobeEl[] = [
  {
    id: "ocean_current",
    label: "洋流",
    label_en: "Currents",
    kind: "vector",
    endpoint: "currents",
    palette: "waves",
    unit: "s",
    overlay: "waves",
    overlay_unit: "s",
    overlay_label: "波周期",
    overlay_label_en: "wave period",
  },
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
  { id: "best_match", short: "Auto" },
  { id: "oscar_v2", short: "OSCAR" },
  { id: "cmems_glo_phy", short: "CMEMS" },
  { id: "meteofrance_currents", short: "SMOC" },
]

const elements = ref<GlobeEl[]>(fallbackElements)
const ncModels = ref<ModelChip[]>([])
const variable = ref("ocean_current")
const model = ref("best_match")
const playing = ref(true)
const flow = ref<Wind | null>(null)
const scalar = ref<ScalarField | null>(null)
const panelOpen = ref(true)
const srcState = ref<{
  mode: "req-current" | "req-wind" | "req-field" | "live" | "synth" | "down-current" | "down-wind" | "down-field"
  kind?: string
  src?: string
}>({ mode: "req-current" })
const globeReady = ref(false)
const clock = computed(() => beijingStamp(scalar.value?.valid_time || undefined, locale.value).clock)
const loadGen = ref(0)
const globeFieldBag = ref<{ model: string; fields: Record<string, ScalarField> } | null>(null)
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
const legendCss = computed(() => paletteCss(activeEl.value?.palette || "waves"))
const legendLabel = computed(() => {
  const el = activeEl.value
  if (!el) return ""
  if (locale.value === "en") return el.overlay_label_en || el.label_en || el.label
  return el.overlay_label || el.label
})
const legendUnit = computed(() => activeEl.value?.overlay_unit || activeEl.value?.unit || "")
const overlayHint = computed(() => {
  const id = activeEl.value?.id
  if (id === "ocean_current") return t("earth.hintCurrents")
  if (id === "wind_speed_10m") return t("earth.hintWind")
  return t("earth.hint")
})
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

function togglePanel() {
  panelOpen.value = !panelOpen.value
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

async function loadWaves(): Promise<ScalarField | null> {
  try {
    const data = await $fetch<ScalarField>(resolveApi("/api/waves"))
    return fieldHasSignal(data) ? data : null
  } catch {
    return null
  }
}

async function load() {
  const el = activeEl.value
  if (!el) return
  const seq = ++loadGen.value
  const mid = model.value
  if (el.kind === "vector" && el.endpoint === "currents") {
    srcState.value = { mode: "req-current" }
    try {
      const [data, waves] = await Promise.all([
        $fetch<Wind & { source?: string; fallback?: boolean }>(resolveApi("/api/currents"), {
          query: { model: mid },
        }),
        loadWaves(),
      ])
      if (seq !== loadGen.value) return
      flow.value = data
      scalar.value = waves
      srcState.value = describeSource(elName(el), data)
    } catch {
      if (seq !== loadGen.value) return
      srcState.value = { mode: "down-current" }
    }
    return
  }
  if (el.kind === "vector") {
    srcState.value = { mode: "req-wind" }
    try {
      const data = await $fetch<Wind>(resolveApi("/api/wind"), { query: { model: mid } })
      if (seq !== loadGen.value) return
      flow.value = data
      scalar.value = windSpeedField(data, { oceanOnly: false })
      srcState.value = describeSource(elName(el), data as { source?: string; fallback?: boolean })
    } catch {
      if (seq !== loadGen.value) return
      flow.value = null
      scalar.value = null
      srcState.value = { mode: "down-wind" }
    }
    return
  }
  flow.value = null
  srcState.value = { mode: "req-field", kind: elName(el) }
  const wm = weatherModelId(mid)
  try {
    const bag = globeFieldBag.value
    let field: ScalarField | undefined = bag?.model === wm ? bag.fields[el.id] : undefined
    if (!fieldHasSignal(field)) {
      const data = await $fetch<{
        model?: string
        fields?: Record<string, ScalarField>
        fallback?: boolean
        source?: string
      }>(resolveApi("/api/globe-fields"), { query: { model: wm } })
      if (seq !== loadGen.value) return
      globeFieldBag.value = { model: wm, fields: data.fields || {} }
      field = globeFieldBag.value.fields[el.id]
    }
    if (seq !== loadGen.value) return
    scalar.value = fieldHasSignal(field) ? field || null : null
    if (!scalar.value) {
      srcState.value = { mode: "down-field", kind: elName(el) }
      return
    }
    const src = field?.source || "open-meteo"
    srcState.value = src.startsWith("synthetic")
      ? { mode: "synth", kind: elName(el) }
      : { mode: "live", kind: elName(el), src }
  } catch {
    if (seq !== loadGen.value) return
    scalar.value = null
    srcState.value = { mode: "down-field", kind: elName(el) }
  }
}

onMounted(async () => {
  try {
    if (import.meta.client && localStorage.getItem(PANEL_KEY) === "0") panelOpen.value = false
  } catch {
    /* private mode */
  }
  await loadCatalog()
  await load()
})
watch([variable, model], load)
watch(panelOpen, (open) => {
  try {
    if (import.meta.client) localStorage.setItem(PANEL_KEY, open ? "1" : "0")
  } catch {
    /* ignore */
  }
})

function describeSource(kind: string, data: { source?: string; fallback?: boolean }) {
  const src = data.source || ""
  if (data.fallback || src.startsWith("synthetic")) {
    return { mode: "synth" as const, kind }
  }
  return { mode: "live" as const, kind, src: src || "open-meteo" }
}
</script>
