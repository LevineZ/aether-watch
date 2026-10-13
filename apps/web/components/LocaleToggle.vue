<template>
  <button
    class="lang-toggle"
    :class="{ onearth: earth }"
    type="button"
    :aria-label="t('lang.toggle')"
    :title="t('lang.toggle')"
    @click="toggleLocale"
  >
    <span :class="{ on: locale === 'zh' }">{{ t("lang.zh") }}</span>
    <span class="sep">/</span>
    <span :class="{ on: locale === 'en' }">{{ t("lang.en") }}</span>
  </button>
</template>

<script setup lang="ts">
defineProps<{ earth?: boolean }>()
const { locale, t, toggleLocale } = useI18n()
</script>

<style scoped>
.lang-toggle {
  display: inline-flex;
  align-items: baseline;
  gap: 0.22rem;
  border: 1px solid var(--rule);
  background: var(--card);
  color: var(--ink-faint);
  border-radius: 999px;
  padding: 0.22rem 0.62rem;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  cursor: pointer;
}
.lang-toggle .on {
  color: var(--accent);
  font-weight: 700;
}
.lang-toggle:hover { border-color: var(--accent); }
.lang-toggle.onearth {
  background: rgba(8, 12, 18, 0.55);
  border-color: rgba(255, 255, 255, 0.18);
  color: #8a8378;
}
.lang-toggle.onearth .on { color: #f4efe6; }
</style>
