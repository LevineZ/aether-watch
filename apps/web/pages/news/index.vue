<template>
  <AppShell title="资讯">
    <div class="chips" style="margin-bottom: 1rem">
      <button class="chip" :class="{ active: category === 'all' }" @click="category = 'all'">全部</button>
      <button
        v-for="c in categories"
        :key="c"
        class="chip"
        :class="{ active: category === c }"
        @click="category = c"
      >
        {{ c }}
      </button>
    </div>
    <p v-if="pending" class="loading">装载稿件…</p>
    <p v-else-if="error" class="error">资讯台暂时读不到稿件。确认 API 已启动。</p>
    <div v-else class="news-list">
      <NuxtLink v-for="a in filtered" :key="a.id" :to="`/news/${a.id}`" class="news-card">
        <div class="date-col">{{ a.published }}</div>
        <div>
          <span class="tag" :class="{ paper: a.category === '论文' }">{{ a.category }}</span>
          <h3>{{ a.title }}</h3>
          <p>{{ a.summary }}</p>
        </div>
      </NuxtLink>
      <p v-if="!filtered.length" class="empty">这一栏还没有稿件。</p>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
useHead({ title: "资讯 · AetherWatch" })
type Article = { id: string; title: string; summary: string; category: string; published: string }
const category = ref("all")
const { data, pending, error } = await useAsyncData("news", () =>
  $fetch<{ articles: Article[]; categories: string[] }>(resolveApi("/api/news")),
)
const articles = computed(() => data.value?.articles || [])
const categories = computed(() => data.value?.categories || [])
const filtered = computed(() =>
  category.value === "all" ? articles.value : articles.value.filter((a) => a.category === category.value),
)
</script>
