<script setup>
import { ref } from 'vue'
import axios from 'axios'

const ruta = ref(String(import.meta.env.VITE_DEFAULT_DBF_PATH || '\\\\svrinverpalmas\\produc\\LD_BCULT\\hijos2026.dbf'))
const limite = ref(100)
const data = ref(null)
const error = ref(null)
const loading = ref(false)

// Búsqueda local en resultados
const search = ref('')
const pageSize = ref(10)
const page = ref(1)

import { computed } from 'vue'

const filteredRecords = computed(() => {
  if (!data.value) return []
  if (!search.value.trim()) return data.value.records
  const q = search.value.toLowerCase()
  return data.value.records.filter(row =>
    Object.values(row).some(v => String(v ?? '').toLowerCase().includes(q))
  )
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRecords.value.length / pageSize.value)))
const paginatedRecords = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredRecords.value.slice(start, start + pageSize.value)
})

function setPage(p) {
  if (p >= 1 && p <= totalPages.value) page.value = p
}

async function consultar() {
  if (!ruta.value.trim()) return
  loading.value = true
  error.value = null
  data.value = null
  search.value = ''
  page.value = 1
  try {
    const encoded = encodeURIComponent(ruta.value.trim())
    const { data: res } = await axios.get(`/api/dbf/${encoded}?limit=${limite.value}`)
    if (res.error) {
      error.value = res.error
    } else {
      data.value = res
    }
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || 'Error al consultar el archivo.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="mt-6">
    <!-- Formulario -->
    <div class="card mb-6">
      <div class="card-header">
        <h5 class="text-base font-semibold text-slate-800 m-0">
          <i class="fas fa-search mr-2"></i>Parámetros de consulta
        </h5>
      </div>
      <div class="card-body">
        <form @submit.prevent="consultar">
          <div class="grid grid-cols-12 gap-4">
            <div class="col-span-12 md:col-span-9">
              <label for="ruta_archivo" class="form-label font-semibold">Ruta del archivo DBF:</label>
              <input
                id="ruta_archivo"
                v-model="ruta"
                type="text"
                class="form-control form-control-lg"
                placeholder="Ej: \\svrinverpalmas\produc\LD_BCULT\archivo.dbf"
                required
              >
              <small class="block text-slate-500 text-xs mt-1.5">
                <i class="fas fa-lightbulb mr-1"></i>Para rutas de red, use doble backslash: \\servidor\carpeta\archivo.dbf
              </small>
            </div>
            <div class="col-span-12 md:col-span-3">
              <label for="limite" class="form-label font-semibold">Límite de registros:</label>
              <input id="limite" v-model.number="limite" type="number" class="form-control form-control-lg" min="1" max="10000">
            </div>
          </div>
          <div class="flex justify-end mt-5">
            <button type="submit" class="btn btn-primary btn-lg" :disabled="loading">
              <span v-if="loading" class="spinner-border spinner-border-sm"></span>
              <i v-else class="fas fa-magnifying-glass"></i>
              {{ loading ? 'Consultando…' : 'Consultar' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="alert alert-danger mb-4 flex items-start justify-between gap-3" role="alert">
      <span><i class="fas fa-exclamation-circle mr-2"></i><strong>Error:</strong> {{ error }}</span>
      <button class="text-rose-500 hover:text-rose-700 shrink-0" @click="error = null">
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- Resultados -->
    <div v-if="data" class="card">
      <div class="card-header flex-wrap gap-2">
        <h5 class="text-base font-semibold text-slate-800 m-0">
          <i class="fas fa-table mr-2"></i>Resultados
        </h5>
        <div class="flex items-center gap-2 flex-wrap">
          <span class="badge bg-info"><i class="fas fa-database mr-1"></i>Total: {{ data.total_records }}</span>
          <span class="badge bg-success"><i class="fas fa-eye mr-1"></i>Mostrados: {{ data.displayed_records }}</span>
          <input v-model="search" class="form-control form-control-sm w-40" placeholder="Buscar..." @input="page=1">
          <select v-model="pageSize" class="form-select form-select-sm w-20" @change="page=1">
            <option :value="10">10</option>
            <option :value="25">25</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </div>
      </div>
      <div>
        <div class="table-responsive">
          <table class="table" style="font-size:.85rem">
            <thead>
              <tr>
                <th v-for="field in data.fields" :key="field">
                  <i class="fas fa-chevron-right text-slate-400 mr-1"></i>{{ field }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!paginatedRecords.length">
                <td :colspan="data.fields.length" class="text-center text-slate-500 py-6">Sin resultados</td>
              </tr>
              <tr v-for="(row, i) in paginatedRecords" :key="i">
                <td v-for="field in data.fields" :key="field">{{ row[field] ?? '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Paginación -->
        <div class="flex items-center justify-between px-5 py-3 border-t border-slate-100">
          <small class="text-slate-500 text-xs">
            {{ filteredRecords.length }} fila{{ filteredRecords.length !== 1 ? 's' : '' }}
            — página {{ page }} / {{ totalPages }}
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
  </section>
</template>
