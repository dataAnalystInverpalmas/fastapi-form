<script setup>
import { computed, onMounted, reactive } from 'vue'
import LineChart from '@/components/ds/LineChart.vue'
import { useDsApi, FLORES, fmtPct, fmtSignedPct, fmtCompact, fmtDate } from '@/composables/useDsApi'

const filtros = reactive({ flor: 'CLA', finca: '', horizonte: 12 })
const { data, loading, error, load } = useDsApi('pronostico-produccion')
const refresh = () => load(filtros)
onMounted(refresh)

const chart = computed(() => {
  const h = data.value?.historia || []
  const p = data.value?.pronostico || []
  const nH = h.length
  const pad = (arr, before, after) => [...Array(before).fill(null), ...arr, ...Array(after).fill(null)]
  // El pronostico arranca desde el ultimo real para que la linea quede conectada.
  const last = h.length ? h[h.length - 1].real : null
  return {
    labels: [...h.map((r) => fmtDate(r.semana)), ...p.map((r) => fmtDate(r.semana))],
    series: [
      { name: 'Real (ld_lonas)', color: '#059669', values: pad(h.map((r) => r.real), 0, p.length) },
      { name: 'Pronóstico estadístico', color: '#0f172a', values: [...Array(nH - 1).fill(null), last, ...p.map((r) => r.pronostico)] },
      { name: 'Proyección oficial (AJ)', color: '#f59e0b', dashed: true, values: [...h.map((r) => r.proy_oficial), ...p.map((r) => r.proy_oficial)] },
    ],
    band: { low: pad(p.map((r) => r.banda_baja), nH, 0), high: pad(p.map((r) => r.banda_alta), nH, 0), color: '#0f172a', name: 'Rango 80% (del backtest)' },
  }
})

const bt = computed(() => data.value?.backtest || {})
const gana = computed(() => bt.value.wape_modelo !== null && bt.value.wape_modelo < bt.value.wape_ingenuo)
const diffOficial = computed(() => {
  const d = data.value
  if (!d?.total_oficial) return null
  return (d.total_pronostico - d.total_oficial) / d.total_oficial
})
</script>

<template>
  <div class="space-y-5">
    <div class="card">
      <div class="card-body flex flex-wrap items-end gap-3">
        <div>
          <label class="form-label">Flor</label>
          <select v-model="filtros.flor" class="form-select w-44">
            <option v-for="f in FLORES" :key="f.value" :value="f.value">{{ f.label }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Finca</label>
          <select v-model="filtros.finca" class="form-select w-32">
            <option value="">Todas</option><option value="001">001</option><option value="002">002</option>
          </select>
        </div>
        <div>
          <label class="form-label">Semanas a pronosticar</label>
          <input v-model.number="filtros.horizonte" type="number" min="4" max="26" class="form-control w-28" />
        </div>
        <button class="btn btn-primary" :disabled="loading" @click="refresh">
          <i class="fas" :class="loading ? 'fa-spinner fa-spin' : 'fa-rotate'"></i>Pronosticar
        </button>
        <p class="m-0 max-w-xl text-xs text-slate-500">
          Modelo: <b>nivel actual × índice estacional por semana ISO</b> (aprende los picos de fiestas de los últimos 4 años).
          No usa curvas ni siembras: es una segunda opinión independiente de la proyección oficial.
        </p>
      </div>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="data?.error" class="alert alert-light">{{ data.error }}</div>

    <template v-if="data && !data.error">
      <div class="grid gap-4 md:grid-cols-4">
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">Error del modelo (backtest)</div>
          <div class="mt-1 text-2xl font-semibold text-slate-900">{{ fmtPct(bt.wape_modelo) }}</div>
          <div class="text-xs text-slate-500">WAPE en {{ bt.origenes }} pronósticos pasados de {{ data.filtros.horizonte }} semanas</div>
        </div></div>
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">Línea base ingenua</div>
          <div class="mt-1 text-2xl font-semibold text-slate-900">{{ fmtPct(bt.wape_ingenuo) }}</div>
          <div class="text-xs text-slate-500">“Igual que la misma semana del año pasado”</div>
        </div></div>
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">Veredicto</div>
          <div class="mt-1 text-base font-semibold" :class="gana ? 'text-emerald-700' : 'text-amber-600'">
            <i class="fas mr-1" :class="gana ? 'fa-circle-check' : 'fa-triangle-exclamation'"></i>
            {{ gana ? 'Le gana a la línea base' : 'No le gana a la línea base' }}
          </div>
          <div class="text-xs text-slate-500">{{ gana ? 'El modelo aporta información.' : 'Para esta flor hay que mejorar el modelo (p. ej. usar siembras).' }}</div>
        </div></div>
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">Pronóstico vs. oficial</div>
          <div class="mt-1 text-2xl font-semibold" :class="Math.abs(diffOficial) > 0.1 ? 'text-rose-600' : 'text-slate-900'">{{ fmtSignedPct(diffOficial) }}</div>
          <div class="text-xs text-slate-500">{{ fmtCompact(data.total_pronostico) }} vs {{ fmtCompact(data.total_oficial) }} tallos en el horizonte</div>
        </div></div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="m-0 text-sm font-semibold">Producción semanal: último año + pronóstico</h3></div>
        <div class="card-body"><LineChart :labels="chart.labels" :series="chart.series" :band="chart.band" :y-format="fmtCompact" :height="320" /></div>
      </div>

      <div class="grid gap-4 md:grid-cols-2">
        <div class="card"><div class="card-body text-sm text-slate-700">
          <h3 class="mb-2 text-sm font-semibold">Semanas ISO de mayor producción (índice estacional)</h3>
          <div v-for="p in data.semanas_pico" :key="p.semana_iso" class="mb-1 flex items-center gap-2">
            <span class="w-20 text-xs text-slate-500">Semana {{ p.semana_iso }}</span>
            <div class="h-2 rounded bg-emerald-500" :style="{ width: p.indice * 90 + 'px' }"></div>
            <span class="text-xs">{{ p.indice.toFixed(2) }}× el promedio</span>
          </div>
        </div></div>
        <div class="card"><div class="card-body text-xs text-slate-600">
          <h3 class="mb-2 text-sm font-semibold text-slate-800">Cómo leerlo</h3>
          <ul class="list-disc space-y-1 pl-4">
            <li>La banda es el rango donde cayó el 80% de los errores en el backtest, no un supuesto teórico.</li>
            <li>Si la proyección oficial queda fuera de la banda varias semanas seguidas, vale la pena revisar las curvas o las siembras de ese periodo.</li>
            <li>La última semana se excluye si aún no está completa (la carga es diaria).</li>
            <li>Siguiente mejora: añadir siembras (<code>ld_plane_history</code>) y curvas como variables explicativas.</li>
          </ul>
        </div></div>
      </div>
    </template>
  </div>
</template>
