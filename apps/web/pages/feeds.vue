<template>
  <AppShell title="动态">
    <p class="banner">摄取演员、切片演员与资讯装载会写进这一条时间线。</p>
    <p v-if="pending" class="loading">读取动态…</p>
    <p v-else-if="error" class="error">动态还没有连上 API。</p>
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
      <p v-if="!events.length" class="empty">还没有事件。上传一份 NetCDF 或等预报缓存刷新。</p>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
useHead({ title: "动态 · AetherWatch" })
type EventRow = { id: number; kind: string; title: string; detail?: string; created_at?: string }
const { data, pending, error } = await useAsyncData("feeds", () =>
  $fetch<{ events: EventRow[] }>(resolveApi("/api/feeds")),
)
const events = computed(() => data.value?.events || [])
function kindLabel(kind: string) {
  return ({ ingest: "预报摄取", dataset: "数据集", news: "资讯", system: "系统" } as Record<string, string>)[kind] || kind
}
function formatTime(iso?: string) {
  if (!iso) return ""
  return beijingStamp(iso).clock
}
</script>
