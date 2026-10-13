<template>
  <div>
    <NuxtRouteAnnouncer />
    <NuxtPage />
    <div class="grain" :class="{ dim: route.path === '/' }" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
</script>
