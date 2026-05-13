<script setup>
import { ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'

const route = useRoute()
const sidebarOpen = ref(false)

function closeSidebar() { sidebarOpen.value = false }

// Cierra sidebar al navegar en móvil
watch(() => route.path, closeSidebar)

// Toasts
const toasts = ref([])
function showToast(message, type = 'info') {
  const id = Date.now()
  toasts.value.push({ id, message, type })
  setTimeout(() => { toasts.value = toasts.value.filter(t => t.id !== id) }, 5000)
}
// Exponer globalmente para uso desde composables
window.$toast = showToast

const navItems = [
  { section: 'General' },
  { path: '/dashboard',           icon: 'fas fa-chart-line',              label: 'Dashboard' },
  { section: 'Datos' },
  { path: '/consultar',           icon: 'fas fa-search',                  label: 'Consultar DBF' },
  { path: '/reporte-dinamico',    icon: 'fas fa-table-columns',           label: 'Reporte Dinámico' },
  { section: 'ETL' },
  { path: '/etl/jobs',            icon: 'fas fa-gears',                   label: 'Jobs ETL' },
  { path: '/load/jobs',           icon: 'fas fa-upload',                  label: 'Cargas DBF' },
  { path: '/etl/params',          icon: 'fas fa-sliders',                 label: 'Parámetros' },
  { path: '/etl/runs',            icon: 'fas fa-clock-rotate-left',       label: 'Historial' },
  { section: 'Consultas' },
  { path: '/consultas/procesos',  icon: 'fas fa-magnifying-glass-chart',  label: 'Procesos' },
]

const bgClass = { success: 'text-bg-success', danger: 'text-bg-danger', warning: 'text-bg-warning', info: 'text-bg-info', primary: 'text-bg-primary' }
const iconClass = { success: 'fa-circle-check', danger: 'fa-circle-xmark', warning: 'fa-triangle-exclamation', info: 'fa-circle-info', primary: 'fa-circle-info' }
</script>

<template>
  <div class="app-wrapper">
    <!-- Sidebar -->
    <aside class="sidebar" id="sidebar" :class="{ 'sidebar-open': sidebarOpen }">
      <div class="sidebar-header">
        <RouterLink to="/dashboard" class="sidebar-brand">
          <i class="fas fa-leaf"></i>
          <span>Inverpalmas</span>
        </RouterLink>
      </div>
      <nav class="sidebar-nav">
        <template v-for="item in navItems" :key="item.section || item.path">
          <div v-if="item.section" class="nav-section-title">{{ item.section }}</div>
          <RouterLink
            v-else
            :to="item.path"
            class="nav-item"
            :class="{ active: route.path === item.path || (item.path !== '/dashboard' && route.path.startsWith(item.path)) }"
          >
            <i :class="item.icon"></i><span>{{ item.label }}</span>
          </RouterLink>
        </template>
      </nav>
      <div class="sidebar-footer">
        <small><i class="fas fa-server me-1"></i>Servidor Local</small>
      </div>
    </aside>

    <div class="sidebar-overlay" :class="{ active: sidebarOpen }" @click="closeSidebar"></div>

    <!-- Main Content -->
    <div class="main-content">
      <header class="topbar">
        <button class="btn btn-link topbar-toggle d-lg-none" type="button" @click="sidebarOpen = !sidebarOpen">
          <i class="fas fa-bars"></i>
        </button>
        <h1 class="topbar-title">{{ route.meta.title || 'Portal de Datos' }}</h1>
      </header>

      <main class="page-content">
        <RouterView />
      </main>

      <footer class="app-footer">
        <small><i class="fas fa-server me-1"></i>Portal de Datos Inverpalmas</small>
      </footer>
    </div>
  </div>

  <!-- Toast container -->
  <div id="toast-container" style="position:fixed;top:1rem;right:1rem;z-index:1200;display:flex;flex-direction:column;gap:.5rem;min-width:280px;max-width:380px;">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="toast align-items-center border-0 shadow show"
      :class="bgClass[t.type] || 'text-bg-secondary'"
    >
      <div class="d-flex">
        <div class="toast-body">
          <i class="fas me-2" :class="iconClass[t.type] || 'fa-circle-info'"></i>
          <span v-html="t.message"></span>
        </div>
        <button type="button" class="btn-close me-2" @click="toasts = toasts.filter(x => x.id !== t.id)"></button>
      </div>
    </div>
  </div>
</template>
