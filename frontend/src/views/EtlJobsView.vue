<script setup>
import { ref, computed, inject } from 'vue'
import axios from 'axios'
import { useEtlPolling, statusMeta, formatDate } from '@/composables/useEtlPolling'

const toast = inject('toast', () => {})

const jobs = ref([])
const search = ref('')
const statusFilter = ref('')
const showAllDuringFlow = ref(false)

const { kpis, countdown, pollError, pollNow } = useEtlPolling({
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

const filteredJobs = computed(() => {
  let data = orderedJobs.value
  if (activeFlow.value?.status === 'running' && !showAllDuringFlow.value) {
    const flowIds = new Set(activeFlow.value.steps.map((step) => step.job_id))
    data = data.filter((job) => flowIds.has(job.job_id))
  }
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
  enviar_email: { label: 'Enviar por correo el reporte de cumplimiento', type: 'checkbox' },
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

// ── Flujos de trabajo (secuencias controladas de jobs) ─────────────────────
// Cada flujo se ejecuta job por job, esperando a que cada uno termine
// exitosamente antes de lanzar el siguiente. Mas flujos se agregaran aqui.
const WORK_FLOWS = [
  {
    id: 'flujo_produccion',
    label: 'Ejecutar flujo para producción',
    // quipus_vs_proy NO va aqui: necesita que antes se descargue a mano la
    // consulta de Curvas Khipus de Tika (tika-quipus<AASS>.csv), asi que sin
    // ese archivo fallaba y frenaba el resto del flujo. Vive en el modulo
    // Proyecciones (paso 1), que es donde se corre con sus pasos manuales.
    // Ojo: compare_tika_produccion_despachos y comparar_picos_demanda lo
    // declaran como dependencia, asi que usan el ultimo resultado disponible.
    steps: ['proyecciones_csv', 'produccion_picos', 'compare_tika_produccion_despachos', 'comparar_picos_demanda'],
  },
  {
    id: 'flujo_informes',
    label: 'Ejecutar Flujo Informes',
    // producto_procesado_csv va primero porque los demas dependen de sus
    // datos actualizados. Entre los tres restantes el orden no importa
    // (no dependen entre si); se ejecutan uno a la vez igual que cualquier
    // otro flujo.
    steps: ['producto_procesado_csv', 'dirigidas_analyzer', 'aportes_grados_pipeline', 'aportes_ponderados_problemas'],
  },
  {
    id: 'flujo_siembras',
    label: 'Ejecutar flujo para siembras',
    steps: ['load_process_siembras', 'load_siembras_teo_real'],
  },
  {
    id: 'flujo_curvas_clavel',
    label: 'Preparar curvas clavel',
    steps: ['tabla_curvas_clavel', 'resumir_curvas_usadas'],
  },
]

const activeFlow = ref(null)

function jobLabel(jobId) {
  return jobs.value.find((j) => j.job_id === jobId)?.name || jobId
}

// ── Accesos directos a jobs individuales ────────────────────────────────────
// Agregar aqui nuevos job_id para exponerlos como boton directo en la seccion.
const QUICK_JOBS = [
  { job_id: 'pedidos_surtidos', label: 'Pedidos Surtidos (Despachos)' },
  { job_id: 'quipus_vs_proy', label: 'Quipus vs Proyecciones' },
  { job_id: 'anomalias_lonas', label: 'Anomalías en Lonas' },
]

function findJob(jobId) {
  return jobs.value.find((j) => j.job_id === jobId) || null
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

const TERMINAL_STATUSES = new Set(['success', 'failed', 'cancelado'])

async function waitForRunCompletion(runId) {
  const POLL_MS = 3000
  const MAX_WAIT_MS = 60 * 60 * 1000 // tope de seguridad: 60 minutos
  const start = Date.now()
  while (Date.now() - start < MAX_WAIT_MS) {
    await delay(POLL_MS)
    try {
      const { data } = await axios.get('/api/etl/runs')
      const run = data.find((r) => r.run_id === runId)
      if (run && TERMINAL_STATUSES.has(run.status)) return run
    } catch {
      // Error transitorio de red: se reintenta en el siguiente ciclo.
    }
  }
  return { status: 'failed', error_message: 'Tiempo de espera agotado esperando la finalización del job.' }
}

async function runFlow(flow) {
  if (activeFlow.value?.status === 'running') return

  activeFlow.value = {
    id: flow.id,
    label: flow.label,
    steps: flow.steps.map((jobId) => ({ job_id: jobId, status: 'pending', run_id: null, error: null })),
    status: 'running',
  }
  showAllDuringFlow.value = false
  toast(`Iniciando flujo "${flow.label}"...`, 'info')

  for (const step of activeFlow.value.steps) {
    step.status = 'running'
    try {
      const { data } = await axios.post(`/api/etl/jobs/${step.job_id}/run`, { params: {} })
      step.run_id = data.run_id
      pollNow()
      const run = await waitForRunCompletion(data.run_id)
      if (run.status !== 'success') {
        step.status = run.status === 'cancelado' ? 'cancelado' : 'failed'
        step.error = run.error_message || 'El job no finalizó correctamente.'
        activeFlow.value.status = 'failed'
        toast(`Flujo detenido: ${jobLabel(step.job_id)} terminó en estado "${step.status}".`, 'danger')
        pollNow()
        return
      }
      step.status = 'success'
    } catch (err) {
      step.status = 'failed'
      step.error = err.response?.data?.detail || err.message || 'Error al encolar el job.'
      activeFlow.value.status = 'failed'
      toast(`Flujo detenido: no se pudo ejecutar ${jobLabel(step.job_id)}.`, 'danger')
      return
    }
  }

  activeFlow.value.status = 'success'
  toast(`Flujo "${flow.label}" completado con éxito.`, 'success')
  pollNow()
}

function flowStatusMeta(status) {
  if (status === 'running') return { tone: 'text-bg-primary', label: 'En ejecución', icon: 'fas fa-rotate' }
  if (status === 'success') return { tone: 'text-bg-success', label: 'Completado', icon: 'fas fa-circle-check' }
  if (status === 'failed') return { tone: 'text-bg-danger', label: 'Detenido con error', icon: 'fas fa-circle-xmark' }
  return { tone: 'text-bg-secondary', label: status, icon: 'fas fa-minus' }
}

function stepStatusMeta(status) {
  if (status === 'pending') return { tone: 'text-bg-secondary', label: 'pendiente', icon: 'fas fa-clock' }
  if (status === 'running') return { tone: 'text-bg-primary', label: 'ejecutando', icon: 'fas fa-rotate' }
  if (status === 'success') return { tone: 'text-bg-success', label: 'listo', icon: 'fas fa-check' }
  if (status === 'cancelado') return { tone: 'text-bg-dark', label: 'cancelado', icon: 'fas fa-ban' }
  return { tone: 'text-bg-danger', label: 'falló', icon: 'fas fa-xmark' }
}

async function openModal(job) {
  modalJob.value = job
  modalParams.value = {}
  try {
    const { data } = await axios.get(`/api/etl/jobs/${job.job_id}/last-params`)
    const last = data.params || {}
    const defaults = job.default_params || {}
    const fresh = data.fresh_date_defaults || {}
    const combined = {}
    for (const key of Object.keys(defaults)) {
      const value = fresh[key] ?? last[key] ?? defaults[key]
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

function datesInOrder(params) {
  if (!params?.fecha_inicio || !params?.fecha_fin) return true
  return new Date(params.fecha_inicio) <= new Date(params.fecha_fin)
}

async function confirmRun() {
  const job = modalJob.value
  if (!job) return
  const payload = buildPayload(job)
  if (!datesInOrder(payload.params)) {
    toast('La fecha de inicio no puede ser mayor que la fecha fin.', 'danger')
    return
  }
  showModal.value = false
  await runJob(job.job_id, payload)
}

function buildPayload(job) {
  const params = {}
  for (const [key, rawVal] of Object.entries(modalParams.value)) {
    const def = PARAM_DEFINITIONS[key]
    if (def?.type === 'checkbox') {
      params[key] = rawVal === true || rawVal === 'true'
      continue
    }
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

    <div class="card border-0 shadow-sm mb-4">
      <div class="card-header bg-light border-bottom d-flex justify-content-between align-items-center">
        <strong>Siguientes recomendados</strong>
        <span class="text-muted small">Flujos de trabajo y jobs listos para ejecutar</span>
      </div>
      <div class="card-body">
        <div class="quick-actions-stack">
          <!-- Flujos de trabajo: secuencias controladas de varios jobs -->
          <div class="quick-actions-group">
            <div class="d-flex flex-wrap gap-2">
              <button
                v-for="flow in WORK_FLOWS"
                :key="flow.id"
                class="btn btn-primary"
                :disabled="activeFlow?.status === 'running'"
                @click="runFlow(flow)"
              >
                <span v-if="activeFlow?.status === 'running' && activeFlow.id === flow.id" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="fas fa-diagram-project me-1"></i>
                {{ activeFlow?.status === 'running' && activeFlow.id === flow.id ? 'Ejecutando flujo…' : flow.label }}
              </button>
            </div>

            <div v-if="activeFlow" class="border rounded-3 p-3 mt-3 bg-white">
              <div class="d-flex justify-content-between align-items-center mb-2">
                <strong class="small">{{ activeFlow.label }}</strong>
                <span class="badge" :class="flowStatusMeta(activeFlow.status).tone">
                  <span v-if="activeFlow.status === 'running'" class="spinner-grow spinner-grow-sm me-1" role="status"></span>
                  <i v-else :class="flowStatusMeta(activeFlow.status).icon" class="me-1"></i>
                  {{ flowStatusMeta(activeFlow.status).label }}
                </span>
              </div>
              <ol class="list-group list-group-numbered small mb-0">
                <li
                  v-for="step in activeFlow.steps"
                  :key="step.job_id"
                  class="list-group-item d-flex justify-content-between align-items-center gap-2"
                >
                  <span>{{ jobLabel(step.job_id) }}</span>
                  <span class="badge" :class="stepStatusMeta(step.status).tone" :title="step.error || ''">
                    <span v-if="step.status === 'running'" class="spinner-grow spinner-grow-sm me-1" role="status"></span>
                    <i v-else :class="stepStatusMeta(step.status).icon" class="me-1"></i>
                    {{ stepStatusMeta(step.status).label }}
                  </span>
                </li>
              </ol>
              <div v-if="activeFlow.status === 'failed'" class="alert alert-danger py-2 small mt-2 mb-0">
                El flujo se detuvo. Revisa el job marcado como "falló" o "cancelado" arriba para más detalle.
              </div>
            </div>
          </div>

          <!-- Jobs individuales: accesos directos a un solo job -->
          <div class="quick-actions-group">
            <div class="text-muted small text-uppercase fw-bold mb-2">Jobs individuales</div>
            <div class="d-flex flex-column gap-2 align-items-start">
              <button
                v-for="quick in QUICK_JOBS"
                :key="quick.job_id"
                class="btn btn-outline-primary quick-job-btn"
                :disabled="!findJob(quick.job_id) || isActive(findJob(quick.job_id))"
                @click="openModal(findJob(quick.job_id))"
              >
                <i class="fas fa-play me-1"></i>{{ quick.label }}
              </button>
            </div>
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

      <div
        v-if="activeFlow?.status === 'running' && !showAllDuringFlow"
        class="px-5 py-2 border-bottom bg-primary-subtle small d-flex justify-content-between align-items-center flex-wrap gap-2"
      >
        <span><i class="fas fa-filter me-1"></i>Mostrando solo los jobs del flujo en ejecución.</span>
        <button class="btn btn-link btn-sm p-0" @click="showAllDuringFlow = true">Ver todos los jobs</button>
      </div>
      <div
        v-else-if="activeFlow?.status === 'running' && showAllDuringFlow"
        class="px-5 py-2 border-bottom bg-light small d-flex justify-content-between align-items-center flex-wrap gap-2"
      >
        <span><i class="fas fa-list me-1"></i>Mostrando todos los jobs mientras el flujo corre.</span>
        <button class="btn btn-link btn-sm p-0" @click="showAllDuringFlow = false">Ver solo el flujo activo</button>
      </div>

      <div class="px-5 py-3 border-bottom border-slate-200 d-flex gap-2 flex-wrap">
        <input v-model="search" class="form-control form-control-sm" placeholder="Buscar job..." style="max-width: 260px">
        <select v-model="statusFilter" class="form-select form-select-sm" style="max-width: 180px">
          <option value="">Todos los estados</option>
          <option value="queued">queued</option>
          <option value="running">running</option>
          <option value="success">success</option>
          <option value="failed">failed</option>
          <option value="cancelado">cancelado</option>
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
                  <div v-if="job.last_error_message" class="small text-danger text-break mt-1" style="max-width: 22rem">
                    {{ job.last_error_message }}
                  </div>
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
            <div v-else-if="PARAM_DEFINITIONS[key]?.type === 'checkbox'" class="form-check">
              <input
                v-model="modalParams[key]"
                type="checkbox"
                class="form-check-input"
                :id="`param-${key}`"
              >
              <label class="form-check-label small" :for="`param-${key}`">Enviar correo al finalizar</label>
            </div>
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

<style scoped>
/* Contenedor extensible para "Siguientes recomendados": cada grupo (flujos,
   jobs individuales, y los que se agreguen despues) va en su propia fila. */
.quick-actions-stack {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.quick-job-btn {
  width: 100%;
  max-width: 360px;
  text-align: left;
}
</style>

