<script setup>
// Grafico de lineas SVG liviano para los prototipos de ciencia de datos.
// series: [{ name, color, values: [number|null], dashed?: bool }]
// band:   { low: [number|null], high: [number|null], color } (opcional)
import { computed, ref } from 'vue'

const props = defineProps({
  labels: { type: Array, required: true },
  series: { type: Array, required: true },
  band: { type: Object, default: null },
  height: { type: Number, default: 280 },
  yFormat: { type: Function, default: (v) => Math.round(v).toLocaleString('es-CO') },
  zeroLine: { type: Boolean, default: false },
})

const W = 900
const PAD = { top: 16, right: 16, bottom: 34, left: 72 }
const hover = ref(null)

const allValues = computed(() => {
  const vals = props.series.flatMap((s) => s.values)
  if (props.band) vals.push(...props.band.low, ...props.band.high)
  return vals.filter((v) => v !== null && v !== undefined && Number.isFinite(v))
})

const yRange = computed(() => {
  let min = Math.min(...allValues.value)
  let max = Math.max(...allValues.value)
  if (!props.zeroLine && min > 0) min = 0
  if (min === max) max = min + 1
  const pad = (max - min) * 0.06
  return [min < 0 ? min - pad : min, max + pad]
})

const innerW = W - PAD.left - PAD.right
const innerH = computed(() => props.height - PAD.top - PAD.bottom)
const x = (i) => PAD.left + (props.labels.length <= 1 ? innerW / 2 : (i / (props.labels.length - 1)) * innerW)
const y = (v) => PAD.top + innerH.value - ((v - yRange.value[0]) / (yRange.value[1] - yRange.value[0])) * innerH.value

function path(values) {
  let d = ''
  let pen = false
  values.forEach((v, i) => {
    if (v === null || v === undefined || !Number.isFinite(v)) { pen = false; return }
    d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`
    pen = true
  })
  return d
}

const bandPath = computed(() => {
  if (!props.band) return ''
  const idx = props.band.low.map((v, i) => i).filter((i) => Number.isFinite(props.band.low[i]) && Number.isFinite(props.band.high[i]))
  if (!idx.length) return ''
  const top = idx.map((i) => `${x(i).toFixed(1)},${y(props.band.high[i]).toFixed(1)}`)
  const bottom = idx.slice().reverse().map((i) => `${x(i).toFixed(1)},${y(props.band.low[i]).toFixed(1)}`)
  return `M${top.join('L')}L${bottom.join('L')}Z`
})

const yTicks = computed(() => {
  const [min, max] = yRange.value
  return Array.from({ length: 5 }, (_, k) => min + ((max - min) * k) / 4)
})

const xTicks = computed(() => {
  const n = props.labels.length
  const step = Math.max(1, Math.ceil(n / 8))
  return props.labels.map((label, i) => ({ label, i })).filter(({ i }) => i % step === 0)
})

function onMove(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  const px = ((event.clientX - rect.left) / rect.width) * W
  const n = props.labels.length
  const i = Math.round(((px - PAD.left) / innerW) * (n - 1))
  hover.value = i >= 0 && i < n ? i : null
}
</script>

<template>
  <div class="relative">
    <svg :viewBox="`0 0 ${W} ${height}`" class="w-full h-auto select-none" @mousemove="onMove" @mouseleave="hover = null">
      <g class="text-slate-400">
        <line v-for="t in yTicks" :key="t" :x1="PAD.left" :x2="W - PAD.right" :y1="y(t)" :y2="y(t)" stroke="currentColor" stroke-opacity="0.25" />
        <text v-for="t in yTicks" :key="'l' + t" :x="PAD.left - 8" :y="y(t) + 4" text-anchor="end" font-size="12" fill="currentColor">{{ yFormat(t) }}</text>
        <text v-for="t in xTicks" :key="'x' + t.i" :x="x(t.i)" :y="height - 10" text-anchor="middle" font-size="12" fill="currentColor">{{ t.label }}</text>
        <line v-if="zeroLine && yRange[0] < 0" :x1="PAD.left" :x2="W - PAD.right" :y1="y(0)" :y2="y(0)" stroke="currentColor" stroke-opacity="0.7" />
      </g>
      <path v-if="bandPath" :d="bandPath" :fill="band.color || '#10b981'" fill-opacity="0.15" />
      <path
        v-for="s in series" :key="s.name" :d="path(s.values)" fill="none" :stroke="s.color" stroke-width="2.25"
        :stroke-dasharray="s.dashed ? '6 4' : null" stroke-linejoin="round" stroke-linecap="round"
      />
      <g v-if="hover !== null">
        <line :x1="x(hover)" :x2="x(hover)" :y1="PAD.top" :y2="PAD.top + innerH" stroke="#64748b" stroke-opacity="0.5" />
        <template v-for="s in series" :key="'p' + s.name">
          <circle v-if="Number.isFinite(s.values[hover])" :cx="x(hover)" :cy="y(s.values[hover])" r="4" :fill="s.color" stroke="white" stroke-width="1.5" />
        </template>
      </g>
    </svg>
    <div
      v-if="hover !== null"
      class="pointer-events-none absolute top-2 rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-md"
      :class="hover > labels.length / 2 ? 'left-20' : 'right-4'"
    >
      <div class="mb-1 font-semibold text-slate-700">{{ labels[hover] }}</div>
      <div v-for="s in series" :key="'t' + s.name" class="flex items-center gap-2">
        <span class="inline-block h-2 w-3 rounded" :style="{ background: s.color }"></span>
        <span class="text-slate-500">{{ s.name }}:</span>
        <span class="font-medium text-slate-800">{{ Number.isFinite(s.values[hover]) ? yFormat(s.values[hover]) : '—' }}</span>
      </div>
      <div v-if="band && Number.isFinite(band.low[hover])" class="mt-1 text-slate-500">
        Rango 80%: {{ yFormat(band.low[hover]) }} – {{ yFormat(band.high[hover]) }}
      </div>
    </div>
    <div class="mt-1 flex flex-wrap gap-4 text-xs text-slate-600">
      <span v-for="s in series" :key="'lg' + s.name" class="flex items-center gap-1.5">
        <svg width="18" height="6"><line x1="0" x2="18" y1="3" y2="3" :stroke="s.color" stroke-width="2.5" :stroke-dasharray="s.dashed ? '5 3' : null" /></svg>
        {{ s.name }}
      </span>
      <span v-if="band" class="flex items-center gap-1.5">
        <span class="inline-block h-2.5 w-4 rounded-sm" :style="{ background: band.color || '#10b981', opacity: 0.25 }"></span>
        {{ band.name || 'Rango 80%' }}
      </span>
    </div>
  </div>
</template>
