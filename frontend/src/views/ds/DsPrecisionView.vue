<script setup>
import { computed, onMounted, reactive } from 'vue'
import LineChart from '@/components/ds/LineChart.vue'
import { useDsApi, FLORES, fmtInt, fmtPct, fmtSignedPct, fmtCompact, fmtYyww } from '@/composables/useDsApi'

const filtros = reactive({ flor: '', finca: '' })
const { data, loading, error, load } = useDsApi('precision-proyecciones')
const refresh = () => load(filtros)
onMounted(refresh)

const semanal = computed(() => data.value?.semanal || [])
const chart = computed(() => ({
  labels: semanal.value.map((r) => fmtYyww(r.sem_prod)),
  series: [
    { name: 'Real', color: '#059669', values: semanal.value.map((r) => r.real) },
    { name: 'Proy. ajustada', color: '#0f172a', values: semanal.value.map((r) => r.proy_ajustada), dashed: true },
    { name: 'Proy. inicial', color: '#f59e0b', values: semanal.value.map((r) => r.proy_inicial), dashed: true },
  ],
}))
const errChart = computed(() => ({
  labels: semanal.value.map((r) => fmtYyww(r.sem_prod)),
  series: [{ name: 'Error semanal proy. ajustada vs real', color: '#e11d48', values: semanal.value.map((r) => r.error_pct) }],
}))

const variedades = computed(() => data.value?.variedades || [])
const maxErr = computed(() => Math.max(1, ...variedades.value.map((v) => v.abs_err)))
const totalErr = computed(() => (data.value?.resumen || []).find((r) => r.fuente === 'proy_ajustada'))
</script>

<template>
  <div class="space-y-5">
    <div class="card">
      <div class="card-body flex flex-wrap items-end gap-3">
        <div>
          <label class="form-label">Flor</label>
          <select v-model="filtros.flor" class="form-select w-44">
            <option value="">Todas</option>
            <option v-for="f in FLORES" :key="f.value" :value="f.value">{{ f.label }}</option>
          </select>
        </div>
        <div>
          <label class="form-label">Finca</label>
          <select v-model="filtros.finca" class="form-select w-32">
            <option value="">Todas</option><option value="001">001</option><option value="002">002</option>
          </select>
        </div>
        <button class="btn btn-primary" :disabled="loading" @click="refresh">
          <i class="fas" :class="loading ? 'fa-spinner fa-spin' : 'fa-rotate'"></i>Calcular
        </button>
        <p class="m-0 max-w-xl text-xs text-slate-500">
          Fuente: <code>quipus_vs_proy</code>, solo filas con producción real. <b>WAPE</b> = suma de errores absolutos / suma real
          (error típico). <b>Sesgo</b> &gt; 0 = sobreestimamos, &lt; 0 = subestimamos.
        </p>
      </div>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <template v-if="data">
      <div class="grid gap-4 md:grid-cols-3">
        <div v-for="r in data.resumen" :key="r.fuente" class="card">
          <div class="card-body">
            <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">{{ r.nombre }}</div>
            <div v-if="r.filas" class="mt-2 flex items-end gap-6">
              <div><div class="text-2xl font-semibold text-slate-900">{{ fmtPct(r.wape) }}</div><div class="text-xs text-slate-500">WAPE (por lote-semana)</div></div>
              <div><div class="text-2xl font-semibold" :class="r.sesgo < 0 ? 'text-amber-600' : 'text-sky-700'">{{ fmtSignedPct(r.sesgo) }}</div><div class="text-xs text-slate-500">Sesgo</div></div>
            </div>
            <div v-else class="mt-2 text-sm text-slate-400">Sin datos para este filtro</div>
            <div v-if="r.filas" class="mt-2 text-xs text-slate-400">{{ fmtInt(r.filas) }} filas · real {{ fmtCompact(r.real) }} tallos</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="m-0 text-sm font-semibold">Real vs. proyectado por semana de producción</h3></div>
        <div class="card-body"><LineChart :labels="chart.labels" :series="chart.series" :y-format="fmtCompact" /></div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="m-0 text-sm font-semibold">Error % semanal (proyección ajustada)</h3>
          <span class="text-xs text-slate-500">Positivo = se proyectó de más</span></div>
        <div class="card-body"><LineChart :labels="errChart.labels" :series="errChart.series" :y-format="(v) => fmtPct(v, 0)" zero-line :height="200" /></div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="m-0 text-sm font-semibold">Variedades que concentran el error (en tallos)</h3>
          <span v-if="totalErr" class="text-xs text-slate-500">Ordenadas por error absoluto: aquí rinde más revisar la curva</span>
        </div>
        <div class="overflow-x-auto">
          <table class="table">
            <thead><tr><th>Variedad</th><th>Flor</th><th class="text-right">Real</th><th class="text-right">Proyectado</th><th>Error absoluto</th><th class="text-right">WAPE</th><th class="text-right">Sesgo</th></tr></thead>
            <tbody>
              <tr v-for="v in variedades" :key="v.flor + v.variedad">
                <td class="font-medium">{{ v.variedad }}</td><td>{{ v.flor }}</td>
                <td class="text-right">{{ fmtInt(v.real) }}</td><td class="text-right">{{ fmtInt(v.proy) }}</td>
                <td class="min-w-[180px]">
                  <div class="flex items-center gap-2">
                    <div class="h-2 rounded bg-rose-400" :style="{ width: (v.abs_err / maxErr) * 120 + 'px' }"></div>
                    <span class="text-xs text-slate-500">{{ fmtCompact(v.abs_err) }}</span>
                  </div>
                </td>
                <td class="text-right">{{ fmtPct(v.wape) }}</td>
                <td class="text-right" :class="v.sesgo < 0 ? 'text-amber-600' : 'text-sky-700'">{{ fmtSignedPct(v.sesgo) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
