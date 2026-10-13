<template>
  <AppShell :title="t('admin.title')">
    <div class="about-grid">
      <section class="panel">
        <h2>{{ t("admin.upload") }}</h2>
        <p style="color:var(--ink-soft);font-size:.9rem">
          {{ t("admin.blurb") }}
        </p>
        <label class="coord-row" style="margin-top:0.8rem">
          Admin token
          <input v-model="token" type="password" style="width:16rem" autocomplete="off" />
        </label>
        <div
          class="drop"
          @dragover.prevent
          @drop.prevent="onDrop"
        >
          <strong>{{ t("admin.drop") }}</strong>
          <p style="color:var(--ink-faint);margin:.4rem 0 0.8rem">{{ t("admin.limit") }}</p>
          <input ref="fileEl" type="file" accept=".nc,.nc4,.netcdf" @change="onFile" />
        </div>
        <p v-if="message" class="banner">{{ message }}</p>
        <div style="margin-top:0.8rem;display:flex;gap:.5rem;flex-wrap:wrap">
          <button class="btn" :disabled="busy" type="button" @click="demo">{{ t("admin.demo") }}</button>
          <button class="ghost" :disabled="busy" type="button" @click="demoCurrents">{{ t("admin.demoCurrents") }}</button>
          <button class="ghost" type="button" @click="refresh">{{ t("admin.refresh") }}</button>
        </div>
      </section>
      <section class="panel">
        <h2>{{ t("admin.datasets") }}</h2>
        <p v-if="busy" class="loading">{{ t("admin.working") }}</p>
        <p v-else-if="error" class="error">{{ error }}</p>
        <div v-else>
          <div v-for="d in datasets" :key="d.id" class="feed-item">
            <div>
              <span class="status-pill" :class="d.status">{{ d.status }}</span>
            </div>
            <div>
              <strong>{{ d.filename }}</strong>
              <p style="color:var(--ink-soft);font-size:.85rem;margin:.25rem 0 0">
                {{ d.preview_variable || t("admin.varPending") }}
                <span v-if="d.dims"> · {{ dimLine(d.dims) }}</span>
              </p>
              <p v-if="d.error_message" class="error" style="padding:0.3rem 0">{{ d.error_message }}</p>
            </div>
          </div>
          <p v-if="!datasets.length" class="empty">{{ t("admin.empty") }}</p>
        </div>
      </section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
const { t } = useI18n()
useHead({ title: computed(() => `${t("admin.title")} · AetherWatch`) })
type Dataset = {
  id: string
  filename: string
  status: string
  dims?: Record<string, number>
  preview_variable?: string
  error_message?: string
}
const token = ref("aether-dev")
const datasets = ref<Dataset[]>([])
const busy = ref(false)
const error = ref("")
const message = ref("")
const fileEl = ref<HTMLInputElement | null>(null)
const api = useApi()

function dimLine(dims: Record<string, number>) {
  return Object.entries(dims).map(([k, v]) => `${k}:${v}`).join(" · ")
}

async function refresh() {
  error.value = ""
  try {
    const data = await $fetch<{ datasets: Dataset[] }>(resolveApi("/api/admin/datasets"), {
      headers: { "X-Admin-Token": token.value },
    })
    datasets.value = data.datasets
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : t("admin.listFail")
  }
}

async function upload(file: File) {
  busy.value = true
  message.value = t("admin.uploading", { name: file.name })
  try {
    const body = new FormData()
    body.append("file", file)
    const res = await api.postForm<{ id: string; status: string }>(
      "/api/admin/datasets/upload",
      body,
      token.value,
    )
    message.value = t("admin.received", { name: file.name, status: res.status })
    await refresh()
    setTimeout(refresh, 2500)
  } catch (e: unknown) {
    message.value = e instanceof Error ? e.message : t("admin.uploadFail")
  } finally {
    busy.value = false
  }
}

function onFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) upload(file)
}
function onDrop(ev: DragEvent) {
  const file = ev.dataTransfer?.files?.[0]
  if (file) upload(file)
}

async function demo() {
  busy.value = true
  message.value = t("admin.demoMaking")
  try {
    const res = await api.post<{ filename: string }>("/api/admin/datasets/demo", token.value)
    message.value = t("admin.demoDone", { name: res.filename })
    await refresh()
    setTimeout(refresh, 2500)
  } catch (e: unknown) {
    message.value = e instanceof Error ? e.message : t("admin.demoFail")
  } finally {
    busy.value = false
  }
}

async function demoCurrents() {
  busy.value = true
  message.value = t("admin.currentsMaking")
  try {
    const res = await api.post<{ filename: string }>("/api/admin/datasets/demo-currents", token.value)
    message.value = t("admin.currentsDone", { name: res.filename })
    await refresh()
    setTimeout(refresh, 2500)
  } catch (e: unknown) {
    message.value = e instanceof Error ? e.message : t("admin.currentsFail")
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  const saved = localStorage.getItem("aw-admin-token")
  if (saved) token.value = saved
  refresh()
})
watch(token, (v) => localStorage.setItem("aw-admin-token", v))
</script>
