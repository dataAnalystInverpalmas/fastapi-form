import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/',                    redirect: '/dashboard' },
    { path: '/dashboard',           component: () => import('../views/DashboardView.vue'),        meta: { title: 'Dashboard' } },
    { path: '/consultar',           component: () => import('../views/ConsultarView.vue'),         meta: { title: 'Consultar DBF' } },
    { path: '/etl/jobs',            component: () => import('../views/EtlJobsView.vue'),           meta: { title: 'Jobs ETL' } },
    { path: '/proyecciones/jobs',   component: () => import('../views/ProyeccionesJobsView.vue'),  meta: { title: 'Proyecciones' } },
    { path: '/load/jobs',           component: () => import('../views/LoadJobsView.vue'),          meta: { title: 'Cargas DBF' } },
    { path: '/tika/jobs',           component: () => import('../views/TikaJobsView.vue'),          meta: { title: 'Cargas Tika' } },
    { path: '/etl/params',          component: () => import('../views/EtlParamsView.vue'),         meta: { title: 'Parámetros ETL' } },
    { path: '/etl/runs',            component: () => import('../views/EtlRunsView.vue'),           meta: { title: 'Historial ETL' } },
    { path: '/ciencia-datos',                         component: () => import('../views/ds/DsHomeView.vue'),      meta: { title: 'Ciencia de datos' } },
    { path: '/ciencia-datos/precision-proyecciones',  component: () => import('../views/ds/DsPrecisionView.vue'), meta: { title: 'Precisión de proyecciones' } },
    { path: '/ciencia-datos/pronostico-produccion',   component: () => import('../views/ds/DsForecastView.vue'),  meta: { title: 'Pronóstico de producción' } },
    { path: '/ciencia-datos/calidad-anomalias',       component: () => import('../views/ds/DsQualityView.vue'),   meta: { title: 'Alertas de calidad' } },
    { path: '/ciencia-datos/riesgo-fusarium',         component: () => import('../views/ds/DsFusariumView.vue'),  meta: { title: 'Riesgo de fusarium' } },
    { path: '/config',             component: () => import('../views/ConfigView.vue'),            meta: { title: 'Configuración' } },
    { path: '/:pathMatch(.*)*',     component: () => import('../views/NotFoundView.vue'),          meta: { title: 'Página no encontrada' } },
  ],
})

export default router

