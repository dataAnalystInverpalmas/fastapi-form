<script setup>
import { ref, computed, inject, onMounted } from 'vue'
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

const orderedJobs = computed(() => {
  const groups = ['01 - Cargas Maestro', '02 - Fuentes y Base', '03 - Derivados Semanales', '04 - Analitica']
  const fallbackRank = groups.length + 1
  return [...jobs.value].sort((a, b) => {
    const aGroup = String(a.flow_group || '')
    const bGroup = String(b.flow_group || '')
    const aRank = groups.includes(aGroup) ? groups.indexOf(aGroup) : fallbackRank
    const bRank = groups.includes(bGroup) ? groups.indexOf(bGroup) : fallbackRank
    if (aRank !== bRank) return aRank - bRank
    return String(a.name || '').localeCompare(String(b.name || ''), 'es')
  })
})

const flowSummary = computed(() => {
  const summary = new Map()
  for (const job of orderedJobs.value) {
    const group = String(job.flow_group || 'Sin grupo')
    const current = summary.get(group) || { group, total: 0, ready: 0, missing: 0 }
    current.total += 1
    if ((job.dependency_status || 'none') === 'ready') current.ready += 1
    if ((job.dependency_status || 'none') === 'missing') current.missing += 1
    summary.set(group, current)
  }
  return [...summary.values()]
})

const recommendedJobs = computed(() => {
  return orderedJobs.value
    .filter((job) => {
      const depStatus = String(job.dependency_status || 'none')
      const lastStatus = String(job.last_status || '')
      if (depStatus !== 'ready') return false
      if (lastStatus === 'running' || lastStatus === 'queued') return false
      return true
    })
    .slice(0, 8)
})

const filteredJobs = computed(() => {
  let data = orderedJobs.value
  if (statusFilter.value) {
    if (statusFilter.value === 'dependency_ready') {
      data = data.filter((job) => (job.dependency_status || 'none') === 'ready')
    } else if (statusFilter.value === 'dependency_missing') {
      data = data.filter((job) => (job.dependency_status || 'none') === 'missing')
    } else {
      data = data.filter((job) => (job.last_status || '') === statusFilter.value)
    }
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
const flowEdges = ref([])

const PARAM_DEFINITIONS = {
  curve_paths: { label: 'Rutas de curvas Tika', type: 'text', placeholder: 'Una ruta por línea', multiline: true },
  curve_years: { label: 'Años de curvas', type: 'text', placeholder: 'Ej: 2026, 2027' },
  modelos_tika: { label: 'Modelos Tika (separados por coma)', type: 'text', placeholder: 'Ej: 161, 328, 485' },
  muestras: { label: 'Número de muestras/lonas', type: 'number', placeholder: 'Defecto: 5' },
  tallos_min: { label: 'Tallos mínimos', type: 'number', placeholder: 'Defecto: 1000' },
  lonas_semana: { label: 'Capacidad de lonas por semana', type: 'number', placeholder: 'Defecto: 65' },
  modelo_tika: { label: 'Modelo Tika', type: 'number', placeholder: 'Ej: 485' },
  semana_actual: { label: 'Semana actual (YYWW)', type: 'number', placeholder: 'Ej: 2613' },
  semana_inicio: { label: 'Semana inicio (YYWW)', type: 'number', placeholder: 'Ej: 2527' },
  semana_fin: { label: 'Semana fin (YYWW)', type: 'number', placeholder: 'Ej: 2620' },
  fecha_inicio_incremental: { label: 'Fecha inicio incremental', type: 'date', placeholder: 'Ej: 2025-12-29' },
  fecha_inicio_exportacion: { label: 'Fecha inicio exportacion', type: 'date', placeholder: 'Ej: 2025-12-29' },
}

function formatArrayValue(key, value) {
  if (!Array.isArray(value)) return value ?? ''
  if (key.endsWith('_paths')) return value.join('\n')
  return value.join(', ')
}

function parseArrayValue(key, rawValue, defaultValue) {
  const text = String(rawValue ?? '').trim()
  if (!text) return []

  const sample = Array.isArray(defaultValue) && defaultValue.length ? defaultValue[0] : ''
  const tokens = key.endsWith('_paths')
    ? text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split(/\n|;/)
    : text.split(',')

  const cleaned = tokens.map((value) => value.trim()).filter(Boolean)
  if (typeof sample === 'number') {
    return cleaned.map((value) => parseInt(value, 10)).filter((value) => !Number.isNaN(value))
  }
  return cleaned
}

function getStatus(status) {
  return statusMeta(status || '')
}

function dependencyBadgeClass(job) {
  const status = job?.dependency_status || 'none'
  if (status === 'ready') return 'text-bg-success'
  if (status === 'missing') return 'text-bg-warning'
  return 'text-bg-secondary'
}

function dependencyLabel(job) {
  const total = Number(job?.dependencies_total || 0)
  const ready = Number(job?.dependencies_ready || 0)
  if (!total) return 'Sin previos'
  return `${ready}/${total} previos listos`
}

function dependencyTooltip(job) {
  const missing = job?.missing_dependencies || []
  if (!missing.length) return ''
  return missing.map((dep) => `${dep.job_id} (${dep.last_status || 'sin ejecucion'})`).join(', ')
}

const filteredFlowEdges = computed(() => {
  const q = search.value.trim().toLowerCase()
  return [...flowEdges.value]
    .filter((edge) => {
      if (!q) return true
      const text = [edge.from, edge.to, edge.from_name, edge.to_name]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return text.includes(q)
    })
    .sort((a, b) => {
      const groupCmp = String(a.flow_group || '').localeCompare(String(b.flow_group || ''), 'es')
      if (groupCmp !== 0) return groupCmp
      return String(a.to_name || '').localeCompare(String(b.to_name || ''), 'es')
    })
})

async function loadFlow() {
  try {
    const { data } = await axios.get('/api/etl/flow')
    flowEdges.value = data?.edges || []
  } catch {
    flowEdges.value = []
  }
}

onMounted(() => {
  loadFlow()
})

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
      combined[key] = formatArrayValue(key, value)
    }
    modalParams.value = combined
  } catch {
    const defaults = job.default_params || {}
    for (const key of Object.keys(defaults)) {
      const value = defaults[key]
      modalParams.value[key] = formatArrayValue(key, value)
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
        params[key] = parseArrayValue(key, value, defaultVal)
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
    loadFlow()
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

    <div class="card border-0 shadow-sm mb-4">
      <div class="card-header bg-light border-bottom d-flex justify-content-between align-items-center">
        <strong>Mapa de flujo ETL</strong>
        <span class="text-muted small">Secuencia sugerida por etapa</span>
      </div>
      <div class="card-body">
        <div class="row g-3">
          <div class="col-12 col-md-6 col-xl-3" v-for="stage in flowSummary" :key="stage.group">
            <div class="border rounded-3 p-3 h-100 bg-white">
              <div class="d-flex justify-content-between align-items-center mb-2">
                <strong class="small">{{ stage.group }}</strong>
                <span class="badge text-bg-secondary">{{ stage.total }}</span>
              </div>
              <div class="small text-muted">Previos listos: {{ stage.ready }}</div>
              <div class="small text-muted">Pendientes: {{ stage.missing }}</div>
            </div>
          </div>
        </div>
        <div class="d-flex gap-2 flex-wrap mt-3 small">
          <span class="badge text-bg-success">Previos listos</span>
          <span class="badge text-bg-warning">Faltan previos</span>
          <span class="badge text-bg-secondary">Sin previos</span>
        </div>
      </div>
    </div>

    <div class="card border-0 shadow-sm mb-4">
      <div class="card-header bg-light border-bottom d-flex justify-content-between align-items-center">
        <strong>Siguientes recomendados</strong>
        <span class="text-muted small">Listos para ejecutar ahora</span>
      </div>
      <div class="card-body">
        <div v-if="!recommendedJobs.length" class="text-muted small">
          No hay jobs recomendados en este momento. Revisa si hay dependencias pendientes o jobs ejecutándose.
        </div>
        <div v-else class="d-flex flex-wrap gap-2">
          <button
            v-for="job in recommendedJobs"
            :key="`rec-${job.job_id}`"
            class="btn btn-sm btn-outline-primary"
            :disabled="isActive(job)"
            @click="openModal(job)"
          >
            <i class="fas fa-play me-1"></i>{{ job.name }}
          </button>
        </div>
      </div>
    </div>

    <div class="card border-0 shadow-sm mb-4">
      <div class="card-header bg-light border-bottom d-flex justify-content-between align-items-center">
        <strong>Relaciones de dependencia</strong>
        <span class="text-muted small">Origen -> destino</span>
      </div>
      <div class="card-body p-0">
        <div v-if="!filteredFlowEdges.length" class="text-muted small px-3 py-3">
          No hay relaciones de dependencia para mostrar con el filtro actual.
        </div>
        <div v-else class="table-responsive">
          <table class="table table-sm table-hover mb-0">
            <thead class="table-light">
              <tr>
                <th>Etapa</th>
                <th>Previa</th>
                <th>Depende de</th>
                <th>Estado previa</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="edge in filteredFlowEdges" :key="`${edge.from}->${edge.to}`">
                <td class="small text-muted">{{ edge.flow_group || 'Sin grupo' }}</td>
                <td>
                  <div><strong>{{ edge.to_name }}</strong></div>
                  <div class="small text-muted">{{ edge.to }}</div>
                </td>
                <td>
                  <div>{{ edge.from_name }}</div>
                  <div class="small text-muted">{{ edge.from }}</div>
                </td>
                <td>
                  <span class="badge" :class="edge.ready ? 'text-bg-success' : 'text-bg-warning'">
                    {{ edge.ready ? 'lista' : (edge.from_last_status || 'sin ejecucion') }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
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
          <option value="dependency_ready">previos listos</option>
          <option value="dependency_missing">faltan previos</option>
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
                <th>Previos</th>
                <th class="text-end">Acción</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredJobs.length">
                <td colspan="6" class="text-center text-muted py-3">Sin resultados</td>
              </tr>
              <tr v-for="job in filteredJobs" :key="job.job_id">
                <td>
                  <code>{{ job.job_id }}</code><br>
                  <strong>{{ job.name }}</strong>
                  <div class="small text-muted mt-1">{{ job.flow_group || 'Sin grupo' }}</div>
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
                <td>
                  <span
                    class="badge"
                    :class="dependencyBadgeClass(job)"
                    :title="dependencyTooltip(job)"
                  >
                    {{ dependencyLabel(job) }}
                  </span>
                  <div v-if="job.dependency_note" class="small text-muted mt-1">{{ job.dependency_note }}</div>
                </td>
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

          <div
            v-if="(modalJob?.missing_dependencies || []).length"
            class="alert alert-warning py-2 small"
          >
            Faltan jobs previos: {{ modalJob.missing_dependencies.map((dep) => dep.job_id).join(', ') }}.
            Puedes ejecutar de todas formas, pero el resultado puede ser incompleto o fallar.
          </div>

          <div v-if="modalJob && Object.keys(modalJob.default_params || {}).length === 0" class="text-muted small">
            Este job no requiere parámetros.
          </div>

          <div v-for="(defVal, key) in modalJob?.default_params" :key="key" class="mb-3">
            <label class="form-label">{{ PARAM_DEFINITIONS[key]?.label || key.replace(/_/g, ' ') }}</label>
            <textarea
              v-if="PARAM_DEFINITIONS[key]?.multiline"
              v-model="modalParams[key]"
              :placeholder="PARAM_DEFINITIONS[key]?.placeholder || ''"
              class="form-control"
              rows="3"
              autocomplete="off"
            ></textarea>
            <input
              v-else
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

