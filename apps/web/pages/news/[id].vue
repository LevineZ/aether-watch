<template>
  <AppShell :title="t('news.title')">
    <p v-if="pending" class="loading">{{ t("news.open") }}</p>
    <p v-else-if="error || !article" class="error">
      {{ t("news.missing") }}
      <NuxtLink to="/news" class="back">{{ t("news.back") }}</NuxtLink>
    </p>
    <article v-else class="article">
      <div>
        <NuxtLink to="/news" class="back">← {{ t("news.back") }}</NuxtLink>
        <div class="prose">
          <span class="tag" :class="{ paper: article.category === '论文' }">{{ article.category }}</span>
          <h1>{{ locale === "en" && article.title_en ? article.title_en : article.title }}</h1>
          <p v-if="locale === 'zh' && article.title_en" style="color:#5e554c;font-style:italic;margin-top:-0.4rem">{{ article.title_en }}</p>
          <div v-html="article.html" />
        </div>
      </div>
      <aside class="side-meta">
        <div style="font-family: Fraunces, serif; color: var(--accent)">{{ t("news.meta") }}</div>
        <dl>
          <dt>{{ t("news.author") }}</dt>
          <dd>{{ article.author }}</dd>
          <dt>{{ t("news.date") }}</dt>
          <dd>{{ article.published }}</dd>
          <dt>{{ t("news.source") }}</dt>
          <dd>{{ article.source || "AetherWatch" }}</dd>
          <dt>{{ t("news.tags") }}</dt>
          <dd>{{ (article.tags || []).join(" · ") }}</dd>
        </dl>
        <a v-if="article.source_url" class="btn" :href="article.source_url" target="_blank" rel="noreferrer" style="display:inline-block;margin-top:1rem">{{ t("news.original") }}</a>
      </aside>
    </article>
  </AppShell>
</template>

<script setup lang="ts">
const { t, locale } = useI18n()
const route = useRoute()
const { data: article, pending, error } = await useAsyncData(
  `news-${route.params.id}`,
  () =>
    $fetch<{
      title: string
      title_en?: string
      html: string
      category: string
      author: string
      published: string
      source?: string
      source_url?: string
      tags?: string[]
    }>(resolveApi(`/api/news/${route.params.id}`)),
)
useHead({ title: computed(() => `${article.value?.title || t("news.title")} · AetherWatch`) })
</script>
