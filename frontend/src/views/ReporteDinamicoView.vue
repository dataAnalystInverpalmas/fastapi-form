<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const selectedFilas = ref(['finca', 'variedad'])
const selectedColumnas = ref([])
const selectedValores = ref([])
const agregacion = ref('SUM')

const campos = ref([])
const metricas = ref([])
const agregaciones = ref(['SUM', 'AVG', 'COUNT', 'MIN', 'MAX'])
const filterOptions = ref({})
const activeFilters = ref({})
const filtrosPanelOpen = ref(true)

const result = ref(null)
const error = ref(null)
const loading = ref(false)
const fromCache = ref(false)

const page = ref(1)
const pageSize = ref(25)
const search = ref('')

const filteredRows = computed(() => {
  if (!result.value) return []
  if (!search.value.trim()) return result.value.data
  const q = search.value.toLowerCase()
  return result.value.data.filter(row => row.some(v => String(v ?? '').toLowerCase().includes(q)))
})
const totalPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize.value)))
const paginatedRows = computed(() => {
  const s = (page.value - 1) * pageSize.value
  return filteredRows.value.slice(s, s + pageSize.value)
})
function setPage(p) { if (p >= 1 && p <= totalPages.value) page.value = p }

const activeFiltrosCount = computed(() =>
  Object.values(activeFilters.value).reduce((acc, s) => acc + s.size, 0)
)

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/reporte-dinamico/filtros')
    const { campos: c, metricas: m, agregaciones: a, ...rest } = data
    campos.value = c || []
    metricas.value = m || []
    agregaciones.value = a || ['SUM', 'AVG', 'COUNT', 'MIN', 'MAX']
    filterOptions.value = rest
    selectedValores.value = [...(m || [])]
  } catch (err) {
    error.value = 'No se pudieron cargar las opciones del servidor.'
  }
})

function toggleFilter(campo, val) {
  if (!activeFilters.value[campo]) activeFilters.value[campo] = new Set()
  const set = activeFilters.value[campo]
  if (set.has(val)) set.delete(val)
  else set.add(val)
  activeFilters.value = { ...activeFilters.value }
}

function isFilterActive(campo, val) {
  return activeFilters.value[campo]?.has(val) ?? false
}

function clearFilters() {
  activeFilters.value = {}
}

function buildFiltros() {
  const f = {}
  for (const [campo, set] of Object.entries(activeFilters.value)) {
    if (set.size) f[campo] = Array.from(set)
  }
  return f
}

async function generate() {
  if (!selectedFilas.value.length) { error.value = 'Selecciona al menos una fila.'; return }
  if (!selectedValores.value.length) { error.value = 'Selecciona al menos un valor.'; return }
  error.value = null
  loading.value = true
  result.value = null
  page.value = 1
  const t0 = performance.now()
  try {
    const { data } = await axios.post('/api/reporte-dinamico', {
      filas: selectedFilas.value,
      columnas: selectedColumnas.value,
      valores: selectedValores.value,
      agregacion: agregacion.value,
      filtros: buildFiltros(),
    })
    result.value = data
    fromCache.value = performance.now() - t0 < 80
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || 'Error al generar el reporte.'
  } finally {
    loading.value = false
  }
}

async function clearCache() {
  try {
    await axios.post('/api/reporte-dinamico/cache/clear')
    if (window.$toast) window.$toast('Caché del reporte dinámico vaciado.', 'info')
    fromCache.value = false
  } catch {
    if (window.$toast) window.$toast('Error al limpiar caché.', 'danger')
  }
}

function toggleSelect(arr, all, val) {
  const idx = arr.indexOf(val)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(val)
}
</script>

<template>
  <div class="mt-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-5">
      <h5 class="m-0 text-base font-semibold text-slate-800">
        <i class="fas fa-table mr-2 text-emerald-500"></i>Reporte Dinámico — Lonas
      </h5>
      <span v-if="fromCache" class="badge bg-secondary" title="Resultado desde caché">
        <i class="fas fa-bolt mr-1"></i>Caché
      </span>
    </div>

    <!-- Panel de configuración -->
    <div class="card mb-4 bg-slate-50/60">
      <div class="card-body">
        <div class="grid grid-cols-12 gap-4 items-start">

          <!-- Filas -->
          <div class="col-span-12 sm:col-span-6 md:col-span-3">
            <label class="form-label font-semibold">
              <i class="fas fa-grip-lines mr-1 text-slate-400"></i>Filas
              <small class="text-slate-400 font-normal ml-1">(GROUP BY)</small>
            </label>
            <select v-model="selectedFilas" multiple class="form-select" style="min-height:100px" title="Ctrl+clic para múltiple">
              <option v-for="c in campos" :key="c" :value="c">{{ c }}</option>
            </select>
            <p class="form-text">Ctrl+clic para selección múltiple</p>
          </div>

          <!-- Columnas -->
          <div class="col-span-12 sm:col-span-6 md:col-span-3">
            <label class="form-label font-semibold">
              <i class="fas fa-columns mr-1 text-slate-400"></i>Columnas
              <small class="text-slate-400 font-normal ml-1">(Pivote)</small>
            </label>
            <select v-model="selectedColumnas" multiple class="form-select" style="min-height:100px">
              <option v-for="c in campos" :key="c" :value="c">{{ c }}</option>
            </select>
            <p class="form-text">Opcional — genera columnas dinámicas</p>
          </div>

          <!-- Valores -->
          <div class="col-span-12 sm:col-span-6 md:col-span-2">
            <label class="form-label font-semibold">
              <i class="fas fa-hashtag mr-1 text-slate-400"></i>Valores
            </label>
            <select v-model="selectedValores" multiple class="form-select" style="min-height:100px">
              <option v-for="m in metricas" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>

          <!-- Agregación -->
          <div class="col-span-12 sm:col-span-6 md:col-span-2">
            <label class="form-label font-semibold">
              <i class="fas fa-calculator mr-1 text-slate-400"></i>Agregación
            </label>
            <select v-model="agregacion" class="form-select">
              <option v-for="a in agregaciones" :key="a" :value="a">{{ a }}</option>
            </select>
          </div>

          <!-- Botones -->
          <div class="col-span-12 sm:col-span-12 md:col-span-2 flex flex-col gap-2 pt-7">
            <button class="btn btn-primary w-full" :disabled="loading" @click="generate">
              <span v-if="loading" class="spinner-border spinner-border-sm"></span>
              <i v-else class="fas fa-play"></i>
              {{ loading ? 'Cargando…' : 'Generar' }}
            </button>
            <button class="btn btn-outline-secondary btn-sm w-full" @click="clearCache">
              <i class="fas fa-trash-alt mr-1"></i>Limpiar caché
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Panel de filtros -->
    <div class="card mb-4">
      <div
        class="flex items-center justify-between px-5 py-3 border-b border-slate-100 cursor-pointer select-none"
        @click="filtrosPanelOpen = !filtrosPanelOpen"
      >
        <span class="font-semibold text-sm text-slate-700">
          <i class="fas fa-filter mr-1 text-slate-400"></i>Filtros
          <span v-if="activeFiltrosCount" class="badge bg-primary ml-2">{{ activeFiltrosCount }}</span>
        </span>
        <i class="fas text-slate-400 text-xs" :class="filtrosPanelOpen ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
      </div>
      <div v-show="filtrosPanelOpen" class="px-5 py-4">
        <div v-if="!Object.keys(filterOptions).length" class="text-slate-500 text-xs">
          <span class="spinner-border spinner-border-sm mr-1"></span>Cargando opciones…
        </div>
        <div v-else class="flex flex-col gap-4">
          <div v-for="(vals, campo) in filterOptions" :key="campo">
            <div class="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              {{ campo }}
            </div>
            <div class="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
              <label
                v-for="val in vals" :key="val"
                class="inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium cursor-pointer transition"
                :class="isFilterActive(campo, val)
                  ? 'bg-emerald-500 text-white border-emerald-500'
                  : 'bg-slate-100 text-slate-700 border-slate-200 hover:border-slate-300'"
                @click="toggleFilter(campo, val)"
              >{{ val }}</label>
            </div>
          </div>
          <div v-if="activeFiltrosCount">
            <button class="btn btn-outline-secondary btn-sm" @click="clearFilters">
              <i class="fas fa-times mr-1"></i>Limpiar todos los filtros
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="alert alert-danger mb-4" role="alert">
      <i class="fas fa-exclamation-circle mr-2"></i>{{ error }}
    </div>

    <!-- Resultados -->
    <div v-if="result">
      <div class="flex items-center justify-between mb-3 flex-wrap gap-3">
        <span class="text-slate-500 text-xs">
          <i class="fas fa-check-circle text-emerald-500 mr-1"></i>
          {{ result.total_rows }} filas · {{ result.columns?.length }} columnas
        </span>
        <div class="flex gap-2">
          <input v-model="search" class="form-control form-control-sm w-40" placeholder="Buscar…" @input="page=1">
          <select v-model="pageSize" class="form-select form-select-sm w-20" @change="page=1">
            <option :value="10">10</option>
            <option :value="25">25</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </div>
      </div>
      <div class="card">
        <div class="table-responsive">
          <table class="table" style="font-size:.82rem">
            <thead>
              <tr>
                <th v-for="col in result.columns" :key="col">{{ col }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!paginatedRows.length">
                <td :colspan="result.columns?.length" class="text-center text-slate-500 py-6">Sin resultados</td>
              </tr>
              <tr v-for="(row, i) in paginatedRows" :key="i">
                <td v-for="(val, j) in row" :key="j">{{ val ?? '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex items-center justify-between px-5 py-3 border-t border-slate-100">
          <small class="text-slate-500 text-xs">
            {{ filteredRows.length }} fila{{ filteredRows.length !== 1 ? 's' : '' }} — página {{ page }} / {{ totalPages }}
          </small>
          <div class="flex gap-1">
            <button class="btn btn-sm btn-outline-secondary" :disabled="page===1" @click="setPage(1)">«</button>
            <button class="btn btn-sm btn-outline-secondary" :disabled="page===1" @click="setPage(page-1)">‹</button>
            <button class="btn btn-sm btn-outline-secondary" :disabled="page===totalPages" @click="setPage(page+1)">›</button>
            <button class="btn btn-sm btn-outline-secondary" :disabled="page===totalPages" @click="setPage(totalPages)">»</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
