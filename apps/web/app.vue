<template>
  <div>
    <NuxtRouteAnnouncer />
    <NuxtPage />
    <div class="grain" :class="{ dim: route.path === '/' }" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const { locale, hydrateLocale } = useI18n()

useHead({
  htmlAttrs: {
    lang: computed(() => (locale.value === "en" ? "en" : "zh-CN")),
  },
})

onMounted(() => {
  hydrateLocale()
})
</script>
