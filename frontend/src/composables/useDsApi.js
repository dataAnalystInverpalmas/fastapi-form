import { ref, inject } from 'vue'
import axios from 'axios'

// Carga de un endpoint /api/ds/* con estado de carga y error.
export function useDsApi(path) {
  const toast = inject('toast', () => {})
  const data = ref(null)
  const loading = ref(false)
  const error = ref('')

  async function load(params = {}) {
    loading.value = true
    error.value = ''
    try {
      const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined))
      const res = await axios.get(`/api/ds/${path}`, { params: clean })
      data.value = res.data
    } catch (err) {
      error.value = err.response?.data?.detail || err.message
      toast(`No se pudo calcular: ${error.value}`, 'danger')
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, load }
}

export const FLORES = [
  { value: 'CLA', label: 'Clavel' },
  { value: 'CM0', label: 'Mini clavel' },
  { value: 'ROC', label: 'Rosa (cultivo)' },
  { value: 'ROS', label: 'Rosa' },
]

export const fmtInt = (v) => (Number.isFinite(v) ? Math.round(v).toLocaleString('es-CO') : '—')
export const fmtPct = (v, d = 1) => (Number.isFinite(v) ? `${(v * 100).toFixed(d)}%` : '—')
export const fmtSignedPct = (v, d = 1) => (Number.isFinite(v) ? `${v > 0 ? '+' : ''}${(v * 100).toFixed(d)}%` : '—')
export const fmtCompact = (v) => {
  if (!Number.isFinite(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)} M`
  if (a >= 1e3) return `${(v / 1e3).toFixed(0)} k`
  return Math.round(v).toString()
}
// sem_prod viene como AASS (ej. 2612 -> "26-12")
export const fmtYyww = (v) => {
  const s = String(Math.round(v)).padStart(4, '0')
  return `${s.slice(0, 2)}-${s.slice(2)}`
}
export const fmtDate = (iso) => (iso ? iso.slice(2, 10) : '')
