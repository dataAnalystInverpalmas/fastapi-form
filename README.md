# Portal de Datos Inverpalmas

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-green.svg)](https://fastapi.tiangolo.com/)
[![Vue.js 3](https://img.shields.io/badge/Vue-3-brightgreen.svg)](https://vuejs.org/)

Aplicacion web fullstack para gestion y analisis de datos de produccion agricola de **Inverpalmas**. Centraliza procesos ETL sobre archivos DBF, reportes automatizados en Excel, y un dashboard interactivo con seguimiento de ejecuciones en tiempo real.

---

## Stack tecnologico

| Capa | Tecnologia |
|------|------------|
| Backend | FastAPI 0.104, Python 3.10+, APScheduler |
| Base de datos | MySQL / MariaDB con connection pool |
| Datos | Pandas, NumPy, SciPy, scikit-learn, dbfread |
| Frontend | Vue 3 (Composition API), Vite, Tailwind CSS, Axios |
| Configuracion | pydantic-settings (.env) |
| Reportes | openpyxl, SQLAlchemy |

---

## Requisitos previos

- Python 3.10+
- Node.js 20+
- MySQL / MariaDB 5.7+
- Acceso de red a `\\svrinverpalmas\...` (rutas UNC del servidor)

---

## Instalacion

### 1. Clonar el repositorio

```bash
git clone https://github.com/dataAnalystInverpalmas/fastapi-form.git
cd fastapi-form
```

### 2. Backend

```bash
# Crear y activar entorno virtual
python -m venv venv
venv\Scripts\activate          # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Variables de entorno

Copia el archivo de ejemplo y completa los valores reales:

```bash
copy .env.example .env
```

Variables minimas necesarias:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=tu_usuario
DB_PASSWORD=tu_password
DB_NAME=informes
```

Ver [.env.example](.env.example) para la lista completa de variables.

### 4. Base de datos

```sql
CREATE DATABASE informes CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'usuario'@'localhost' IDENTIFIED BY 'password';
GRANT ALL PRIVILEGES ON informes.* TO 'usuario'@'localhost';
FLUSH PRIVILEGES;
```

Las tablas ETL (`etl_jobs`, `etl_job_runs`, `etl_job_last_params`) se crean automaticamente al iniciar la aplicacion.

### 5. Frontend

```bash
cd frontend
npm install
```

---

## Ejecucion

### Modo desarrollo

**Terminal 1 - Backend:**
```bash
uvicorn main:app --reload
# http://localhost:8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
# http://localhost:5173  (proxy a :8000 configurado en vite.config.js)
```

### Modo produccion

```bash
# Compilar frontend (genera frontend/dist/)
cd frontend && npm run build && cd ..

# Iniciar backend (sirve el SPA desde /assets y catch-all)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Tests

```bash
# Pipeline de produccion
python -m unittest app.services.tests.test_production_pipeline_generator

# Pipeline de fusarium
python -m unittest app.services.tests.test_fusarium_pipeline_generator

# Pipeline de calidades
python -m unittest app.services.tests.test_qualities_pipeline_generator

# Reporte de productividad por variedades
python -m unittest app.services.tests.test_productivity_varieties_report_generator
```

---

## Estructura del proyecto

```
fastapi-form/
├── main.py                        # Entrypoint Uvicorn (re-exporta app.main)
├── requirements.txt
├── .env.example                   # Plantilla de variables de entorno
├── AGENTS.md                      # Convenciones del repositorio
│
├── app/
│   ├── main.py                    # create_app() + lifespan + scheduler
│   ├── core/
│   │   ├── config.py              # Shim de compatibilidad (usa settings)
│   │   ├── db.py                  # Connection pool MySQL (pool_size=5)
│   │   └── settings.py            # Settings via pydantic-settings
│   ├── routes/
│   │   ├── api.py                 # Endpoints REST /api/*
│   │   └── web.py                 # Rutas Jinja2 (interfaz legacy)
│   └── services/
│       ├── curve_functions.py     # Funciones de curva de produccion
│       ├── etl_catalog.py         # Construccion del catalogo de jobs
│       ├── etl_constants.py       # Constantes compartidas entre rutas
│       ├── etl_definition.py      # Dataclass ETLJobDefinition
│       ├── etl_helpers.py         # Utilidades compartidas (read_dbf, etc.)
│       ├── etl_params.py          # Validacion/coercion de parametros ETL
│       ├── etl_registry.py        # Registro lazy de jobs
│       ├── etl_repository.py      # Acceso a MySQL (runs, jobs, params)
│       ├── etl_runner.py          # ThreadPoolExecutor + start_job()
│       ├── pivot_service.py       # Reporte dinamico con whitelist SQL
│       ├── date_service.py        # Utilidades de fechas (zona Bogota)
│       ├── dbf_reader.py          # Lectura de DBF con multiples encodings
│       ├── query_processes.py     # Consultas parametrizadas
│       ├── aportes_ponderados_query.py
│       ├── cortes_lonas_query.py
│       ├── dbf_loaders/           # Cargadores individuales de DBF a MySQL
│       │   ├── load_causas_generator.py
│       │   ├── load_colores_generator.py
│       │   ├── load_cosechas_generator.py
│       │   ├── load_fiestas_generator.py
│       │   ├── load_lonas_generator.py
│       │   ├── load_plano_cultivo_fm_generator.py
│       │   ├── load_tabla_descarta_curva_generator.py
│       │   ├── load_tabla_metas_generator.py
│       │   ├── load_tabla_nacional_generator.py
│       │   └── load_variedades_generator.py
│       ├── etl_jobs/              # Generadores ETL (un archivo por job)
│       │   ├── anomalias_lonas_generator.py
│       │   ├── aportes_grados_generator.py
│       │   ├── bajas_exportado_generator.py
│       │   ├── comparar_picos_demanda_generator.py
│       │   ├── compare_tika_produccion_generator.py
│       │   ├── dirigidas_generator.py
│       │   ├── excel_generator.py
│       │   ├── fusarium_pipeline_generator.py
│       │   ├── load_fusarium_generator.py
│       │   ├── pedidos_surtidos_generator.py
│       │   ├── process_guarde_generator.py
│       │   ├── process_siembras_generator.py
│       │   ├── produccion_picos_generator.py
│       │   ├── production_pipeline_generator.py
│       │   ├── productivity_varieties_report_generator.py
│       │   ├── producto_procesado_generator.py
│       │   ├── proyecciones_generator.py
│       │   ├── qualities_pipeline_generator.py
│       │   ├── quipus_vs_proy_generator.py
│       │   ├── resumir_curvas_usadas_generator.py
│       │   ├── siembras_teo_real_generator.py
│       │   └── tabla_curvas_clavel_generator.py
│       └── tests/
│           ├── test_production_pipeline_generator.py
│           ├── test_fusarium_pipeline_generator.py
│           ├── test_qualities_pipeline_generator.py
│           └── test_productivity_varieties_report_generator.py
│
├── frontend/
│   ├── index.html
│   ├── vite.config.js             # Proxy /api -> :8000 en dev
│   ├── tailwind.config.js
│   └── src/
│       ├── main.js
│       ├── App.vue                # Shell: sidebar + toasts (provide/inject)
│       ├── router/
│       │   └── index.js           # Rutas con lazy loading + catch-all 404
│       ├── composables/
│       │   ├── useEtlPolling.js   # Polling adaptativo (4s activo / 20s idle)
│       │   └── useFileDownload.js # Descarga de archivos binarios
│       └── views/
│           ├── DashboardView.vue
│           ├── ConsultarView.vue
│           ├── ReporteDinamicoView.vue
│           ├── EtlJobsView.vue
│           ├── LoadJobsView.vue
│           ├── EtlParamsView.vue
│           ├── EtlRunsView.vue
│           └── ConsultasProcesosView.vue
│
├── templates/                     # HTML Jinja2 (interfaz legacy)
└── static/                        # CSS/JS estaticos (interfaz legacy)
```

---

## Jobs ETL disponibles

### Cargas DBF a MySQL (`/load/jobs`)

| Job ID | Descripcion |
|--------|-------------|
| `load_maestra_lonas` | Lonas 2024-2026 desde `lonas*.dbf` |
| `load_maestra_variedades` | Variedades de flores |
| `load_maestra_cosechas` | Tabla de cosechas |
| `load_maestra_colores` | Colores de flores |
| `load_maestra_causas` | Causas de baja |
| `load_maestra_fiestas` | Dias festivos |
| `load_tabla_descarta_curva` | Descarta curva |
| `load_tabla_metas` | Metas por variedad |
| `load_tabla_nacional` | Datos nacionales `rflo*.dbf` |
| `load_plano_cultivo_fm` | Plano de cultivo fm |
| `load_maestra_fusarium` | Historico de fusarium |

> Los jobs `load_maestra_lonas`, `load_tabla_descarta_curva`, `load_tabla_metas` y `load_tabla_nacional` se ejecutan automaticamente cada dia a las 10:00 AM (hora Bogota).

### Procesos ETL (`/etl/jobs`)

| Job ID | Descripcion |
|--------|-------------|
| `excel_labores` | Genera `labores_de_siembra.xlsx` |
| `bajas_exportado` | `bajas_por_mes.csv` y `bajas_desde_2010.csv` |
| `producto_procesado_csv` | `pprocesado.csv` desde `pprocesado*.dbf` |
| `proyecciones_csv` | `proyecciones.csv` combinando DBFs + presupuesto |
| `produccion_picos` | Reporte de produccion por picos |
| `production_pipeline` | Pipeline completo de produccion con curvas suavizadas por ciclo y finca |
| `fusarium_pipeline` | Pipeline de analisis de fusarium |
| `qualities_pipeline` | Pipeline de calidades de produccion |
| `productivity_varieties_report` | Reporte de productividad por variedades con `pico` y `ciclo` |
| `quipus_vs_proy` | Quipus vs proyecciones |
| `compare_tika_produccion` | Comparativa Tika / produccion / despachos |
| `comparar_picos_demanda` | Picos de produccion vs demanda |
| `dirigidas` | Analisis de dirigidas |
| `anomalias_lonas` | Deteccion de anomalias en lonas |
| `pedidos_surtidos` | Procesos de pedidos surtidos |
| `aportes_grados` | Aportes por grados |
| `resumir_curvas_usadas` | Resumen de curvas de produccion usadas |
| `tabla_curvas_clavel` | Tabla de curvas por variedad de clavel |

---

## Arquitectura ETL

El sistema ETL sigue un patron registry/catalog/runner claramente separado:

```
etl_catalog.py      -> define la lista de ETLJobDefinition
etl_registry.py     -> expone get_job() / list_jobs() con carga lazy
etl_runner.py       -> ejecuta jobs en ThreadPoolExecutor
etl_repository.py   -> persiste estado en MySQL (etl_jobs, etl_job_runs)
etl_params.py       -> valida y coerciona parametros tipados
```

Los jobs con `supports_params=True` aceptan parametros configurables desde la UI en `/etl/params`. Los ultimos parametros usados se persisten automaticamente.

---

## Convenciones del proyecto

Ver [AGENTS.md](AGENTS.md) para las reglas especificas del repositorio, en particular:

- `pico` en los pipelines de produccion es la **edad del ultimo punto de la mejor ventana consecutiva** de `f_m`: ventana de 4 edades para ciclo 1, 10 edades para ciclo 2.
- `ciclo 1` cubre edades 0-35; `ciclo 2` cubre edades 36-70.
- Los resumenes incluyen una finca sintetica `000` (todas las fincas combinadas) ademas de `001` y `002`.

---

## Notas de desarrollo

**Lectura de DBF:** se intentan los encodings `latin1`, `cp1252`, `utf-8`, `iso-8859-1` automaticamente.

**Seguridad SQL:** `pivot_service.py` usa whitelist estricta + backtick-quoting. Ningun valor del usuario se interpola directamente en queries.

**Frontend:** los toasts se distribuyen con `provide('toast', fn)` en `App.vue` y se consumen con `inject('toast')` en cada vista.

**CORS:** solo permite `http://localhost:5173` (dev server de Vite). En produccion el frontend se sirve como SPA desde FastAPI.

---

## Licencia

Privado - Inverpalmas. Todos los derechos reservados.
