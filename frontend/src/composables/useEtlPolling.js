/**
 * useEtlPolling — polling inteligente de KPIs y estado de jobs ETL.
 * Migrado desde static/js/etl-polling.js
 */
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const FAST_MS = 4000
const IDLE_MS = 20_000

const STATUS_META = {
  success: { tone: 'bg-success', icon: 'fas fa-check', label: 'success', loading: false },
  failed: { tone: 'bg-danger', icon: 'fas fa-xmark', label: 'failed', loading: false },
  running: { tone: 'bg-primary', icon: 'fas fa-rotate', label: 'running', loading: true },
  queued: { tone: 'bg-warning', icon: 'fas fa-clock', label: 'queued', loading: false },
  cancelado: { tone: 'bg-dark', icon: 'fas fa-ban', label: 'cancelado', loading: false },
  '': { tone: 'bg-secondary', icon: 'fas fa-minus', label: 'sin ejecuciones', loading: false },
}

export function statusMeta(status) {
  return STATUS_META[status] ?? STATUS_META['']
}

export function formatDate(iso) {
  if (!iso) return '–'
  try {
    const d = new Date(iso.includes('T') ? iso : iso.replace(' ', 'T'))
    return isNaN(d) ? iso : d.toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })
  } catch { return iso }
}

/**
 * @param {Object} options
 * @param {'etl'|'load'|'tika'|'proyecciones'|'runs'|'dashboard'} options.pageType
 * @param {string} [options.jobsApi]   URL de la API de jobs (para páginas etl/load)
 * @param {Function} [options.onJobsUpdate]  callback(jobs)
 * @param {Function} [options.onRunsUpdate]  callback(runs)
 */
export function useEtlPolling({ pageType, jobsApi, onJobsUpdate, onRunsUpdate } = {}) {
  const kpis = ref({ queued: 0, running: 0, success: 0, failed: 0 })
  const countdown = ref(0)
  const pollError = ref(null)
  let pollTimer = null
  let countdownTimer = null
  let isPolling = false

  function startCountdown(ms) {
    clearInterval(countdownTimer)
    countdown.value = Math.round(ms / 1000)
    countdownTimer = setInterval(() => {
      countdown.value = Math.max(0, countdown.value - 1)
      if (countdown.value === 0) clearInterval(countdownTimer)
    }, 1000)
  }

  function scheduleNext(kpisVal) {
    clearTimeout(pollTimer)
    const interval = (kpisVal.queued > 0 || kpisVal.running > 0) ? FAST_MS : IDLE_MS
    startCountdown(interval)
    pollTimer = setTimeout(poll, interval)
  }

  async function poll() {
    if (isPolling) return
    isPolling = true
    try {
      const [kpisRes, jobsRes, runsRes] = await Promise.all([
        axios.get('/api/etl/kpis'),
        (pageType === 'etl' || pageType === 'load' || pageType === 'tika' || pageType === 'proyecciones') && jobsApi
          ? axios.get(jobsApi)
          : Promise.resolve(null),
        (pageType === 'runs' || pageType === 'dashboard')
          ? axios.get('/api/etl/runs')
          : Promise.resolve(null),
      ])

      kpis.value = kpisRes.data
      if (jobsRes && onJobsUpdate) onJobsUpdate(jobsRes.data)
      if (runsRes && onRunsUpdate) onRunsUpdate(runsRes.data)
      pollError.value = null
      scheduleNext(kpis.value)
    } catch (err) {
      console.warn('[useEtlPolling] poll error:', err)
      pollError.value = err.response?.data?.detail || err.message || 'No se pudo actualizar. Reintentando...'
      // Mantiene los ultimos datos conocidos en pantalla en vez de mostrar ceros.
      scheduleNext(kpis.value)
    } finally {
      isPolling = false
    }
  }

  function pollNow() {
    clearTimeout(pollTimer)
    clearInterval(countdownTimer)
    poll()
  }

  onMounted(() => poll())
  onUnmounted(() => {
    clearTimeout(pollTimer)
    clearInterval(countdownTimer)
  })

  return { kpis, countdown, pollError, poll, pollNow }
}
