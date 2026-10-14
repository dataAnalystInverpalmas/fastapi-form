<script setup>
import { ref, computed, inject } from 'vue'
import axios from 'axios'
import { useEtlPolling, statusMeta, formatDate } from '@/composables/useEtlPolling'

const toast = inject('toast', () => {})

const jobs = ref([])
const running = ref({})
const search = ref('')
const statusFilter = ref('')

const { kpis, countdown, pollError, pollNow } = useEtlPolling({
  pageType: 'tika',
  jobsApi: '/api/tika/jobs',
  onJobsUpdate: (data) => {
    jobs.value = data
  },
})

const kpiCards = computed(() => [
  { key: 'queued', value: kpis.value.queued, label: 'En Cola', color: 'text-secondary', icon: 'fas fa-clock' },
  { key: 'running', value: kpis.value.running, label: 'Ejecutando', color: 'text-primary', icon: 'fas fa-spinner fa-spin' },
  { key: 'success', value: kpis.value.success, label: 'Exitosos (7d)', color: 'text-success', icon: 'fas fa-circle-check' },
  { key: 'failed', value: kpis.value.failed, label: 'Fallidos (7d)', color: 'text-danger', icon: 'fas fa-circle-xmark' },
])

const filteredJobs = computed(() => {
  let data = jobs.value
  if (statusFilter.value) {
    data = data.filter((job) => (job.last_status || '') === statusFilter.value)
  }
  if (search.value.trim()) {
    const q = search.value.toLowerCase()
    data = data.filter((job) => {
      return [job.job_id, job.name, job.description]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(q))
    })
  }
  return data
})

function getStatus(status) {
  return statusMeta(status || '')
}

async function runJob(jobId) {
  running.value[jobId] = true
  try {
    const { data } = await axios.post(`/api/etl/jobs/${jobId}/run`, { params: {} })
    toast(`Job ${jobId} enviado a la cola (run #${data.run_id}).`, 'info')
    pollNow()
  } catch (err) {
    const msg = err.response?.data?.detail || 'Error al encolar el job.'
    toast(msg, 'danger')
  } finally {
    running.value[jobId] = false
  }
}

function isActive(job) {
  return job.last_status === 'running' || job.last_status === 'queued' || running.value[job.job_id]
}

const cancelling = ref({})

async function cancelRun(job) {
  if (!job.last_run_id) return
  cancelling.value[job.job_id] = true
  try {
    const { data } = await axios.post(`/api/etl/runs/${job.last_run_id}/cancel`)
    toast(data.message || 'Ejecución cancelada.', 'warning')
    pollNow()
  } catch (err) {
    const msg = err.response?.data?.detail || 'No se pudo cancelar la ejecución.'
    toast(msg, 'danger')
  } finally {
    cancelling.value[job.job_id] = false
  }
}
</script>

<template>
  <section class="mt-4 space-y-4">
    <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
      <h4 class="mb-0"><i class="fas fa-file-csv me-2"></i>Cargas Tika a MySQL</h4>
      <div class="d-flex gap-2">
        <button class="btn btn-outline-secondary btn-sm" @click="pollNow">
          <i class="fas fa-rotate me-1"></i>Actualizar ahora
        </button>
        <RouterLink to="/etl/runs" class="btn btn-outline-secondary btn-sm">
          <i class="fas fa-clock-rotate-left me-1"></i>Ver historial
        </RouterLink>
      </div>
    </div>

    <div v-if="pollError" class="alert alert-warning py-2 small d-flex align-items-center gap-2">
      <i class="fas fa-triangle-exclamation"></i>
      Conexión inestable con el servidor: {{ pollError }}. Los datos en pantalla pueden estar desactualizados.
    </div>

    <div class="row g-3 mb-4">
      <div class="col-6 col-md-3" v-for="kpi in kpiCards" :key="kpi.key">
        <div class="card kpi-card border-0 shadow-sm h-100" :class="'kpi-' + kpi.key + (kpi.key === 'running' && kpis.running > 0 ? ' kpi-active' : '')">
          <div class="card-body text-center py-3">
            <div class="kpi-value" :class="kpi.color">{{ kpi.value }}</div>
            <div class="kpi-label text-muted"><i :class="kpi.icon" class="me-1"></i>{{ kpi.label }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="card border-0 shadow-sm">
      <div class="card-header bg-light border-bottom d-flex justify-content-between align-items-center">
        <strong>Cargas Tika disponibles</strong>
        <span class="badge bg-secondary">
          <i class="fas fa-satellite-dish me-1"></i>{{ countdown }}s
        </span>
      </div>

      <div class="px-5 py-3 border-bottom border-slate-200 d-flex gap-2 flex-wrap">
        <input v-model="search" class="form-control form-control-sm" placeholder="Buscar carga..." style="max-width: 260px">
        <select v-model="statusFilter" class="form-select form-select-sm" style="max-width: 180px">
          <option value="">Todos los estados</option>
          <option value="queued">queued</option>
          <option value="running">running</option>
          <option value="success">success</option>
          <option value="failed">failed</option>
        </select>
      </div>

      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-hover mb-0">
            <thead class="table-light">
              <tr>
                <th>Job</th>
                <th>Descripcion</th>
                <th>Ultimo estado</th>
                <th>Ultima ejecucion</th>
                <th class="text-end">Accion</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredJobs.length">
                <td colspan="5" class="text-center text-muted py-3">Sin resultados</td>
              </tr>
              <tr v-for="job in filteredJobs" :key="job.job_id" :id="job.job_id">
                <td><code>{{ job.job_id }}</code><br><strong>{{ job.name }}</strong></td>
                <td class="text-muted small">{{ job.description }}</td>
                <td>
                  <span class="badge" :class="getStatus(job.last_status).tone">
                    <span v-if="getStatus(job.last_status).loading" class="spinner-grow spinner-grow-sm me-1" role="status"></span>
                    <i v-else :class="getStatus(job.last_status).icon" class="me-1"></i>
                    {{ getStatus(job.last_status).label }}
                  </span>
                  <div v-if="job.last_error_message" class="small text-danger text-break mt-1" style="max-width: 22rem">
                    {{ job.last_error_message }}
                  </div>
                </td>
                <td class="text-muted small">{{ formatDate(job.last_started_at) }}</td>
                <td class="text-end">
                  <button
                    v-if="isActive(job) && job.last_run_id"
                    class="btn btn-sm btn-outline-danger me-1"
                    :disabled="cancelling[job.job_id]"
                    @click="cancelRun(job)"
                  >
                    <span v-if="cancelling[job.job_id]" class="spinner-border spinner-border-sm me-1"></span>
                    <i v-else class="fas fa-ban me-1"></i>
                    Cancelar
                  </button>
                  <button class="btn btn-sm btn-success" :disabled="isActive(job)" @click="runJob(job.job_id)">
                    <span v-if="running[job.job_id]" class="spinner-border spinner-border-sm me-1"></span>
                    <i v-else class="fas fa-upload me-1"></i>
                    {{ running[job.job_id] ? 'En cola...' : 'Cargar' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </section>
</template>
