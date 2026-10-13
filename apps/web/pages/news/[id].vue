<template>
  <AppShell title="资讯">
    <p v-if="pending" class="loading">打开稿件…</p>
    <p v-else-if="error || !article" class="error">找不到这篇。 <NuxtLink to="/news" class="back">返回资讯</NuxtLink></p>
    <article v-else class="article">
      <div>
        <NuxtLink to="/news" class="back">← 返回资讯</NuxtLink>
        <div class="prose">
          <span class="tag" :class="{ paper: article.category === '论文' }">{{ article.category }}</span>
          <h1>{{ article.title }}</h1>
          <p v-if="article.title_en" style="color:#5e554c;font-style:italic;margin-top:-0.4rem">{{ article.title_en }}</p>
          <div v-html="article.html" />
        </div>
      </div>
      <aside class="side-meta">
        <div style="font-family: Fraunces, serif; color: var(--accent)">文稿信息</div>
        <dl>
          <dt>作者</dt>
          <dd>{{ article.author }}</dd>
          <dt>日期</dt>
          <dd>{{ article.published }}</dd>
          <dt>来源</dt>
          <dd>{{ article.source || "AetherWatch" }}</dd>
          <dt>标签</dt>
          <dd>{{ (article.tags || []).join(" · ") }}</dd>
        </dl>
        <a v-if="article.source_url" class="btn" :href="article.source_url" target="_blank" rel="noreferrer" style="display:inline-block;margin-top:1rem">查看原文 ↗</a>
      </aside>
    </article>
  </AppShell>
</template>

<script setup lang="ts">
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
useHead({ title: () => `${article.value?.title || "资讯"} · AetherWatch` })
</script>
