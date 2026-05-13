<script setup>
import { useFileDownload } from '@/composables/useFileDownload'
import { ref } from 'vue'

const { downloading: dl1, error: err1, download: dl_cortes } = useFileDownload()
const { downloading: dl2, error: err2, download: dl_aportes } = useFileDownload()

const cortesInicio = ref('')
const cortesFin = ref('')
async function exportarCortes() {
  if (!cortesInicio.value || !cortesFin.value) return
  await dl_cortes('/api/consultas/exporta-cortes', {
    fecha_inicio: cortesInicio.value,
    fecha_fin: cortesFin.value,
  }, 'cortes_lonas.xlsx')
}

const aportesInicio = ref('2025-12-29')
const aportesFin = ref('')
async function exportarAportes() {
  if (!aportesInicio.value || !aportesFin.value) return
  await dl_aportes('/api/consultas/aportes-ponderados', {
    fecha_inicio: aportesInicio.value,
    fecha_fin: aportesFin.value,
  }, 'aportes_ponderados.xlsx')
}
</script>

<template>
  <section class="mt-6">
    <div class="flex items-center justify-between flex-wrap gap-3 mb-5">
      <h4 class="m-0 text-lg font-semibold text-slate-800">
        <i class="fas fa-magnifying-glass-chart mr-2"></i>Procesos de Consulta
      </h4>
      <RouterLink to="/dashboard" class="btn btn-outline-secondary btn-sm">
        <i class="fas fa-house mr-1"></i>Volver al Dashboard
      </RouterLink>
    </div>

    <div class="alert alert-light mb-5 text-xs">
      Ejecuta consultas parametrizadas y descarga el resultado en Excel.
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-5">

      <!-- Exportar cortes de lonas -->
      <div class="card h-full">
        <div class="card-header flex-col items-start gap-1">
          <strong class="text-slate-800">Exportar Cortes de Lonas</strong>
          <div class="text-slate-500 text-xs mt-0.5">
            <code class="bg-slate-100 px-1.5 py-0.5 rounded text-xs">exporta_cortes_lonas</code>
          </div>
        </div>
        <div class="card-body">
          <p class="text-slate-500 text-xs mb-4">Genera un Excel con el reporte de cortes de lonas para el rango de fechas indicado.</p>
          <div v-if="err1" class="alert alert-danger mb-3 text-xs">
            <i class="fas fa-exclamation-circle mr-1"></i>{{ err1 }}
          </div>
          <form @submit.prevent="exportarCortes" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="form-label text-xs">Fecha inicio</label>
              <input v-model="cortesInicio" type="date" class="form-control" required>
            </div>
            <div>
              <label class="form-label text-xs">Fecha fin</label>
              <input v-model="cortesFin" type="date" class="form-control" required>
            </div>
            <div class="sm:col-span-2 flex justify-end">
              <button type="submit" class="btn btn-primary btn-sm" :disabled="dl1">
                <span v-if="dl1" class="spinner-border spinner-border-sm"></span>
                <i v-else class="fas fa-file-excel"></i>
                {{ dl1 ? 'Generando…' : 'Generar y Descargar' }}
              </button>
            </div>
          </form>
        </div>
      </div>

      <!-- Aportes ponderados con problemas -->
      <div class="card h-full">
        <div class="card-header flex-col items-start gap-1">
          <strong class="text-slate-800">Aportes Ponderados con Problemas</strong>
          <div class="text-slate-500 text-xs mt-0.5">
            <code class="bg-slate-100 px-1.5 py-0.5 rounded text-xs">aportes_ponderados_problemas</code>
          </div>
        </div>
        <div class="card-body">
          <p class="text-slate-500 text-xs mb-4">Genera un Excel con los aportes ponderados que presentan problemas en el rango indicado.</p>
          <div v-if="err2" class="alert alert-danger mb-3 text-xs">
            <i class="fas fa-exclamation-circle mr-1"></i>{{ err2 }}
          </div>
          <form @submit.prevent="exportarAportes" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="form-label text-xs">Fecha inicio</label>
              <input v-model="aportesInicio" type="date" class="form-control" required>
            </div>
            <div>
              <label class="form-label text-xs">Fecha fin</label>
              <input v-model="aportesFin" type="date" class="form-control" required>
            </div>
            <div class="sm:col-span-2 flex justify-end">
              <button type="submit" class="btn btn-primary btn-sm" :disabled="dl2">
                <span v-if="dl2" class="spinner-border spinner-border-sm"></span>
                <i v-else class="fas fa-file-excel"></i>
                {{ dl2 ? 'Generando…' : 'Generar y Descargar' }}
              </button>
            </div>
          </form>
        </div>
      </div>

    </div>
  </section>
</template>
