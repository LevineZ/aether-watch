<template>
  <AppShell :title="t('feeds.title')">
    <p class="banner">{{ t("feeds.banner") }}</p>
    <p v-if="pending" class="loading">{{ t("feeds.loading") }}</p>
    <p v-else-if="error" class="error">{{ t("feeds.error") }}</p>
    <div v-else class="feed">
      <div v-for="e in events" :key="e.id" class="feed-item">
        <div>
          <div class="kind">{{ kindLabel(e.kind) }}</div>
          <div class="date-col">{{ formatTime(e.created_at) }}</div>
        </div>
        <div>
          <strong>{{ e.title }}</strong>
          <p v-if="e.detail" style="color:var(--ink-soft);margin:.3rem 0 0;font-size:.9rem">{{ e.detail }}</p>
        </div>
      </div>
      <p v-if="!events.length" class="empty">{{ t("feeds.empty") }}</p>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
const { t, locale } = useI18n()
useHead({ title: computed(() => `${t("feeds.title")} · AetherWatch`) })
type EventRow = { id: number; kind: string; title: string; detail?: string; created_at?: string }
const { data, pending, error } = await useAsyncData("feeds", () =>
  $fetch<{ events: EventRow[] }>(resolveApi("/api/feeds")),
)
const events = computed(() => data.value?.events || [])
function kindLabel(kind: string) {
  if (kind === "ingest") return t("feeds.kind.ingest")
  if (kind === "dataset") return t("feeds.kind.dataset")
  if (kind === "news") return t("feeds.kind.news")
  if (kind === "system") return t("feeds.kind.system")
  return kind
}
function formatTime(iso?: string) {
  if (!iso) return ""
  return t("earth.clock", { time: beijingStamp(iso, locale.value).clock })
}
</script>
