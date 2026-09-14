<script setup>
import { ref, reactive, computed, onMounted, inject } from 'vue'
import axios from 'axios'

const toast = inject('toast', () => {})

const loading = ref(true)
const groups = ref({})
const values = ref({})
const defaults = ref({})
const overrides = ref({})
const formValues = reactive({})
const expanded = reactive({})
const saving = reactive({})
const search = ref('')

function fieldKind(value) {
  if (typeof value === 'boolean') return 'boolean'
  if (typeof value === 'number') return 'number'
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) return 'dict'
  if (Array.isArray(value)) return 'list'
  return 'text'
}

function toFormValue(value) {
  const kind = fieldKind(value)
  if (kind === 'boolean') return value ? 'true' : 'false'
  if (kind === 'dict') return JSON.stringify(value, null, 2)
  if (kind === 'list') return value.join(', ')
  return value ?? ''
}

function groupTitle(name) {
  return name
    .replace(/_/g, ' ')
    .split(' ')
    .map((word) => (word ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(' ')
}

function formatDefault(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const filteredGroups = computed(() => {
  const term = search.value.trim().toLowerCase()
  if (!term) return groups.value

  const result = {}
  for (const [group, keys] of Object.entries(groups.value)) {
    const matchingKeys = keys.filter((key) => key.toLowerCase().includes(term))
    if (matchingKeys.length || groupTitle(group).toLowerCase().includes(term)) {
      result[group] = groupTitle(group).toLowerCase().includes(term) ? keys : matchingKeys
    }
  }
  return result
})

async function loadConfig() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/config/values')
    groups.value = data.groups
    values.value = data.values
    defaults.value = data.defaults
    overrides.value = data.overrides

    for (const key of Object.keys(data.values)) {
      formValues[key] = toFormValue(data.values[key])
    }
  } catch (err) {
    toast('Error al cargar la configuración.', 'danger')
  } finally {
    loading.value = false
  }
}

onMounted(loadConfig)

function toggleGroup(group) {
  expanded[group] = !expanded[group]
}

async function saveGroup(group) {
  saving[group] = true
  try {
    const payload = {}
    for (const key of groups.value[group]) {
      payload[key] = formValues[key]
    }
    await axios.post('/api/config/save', payload)
    toast(`Configuración de "${groupTitle(group)}" guardada.`, 'success')
    await loadConfig()
  } catch (err) {
    const msg = err.response?.data?.detail || 'No se pudo guardar la configuración.'
    toast(msg, 'danger')
  } finally {
    saving[group] = false
  }
}

async function resetAll() {
  if (!confirm('¿Restaurar todos los valores de configuración a sus defaults?')) return
  try {
    await axios.post('/api/config/reset')
    toast('Configuración restaurada a valores por defecto.', 'success')
    await loadConfig()
  } catch (err) {
    toast('No se pudo restaurar la configuración.', 'danger')
  }
}
</script>

<template>
  <section class="mt-4">
    <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
      <h4 class="mb-0"><i class="fas fa-gear me-2"></i>Configuración general de la aplicación</h4>
      <button type="button" class="btn border-rose-300 bg-white text-rose-600 hover:bg-rose-50" @click="resetAll">
        <i class="fas fa-rotate-left me-1"></i>Restaurar valores por defecto
      </button>
    </div>

    <div class="alert alert-light border mb-3 small">
      Aquí puedes ajustar los valores globales usados por los jobs ETL (rutas, filtros, umbrales). Los cambios quedan guardados como sobreescritura local, sin necesidad de editar código ni reiniciar la app.
    </div>

    <div class="mb-3">
      <input
        v-model="search"
        type="search"
        class="form-control"
        placeholder="Buscar por nombre de variable o grupo..."
      >
    </div>

    <div v-if="loading" class="text-muted text-center py-4">Cargando...</div>

    <div v-else class="flex flex-col gap-3">
      <div
        v-for="(keys, group) in filteredGroups"
        :key="group"
        v-show="keys.length"
        class="card"
      >
        <button
          type="button"
          class="card-header w-full text-left cursor-pointer"
          @click="toggleGroup(group)"
        >
          <span class="font-semibold">{{ groupTitle(group) }}</span>
          <span class="flex items-center gap-2">
            <span class="badge border-slate-200 bg-slate-100 text-slate-600">{{ keys.length }}</span>
            <i class="fas" :class="expanded[group] ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
          </span>
        </button>

        <div v-show="expanded[group]" class="card-body">
          <form class="row g-3" @submit.prevent="saveGroup(group)">
            <div class="col-12 col-md-6" v-for="key in keys" :key="key">
              <label class="form-label small mb-1" :for="`config-${key}`">{{ key }}</label>

              <select v-if="fieldKind(values[key]) === 'boolean'" :id="`config-${key}`" v-model="formValues[key]" class="form-select">
                <option value="true">true</option>
                <option value="false">false</option>
              </select>

              <input
                v-else-if="fieldKind(values[key]) === 'number'"
                :id="`config-${key}`"
                v-model="formValues[key]"
                type="number"
                step="any"
                class="form-control"
              >

              <textarea
                v-else-if="fieldKind(values[key]) === 'dict'"
                :id="`config-${key}`"
                v-model="formValues[key]"
                class="form-control font-mono text-xs"
                rows="4"
              ></textarea>

              <textarea
                v-else-if="fieldKind(values[key]) === 'list'"
                :id="`config-${key}`"
                v-model="formValues[key]"
                class="form-control"
                rows="2"
              ></textarea>

              <input
                v-else
                :id="`config-${key}`"
                v-model="formValues[key]"
                type="text"
                class="form-control"
              >

              <div class="form-text text-muted">
                <span v-if="fieldKind(values[key]) === 'dict'">JSON (objeto clave/valor). </span>
                <span v-else-if="fieldKind(values[key]) === 'list'">Lista separada por comas. </span>
                Por defecto: {{ formatDefault(defaults[key]) }}
              </div>
              <div v-if="overrides[key] !== undefined" class="form-text text-emerald-700">
                Sobreescritura actual: {{ formatDefault(overrides[key]) }}
              </div>
            </div>

            <div class="col-12 flex justify-end">
              <button type="submit" class="btn btn-primary btn-sm" :disabled="saving[group]">
                <span v-if="saving[group]" class="spinner-border spinner-border-sm me-1"></span>
                <i v-else class="fas fa-floppy-disk me-1"></i>
                Guardar cambios
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </section>
</template>
