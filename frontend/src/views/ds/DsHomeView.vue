<script setup>
import { computed, onMounted } from 'vue'
import { useDsApi } from '@/composables/useDsApi'

const { data, loading, error, load } = useDsApi('proyectos')
onMounted(() => load())

const proyectos = computed(() => data.value?.proyectos || [])
const prototipos = computed(() => proyectos.value.filter((p) => p.estado === 'prototipo'))
const ideas = computed(() => proyectos.value.filter((p) => p.estado !== 'prototipo'))

const nivelClass = {
  Inicial: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  Intermedio: 'border-sky-200 bg-sky-50 text-sky-700',
  Avanzado: 'border-violet-200 bg-violet-50 text-violet-700',
}

const pasos = [
  { t: 'Empieza por la pregunta', d: 'Cada proyecto parte de una decisión concreta del negocio, no de una técnica.' },
  { t: 'Mide contra una línea base', d: 'Un modelo solo vale si le gana a la regla simple que ya se usa (p. ej. “igual que el año pasado”).' },
  { t: 'Valida en el tiempo', d: 'Entrena con el pasado y evalúa en el futuro, como se usará en la práctica.' },
  { t: 'Itera con los usuarios', d: 'Muestra el prototipo a producción/calidad, valida que las alertas tengan sentido y ajusta.' },
]
</script>

<template>
  <div class="space-y-6">
    <div class="card">
      <div class="card-body">
        <h2 class="mb-1 text-lg font-semibold text-slate-900"><i class="fas fa-flask mr-2 text-emerald-500"></i>Laboratorio de ciencia de datos</h2>
        <p class="mb-4 text-sm text-slate-600">
          Proyectos sugeridos a partir de una revisión de la base <code>informes</code>: 10 años de cortes en <code>ld_lonas</code> (3,4 M registros),
          clasificación por grado desde 2021, proyecciones vs. real, historia de fusarium por lote y pruebas de florero.
          Los marcados como <b>prototipo</b> ya funcionan sobre los datos reales; los demás son el siguiente paso sugerido.
        </p>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div v-for="(p, i) in pasos" :key="p.t" class="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div class="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-700">Paso {{ i + 1 }}</div>
            <div class="text-sm font-medium text-slate-800">{{ p.t }}</div>
            <div class="mt-1 text-xs text-slate-500">{{ p.d }}</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-if="loading" class="text-sm text-slate-500"><i class="fas fa-spinner fa-spin mr-1"></i>Cargando…</div>

    <section v-if="prototipos.length">
      <h3 class="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Prototipos disponibles</h3>
      <div class="grid gap-4 md:grid-cols-2">
        <RouterLink v-for="p in prototipos" :key="p.id" :to="p.ruta" class="card action-card block no-underline">
          <div class="card-body">
            <div class="mb-2 flex items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600"><i :class="p.icono"></i></span>
                <h4 class="m-0 text-base font-semibold text-slate-900">{{ p.titulo }}</h4>
              </div>
              <span class="badge" :class="nivelClass[p.nivel]">{{ p.nivel }}</span>
            </div>
            <p class="mb-2 text-sm text-slate-700">{{ p.pregunta }}</p>
            <p class="mb-3 text-xs text-slate-500"><b>Técnica:</b> {{ p.tecnica }}</p>
            <div class="flex flex-wrap gap-1.5">
              <code v-for="t in p.tablas" :key="t" class="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{{ t }}</code>
            </div>
            <div class="mt-3 text-sm font-medium text-emerald-700">Abrir prototipo <i class="fas fa-arrow-right ml-1"></i></div>
          </div>
        </RouterLink>
      </div>
    </section>

    <section v-if="ideas.length">
      <h3 class="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Siguientes proyectos sugeridos</h3>
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <div v-for="p in ideas" :key="p.id" class="card">
          <div class="card-body">
            <div class="mb-2 flex items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-500"><i :class="p.icono"></i></span>
                <h4 class="m-0 text-sm font-semibold text-slate-900">{{ p.titulo }}</h4>
              </div>
              <span class="badge" :class="nivelClass[p.nivel]">{{ p.nivel }}</span>
            </div>
            <p class="mb-2 text-sm text-slate-700">{{ p.pregunta }}</p>
            <p class="mb-1 text-xs text-slate-500"><b>Técnica:</b> {{ p.tecnica }}</p>
            <p class="mb-3 text-xs text-slate-500"><b>Valor:</b> {{ p.valor }}</p>
            <div class="flex flex-wrap gap-1.5">
              <code v-for="t in p.tablas" :key="t" class="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{{ t }}</code>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
