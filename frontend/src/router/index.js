import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/',                    redirect: '/dashboard' },
    { path: '/dashboard',           component: () => import('../views/DashboardView.vue'),        meta: { title: 'Dashboard' } },
    { path: '/consultar',           component: () => import('../views/ConsultarView.vue'),         meta: { title: 'Consultar DBF' } },
    { path: '/reporte-dinamico',    component: () => import('../views/ReporteDinamicoView.vue'),   meta: { title: 'Reporte Dinámico' } },
    { path: '/etl/jobs',            component: () => import('../views/EtlJobsView.vue'),           meta: { title: 'Jobs ETL' } },
    { path: '/load/jobs',           component: () => import('../views/LoadJobsView.vue'),          meta: { title: 'Cargas DBF' } },
    { path: '/etl/params',          component: () => import('../views/EtlParamsView.vue'),         meta: { title: 'Parámetros ETL' } },
    { path: '/etl/runs',            component: () => import('../views/EtlRunsView.vue'),           meta: { title: 'Historial ETL' } },
    { path: '/consultas/procesos',  component: () => import('../views/ConsultasProcesosView.vue'), meta: { title: 'Procesos de Consulta' } },
    { path: '/:pathMatch(.*)*',     redirect: '/dashboard' },
  ],
})

export default router

