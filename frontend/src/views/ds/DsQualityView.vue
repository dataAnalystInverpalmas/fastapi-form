<script setup>
import { computed, onMounted, reactive } from 'vue'
import LineChart from '@/components/ds/LineChart.vue'
import { useDsApi, FLORES, fmtInt, fmtPct, fmtCompact, fmtDate } from '@/composables/useDsApi'

const filtros = reactive({ flor: '', semanas: 8 })
const soloAlertas = reactive({ on: false })
const { data, loading, error, load } = useDsApi('calidad-anomalias')
const refresh = () => load(filtros)
onMounted(refresh)

const tendencia = computed(() => data.value?.tendencia || [])
const chart = computed(() => ({
  labels: tendencia.value.map((r) => fmtDate(r.semana)),
  series: [{ name: '% nacional semanal', color: '#e11d48', values: tendencia.value.map((r) => r.pct_nal) }],
}))
const bloques = computed(() => (data.value?.bloques || []).filter((b) => !soloAlertas.on || b.alerta))
const res = computed(() => data.value?.resumen || {})
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
          <label class="form-label">Ventana (semanas)</label>
          <input v-model.number="filtros.semanas" type="number" min="2" max="26" class="form-control w-28" />
        </div>
        <button class="btn btn-primary" :disabled="loading" @click="refresh">
          <i class="fas" :class="loading ? 'fa-spinner fa-spin' : 'fa-rotate'"></i>Analizar
        </button>
        <p class="m-0 max-w-xl text-xs text-slate-500">
          Compara el % de flor <b>nacional</b> (grado NAL en <code>ld_producto_procesado</code>) de cada bloque-variedad contra el de esa variedad en toda la
          empresa. La tasa se “ajusta” hacia la de la variedad para que bloques con pocos tallos no generen falsas alarmas.
        </p>
      </div>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading && !data" class="text-sm text-slate-500"><i class="fas fa-spinner fa-spin mr-1"></i>Procesando millones de registros, puede tardar unos segundos…</div>

    <template v-if="data">
      <div class="grid gap-4 md:grid-cols-4">
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">% nacional en la ventana</div>
          <div class="mt-1 text-2xl font-semibold text-slate-900">{{ fmtPct(res.pct_nal) }}</div>
          <div class="text-xs text-slate-500">de {{ fmtCompact(res.total_tallos) }} tallos clasificados</div>
        </div></div>
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">Bloque-variedades evaluados</div>
          <div class="mt-1 text-2xl font-semibold text-slate-900">{{ fmtInt(res.bloques_evaluados) }}</div>
        </div></div>
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">En alerta</div>
          <div class="mt-1 text-2xl font-semibold text-rose-600">{{ fmtInt(res.bloques_alerta) }}</div>
          <div class="text-xs text-slate-500">≥ {{ data.parametros.razon_alerta }}× su variedad y ≥ {{ data.parametros.exceso_minimo }} tallos de exceso</div>
        </div></div>
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">Tallos de exceso en alertas</div>
          <div class="mt-1 text-2xl font-semibold text-slate-900">{{ fmtCompact(res.exceso_alerta) }}</div>
          <div class="text-xs text-slate-500">nacional por encima de lo esperado</div>
        </div></div>
      </div>

      <div class="card">
        <div class="card-header"><h3 class="m-0 text-sm font-semibold">Tendencia del % nacional (últimos 2 años)</h3></div>
        <div class="card-body"><LineChart :labels="chart.labels" :series="chart.series" :y-format="(v) => fmtPct(v, 0)" :height="220" zero-line /></div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="m-0 text-sm font-semibold">Bloques con mayor exceso de nacional</h3>
          <label class="flex items-center gap-2 text-xs text-slate-600"><input v-model="soloAlertas.on" type="checkbox" /> Solo alertas</label>
        </div>
        <div class="overflow-x-auto">
          <table class="table">
            <thead><tr><th>Finca</th><th>Bloque</th><th>Flor</th><th>Variedad</th><th class="text-right">Tallos</th><th class="text-right">% NAL bloque</th><th class="text-right">% NAL variedad</th><th class="text-right">Veces</th><th class="text-right">Exceso tallos</th><th></th></tr></thead>
            <tbody>
              <tr v-for="b in bloques" :key="b.finca + b.bloque + b.variedad">
                <td>{{ b.finca }}</td><td>{{ b.bloque }}</td><td>{{ b.flor }}</td><td class="font-medium">{{ b.variedad }}</td>
                <td class="text-right">{{ fmtInt(b.total) }}</td>
                <td class="text-right font-medium">{{ fmtPct(b.tasa_bloque) }}</td>
                <td class="text-right text-slate-500">{{ fmtPct(b.tasa_variedad) }}</td>
                <td class="text-right">{{ b.razon?.toFixed(1) }}×</td>
                <td class="text-right">{{ fmtInt(b.exceso_tallos) }}</td>
                <td><span v-if="b.alerta" class="badge border-rose-200 bg-rose-50 text-rose-700">Alerta</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
