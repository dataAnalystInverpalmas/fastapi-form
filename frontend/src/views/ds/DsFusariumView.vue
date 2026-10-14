<script setup>
import { computed, onMounted, reactive } from 'vue'
import { useDsApi, FLORES, fmtInt, fmtPct } from '@/composables/useDsApi'

const filtros = reactive({ flor: '' })
const { data, loading, error, load } = useDsApi('riesgo-fusarium')
const refresh = () => load(filtros)
onMounted(refresh)

const modelo = computed(() => data.value?.modelo || {})
const maxImp = computed(() => Math.max(0.0001, ...(modelo.value.importancia || []).map((i) => i.importancia)))
const maxVar = computed(() => Math.max(0.0001, ...(data.value?.variedades || []).map((v) => v.tasa_ajustada)))
const aucLabel = computed(() => {
  const a = modelo.value.auc
  if (!Number.isFinite(a)) return ''
  if (a >= 0.8) return 'Buena capacidad para ordenar lotes por riesgo'
  if (a >= 0.7) return 'Capacidad aceptable'
  return 'Débil: usar solo como referencia'
})
const riskClass = (p) => (p >= 0.5 ? 'bg-rose-500' : p >= 0.25 ? 'bg-amber-400' : 'bg-emerald-400')
</script>

<template>
  <div class="space-y-5">
    <div class="card">
      <div class="card-body flex flex-wrap items-end gap-3">
        <div>
          <label class="form-label">Flor</label>
          <select v-model="filtros.flor" class="form-select w-44">
            <option value="">Todas</option>
            <option v-for="f in FLORES.filter((f) => ['CLA', 'CM0'].includes(f.value))" :key="f.value" :value="f.value">{{ f.label }}</option>
          </select>
        </div>
        <button class="btn btn-primary" :disabled="loading" @click="refresh">
          <i class="fas" :class="loading ? 'fa-spinner fa-spin' : 'fa-rotate'"></i>Calcular
        </button>
        <p class="m-0 max-w-2xl text-xs text-slate-500">
          Usa la última evaluación de cada lote en <code>ld_fusarium</code>. Un lote es de <b>riesgo alto</b> si termina con
          ≥ {{ data?.umbral_alto ?? 10 }}% de matas con fusarium. Las tasas se ajustan hacia la de la flor para que variedades con pocos lotes no
          aparezcan arriba por azar.
        </p>
      </div>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <template v-if="data?.resumen">
      <div class="grid gap-4 md:grid-cols-4">
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">Lotes analizados</div>
          <div class="mt-1 text-2xl font-semibold text-slate-900">{{ fmtInt(data.resumen.lotes) }}</div>
        </div></div>
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">% matas con fusarium</div>
          <div class="mt-1 text-2xl font-semibold text-slate-900">{{ fmtPct(data.resumen.tasa_global) }}</div>
        </div></div>
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">Lotes con riesgo alto</div>
          <div class="mt-1 text-2xl font-semibold text-rose-600">{{ fmtPct(data.resumen.pct_lotes_alto) }}</div>
        </div></div>
        <div class="card"><div class="card-body">
          <div class="text-xs font-semibold uppercase tracking-wide text-slate-500">AUC del modelo (validación temporal)</div>
          <div class="mt-1 text-2xl font-semibold text-slate-900">{{ modelo.auc?.toFixed(2) ?? '—' }}</div>
          <div class="text-xs text-slate-500">{{ aucLabel }}</div>
        </div></div>
      </div>

      <div class="grid gap-4 lg:grid-cols-2">
        <div class="card">
          <div class="card-header"><h3 class="m-0 text-sm font-semibold">Variedades con mayor fusarium (tasa ajustada)</h3></div>
          <div class="overflow-x-auto">
            <table class="table">
              <thead><tr><th>Variedad</th><th>Flor</th><th class="text-right">Lotes</th><th>% matas</th><th class="text-right">% lotes alto</th></tr></thead>
              <tbody>
                <tr v-for="v in data.variedades" :key="v.flor + v.variedad">
                  <td class="font-medium">{{ v.variedad }}</td><td>{{ v.flor }}</td><td class="text-right">{{ v.lotes }}</td>
                  <td class="min-w-[150px]"><div class="flex items-center gap-2">
                    <div class="h-2 rounded bg-rose-400" :style="{ width: (v.tasa_ajustada / maxVar) * 90 + 'px' }"></div>
                    <span class="text-xs">{{ fmtPct(v.tasa_ajustada) }}</span>
                    <span class="text-[11px] text-slate-400">(flor {{ fmtPct(v.tasa_flor) }})</span>
                  </div></td>
                  <td class="text-right">{{ fmtPct(v.pct_alto, 0) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="space-y-4">
          <div class="card">
            <div class="card-header"><h3 class="m-0 text-sm font-semibold">Sustrato</h3></div>
            <div class="overflow-x-auto">
              <table class="table">
                <thead><tr><th>Sustrato</th><th>Flor</th><th class="text-right">Lotes</th><th class="text-right">% matas</th><th class="text-right">% lotes alto</th></tr></thead>
                <tbody>
                  <tr v-for="s in data.sustratos" :key="s.flor + s.sustrato">
                    <td>{{ s.sustrato }}</td><td>{{ s.flor }}</td><td class="text-right">{{ s.lotes }}</td>
                    <td class="text-right">{{ fmtPct(s.tasa_ajustada) }}</td><td class="text-right">{{ fmtPct(s.pct_alto, 0) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-if="modelo.disponible" class="card"><div class="card-body">
            <h3 class="mb-1 text-sm font-semibold">¿Qué pesa más en el modelo?</h3>
            <p class="mb-3 text-xs text-slate-500">
              Cuánto empeora el AUC si se “desordena” cada variable. Entrenado con {{ fmtInt(modelo.lotes_entrenamiento) }} lotes hasta
              {{ modelo.corte_fecha }} y evaluado en {{ fmtInt(modelo.lotes_prueba) }} lotes posteriores.
            </p>
            <div v-for="i in modelo.importancia" :key="i.variable" class="mb-1 flex items-center gap-2 text-xs">
              <span class="w-20 text-slate-600">{{ i.variable }}</span>
              <div class="h-2 rounded bg-sky-500" :style="{ width: Math.max(0, i.importancia / maxImp) * 160 + 'px' }"></div>
              <span class="text-slate-500">{{ i.importancia.toFixed(3) }}</span>
            </div>
          </div></div>
        </div>
      </div>

      <div v-if="modelo.lotes_activos?.length" class="card">
        <div class="card-header">
          <h3 class="m-0 text-sm font-semibold">Lotes sembrados con mayor probabilidad de terminar en riesgo alto</h3>
          <span class="text-xs text-slate-500">Para priorizar monitoreo; no reemplaza la evaluación en campo</span>
        </div>
        <div class="overflow-x-auto">
          <table class="table">
            <thead><tr><th>Finca</th><th>Bloque</th><th>Cosecha</th><th>Variedad</th><th>Sustrato</th><th class="text-right">Matas</th><th class="text-right">% actual</th><th>Prob. riesgo alto</th></tr></thead>
            <tbody>
              <tr v-for="l in modelo.lotes_activos" :key="l.finca + l.bloque + l.cosecha + l.variedad">
                <td>{{ l.finca }}</td><td>{{ l.bloque }}</td><td>{{ l.cosecha }}</td><td class="font-medium">{{ l.variedad }}</td>
                <td class="text-xs">{{ l.sustrato }}</td><td class="text-right">{{ fmtInt(l.matas) }}</td>
                <td class="text-right">{{ l.porc?.toFixed(1) }}%</td>
                <td class="min-w-[150px]"><div class="flex items-center gap-2">
                  <div class="h-2 rounded" :class="riskClass(l.prob_alto)" :style="{ width: l.prob_alto * 100 + 'px' }"></div>
                  <span class="text-xs font-medium">{{ fmtPct(l.prob_alto, 0) }}</span>
                </div></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
