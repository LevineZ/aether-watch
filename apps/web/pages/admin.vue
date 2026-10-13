<template>
  <AppShell title="管理">
    <div class="about-grid">
      <section class="panel">
        <h2>上传 NetCDF</h2>
        <p style="color:var(--ink-soft);font-size:.9rem">
          管理员把 <code>.nc</code> / <code>.nc4</code> 场文件写入对象存储，演员链负责解析与切片。
          令牌默认写在 <code>.env.example</code> 的 <code>ADMIN_TOKEN</code>。
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
          <strong>把 NetCDF 拖到这里，或选择文件</strong>
          <p style="color:var(--ink-faint);margin:.4rem 0 0.8rem">上限 250 MB。解析完成后会出现在预报页的模式芯片里。</p>
          <input ref="fileEl" type="file" accept=".nc,.nc4,.netcdf" @change="onFile" />
        </div>
        <p v-if="message" class="banner">{{ message }}</p>
        <div style="margin-top:0.8rem;display:flex;gap:.5rem;flex-wrap:wrap">
          <button class="btn" :disabled="busy" type="button" @click="demo">生成演示 NetCDF</button>
          <button class="ghost" :disabled="busy" type="button" @click="demoCurrents">生成演示洋流 NetCDF</button>
          <button class="ghost" type="button" @click="refresh">刷新列表</button>
        </div>
      </section>
      <section class="panel">
        <h2>数据集</h2>
        <p v-if="busy" class="loading">工作中…</p>
        <p v-else-if="error" class="error">{{ error }}</p>
        <div v-else>
          <div v-for="d in datasets" :key="d.id" class="feed-item">
            <div>
              <span class="status-pill" :class="d.status">{{ d.status }}</span>
            </div>
            <div>
              <strong>{{ d.filename }}</strong>
              <p style="color:var(--ink-soft);font-size:.85rem;margin:.25rem 0 0">
                {{ d.preview_variable || "变量待解析" }}
                <span v-if="d.dims"> · {{ dimLine(d.dims) }}</span>
              </p>
              <p v-if="d.error_message" class="error" style="padding:0.3rem 0">{{ d.error_message }}</p>
            </div>
          </div>
          <p v-if="!datasets.length" class="empty">还没有上传。先生成一份演示场，或拖入自己的 `.nc`。</p>
        </div>
      </section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
useHead({ title: "管理 · AetherWatch" })
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
    error.value = e instanceof Error ? e.message : "无法列出数据集（检查 token）"
  }
}

async function upload(file: File) {
  busy.value = true
  message.value = `正在上传 ${file.name}…`
  try {
    const body = new FormData()
    body.append("file", file)
    const res = await api.postForm<{ id: string; status: string }>(
      "/api/admin/datasets/upload",
      body,
      token.value,
    )
    message.value = `已接收 ${file.name}（${res.status}）。演员正在解析。`
    await refresh()
    setTimeout(refresh, 2500)
  } catch (e: unknown) {
    message.value = e instanceof Error ? e.message : "上传失败"
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
  message.value = "正在生成演示场…"
  try {
    const res = await api.post<{ filename: string }>("/api/admin/datasets/demo", token.value)
    message.value = `已写入 ${res.filename}，等待 NcIngestActor / NcTileActor。`
    await refresh()
    setTimeout(refresh, 2500)
  } catch (e: unknown) {
    message.value = e instanceof Error ? e.message : "演示生成失败"
  } finally {
    busy.value = false
  }
}

async function demoCurrents() {
  busy.value = true
  message.value = "正在生成演示洋流场…"
  try {
    const res = await api.post<{ filename: string }>("/api/admin/datasets/demo-currents", token.value)
    message.value = `已写入 ${res.filename}。就绪后可在地球页洋流模式中选用。`
    await refresh()
    setTimeout(refresh, 2500)
  } catch (e: unknown) {
    message.value = e instanceof Error ? e.message : "演示洋流生成失败"
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
