<script setup>
import { ref, computed } from 'vue'
import { useEtlPolling, statusMeta, formatDate } from '@/composables/useEtlPolling'

const recentRuns = ref([])
const runSearch = ref('')

const { kpis, countdown, pollError } = useEtlPolling({
  pageType: 'dashboard',
  onRunsUpdate: (runs) => {
    recentRuns.value = runs.slice(0, 10)
  },
})

const kpiCards = computed(() => [
  { key: 'queued', value: kpis.value.queued, label: 'En Cola', color: 'text-secondary', icon: 'fas fa-clock' },
  { key: 'running', value: kpis.value.running, label: 'Ejecutando', color: 'text-primary', icon: 'fas fa-spinner fa-spin' },
  { key: 'success', value: kpis.value.success, label: 'Exitosos (7d)', color: 'text-success', icon: 'fas fa-circle-check' },
  { key: 'failed', value: kpis.value.failed, label: 'Fallidos (7d)', color: 'text-danger', icon: 'fas fa-circle-xmark' },
])

const quickActions = [
  { href: '/etl/jobs', icon: 'fas fa-gears', title: 'Jobs ETL', desc: 'Ejecutar procesos ETL', bg: 'bg-primary-subtle' },
  { href: '/load/jobs', icon: 'fas fa-upload', title: 'Cargas DBF', desc: 'Cargar archivos DBF a MySQL', bg: 'bg-success-subtle' },
  { href: '/consultar', icon: 'fas fa-search', title: 'Consultar DBF', desc: 'Explorar archivos DBF', bg: 'bg-info-subtle' },
  { href: '/etl/params', icon: 'fas fa-sliders', title: 'Parámetros', desc: 'Configurar parámetros de jobs', bg: 'bg-warning-subtle' },
  { href: '/etl/runs', icon: 'fas fa-clock-rotate-left', title: 'Historial', desc: 'Ver ejecuciones pasadas', bg: 'bg-secondary-subtle' },
]

const filteredRuns = computed(() => {
  if (!runSearch.value.trim()) return recentRuns.value
  const query = runSearch.value.toLowerCase()
  return recentRuns.value.filter((run) => {
    return [run.job_id, run.status]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query))
  })
})

function getStatus(status) {
  return statusMeta(status || '')
}
</script>

<template>
  <div class="space-y-4">
    <div v-if="pollError" class="alert alert-warning py-2 small d-flex align-items-center gap-2">
      <i class="fas fa-triangle-exclamation"></i>
      Conexión inestable con el servidor: {{ pollError }}. Los datos en pantalla pueden estar desactualizados.
    </div>
    <div class="row g-3 mb-4">
      <div class="col-6 col-md-3" v-for="kpi in kpiCards" :key="kpi.key">
        <div class="card kpi-card border-0 shadow-sm h-100" :class="'kpi-' + kpi.key + (kpi.key === 'running' && kpis.running > 0 ? ' kpi-active' : '')">
          <div class="card-body text-center py-3">
            <div class="kpi-value" :class="kpi.color">{{ kpi.value }}</div>
            <div class="kpi-label text-muted">
              <i :class="kpi.icon" class="me-1"></i>{{ kpi.label }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <h6 class="text-muted text-uppercase small fw-bold mb-3">
      <i class="fas fa-bolt me-1"></i>Acciones rapidas
    </h6>
    <div class="row g-3 mb-4">
      <div class="col-md-6 col-lg-4" v-for="card in quickActions" :key="card.href">
        <RouterLink :to="card.href" class="text-decoration-none">
          <div class="card border-0 shadow-sm h-100 action-card">
            <div class="card-body d-flex align-items-center gap-3 py-3">
              <div class="action-icon" :class="card.bg">
                <i :class="card.icon"></i>
              </div>
              <div>
                <h6 class="mb-1 text-dark">{{ card.title }}</h6>
                <small class="text-muted">{{ card.desc }}</small>
              </div>
            </div>
          </div>
        </RouterLink>
      </div>
    </div>

    <div class="d-flex justify-content-between align-items-center gap-2 flex-wrap mb-2">
      <h6 class="text-muted text-uppercase small fw-bold mb-0">
        <i class="fas fa-clock-rotate-left me-1"></i>Ultimas ejecuciones
        <span class="ms-2 badge bg-secondary" style="font-size:.7rem">
          <i class="fas fa-satellite-dish me-1"></i>{{ countdown }}s
        </span>
      </h6>
      <input v-model="runSearch" class="form-control form-control-sm" placeholder="Filtrar por job/estado" style="width:220px">
    </div>

    <div class="card border-0 shadow-sm">
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-hover mb-0">
            <thead class="table-light">
              <tr>
                <th>Job</th>
                <th>Estado</th>
                <th>Inicio</th>
                <th>Duracion</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredRuns.length">
                <td colspan="4" class="text-muted text-center py-3">Sin resultados</td>
              </tr>
              <tr v-for="run in filteredRuns" :key="run.run_id">
                <td><code>{{ run.job_id }}</code></td>
                <td>
                  <span class="badge" :class="getStatus(run.status).tone">
                    <span v-if="getStatus(run.status).loading" class="spinner-grow spinner-grow-sm me-1" role="status"></span>
                    <i v-else :class="getStatus(run.status).icon" class="me-1"></i>
                    {{ getStatus(run.status).label }}
                  </span>
                </td>
                <td class="text-muted small">{{ formatDate(run.started_at) }}</td>
                <td class="text-muted small">{{ run.duration_seconds ? run.duration_seconds + 's' : '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

