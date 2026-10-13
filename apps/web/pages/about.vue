<template>
  <AppShell :title="t('about.title')">
    <div class="about-grid">
      <section class="prose">
        <h1>{{ t("about.h1") }}</h1>
        <p>{{ t("about.p1") }}</p>
        <h2>{{ t("about.data") }}</h2>
        <p>
          <strong>{{ t("about.p2a") }}</strong>
          {{ t("about.p2") }}
        </p>
        <p>
          <strong>{{ t("about.p3a") }}</strong>
          {{ t("about.p3") }}
        </p>
        <h2>{{ t("about.v1") }}</h2>
        <p>{{ t("about.p4") }}</p>
        <h2>{{ t("about.brand") }}</h2>
        <p>{{ t("about.p5") }}</p>
      </section>
      <aside class="side-meta">
        <div style="font-family: Fraunces, serif; color: var(--accent)">{{ t("about.stack") }}</div>
        <dl>
          <dt>Web</dt>
          <dd>Nuxt 3 · TypeScript · MapLibre GL</dd>
          <dt>API</dt>
          <dd>FastAPI · Python 3.12 · xarray</dd>
          <dt>Actors</dt>
          <dd>Taskiq · Redis</dd>
          <dt>Store</dt>
          <dd>Postgres 16 · MinIO · Redis 7</dd>
          <dt>Edge</dt>
          <dd>Caddy · Docker Compose</dd>
        </dl>
      </aside>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
const { t } = useI18n()
useHead({ title: computed(() => `${t("about.title")} · AetherWatch`) })
</script>
