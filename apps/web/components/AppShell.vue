<template>
  <div class="layout" :class="{ earth: variant === 'earth' }">
    <button class="mobile-toggle" type="button" v-if="variant !== 'earth'" @click="open = !open">☰</button>
    <aside v-if="variant !== 'earth'" class="rail" :class="{ open }">
      <NuxtLink to="/" class="brand">
        <BrandMark />
        <span>
          <span class="brand-name">AetherWatch</span>
          <span class="brand-sub">Model Forecast</span>
        </span>
      </NuxtLink>
      <nav class="nav">
        <NuxtLink v-for="item in items" :key="item.to" :to="item.to" :class="{ active: isActive(item.to) }">
          <span class="cn">{{ item.cn }}</span>
          <span class="en">{{ item.en }}</span>
        </NuxtLink>
      </nav>
      <div class="rail-foot">
        <div>观测者</div>
        <div class="visitors">{{ visitors }}</div>
      </div>
    </aside>
    <main class="stage">
      <header class="topbar">
        <div>
          <p class="page-kicker">AetherWatch</p>
          <h1 class="page-title">{{ title }}</h1>
        </div>
        <div class="page-date">{{ dateLine }}</div>
      </header>
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ title: string; variant?: "paper" | "earth" }>()
const open = ref(false)
const route = useRoute()
const visitors = ref("—")
const dateLine = beijingStamp().dateLine
const items = [
  { to: "/", cn: "地球", en: "Earth" },
  { to: "/forecast", cn: "预报", en: "Forecast" },
  { to: "/news", cn: "资讯", en: "News" },
  { to: "/feeds", cn: "动态", en: "Feeds" },
  { to: "/about", cn: "关于", en: "About" },
  { to: "/admin", cn: "管理", en: "Admin" },
]

function isActive(to: string) {
  if (to === "/") return route.path === "/"
  return route.path === to || route.path.startsWith(`${to}/`)
}

onMounted(async () => {
  try {
    const meta = await $fetch<{ visitors: number }>(resolveApi("/api/meta"))
    visitors.value = String(meta.visitors ?? "—")
  } catch {
    visitors.value = "—"
  }
})

watch(() => props.title, () => { open.value = false })
</script>
