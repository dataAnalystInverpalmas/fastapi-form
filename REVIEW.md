# Revisión Experta del Proyecto — Portal de Datos Inverpalmas

> Revisado el 30 de mayo de 2026. Todo funciona correctamente en producción.  
> Este documento identifica mejoras técnicas, no errores críticos.

---

## Arquitectura General

```
fastapi-form/
├── main.py                  ← entrypoint Uvicorn (re-exporta app.main)
├── app/
│   ├── main.py              ← create_app() + scheduler + rutas
│   ├── core/
│   │   ├── config.py        ← shim de compatibilidad hacia atrás
│   │   ├── db.py            ← conexión MySQL (sin pool)
│   │   └── settings.py      ← Settings (pydantic-settings)
│   ├── routes/
│   │   ├── api.py           ← endpoints REST /api/*
│   │   └── web.py           ← rutas Jinja2 (legacy, en proceso de migrar a Vue)
│   └── services/
│       ├── etl_catalog.py   ← construye el catálogo de jobs
│       ├── etl_definition.py ← dataclass ETLJobDefinition
│       ├── etl_helpers.py   ← utilidades compartidas (read_dbf, etc.)
│       ├── etl_params.py    ← validación/normalización de parámetros
│       ├── etl_registry.py  ← JOBS dict global (cargado al importar)
│       ├── etl_repository.py ← acceso a MySQL (runs, jobs, params)
│       ├── etl_runner.py    ← ThreadPoolExecutor + start_job()
│       ├── pivot_service.py ← reporte dinámico con whitelist SQL
│       ├── dbf_loaders/     ← loaders individuales de DBF
│       ├── etl_jobs/        ← generadores ETL (un archivo por job)
│       └── tests/           ← unit tests
├── frontend/                ← Vue 3 + Vite + Tailwind + Bootstrap
│   └── src/
│       ├── App.vue          ← shell con sidebar + toasts
│       ├── router/          ← rutas con lazy loading
│       ├── composables/     ← useEtlPolling, useFileDownload
│       └── views/           ← una vista por sección
├── load_tests/              ← notebooks + functions.py (¡usado en producción!)
├── static/                  ← CSS/JS legacy (Jinja2)
└── templates/               ← HTML Jinja2 (legacy)
```

**Lo que funciona muy bien:**
- Patrón registry para ETL (catálogo, definición, runner separados)
- Validación de parámetros ETL tipada y robusta (`etl_params.py`)
- SQL injection imposible en `pivot_service.py` (whitelist + backtick-quoting)
- Polling adaptativo en `useEtlPolling.js` (rápido cuando hay jobs corriendo, lento si no)
- Lazy loading de todas las vistas Vue en el router
- Scheduler APScheduler para jobs diarios automáticos
- Finca sintética `000` calculada en cada pipeline de resumen

---

## Problemas Críticos

### 1. Producción importa desde `load_tests/`

**Archivo:** `app/services/etl_jobs/production_pipeline_generator.py`, línea 11

```python
from load_tests.functions import curve_ini, curve_values_by_age, datos_curva, rescale_to_total
```

`load_tests/` es un directorio de desarrollo/notebooks. El código de producción no debe depender de él:
- Falla si el working directory no es la raíz del proyecto
- Acoplamiento incorrecto entre capas
- Las funciones de curva son lógica de negocio, no utilidades de test

**Solución:** Mover las funciones de curva a `app/services/curve_functions.py` y actualizar el import.

---

### 2. `@app.on_event` está deprecated en FastAPI moderno

**Archivo:** `app/main.py`, líneas 76 y 84

```python
@app.on_event("startup")   # ← deprecated desde FastAPI 0.93
@app.on_event("shutdown")  # ← deprecated desde FastAPI 0.93
```

**Solución:** Migrar a `lifespan` context manager:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_jobs()
    for job_id in _DAILY_JOBS:
        _schedule_daily_job(job_id)
    _scheduler.start()
    yield
    _scheduler.shutdown(wait=False)

app = FastAPI(..., lifespan=lifespan)
```

---

## Problemas de Alta Prioridad

### 3. Sin connection pooling en la base de datos

**Archivo:** `app/core/db.py`

Cada llamada a `db_connection()` abre y cierra una conexión MySQL desde cero. Con ETL jobs corriendo en paralelo (ThreadPoolExecutor), esto genera overhead y puede agotar conexiones bajo carga.

**Solución:** Usar `mysql.connector.pooling.MySQLConnectionPool` o SQLAlchemy engine con pool (ya está SQLAlchemy en `requirements.txt`):

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

_engine = create_engine(
    f"mysql+mysqlconnector://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
)
```

---

### 4. `_ETL_JOBS_EXTRA_IDS` definido en dos lugares

**Archivos:** `app/routes/api.py` línea 39 y `app/routes/web.py` línea 38

```python
# Mismo set en ambos archivos:
_ETL_JOBS_EXTRA_IDS = {
    "load_process_guarde",
    "load_process_siembras",
    "load_siembras_teo_real",
}
```

Si se agrega un job, hay que recordar actualizarlo en ambos sitios.

**Solución:** Mover la constante a `app/services/etl_registry.py` o a `app/services/etl_constants.py` e importarla en ambas rutas.

---

### 5. CSS híbrido: Tailwind + Bootstrap mezclados

**Archivos:** `frontend/src/**/*.vue`

El frontend usa simultáneamente clases de Bootstrap (`card`, `btn`, `shadow-sm`, `col-md-3`, `d-flex`) y de Tailwind (`space-y-4`, `gap-3`, `text-uppercase`). Esto genera:

- Doble bundle de CSS (~60–80 KB extra sin PurgeCSS correctamente configurado)
- Inconsistencia visual (breakpoints distintos, espaciados distintos)
- Mayor curva de mantenimiento

**Recomendación:** Estandarizar en **Tailwind CSS** (ya configurado con PostCSS) y reemplazar gradualmente los componentes Bootstrap. O al contrario, usar Bootstrap completo con Tailwind deshabilitado. Lo importante es elegir uno.

---

### 6. `window.$toast` es un anti-patrón en Vue 3

**Archivo:** `frontend/src/App.vue`, línea 15

```javascript
window.$toast = showToast  // ← anti-patrón
```

Exponer funciones Vue en `window` rompe la reactividad del framework, dificulta TypeScript, y no funciona en SSR.

**Solución:** Usar `provide`/`inject` de Vue 3:

```javascript
// App.vue
provide('toast', showToast)

// En cualquier componente hijo
const toast = inject('toast')
toast('Mensaje', 'success')
```

O crear un store Pinia (ya es dependencia pero no tiene stores definidos).

---

## Problemas de Prioridad Media

### 7. Endpoint legacy `/etl/proyecciones/run` duplicado

**Archivo:** `app/routes/api.py`, línea ~175

```python
@router.post("/etl/proyecciones/run")  # ← ya existe /etl/jobs/proyecciones_csv/run
def api_run_proyecciones_etl():
```

Este endpoint específico es redundante: el endpoint genérico `POST /etl/jobs/{job_id}/run` ya cubre este caso. Candidato a eliminar.

---

### 8. `etl_registry.py` carga el catálogo al importar

**Archivo:** `app/services/etl_registry.py`, línea 7

```python
JOBS: dict[str, ETLJobDefinition] = build_job_catalog()  # ejecuta al importar
```

Si `build_job_catalog()` falla (import de un generator falla, settings inválidos), la aplicación no arranca con un error poco claro. 

**Solución:** Patrón lazy con inicialización explícita en `bootstrap_jobs()`:

```python
_JOBS: dict[str, ETLJobDefinition] | None = None

def get_registry() -> dict[str, ETLJobDefinition]:
    global _JOBS
    if _JOBS is None:
        _JOBS = build_job_catalog()
    return _JOBS
```

---

### 9. `kpiCards` declarado antes que `kpis` en `EtlJobsView.vue`

**Archivo:** `frontend/src/views/EtlJobsView.vue`, líneas 8–13

```javascript
const kpiCards = computed(() => [          // ← usa kpis.value
  { key: 'queued', value: kpis.value.queued, ... },
])

const { kpis, countdown, pollNow } = useEtlPolling(...)  // ← kpis declarado después
```

Funciona por cierre léxico (closure) de JavaScript, pero confunde a quien lee el código. Reordenar: declarar `useEtlPolling` antes de `kpiCards`.

---

### 10. Falta `.env.example`

El proyecto acepta variables de entorno (pydantic-settings) pero no hay ningún archivo de ejemplo. Quien clone el repo no sabe qué variables configurar.

**Solución:** Crear `.env.example` en la raíz con todas las claves y valores de ejemplo (sin secretos reales):

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=tu_usuario
DB_PASSWORD=
DB_NAME=informes
DEBUG=false
DEFAULT_DBF_PATH=\\svrinverpalmas\produc\LD_BCULT\hijos2026.dbf
```

---

### 11. `requirements.txt` usa versiones no fijadas para dependencias críticas

```
scikit-learn>=1.4.0   # ← puede instalar cualquier versión futura
scipy>=1.12.0
```

Las demás dependencias sí están fijadas con `==`. Las APIs de scipy/sklearn cambian entre minor versions.

**Solución:** Fijar versiones exactas en producción:

```
scikit-learn==1.5.2
scipy==1.14.1
```

---

### 12. No hay ruta 404 en el router Vue

**Archivo:** `frontend/src/router/index.js`

Si el usuario navega a una URL desconocida dentro del SPA, Vue Router no tiene catch-all y muestra una página en blanco.

**Solución:** Añadir al final de `routes`:

```javascript
{ path: '/:pathMatch(.*)*', redirect: '/dashboard' }
```

---

### 13. Falta `__init__.py` en `app/services/tests/`

El directorio `app/services/tests/` contiene tests pero no `__init__.py`. Funciona con pytest en modo namespace, pero puede fallar al correr con `python -m unittest` según el PYTHONPATH.

**Solución:** Añadir `app/services/tests/__init__.py` vacío.

---

## Sugerencias de Organización

### Estructura propuesta de `app/services/`

```
app/services/
├── curve_functions.py      ← (NUEVO) mover desde load_tests/functions.py
├── etl_constants.py        ← (NUEVO) _ETL_JOBS_EXTRA_IDS y otras constantes compartidas
├── date_service.py
├── dbf_reader.py
├── etl_catalog.py
├── etl_definition.py
├── etl_helpers.py
├── etl_params.py
├── etl_registry.py
├── etl_repository.py
├── etl_runner.py
├── pivot_service.py
├── query_processes.py
├── aportes_ponderados_query.py
├── cortes_lonas_query.py
├── dbf_loaders/
├── etl_jobs/
└── tests/
    └── __init__.py         ← (NUEVO) vacío
```

### Separar `load_tests/`

```
load_tests/
├── notebooks/              ← ejecutar_etl_jobs.ipynb, etc.
└── scripts/                ← production_pipeline.py, qualities_pipeline.py
```

---

## Puntos Positivos a Mantener

| Área | Práctica destacada |
|------|--------------------|
| Seguridad SQL | `pivot_service.py` usa whitelist estricta + backtick-quoting; sin interpolación de strings |
| ETL Registry | Patrón catalog + registry + runner claramente separados |
| Parámetros ETL | Validación/coerción tipada en `etl_params.py` funciona perfectamente |
| Polling Vue | `useEtlPolling.js` adapta el intervalo según estado activo/inactivo |
| Lazy loading | Todas las rutas Vue usan `() => import(...)` |
| Settings | `pydantic-settings` permite overrides por env sin cambiar código |
| Finca `000` | Resumen sintético calculado en pipelines antes del reporte |
| Tests | Tests unitarios para los 4 pipelines principales |
| CORS | Solo permite el dev server de Vite, no `*` |
| Scheduler | APScheduler con timezone Bogotá para jobs diarios |

---

## Resumen de Prioridades

| # | Mejora | Impacto | Esfuerzo |
|---|--------|---------|----------|
| 1 | Mover funciones de curva de `load_tests/` a `app/services/` | Alto | Bajo |
| 2 | Migrar `on_event` a `lifespan` | Medio | Bajo |
| 3 | Connection pooling en `db.py` | Alto | Medio |
| 4 | Unificar `_ETL_JOBS_EXTRA_IDS` | Bajo | Muy bajo |
| 5 | Estandarizar CSS (Tailwind vs Bootstrap) | Medio | Alto |
| 6 | Reemplazar `window.$toast` con `provide/inject` | Bajo | Bajo |
| 7 | Eliminar endpoint `/etl/proyecciones/run` legacy | Bajo | Muy bajo |
| 8 | Lazy init del registry ETL | Medio | Bajo |
| 9 | Reordenar `kpiCards` y `kpis` en EtlJobsView | Bajo | Muy bajo |
| 10 | Crear `.env.example` | Medio | Muy bajo |
| 11 | Fijar versiones scipy/sklearn | Medio | Muy bajo |
| 12 | Añadir ruta 404 en router Vue | Bajo | Muy bajo |
| 13 | Añadir `__init__.py` en `tests/` | Bajo | Muy bajo |
