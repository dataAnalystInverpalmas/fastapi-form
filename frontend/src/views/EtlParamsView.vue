<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { statusMeta, formatDate } from '@/composables/useEtlPolling'

const jobs = ref([])
const saving = ref({})
const savedMsg = ref({})

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/etl/params')
    jobs.value = data.map(job => ({
      ...job,
      formParams: Object.fromEntries(
        Object.entries(job.default_params || {}).map(([k, defVal]) => {
          const lastVal = (job.last_params || {})[k]
          const v = lastVal !== undefined ? lastVal : defVal
          return [k, Array.isArray(v) ? v.join(', ') : (v ?? '')]
        })
      ),
    }))
  } catch (err) {
    if (window.$toast) window.$toast('Error al cargar parámetros.', 'danger')
  }
})

async function saveParams(job) {
  saving.value[job.job_id] = true
  savedMsg.value[job.job_id] = null
  try {
    // Convertir valores del form a tipos correctos
    const params = {}
    for (const [k, rawVal] of Object.entries(job.formParams)) {
      const defVal = job.default_params[k]
      const val = String(rawVal).trim()
      if (Array.isArray(defVal)) {
        params[k] = val.split(',').map(v => parseInt(v.trim(), 10)).filter(n => !isNaN(n))
      } else if (typeof defVal === 'number') {
        params[k] = parseFloat(val) || 0
      } else {
        params[k] = val
      }
    }
    await axios.post(`/api/etl/params/${job.job_id}/save`, { params })
    savedMsg.value[job.job_id] = 'Parámetros guardados'
    if (window.$toast) window.$toast(`Parámetros de <strong>${job.name}</strong> guardados.`, 'success')
    setTimeout(() => { savedMsg.value[job.job_id] = null }, 3000)
  } catch (err) {
    const msg = err.response?.data?.detail || 'Error al guardar.'
    if (window.$toast) window.$toast(msg, 'danger')
  } finally {
    saving.value[job.job_id] = false
  }
}

function inputType(defVal) {
  return typeof defVal === 'number' ? 'number' : 'text'
}

function getStatus(status) {
  return statusMeta(status || '')
}
</script>

<template>
  <section class="mt-4">
    <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
      <h4 class="mb-0"><i class="fas fa-sliders me-2"></i>Parámetros de Jobs ETL</h4>
      <RouterLink to="/etl/jobs" class="btn btn-outline-secondary btn-sm">
        <i class="fas fa-gears me-1"></i>Volver a Jobs
      </RouterLink>
    </div>

    <div class="alert alert-light border mb-3 small">
      Edita y guarda parámetros por job. La ejecución se hace manualmente desde Jobs ETL o Cargas DBF.
    </div>

    <div v-if="!jobs.length" class="text-muted text-center py-4">Cargando...</div>

    <div class="row g-3">
      <div class="col-12 col-xl-6" v-for="job in jobs" :key="job.job_id">
        <div class="card border-0 shadow-sm h-100">
          <div class="card-header bg-light d-flex justify-content-between align-items-start">
            <div>
              <strong>{{ job.name }}</strong>
              <div class="text-muted small"><code>{{ job.job_id }}</code></div>
              <div class="text-muted small">{{ job.menu_type === 'load' ? 'Cargas DBF a MySQL' : 'Jobs ETL' }}</div>
            </div>
            <span class="badge" :class="getStatus(job.last_status).tone">
              <span v-if="getStatus(job.last_status).loading" class="spinner-grow spinner-grow-sm me-1" role="status"></span>
              <i v-else :class="getStatus(job.last_status).icon" class="me-1"></i>
              {{ getStatus(job.last_status).label }}
            </span>
          </div>
          <div class="card-body">
            <p class="text-muted small mb-3">{{ job.description }}</p>

            <form @submit.prevent="saveParams(job)" class="row g-3">
              <div class="col-12" v-for="(defVal, key) in job.default_params" :key="key">
                <label class="form-label small mb-1">{{ key.replace(/_/g, ' ') }}</label>
                <input
                  v-model="job.formParams[key]"
                  :type="inputType(defVal)"
                  class="form-control"
                  :placeholder="Array.isArray(defVal) ? 'Separado por coma' : ''"
                  step="1"
                >
                <div class="form-text">Defecto: {{ Array.isArray(defVal) ? defVal.join(', ') : defVal }}</div>
              </div>

              <div class="col-12 d-flex justify-content-between align-items-center">
                <small class="text-muted">Última ejecución: {{ formatDate(job.last_started_at) }}</small>
                <div class="d-flex align-items-center gap-2">
                  <span v-if="savedMsg[job.job_id]" class="text-success small">
                    <i class="fas fa-check me-1"></i>{{ savedMsg[job.job_id] }}
                  </span>
                  <button type="submit" class="btn btn-primary btn-sm" :disabled="saving[job.job_id]">
                    <span v-if="saving[job.job_id]" class="spinner-border spinner-border-sm me-1"></span>
                    <i v-else class="fas fa-floppy-disk me-1"></i>
                    Guardar
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
