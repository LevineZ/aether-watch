<template>
  <div>
    <div class="chart-legend">
      <span v-for="m in series" :key="m.id">
        <i class="dot" :style="{ background: m.color, display: 'inline-block' }" />
        {{ m.name }}
      </span>
    </div>
    <svg class="chart" viewBox="0 0 800 280" role="img" :aria-label="label">
      <rect x="0" y="0" width="800" height="280" fill="#fffdf8" />
      <g v-for="(g, i) in yGrid" :key="'g'+i">
        <line :x1="pad.l" :x2="800 - pad.r" :y1="g.y" :y2="g.y" stroke="#eadfce" />
        <text :x="pad.l - 8" :y="g.y + 4" text-anchor="end" fill="#8a8074" font-size="11" font-family="IBM Plex Mono">{{ g.label }}</text>
      </g>
      <g v-for="m in polylines" :key="m.id">
        <polyline fill="none" :stroke="m.color" stroke-width="2.2" stroke-linejoin="round" :points="m.points" />
      </g>
      <g v-if="hover">
        <line :x1="hover.x" :x2="hover.x" :y1="pad.t" :y2="280 - pad.b" stroke="#c1440e" stroke-dasharray="3 4" />
        <text :x="Math.min(hover.x + 8, 640)" :y="22" fill="#1b1713" font-size="12" font-family="Figtree">{{ hover.label }}</text>
      </g>
      <rect x="0" y="0" width="800" height="280" fill="transparent" @mousemove="onMove" @mouseleave="hover = null" />
    </svg>
  </div>
</template>

<script setup lang="ts">
type ModelSeries = { id: string; name: string; color: string; values: (number | null)[] }

const props = defineProps<{
  times: string[]
  series: ModelSeries[]
  unit?: string
  label?: string
}>()

const pad = { l: 48, r: 16, t: 16, b: 28 }
const hover = ref<{ x: number; label: string } | null>(null)

const stats = computed(() => {
  const vals: number[] = []
  for (const m of props.series) {
    for (const v of m.values) if (v != null && Number.isFinite(v)) vals.push(v)
  }
  const min = vals.length ? Math.min(...vals) : 0
  const max = vals.length ? Math.max(...vals) : 1
  const span = max - min || 1
  return { min, max, span }
})

const yGrid = computed(() => {
  const { min, max, span } = stats.value
  const ticks = 5
  return Array.from({ length: ticks }, (_, i) => {
    const v = min + (span * i) / (ticks - 1)
    const y = 280 - pad.b - ((v - min) / span) * (280 - pad.t - pad.b)
    return { y, label: v.toFixed(0) }
  })
})

const polylines = computed(() => {
  const n = props.times.length || 1
  const { min, span } = stats.value
  return props.series.map((m) => {
    const pts: string[] = []
    m.values.forEach((v, i) => {
      if (v == null || !Number.isFinite(v)) return
      const x = pad.l + (i / Math.max(1, n - 1)) * (800 - pad.l - pad.r)
      const y = 280 - pad.b - ((v - min) / span) * (280 - pad.t - pad.b)
      pts.push(`${x},${y}`)
    })
    return { id: m.id, color: m.color, points: pts.join(" ") }
  })
})

function onMove(ev: MouseEvent) {
  const svg = ev.currentTarget as SVGRectElement
  const box = svg.getBoundingClientRect()
  const x = ((ev.clientX - box.left) / box.width) * 800
  const n = props.times.length
  if (!n) return
  const i = Math.round(((x - pad.l) / (800 - pad.l - pad.r)) * (n - 1))
  const idx = Math.min(n - 1, Math.max(0, i))
  const bits = props.series
    .map((m) => {
      const v = m.values[idx]
      return v == null ? null : `${m.name} ${Number(v).toFixed(1)}${props.unit || ""}`
    })
    .filter(Boolean)
  hover.value = {
    x: pad.l + (idx / Math.max(1, n - 1)) * (800 - pad.l - pad.r),
    label: `${(props.times[idx] || "").replace("T", " ").slice(5, 16)}  ${bits.join(" · ")}`,
  }
}
</script>
