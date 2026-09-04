<script setup>
import { ref, computed } from 'vue'
import { useEtlPolling, statusMeta, formatDate } from '@/composables/useEtlPolling'

const runs = ref([])
const search = ref('')
const statusFilter = ref('')
const pageSize = ref(25)
const page = ref(1)

const { countdown, pollNow } = useEtlPolling({
  pageType: 'runs',
  onRunsUpdate: (data) => {
    runs.value = data
    page.value = 1
  },
})

const filtered = computed(() => {
  let data = runs.value
  if (statusFilter.value) data = data.filter((x) => x.status === statusFilter.value)
  if (search.value.trim()) {
    const q = search.value.toLowerCase()
    data = data.filter((x) => (x.job_id || '').toLowerCase().includes(q))
  }
  return data
})

const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paginated = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filtered.value.slice(start, start + pageSize.value)
})

function getStatus(status) {
  return statusMeta(status || '')
}

function setPage(nextPage) {
  if (nextPage >= 1 && nextPage <= totalPages.value) page.value = nextPage
}

function shortPath(pathValue) {
  if (!pathValue) return '–'
  return pathValue.replace(/\\/g, '/').split('/').pop()
}

function shortError(errorValue) {
  if (!errorValue) return '–'
  return errorValue.length > 60 ? `${errorValue.slice(0, 60)}...` : errorValue
}
</script>

<template>
  <section class="mt-4 space-y-4">
    <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
      <h4 class="mb-0"><i class="fas fa-list-check me-2"></i>Historial de ejecuciones</h4>
      <div class="d-flex gap-2">
        <button class="btn btn-outline-secondary btn-sm" @click="pollNow">
          <i class="fas fa-rotate me-1"></i>Actualizar
        </button>
        <RouterLink to="/etl/jobs" class="btn btn-outline-secondary btn-sm">
          <i class="fas fa-arrow-left me-1"></i>Volver a jobs
        </RouterLink>
      </div>
    </div>

    <div class="card border-0 shadow-sm">
      <div class="card-header bg-light border-bottom d-flex justify-content-between align-items-center flex-wrap gap-2">
        <strong>Ultimas {{ runs.length }} ejecuciones</strong>
        <div class="d-flex gap-2 align-items-center">
          <input v-model="search" class="form-control form-control-sm" placeholder="Buscar job..." style="width:160px">
          <select v-model="statusFilter" class="form-select form-select-sm" style="width:130px">
            <option value="">Todos</option>
            <option value="success">success</option>
            <option value="failed">failed</option>
            <option value="running">running</option>
            <option value="queued">queued</option>
          </select>
          <select v-model="pageSize" class="form-select form-select-sm" style="width:90px" @change="page=1">
            <option :value="10">10</option>
            <option :value="25">25</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
          <span class="badge bg-secondary">
            <i class="fas fa-satellite-dish me-1"></i>{{ countdown }}s
          </span>
        </div>
      </div>

      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-striped mb-0" style="font-size:.875rem">
            <thead class="table-light">
              <tr>
                <th>Run ID</th>
                <th>Job</th>
                <th>Estado</th>
                <th>Inicio</th>
                <th>Fin</th>
                <th>Dur. (s)</th>
                <th>Salida</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!paginated.length">
                <td colspan="8" class="text-center text-muted py-3">Sin resultados</td>
              </tr>
              <tr v-for="run in paginated" :key="run.run_id">
                <td>{{ run.run_id }}</td>
                <td><code>{{ run.job_id }}</code></td>
                <td>
                  <span class="badge" :class="getStatus(run.status).tone">
                    <span v-if="getStatus(run.status).loading" class="spinner-grow spinner-grow-sm me-1" role="status"></span>
                    <i v-else :class="getStatus(run.status).icon" class="me-1"></i>
                    {{ getStatus(run.status).label }}
                  </span>
                </td>
                <td class="text-muted">{{ formatDate(run.started_at) }}</td>
                <td class="text-muted">{{ formatDate(run.finished_at) }}</td>
                <td>{{ run.duration_seconds ?? '–' }}</td>
                <td :title="run.output_path || ''">{{ shortPath(run.output_path) }}</td>
                <td class="text-danger small" :title="run.error_message || ''">{{ shortError(run.error_message) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex justify-content-between align-items-center px-3 py-2 border-top">
          <small class="text-muted">
            {{ filtered.length }} resultado{{ filtered.length !== 1 ? 's' : '' }}
            — pagina {{ page }} / {{ totalPages }}
          </small>
          <div class="d-flex gap-1">
            <button class="btn btn-sm btn-outline-secondary" :disabled="page === 1" @click="setPage(1)">«</button>
            <button class="btn btn-sm btn-outline-secondary" :disabled="page === 1" @click="setPage(page - 1)">‹</button>
            <button class="btn btn-sm btn-outline-secondary" :disabled="page === totalPages" @click="setPage(page + 1)">›</button>
            <button class="btn btn-sm btn-outline-secondary" :disabled="page === totalPages" @click="setPage(totalPages)">»</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

