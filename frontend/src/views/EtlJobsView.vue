<script setup>
import { ref, computed, inject } from 'vue'
import axios from 'axios'
import { useEtlPolling, statusMeta, formatDate } from '@/composables/useEtlPolling'

const toast = inject('toast', () => {})

const jobs = ref([])
const search = ref('')
const statusFilter = ref('')

const { kpis, countdown, pollNow } = useEtlPolling({
  pageType: 'etl',
  jobsApi: '/api/etl/jobs',
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

const showModal = ref(false)
const modalJob = ref(null)
const modalParams = ref({})
const running = ref({})

const PARAM_DEFINITIONS = {
  modelos_tika: { label: 'Modelos Tika (separados por coma)', type: 'text', placeholder: 'Ej: 161, 328, 485' },
  muestras: { label: 'Número de muestras/lonas', type: 'number', placeholder: 'Defecto: 5' },
  tallos_min: { label: 'Tallos mínimos', type: 'number', placeholder: 'Defecto: 1000' },
  lonas_semana: { label: 'Capacidad de lonas por semana', type: 'number', placeholder: 'Defecto: 65' },
  modelo_tika: { label: 'Modelo Tika', type: 'number', placeholder: 'Ej: 485' },
  semana_actual: { label: 'Semana actual (YYWW)', type: 'number', placeholder: 'Ej: 2613' },
  semana_inicio: { label: 'Semana inicio (YYWW)', type: 'number', placeholder: 'Ej: 2527' },
  semana_fin: { label: 'Semana fin (YYWW)', type: 'number', placeholder: 'Ej: 2620' },
}

function getStatus(status) {
  return statusMeta(status || '')
}

async function openModal(job) {
  modalJob.value = job
  modalParams.value = {}
  try {
    const { data } = await axios.get(`/api/etl/jobs/${job.job_id}/last-params`)
    const last = data.params || {}
    const defaults = job.default_params || {}
    const combined = {}
    for (const key of Object.keys(defaults)) {
      const value = last[key] ?? defaults[key]
      combined[key] = Array.isArray(value) ? value.join(', ') : (value ?? '')
    }
    modalParams.value = combined
  } catch {
    const defaults = job.default_params || {}
    for (const key of Object.keys(defaults)) {
      const value = defaults[key]
      modalParams.value[key] = Array.isArray(value) ? value.join(', ') : (value ?? '')
    }
  }
  showModal.value = true
}

async function confirmRun() {
  const job = modalJob.value
  if (!job) return
  showModal.value = false
  await runJob(job.job_id, buildPayload(job))
}

function buildPayload(job) {
  const params = {}
  for (const [key, rawVal] of Object.entries(modalParams.value)) {
    const def = PARAM_DEFINITIONS[key]
    const value = String(rawVal).trim()
    if (!value) continue
    if (def?.type === 'number') {
      params[key] = parseInt(value, 10) || null
    } else {
      const defaultVal = (job.default_params || {})[key]
      if (Array.isArray(defaultVal)) {
        params[key] = value.split(',').map((v) => parseInt(v.trim(), 10)).filter((n) => !isNaN(n))
      } else {
        params[key] = value
      }
    }
  }
  return { params }
}

async function runJob(jobId, payload = { params: {} }) {
  running.value[jobId] = true
  try {
    const { data } = await axios.post(`/api/etl/jobs/${jobId}/run`, payload)
    toast(`Job <strong>${jobId}</strong> enviado a la cola (run #${data.run_id}).`, 'info')
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
</script>

<template>
  <section class="mt-4 space-y-4">
    <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
      <h4 class="mb-0"><i class="fas fa-gears me-2"></i>Ejecución de ETL</h4>
      <div class="d-flex gap-2">
        <RouterLink to="/etl/params" class="btn btn-outline-primary btn-sm">
          <i class="fas fa-sliders me-1"></i>Parámetros por Job
        </RouterLink>
        <button class="btn btn-outline-secondary btn-sm" @click="pollNow">
          <i class="fas fa-rotate me-1"></i>Actualizar ahora
        </button>
        <RouterLink to="/etl/runs" class="btn btn-outline-secondary btn-sm">
          <i class="fas fa-clock-rotate-left me-1"></i>Ver historial
        </RouterLink>
      </div>
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
        <strong>Jobs disponibles</strong>
        <span class="badge bg-secondary">
          <i class="fas fa-satellite-dish me-1"></i>{{ countdown }}s
        </span>
      </div>

      <div class="px-5 py-3 border-bottom border-slate-200 d-flex gap-2 flex-wrap">
        <input v-model="search" class="form-control form-control-sm" placeholder="Buscar job..." style="max-width: 260px">
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
                <th>Descripción</th>
                <th>Último estado</th>
                <th>Última ejecución</th>
                <th class="text-end">Acción</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredJobs.length">
                <td colspan="5" class="text-center text-muted py-3">Sin resultados</td>
              </tr>
              <tr v-for="job in filteredJobs" :key="job.job_id">
                <td>
                  <code>{{ job.job_id }}</code><br>
                  <strong>{{ job.name }}</strong>
                </td>
                <td class="text-muted small">{{ job.description }}</td>
                <td>
                  <span class="badge" :class="getStatus(job.last_status).tone">
                    <span v-if="getStatus(job.last_status).loading" class="spinner-grow spinner-grow-sm me-1" role="status"></span>
                    <i v-else :class="getStatus(job.last_status).icon" class="me-1"></i>
                    {{ getStatus(job.last_status).label }}
                  </span>
                </td>
                <td class="text-muted small">{{ formatDate(job.last_started_at) }}</td>
                <td class="text-end">
                  <button class="btn btn-sm btn-primary" :disabled="isActive(job)" @click="openModal(job)">
                    <span v-if="running[job.job_id]" class="spinner-border spinner-border-sm me-1"></span>
                    <i v-else class="fas fa-play me-1"></i>
                    {{ running[job.job_id] ? 'En cola…' : 'Ejecutar' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <div v-if="showModal" class="modal" style="background:rgba(2,6,23,.45)">
    <div class="modal-dialog modal-dialog-centered">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">Ejecutar job con parámetros</h5>
          <button type="button" class="btn-close" @click="showModal = false"></button>
        </div>
        <div class="modal-body">
          <p class="text-muted small mb-3">Job: <strong>{{ modalJob?.name }}</strong> — <code>{{ modalJob?.job_id }}</code></p>

          <div v-if="modalJob && Object.keys(modalJob.default_params || {}).length === 0" class="text-muted small">
            Este job no requiere parámetros.
          </div>

          <div v-for="(defVal, key) in modalJob?.default_params" :key="key" class="mb-3">
            <label class="form-label">{{ PARAM_DEFINITIONS[key]?.label || key.replace(/_/g, ' ') }}</label>
            <input
              v-model="modalParams[key]"
              :type="PARAM_DEFINITIONS[key]?.type || 'text'"
              :placeholder="PARAM_DEFINITIONS[key]?.placeholder || ''"
              class="form-control"
              autocomplete="off"
            >
            <div class="form-text">Defecto: {{ Array.isArray(defVal) ? defVal.join(', ') : defVal }}</div>
          </div>

          <div class="form-text mt-2">Opcional: si se deja vacío usa la configuración por defecto del job.</div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline-secondary" @click="showModal = false">Cancelar</button>
          <button class="btn btn-primary" @click="confirmRun">
            <i class="fas fa-play me-1"></i>Ejecutar
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

