<template>
  <AppShell :title="t('news.title')">
    <div class="chips" style="margin-bottom: 1rem">
      <button class="chip" :class="{ active: category === 'all' }" @click="category = 'all'">{{ t("news.all") }}</button>
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
    <p v-if="pending" class="loading">{{ t("news.loading") }}</p>
    <p v-else-if="error" class="error">{{ t("news.error") }}</p>
    <div v-else class="news-list">
      <NuxtLink v-for="a in filtered" :key="a.id" :to="`/news/${a.id}`" class="news-card">
        <div class="date-col">{{ a.published }}</div>
        <div>
          <span class="tag" :class="{ paper: a.category === '论文' }">{{ a.category }}</span>
          <h3>{{ locale === "en" && a.title_en ? a.title_en : a.title }}</h3>
          <p>{{ a.summary }}</p>
        </div>
      </NuxtLink>
      <p v-if="!filtered.length" class="empty">{{ t("news.empty") }}</p>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
const { t, locale } = useI18n()
useHead({ title: computed(() => `${t("news.title")} · AetherWatch`) })
type Article = { id: string; title: string; title_en?: string; summary: string; category: string; published: string }
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
