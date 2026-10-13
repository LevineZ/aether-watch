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
      <EarthGlobe :wind="wind" :playing="playing" />
      <template #fallback>
        <div class="loading" style="color:#ddd;padding:6rem 2rem">正在装载地球…</div>
      </template>
    </ClientOnly>
    <aside class="earth-panel">
      <label>模式</label>
      <div class="chips">
        <button v-for="m in models" :key="m.id" class="chip" :class="{ active: model === m.id }" @click="model = m.id">
          {{ m.short }}
        </button>
      </div>
      <label>要素</label>
      <div class="chips">
        <button class="chip active">风场</button>
        <button class="chip" disabled>温度</button>
        <button class="chip" disabled>气压</button>
        <button class="chip" disabled>降水</button>
      </div>
      <label>图层</label>
      <div class="chips">
        <button class="chip" :class="{ active: playing }" @click="playing = !playing">
          {{ playing ? "风场动画 开" : "风场动画 停" }}
        </button>
      </div>
      <div class="clock">
        {{ clock }}
        <div style="opacity:.7;margin-top:.2rem">{{ source }}</div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
useHead({ title: "地球 · AetherWatch" })
const nav = [
  { to: "/", cn: "地球" },
  { to: "/forecast", cn: "预报" },
  { to: "/news", cn: "资讯" },
  { to: "/feeds", cn: "动态" },
  { to: "/about", cn: "关于" },
  { to: "/admin", cn: "管理" },
]
const models = [
  { id: "gfs_seamless", short: "GFS" },
  { id: "ecmwf_ifs025", short: "IFS" },
  { id: "ecmwf_aifs025_single", short: "AIFS" },
  { id: "icon_seamless", short: "ICON" },
]
const model = ref("gfs_seamless")
const playing = ref(true)
const wind = ref(null)
const source = ref("正在请求 Open-Meteo 10 m 风场…")
const clock = beijingStamp().clock

async function load() {
  source.value = "正在请求 Open-Meteo 10 m 风场…"
  try {
    const data = await $fetch(resolveApi("/api/wind"), { query: { model: model.value } })
    wind.value = data as never
    source.value = `来源 ${(data as { source?: string }).source || "open-meteo"}`
  } catch {
    source.value = "风场暂不可用，将显示合成场"
  }
}

onMounted(load)
watch(model, load)
</script>
