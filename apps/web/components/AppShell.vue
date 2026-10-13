<template>
  <div class="layout" :class="{ earth: variant === 'earth' }">
    <button class="mobile-toggle" type="button" v-if="variant !== 'earth'" @click="open = !open">☰</button>
    <aside v-if="variant !== 'earth'" class="rail" :class="{ open }">
      <NuxtLink to="/" class="brand">
        <BrandMark />
        <span>
          <span class="brand-name">AetherWatch</span>
          <span class="brand-sub">{{ t("brand.sub") }}</span>
        </span>
      </NuxtLink>
      <nav class="nav">
        <NuxtLink v-for="item in items" :key="item.to" :to="item.to" :class="{ active: isActive(item.to) }">
          <span class="cn">{{ t(item.primary) }}</span>
          <span class="en">{{ t(item.secondary) }}</span>
        </NuxtLink>
      </nav>
      <div class="rail-foot">
        <div>{{ t("rail.observers") }}</div>
        <div class="visitors">{{ visitors }}</div>
      </div>
    </aside>
    <main class="stage">
      <header class="topbar">
        <div>
          <p class="page-kicker">{{ kicker || "AetherWatch" }}</p>
          <h1 class="page-title">{{ title }}</h1>
        </div>
        <div class="topbar-end">
          <LocaleToggle class="top-lang" />
          <div class="page-date">{{ dateLine }}</div>
        </div>
      </header>
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import type { MessageKey } from "~/utils/messages"

const props = withDefaults(defineProps<{ title: string; variant?: "paper" | "earth"; kicker?: string }>(), {
  kicker: "",
})
const { t, locale } = useI18n()
const open = ref(false)
const route = useRoute()
const visitors = ref("—")
const dateLine = computed(() => beijingStamp(undefined, locale.value).dateLine)
const items: { to: string; primary: MessageKey; secondary: MessageKey }[] = [
  { to: "/", primary: "nav.earth", secondary: "nav.earthEn" },
  { to: "/forecast", primary: "nav.forecast", secondary: "nav.forecastEn" },
  { to: "/news", primary: "nav.news", secondary: "nav.newsEn" },
  { to: "/feeds", primary: "nav.feeds", secondary: "nav.feedsEn" },
  { to: "/about", primary: "nav.about", secondary: "nav.aboutEn" },
  { to: "/admin", primary: "nav.admin", secondary: "nav.adminEn" },
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
